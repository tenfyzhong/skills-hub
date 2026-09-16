"""Position-preserving MySQL dump lexer. Never executes SQL or client commands."""

from dataclasses import dataclass, field
import re

from i18n import message


@dataclass(frozen=True)
class Token:
    value: str
    kind: str
    line: int
    end_line: int

    @property
    def kw(self):
        return self.value.upper() if self.kind == 'word' else ''


@dataclass
class Statement:
    tokens: list
    file: str
    guards: list = field(default_factory=list)
    error: str = ''

    @property
    def line(self):
        return self.tokens[0].line if self.tokens else 1

    def evidence(self):
        # String values (including defaults, credentials and GTIDs) are never copied.
        return ' '.join("'<redacted>'" if t.kind == 'string' else t.value
                        for t in self.tokens[:50])[:500]


def split_top(tokens, separator=','):
    groups, start, depth = [], 0, 0
    for i, t in enumerate(tokens):
        if t.kind == 'symbol':
            if t.value == '(':
                depth += 1
            elif t.value == ')':
                depth -= 1
            elif t.value == separator and depth == 0:
                groups.append(tokens[start:i])
                start = i + 1
    groups.append(tokens[start:])
    return groups


def closing(tokens, start):
    depth = 0
    for i in range(start, len(tokens)):
        t = tokens[i]
        if t.kind == 'symbol' and t.value == '(':
            depth += 1
        elif t.kind == 'symbol' and t.value == ')':
            depth -= 1
            if depth == 0:
                return i
    raise ValueError(message('Unclosed parenthesis'))


def identifier(tokens, start):
    if start >= len(tokens) or tokens[start].kind not in ('word', 'ident'):
        raise ValueError(message('Missing recognizable object name'))
    parts, i = [tokens[start].value], start + 1
    if i < len(tokens) and tokens[i].value == '.':
        if i + 1 >= len(tokens) or tokens[i + 1].kind not in ('word', 'ident'):
            raise ValueError(message('Incomplete qualified object name'))
        parts.append(tokens[i + 1].value)
        i += 2
    return parts, i


def qualified(parts, database):
    def escape(part):
        return '`' + part.replace('`', '``') + '`' if '.' in part or '`' in part else part
    return '.'.join(escape(p) for p in (parts if len(parts) == 2 else [database or '?', parts[0]]))


