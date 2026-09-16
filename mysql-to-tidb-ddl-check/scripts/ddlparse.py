"""Small structural parser for the documented subset; not a SQL validator."""

from dataclasses import dataclass, field

from sqlscan import closing, identifier, qualified, split_top


TYPES = set('TINYINT SMALLINT MEDIUMINT INT INTEGER BIGINT DECIMAL NUMERIC FLOAT DOUBLE REAL BIT BOOL BOOLEAN CHAR VARCHAR BINARY VARBINARY TINYTEXT TEXT MEDIUMTEXT LONGTEXT TINYBLOB BLOB MEDIUMBLOB LONGBLOB ENUM SET DATE DATETIME TIMESTAMP TIME YEAR JSON GEOMETRY POINT LINESTRING POLYGON MULTIPOINT MULTILINESTRING MULTIPOLYGON GEOMETRYCOLLECTION'.split())
SPATIAL = set('GEOMETRY POINT LINESTRING POLYGON MULTIPOINT MULTILINESTRING MULTIPOLYGON GEOMETRYCOLLECTION'.split())


def option(tokens, names):
    """Read unquoted keyword options without mistaking strings/identifiers for SQL."""
    for i in range(len(tokens)):
        for name in names:
            words = name.split()
            if [t.kw for t in tokens[i:i + len(words)]] == words:
                j = i + len(words)
                if j < len(tokens) and tokens[j].value == '=':
                    j += 1
                if j < len(tokens):
                    return tokens[j].value.lower()
    return None


@dataclass
class Column:
    name: str
    type: str
    tokens: list
    length: int | None = None
    signature: tuple = ()
    charset: str | None = None
    collation: str | None = None
    auto: bool = False
    virtual: bool = False


@dataclass
class Index:
    name: str
    columns: list
    tokens: list
    kind: str = 'KEY'


@dataclass
class ForeignKey:
    columns: list
    parent: str
    parent_columns: list
    tokens: list


@dataclass
class Table:
    name: str
    statement: object
    columns: dict = field(default_factory=dict)
    indexes: list = field(default_factory=list)
    foreign_keys: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    options: list = field(default_factory=list)
    unknown: list = field(default_factory=list)
    temporary: bool = False
    charset: str | None = None
    collation: str | None = None


def column(tokens):
    parts, i = identifier(tokens, 0)
    if len(parts) != 1 or i >= len(tokens) or tokens[i].kw not in TYPES:
        raise ValueError('Column type or definition outside parser coverage')
    typ = tokens[i].kw
    typ = {'INTEGER': 'INT', 'NUMERIC': 'DECIMAL', 'BOOL': 'TINYINT', 'BOOLEAN': 'TINYINT'}.get(typ, typ)
    i += 1
    length, parameters = None, ()
    if i < len(tokens) and tokens[i].value == '(':
        end = closing(tokens, i)
        parameters = tuple(t.value for t in tokens[i + 1:end])
        if parameters and parameters[0].isdigit():
            length = int(parameters[0])
        i = end + 1
    attrs = tokens[i:]
    # Skip balanced expression bodies when checking column attributes.
    allowed = set('UNSIGNED ZEROFILL NULL NOT DEFAULT AUTO_INCREMENT UNIQUE PRIMARY KEY COMMENT COLLATE CHARACTER SET CHARSET GENERATED ALWAYS AS VIRTUAL STORED CHECK CONSTRAINT ENFORCED ON UPDATE CURRENT_TIMESTAMP CURRENT_DATE CURRENT_TIME LOCALTIME LOCALTIMESTAMP BINARY'.split())
    j = 0
    while j < len(attrs):
        t = attrs[j]
        if t.value == '(':
            j = closing(attrs, j) + 1
            continue
        if t.kw in ('DEFAULT', 'COMMENT', 'COLLATE', 'CHARSET', 'CONSTRAINT'):
            if j + 1 >= len(attrs):
                raise ValueError('Missing column attribute value')
            if t.kw == 'DEFAULT' and attrs[j + 1].value == '(':
                j = closing(attrs, j + 1) + 1
                continue
            j += 2
            continue
        if t.kw in ('CHECK', 'AS') and (j + 1 >= len(attrs) or attrs[j + 1].value != '('):
            raise ValueError('Missing expression parentheses')
        if t.kw == 'CHARACTER' and j + 1 < len(attrs) and attrs[j + 1].kw == 'SET':
            j += 3
            continue
        if t.kind == 'word' and t.kw not in allowed:
            raise ValueError('Column attribute outside parser coverage')
        j += 1
    unsigned = any(t.kw == 'UNSIGNED' for t in attrs)
    if typ in ('INT', 'TINYINT', 'SMALLINT', 'MEDIUMINT', 'BIGINT'):
        parameters = ()  # Display width is not storage size.
    return Column(parts[0], typ, tokens, length, (typ, parameters, unsigned),
                  option(attrs, ['CHARACTER SET', 'CHARSET']), option(attrs, ['COLLATE']),
                  any(t.kw == 'AUTO_INCREMENT' for t in attrs),
                  any(t.kw == 'AS' for t in attrs) and not any(t.kw == 'STORED' for t in attrs))