class Scanner:
    def __init__(self, sql_mode='', source_number=None):
        self.mode = set(sql_mode.upper().split(',')) if sql_mode is not None else None
        self.saved = {}
        self.source_number = source_number
        self.header_versions = []

    def update_mode(self, tokens):
        if not tokens or tokens[0].kw != 'SET':
            return
        for group in split_top(tokens[1:]):
            eq = next((i for i, t in enumerate(group) if t.value == '='), None)
            if eq is None:
                continue
            lhs = ''.join(t.value for t in group[:eq]).upper()
            rhs = group[eq + 1:]
            rhs_name = ''.join(t.value for t in rhs).upper()
            if lhs.startswith('@') and not lhs.startswith('@@'):
                if rhs_name in ('@@SQL_MODE', '@@SESSION.SQL_MODE'):
                    self.saved[lhs] = None if self.mode is None else self.mode.copy()
                continue
            if lhs in ('SQL_MODE', 'SESSIONSQL_MODE', 'LOCALSQL_MODE', '@@SQL_MODE', '@@SESSION.SQL_MODE'):
                if len(rhs) == 1 and rhs[0].kind == 'string':
                    self.mode = set(rhs[0].value.upper().split(','))
                elif rhs_name in self.saved:
                    value = self.saved[rhs_name]
                    self.mode = None if value is None else value.copy()
                else:
                    self.mode = None

    def statements(self, text, filename):
        chars = list(text)
        delimiter, tokens, guards = ';', [], []
        i, line, uncertain = 0, 1, False
        size = len(chars)
        ranges, emitted = [], 0

        def statement(error=''):
            return Statement(tokens.copy(), filename, guards.copy(), error or
                             (message('Unknown SQL mode; string or identifier boundaries cannot be confirmed') if uncertain else ''))

        while i < size:
            c = chars[i]
            if c.isspace() or c == '\ufeff':
                line += c == '\n'
                i += 1
                continue
            # DELIMITER is a line-oriented client instruction, not SQL.
            if not tokens and (i == 0 or ''.join(chars[text.rfind('\n', 0, i) + 1:i]).strip() == ''):
                end = text.find('\n', i)
                end = size if end < 0 else end
                directive = ''.join(chars[i:end]).strip()
                match = re.fullmatch(r'(?i)DELIMITER\s+(\S+)', directive)
                if match:
                    delimiter = match.group(1)
                    i = end
                    continue
            if ''.join(chars[i:i + len(delimiter)]) == delimiter:
                if tokens:
                    result = statement()
                    self.update_mode(tokens)
                    if any(g > (self.source_number or 0) for g in guards) and tokens[0].kw == 'SET':
                        self.mode = None
                    emitted += 1
                    yield result
                tokens, guards, uncertain = [], [], False
                i += len(delimiter)
                continue
            for end, guard in ranges:
                if i < end and guard not in guards:
                    guards.append(guard)
            if c == '#' or (c == '-' and i + 1 < size and chars[i + 1] == '-' and
                            (i + 2 == size or chars[i + 2].isspace())):
                end = text.find('\n', i)
                if not tokens and not emitted:
                    header = re.fullmatch(r'--\s*Server version\s+([^\s]+).*', text[i:size if end < 0 else end])
                    if header:
                        self.header_versions.append(header.group(1))
                i = size if end < 0 else end
                continue
            if c == '/' and i + 1 < size and chars[i + 1] == '*':
                end = text.find('*/', i + 2)
                if end < 0:
                    if not tokens:
                        tokens.append(Token('/*', 'symbol', line, line))
                    yield statement(message('Unclosed comment'))
                    return
                if i + 2 < size and chars[i + 2] == '!':
                    match = re.match(r'/\*!(\d{5,6})?\s*', text[i:end])
                    guard = int(match.group(1)) if match.group(1) else 0
                    guards.append(guard)
                    ranges.append((end, guard))
                    # Replace only wrappers; keep offsets/newlines and scan the body normally.
                    for j in list(range(i, i + match.end())) + [end, end + 1]:
                        if chars[j] != '\n':
                            chars[j] = ' '
                    continue
                line += text[i:end + 2].count('\n')
                i = end + 2
                continue
            if c in ('\'', '"', '`'):
                quote, start_line, value = c, line, []
                kind = 'ident' if c == '`' or (c == '"' and self.mode is not None and 'ANSI_QUOTES' in self.mode) else 'string'
                if self.mode is None and c == '"':
                    uncertain = True
                i += 1
                complete = False
                while i < size:
                    c = chars[i]
                    if c == quote:
                        if i + 1 < size and chars[i + 1] == quote:
                            value.append(c)
                            i += 2
                            continue
                        i += 1
                        complete = True
                        break
                    if c == '\\' and kind == 'string':
                        if self.mode is None:
                            uncertain = True
                        if self.mode is None or 'NO_BACKSLASH_ESCAPES' not in self.mode:
                            if i + 1 < size:
                                value.append(chars[i + 1])
                                line += chars[i + 1] == '\n'
                                i += 2
                                continue
                    value.append(c)
                    line += c == '\n'
                    i += 1
                tokens.append(Token(''.join(value), kind, start_line, line))
                if not complete:
                    yield statement(message('Unclosed string or identifier'))
                    return
                continue
            if c.isalnum() or c in ('_', '$'):
                start = i
                while i < size and (chars[i].isalnum() or chars[i] in ('_', '$')):
                    # A custom delimiter may itself contain identifier characters.
                    if i > start and ''.join(chars[i:i + len(delimiter)]) == delimiter:
                        break
                    i += 1
                value = ''.join(chars[start:i])
                tokens.append(Token(value, 'number' if value.isdecimal() else 'word', line, line))
                continue
            tokens.append(Token(c, 'symbol', line, line))
            i += 1
        if tokens:
            result = statement()
            self.update_mode(tokens)
            yield result