def index_columns(tokens, start):
    if start >= len(tokens) or tokens[start].value != '(':
        raise ValueError('Missing index column parentheses')
    end = closing(tokens, start)
    cols = []
    for group in split_top(tokens[start + 1:end]):
        if not group:
            raise ValueError('Empty index column')
        names, i = identifier(group, 0)
        prefix = None
        if i < len(group) and group[i].value == '(':
            stop = closing(group, i)
            if stop != i + 2 or group[i + 1].kind != 'number':
                raise ValueError('Index expression outside parser coverage')
            prefix = int(group[i + 1].value)
            i = stop + 1
        if i < len(group) and group[i].kw in ('ASC', 'DESC'):
            i += 1
        if i != len(group) or len(names) != 1:
            raise ValueError('Index column form outside parser coverage')
        cols.append((names[0], prefix))
    return cols, end


def parse_table(statement, database, defaults):
    tokens = statement.tokens
    i = next(i for i, t in enumerate(tokens) if t.kw == 'TABLE') + 1
    if [t.kw for t in tokens[i:i + 3]] == ['IF', 'NOT', 'EXISTS']:
        i += 3
    names, i = identifier(tokens, i)
    table = Table(qualified(names, database), statement, temporary=any(t.kw == 'TEMPORARY' for t in tokens[:i]))
    if i >= len(tokens) or tokens[i].value != '(':
        raise ValueError('This release parses CREATE TABLE with explicit columns only; LIKE/AS SELECT is not covered')
    end = closing(tokens, i)
    table.options = tokens[end + 1:]
    db = names[0] if len(names) == 2 else database
    inherited = defaults.get(db, {})
    table.charset = option(table.options, ['CHARACTER SET', 'CHARSET']) or inherited.get('charset')
    table.collation = option(table.options, ['COLLATE'])
    if not table.collation and not option(table.options, ['CHARACTER SET', 'CHARSET']):
        table.collation = inherited.get('collation')
    if table.collation and not table.charset:
        table.charset = table.collation.split('_')[0]
    for group in split_top(tokens[i + 1:end]):
        try:
            if not group:
                raise ValueError('Empty column or constraint')
            original = group
            if group[0].kw == 'CONSTRAINT':
                group = group[2:] if len(group) > 1 and group[1].kw not in ('CHECK', 'FOREIGN', 'UNIQUE', 'PRIMARY') else group[1:]
            if not group:
                raise ValueError('Incomplete constraint')
            kind = group[0].kw
            if kind in ('PRIMARY', 'UNIQUE', 'KEY', 'INDEX', 'FULLTEXT', 'SPATIAL', 'FOREIGN'):
                start = next((j for j, t in enumerate(group) if t.value == '('), None)
                if start is None:
                    raise ValueError('Missing index column list')
                cols, stop = index_columns(group, start)
                method = option(group[:start], ['USING'])
                if method and method != 'btree':
                    table.unknown.append((group[:start], 'Index access method outside parser coverage'))
                if kind == 'FOREIGN':
                    if stop + 1 >= len(group) or group[stop + 1].kw != 'REFERENCES':
                        raise ValueError('Missing REFERENCES')
                    parent, j = identifier(group, stop + 2)
                    parent_cols, parent_end = index_columns(group, j)
                    tail = group[parent_end + 1:]
                    j = 0
                    while j < len(tail):
                        if tail[j].kw != 'ON' or j + 2 >= len(tail) or tail[j + 1].kw not in ('DELETE', 'UPDATE'):
                            table.unknown.append((tail[j:], 'Foreign key option outside parser coverage'))
                            break
                        j += 2
                        if tail[j].kw in ('RESTRICT', 'CASCADE'):
                            j += 1
                        elif [t.kw for t in tail[j:j + 2]] in (['SET', 'NULL'], ['SET', 'DEFAULT'], ['NO', 'ACTION']):
                            j += 2
                        else:
                            table.unknown.append((tail[j:], 'Foreign key reference action outside parser coverage'))
                            break
                    table.foreign_keys.append(ForeignKey([c[0] for c in cols], qualified(parent, db), [c[0] for c in parent_cols], original))
                else:
                    table.indexes.append(Index('PRIMARY' if kind == 'PRIMARY' else 'index', cols, original, kind))
                    tail = group[stop + 1:]
                    if tail:
                        # Explicit BTREE and an index comment are the bounded supported options.
                        j = 0
                        while j < len(tail):
                            if tail[j].kw == 'USING' and j + 1 < len(tail) and tail[j + 1].kw == 'BTREE':
                                j += 2
                            elif tail[j].kw == 'COMMENT' and j + 1 < len(tail) and tail[j + 1].kind == 'string':
                                j += 2
                            else:
                                table.unknown.append((tail[j:], 'Index option outside parser coverage'))
                                break
            elif kind == 'CHECK':
                if len(group) < 2 or group[1].value != '(':
                    raise ValueError('Missing CHECK expression')
                table.checks.append(original)
            else:
                col = column(group)
                if col.name in table.columns:
                    raise ValueError('Duplicate column name')
                table.columns[col.name] = col
                if any(t.kw == 'CHECK' for t in group[2:]):
                    table.checks.append(group)
                if any(t.kw in ('PRIMARY', 'UNIQUE', 'KEY') for t in group[2:]):
                    table.indexes.append(Index('PRIMARY', [(col.name, None)], group,
                                               'UNIQUE' if any(t.kw == 'UNIQUE' for t in group[2:]) else 'PRIMARY'))
        except (ValueError, StopIteration) as exc:
            table.unknown.append((group, str(exc)))
    return table
