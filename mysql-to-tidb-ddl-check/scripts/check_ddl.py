#!/usr/bin/env python3
"""Offline, conservative MySQL dump assessment for TiDB 8.5 and TiDB Cloud.

This is a bounded structural checker, not an SQL validator or migration runner.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

from i18n import LANGUAGES, diagnostic, localize_report, message, message_join, validate_language
from ddlparse import SPATIAL, column, option, parse_table
from sqlscan import Scanner, Statement, closing, identifier, qualified, split_top


SNAPSHOT = '2026-09-16'
BASE = 'https://docs.pingcap.com/tidb/v8.5/'
SOURCES = {
    'compat': BASE + 'mysql-compatibility/',
    'cloud': 'https://docs.pingcap.com/tidbcloud/mysql-compatibility/',
    'features': 'https://docs.pingcap.com/tidbcloud/features/',
    'fulltext': 'https://docs.pingcap.com/ai/vector-search-full-text-search-sql/',
    'auto': BASE + 'auto-increment/',
    'constraints': BASE + 'constraints/',
    'fk': BASE + 'foreign-key/',
    'char': BASE + 'character-set-and-collation/',
    'limits': BASE + 'tidb-limitations/',
    'views': BASE + 'views/',
    'dump': 'https://dev.mysql.com/doc/refman/8.4/en/mysqldump-stored-programs.html',
    'comments': 'https://dev.mysql.com/doc/refman/8.4/en/comments.html',
    'check': 'https://dev.mysql.com/doc/refman/8.0/en/create-table-check-constraints.html',
}
# Titles, remediation and evidence references are shared by JSON and Markdown.
RULES = {
    'OBJ-001': (message('Stored procedure or stored function'), message('Move the logic into an application service while preserving parameters, return values, transaction boundaries, and error handling. Trace body dependencies manually.'), ['compat', 'cloud']),
    'OBJ-002': (message('Trigger'), message('Identify the owning table and every write path. Move trigger logic into the application while preserving atomicity; do not simply delete it.'), ['compat', 'cloud']),
    'OBJ-003': (message('Scheduled event'), message('Move the event to an external scheduler, preserving its schedule, time zone, idempotency, and concurrency constraints.'), ['compat', 'cloud']),
    'OBJ-004': (message('External UDF'), message('Inspect visible dependencies and evaluate verified built-in functions or application code as replacements.'), ['compat', 'cloud']),
    'IDX-001': (message('Full-text index'), message('Use the minimum capability set across providers and regions by default; use verified target evidence only for an explicit deployment-specific assessment. Ordinary indexes or LIKE are not equivalent replacements.'), ['compat', 'fulltext', 'features']),
    'TYPE-001': (message('Spatial type or index'), message('Identify spatial query requirements before evaluating alternative services or representations. JSON is not automatically equivalent.'), ['compat']),
    'IDX-002': (message('Descending index'), message('Validate query plans and performance for queries using this index. DDL alone does not prove incorrect query results.'), ['compat']),
    'AUTO-001': (message('Auto-increment assumptions'), message('Check assumptions about gapless IDs, commit order, inferred batch IDs, and mixed explicit IDs. Evaluate compatibility mode for the workload; do not automatically switch to AUTO_RANDOM.'), ['auto']),
    'AUTO-002': (message('Adding auto-increment to an existing column'), message('Verify the preceding schema and evaluate rebuilding the table and migrating data. Changing the starting value differs from adding the attribute.'), ['auto']),
    'FK-001': (message('Foreign key structure and dependencies'), message('Obtain parent table definitions, verify column types and parent indexes, and address specific restrictions. Do not remove constraints by default.'), ['constraints', 'fk']),
    'CHECK-001': (message('CHECK enforcement conditions'), message('Verify the source version, ENFORCED status, and target tidb_enable_check_constraint setting before planning enforcement and data validation.'), ['constraints', 'check']),
    'CHECK-002': (message('Inline CHECK in ALTER'), message('Separate column changes and constraint operations into supported forms, and validate existing data.'), ['constraints']),
    'CHAR-001': (message('Character set or collation'), message('Verify exact names, inheritance, and the target collation framework. Validate sorting, comparisons, and uniqueness before replacing them.'), ['char']),
    'PART-001': (message('Subpartitioning'), message('Evaluate single-level partitioning or a regular table, then validate query and operational effects separately.'), ['compat']),
    'LIMIT-001': (message('Schema limits'), message('Verify target settings and byte calculations before adjusting definitions or supported limits. DDL cannot determine actual row size.'), ['limits']),
    'VIEW-001': (message('View write assumptions'), message('Check whether the application writes through views. A view definition does not prove that view DML exists.'), ['views']),
    'ENGINE-001': (message('Source storage engine semantics'), message('Check dependencies on source engine behavior. Removing ENGINE does not prove semantic equivalence.'), ['compat']),
    'EXPR-001': (message('DDL expression'), message('Verify target support for the function or expression. Do not propose an equivalent rewrite without validating its semantics.'), ['compat']),
    'CONTEXT-001': (message('Privileges or cross-database dependencies'), message('Verify target accounts, privileges, and cross-database objects. Do not automatically remove DEFINER or switch to INVOKER.'), ['views']),
    'CONTEXT-002': (message('Dump session context'), message('Verify support and effects of each session statement. Do not unconditionally remove SET statements or import wrappers.'), ['compat']),
    'INPUT-001': (message('Insufficient source version evidence'), message('Provide the complete source MySQL server version. The client version is not a substitute.'), ['dump']),
    'INPUT-002': (message('Unknown export scope'), message('Confirm that routines, events, and triggers were included, and inspect export errors. Missing definitions do not prove absence in the source database.'), ['dump']),
    'INPUT-003': (message('Incomplete structural assessment'), message('Complete or manually inspect this input. The tool does not execute SQL; uncovered items cannot be treated as passing.'), ['comments']),
    'INPUT-004': (message('Unknown object context'), message('Provide the default database, inherited settings, dependencies, or file execution order. Directory sorting does not establish execution order.'), ['dump']),
    'INPUT-005': (message('Unknown target configuration'), message('Provide the Cloud plan and verify capability evidence. Provider and region are optional; do not request them. Recheck rolling product documentation when using the skill.'), ['cloud']),
}
CHARSETS = {'ascii': 1, 'binary': 1, 'latin1': 1, 'gbk': 2, 'utf8': 3, 'utf8mb3': 3, 'utf8mb4': 4}
COLLATIONS = set('ascii_bin binary gbk_bin gbk_chinese_ci latin1_bin utf8_bin utf8_general_ci utf8_unicode_ci utf8mb4_bin utf8mb4_general_ci utf8mb4_unicode_ci utf8mb4_0900_ai_ci utf8mb4_0900_bin'.split())
STRING_TYPES = set('CHAR VARCHAR TINYTEXT TEXT MEDIUMTEXT LONGTEXT ENUM SET'.split())
KNOWN_FUNCTIONS = set('CURRENT_TIMESTAMP CURRENT_DATE CURRENT_TIME NOW LOCALTIME LOCALTIMESTAMP ABS CEIL CEILING FLOOR ROUND CONCAT CONCAT_WS LOWER UPPER LENGTH CHAR_LENGTH COALESCE IF IFNULL NULLIF CAST CONVERT JSON_EXTRACT JSON_UNQUOTE JSON_OBJECT JSON_ARRAY DATE YEAR MONTH DAY COUNT SUM MIN MAX AVG SUBSTRING SUBSTR TRIM REPLACE MOD'.split())
UNSUPPORTED_FUNCTIONS = {'EXTRACTVALUE', 'UPDATEXML'}


def version_tuple(value):
    if not value:
        return None
    match = re.fullmatch(r'(\d+)\.(\d+)(?:\.(\d+))?(?:[-+][\w.-]+)?', value)
    if not match or 'mariadb' in value.lower():
        return None
    return tuple(int(x or 0) for x in match.groups())


def validate_target(value):
    target = {'product': 'self-managed', 'version': '8.5'} if value is None else dict(value)
    if target.get('product') not in ('self-managed', 'cloud'):
        raise ValueError('target.product must be self-managed or cloud')
    for key in ('version', 'plan', 'provider', 'region'):
        if key in target and not isinstance(target[key], str):
            raise ValueError(f'target.{key} must be a string')
    for key in ('settings', 'capabilities'):
        if not isinstance(target.get(key, {}), dict):
            raise ValueError(f'target.{key} must be an object')
    for key, value in target.get('settings', {}).items():
        if key in ('max-index-length', 'table-column-count-limit', 'index-limit'):
            if type(value) is not int or value <= 0:
                raise ValueError(f'{key} must be a positive integer')
        elif key in ('tidb_enable_check_constraint', 'new_collations_enabled_on_first_bootstrap'):
            if type(value) is not bool:
                raise ValueError(f'{key} must be a boolean')
        else:
            raise ValueError(f'Unsupported target setting: {key}')
    for key, value in target.get('capabilities', {}).items():
        if key != 'fulltext' or type(value) is not bool:
            raise ValueError('capabilities only accepts a fulltext boolean')
    return target


class Assessment:
    def __init__(self, sources, source_version, target, export_scope, ordered):
        self.sources = dict(sources.items() if ordered else sorted(sources.items()))
        self.target, self.ordered = validate_target(target), ordered
        headers = set()
        for text in sources.values():
            scanner = Scanner()
            next(scanner.statements(text, ''), None)
            headers.update(scanner.header_versions)
        conflict = len(headers) > 1 or bool(source_version and headers and headers != {source_version})
        version = source_version or (next(iter(headers)) if len(headers) == 1 else None)
        self.source = {'version': version, 'evidence': 'user' if source_version else 'dump-header' if version else 'unknown',
                       'header_versions': sorted(headers), 'conflict': conflict}
        self.version = None if conflict else version_tuple(version)
        self.findings, self.tables, self.objects, self.defaults = [], {}, {}, {}
        self.statement_count = 0
        self.coverage = {key: 'not-applicable' for key in RULES}
        if not self.version or self.version[:2] not in ((5, 7), (8, 0), (8, 4)):
            self.add('INPUT-001', None, '', message('The source version is unknown, conflicting, or outside the 5.7/8.0/8.4 coverage range.'), certainty='not-assessed')
        if not {'routines', 'events', 'triggers'}.issubset(set(export_scope or [])):
            self.add('INPUT-002', None, '', message('The files do not establish complete stored-program export coverage.'), certainty='not-assessed')
        if len(sources) > 1 and not ordered:
            self.add('INPUT-004', None, '', message('No execution order was declared for multiple files; each file has an independent session context.'))
        tv = version_tuple(self.target.get('version'))
        self.target_known = self.target['product'] == 'self-managed' and tv is not None and tv[:2] == (8, 5)
        if self.target['product'] == 'self-managed' and not self.target_known:
            self.add('INPUT-005', None, '', message('The target is not explicitly TiDB 8.5; version-dependent findings need confirmation.'))
        if self.target['product'] == 'cloud' and not self.target.get('plan'):
            self.add('INPUT-005', None, '', message('The Cloud plan is missing.'))

    def minimum_regional_fulltext(self):
        # Documentation snapshot: Starter is region-limited; the other listed
        # plans do not offer FULLTEXT. Unknown plans retain uncertainty.
        return (self.target['product'] == 'cloud'
                and not all(self.target.get(k) for k in ('provider', 'region'))
                and self.target.get('plan', '').lower() in
                ('starter', 'essential', 'premium', 'dedicated'))

    def mark(self, rule, status='checked'):
        rank = {'not-applicable': 0, 'checked': 1, 'needs-confirmation': 2, 'not-assessed': 3}
        if rank[status] > rank[self.coverage[rule]]:
            self.coverage[rule] = status

    def add(self, rule, stmt, obj, impact, severity='medium', certainty='needs-confirmation', tokens=None):
        if certainty == 'confirmed' and not rule.startswith('INPUT-'):
            common_cloud = rule in ('OBJ-001', 'OBJ-002', 'OBJ-003', 'OBJ-004', 'TYPE-001', 'PART-001', 'ENGINE-001', 'EXPR-001')
            fulltext_evidence = rule == 'IDX-001' and (self.minimum_regional_fulltext() or 'fulltext' in self.target.get('capabilities', {}))
            if not self.target_known and not (self.target['product'] == 'cloud' and (common_cloud or fulltext_evidence)):
                certainty = 'needs-confirmation'
            if stmt and stmt.guards:
                source_number = self.version[0] * 10000 + self.version[1] * 100 + self.version[2] if self.version else 0
                if any(g > source_number or g >= 90000 for g in stmt.guards):
                    certainty = 'needs-confirmation'
                    impact += message(' The version condition of an executable comment needs verification.')
            if certainty != 'confirmed' and severity == 'blocker':
                severity = 'high'
        use = tokens if tokens else (stmt.tokens if stmt else [])
        location = {'file': stmt.file if stmt else '', 'line_start': use[0].line if use else 0,
                    'line_end': use[-1].end_line if use else 0}
        evidence = Statement(use, '').evidence() if use else ''
        title, advice, urls = RULES[rule]
        item = {'rule_id': rule, 'title': title, 'object': obj, 'location': location, 'evidence': evidence,
                'severity': severity, 'certainty': certainty, 'impact': impact, 'recommendation': advice,
                'source_urls': [SOURCES[s] for s in urls]}
        if item not in self.findings:
            self.findings.append(item)
        self.mark(rule, 'not-assessed' if certainty == 'not-assessed' else 'needs-confirmation' if certainty == 'needs-confirmation' else 'checked')

    def gap(self, stmt, impact, tokens=None):
        self.add('INPUT-003', stmt, '', impact, certainty='not-assessed', tokens=tokens)

    def expressions(self, stmt, obj, tokens, context='query'):
        self.mark('EXPR-001')
        before = len(self.findings)
        syntax = set('CHECK IN AS VALUES OVER PARTITION CASE WHEN AND OR NOT'.split())
        for i, token in enumerate(tokens[:-1]):
            if tokens[i + 1].value != '(' or token.kind not in ('word', 'ident') or token.kw in syntax:
                continue
            name = token.value.upper()
            if name in UNSUPPORTED_FUNCTIONS:
                self.add('EXPR-001', stmt, obj, message('The expression uses the unsupported function {0}.', name), 'blocker', 'confirmed', [token])
            elif name not in KNOWN_FUNCTIONS or (context == 'AS' and name == 'NULLIF'):
                self.add('EXPR-001', stmt, obj, message('Function {0} is outside the verified function subset.', name), tokens=[token])
        if context == 'DEFAULT' and len(self.findings) == before:
            self.add('EXPR-001', stmt, obj, message('Expression defaults depend on the column type and specific expression; verify target support.'), tokens=tokens)

    def checks(self, stmt, obj, checks):
        enabled = self.target.get('settings', {}).get('tidb_enable_check_constraint')
        for tokens in checks:
            self.mark('CHECK-001')
            words = [t.kw for t in tokens]
            not_enforced = any(words[i:i + 2] == ['NOT', 'ENFORCED'] for i in range(len(words)))
            if not_enforced and enabled is True:
                continue
            if enabled is True and self.version and self.version >= (8, 0, 16):
                continue
            reason = message('Verify whether CHECK is enforced on both the source and the target.')
            if self.version and self.version < (8, 0, 16):
                reason += message(' The source predates 8.0.16; do not assume the constraint was enforced.')
            mismatch = not not_enforced and self.version is not None and (
                (enabled is False and self.version >= (8, 0, 16)) or
                (enabled is True and self.version < (8, 0, 16)))
            self.add('CHECK-001', stmt, obj, reason, 'high', 'confirmed' if mismatch else 'needs-confirmation', tokens)

    def charset(self, stmt, obj, charset, collation, tokens):
        self.mark('CHAR-001')
        if charset and charset not in CHARSETS:
            self.add('CHAR-001', stmt, obj, message('Character set {0} is not in the target support list.', charset), 'blocker', 'confirmed', tokens)
        if collation and collation not in COLLATIONS:
            self.add('CHAR-001', stmt, obj, message('Collation {0} is not in the verified support list.', collation), tokens=tokens)
        if charset and not collation:
            self.add('CHAR-001', stmt, obj, message('An explicit character set has no collation; target default comparison semantics might differ.'), tokens=tokens)
        if charset == 'latin1':
            self.add('CHAR-001', stmt, obj, message('Validate latin1 behavior against actual data; a supported name does not guarantee identical byte semantics.'), 'high', tokens=tokens)
        if collation and not collation.endswith('_bin') and collation != 'binary':
            if self.target.get('settings', {}).get('new_collations_enabled_on_first_bootstrap') is False:
                self.add('CHAR-001', stmt, obj, message('The target disables the new collation framework; verify comparison semantics.'), 'high', tokens=tokens)

    def limit(self, table, actual, default, config, label, tokens):
        self.mark('LIMIT-001')
        settings = self.target.get('settings', {})
        bound = settings.get(config, default) if config else default
        if actual > bound:
            confirmed = config is None or config in settings
            self.add('LIMIT-001', table.statement, table.name, message('{0}={1}; target limit or documented default={2}.', label, actual, bound),
                     'blocker' if confirmed else 'medium', 'confirmed' if confirmed else 'needs-confirmation', tokens)

    def table_rules(self, table):
        stmt = table.statement
        for group, error in table.unknown:
            self.gap(stmt, error, group)
        if not table.columns:
            self.gap(stmt, message('No columns were recognized; the table structure cannot be fully assessed.'))
        for col in table.columns.values():
            obj = table.name + '.' + col.name
            if col.auto:
                self.add('AUTO-001', stmt, obj, message('DDL establishes an auto-increment attribute but cannot confirm application assumptions about IDs.'), 'info', tokens=col.tokens)
            if col.type in SPATIAL:
                self.add('TYPE-001', stmt, obj, message('The target does not support this spatial type.'), 'blocker', 'confirmed', col.tokens)
            if col.type in STRING_TYPES:
                charset = col.charset or (col.collation.split('_')[0] if col.collation else table.charset)
                collation = col.collation or (None if col.charset else table.collation)
                if not charset and not collation:
                    self.add('INPUT-004', stmt, obj, message('The effective character set and collation of this string column are unknown.'), tokens=col.tokens)
                else:
                    self.charset(stmt, obj, charset, collation, col.tokens)
            for i, t in enumerate(col.tokens):
                if t.kw in ('AS', 'CHECK', 'DEFAULT'):
                    if i + 1 < len(col.tokens) and col.tokens[i + 1].value == '(':
                        end = closing(col.tokens, i + 1)
                        self.expressions(stmt, obj, col.tokens[i + 2:end], context=t.kw)
        if table.charset or table.collation:
            self.charset(stmt, table.name, table.charset, table.collation, table.options)
        self.checks(stmt, table.name, table.checks)
        for check in table.checks:
            start = next((i for i, t in enumerate(check) if t.kw == 'CHECK'), None)
            if start is not None and start + 1 < len(check) and check[start + 1].value == '(':
                end = closing(check, start + 1)
                self.expressions(stmt, table.name, check[start + 2:end])
        for idx in table.indexes:
            if idx.kind == 'FULLTEXT':
                self.mark('IDX-001')
                capability = self.target.get('capabilities', {}).get('fulltext')
                if self.minimum_regional_fulltext():
                    self.add('IDX-001', stmt, table.name, message('FULLTEXT is incompatible with the minimum capability set across providers and regions for this Cloud plan. Provider or region was omitted.'), 'high', 'confirmed', idx.tokens)
                elif self.target['product'] == 'self-managed' or capability is False:
                    self.add('IDX-001', stmt, table.name, message('The target lacks the required FULLTEXT index capability; accepting syntax does not mean the index is effective.'), 'high', 'confirmed', idx.tokens)
                elif capability is not True or not all(self.target.get(k) for k in ('plan', 'provider', 'region')):
                    self.add('IDX-001', stmt, table.name, message('Verify the Cloud plan and current full-text capability evidence.'), 'high', tokens=idx.tokens)
            if idx.kind == 'SPATIAL':
                self.add('TYPE-001', stmt, table.name, message('The target does not support spatial indexes.'), 'blocker', 'confirmed', idx.tokens)
            if any(t.kw == 'DESC' for t in idx.tokens):
                self.add('IDX-002', stmt, table.name, message('The target implements DESC index attributes differently.'), 'medium', 'confirmed', idx.tokens)
            self.limit(table, len(idx.columns), 16, None, message('Index column count'), idx.tokens)
            total, known = 0, True
            for name, prefix in idx.columns:
                col = table.columns.get(name)
                if not col:
                    self.gap(stmt, message('The index references an unrecognized column.'), idx.tokens)
                    known = False
                    continue
                if col.type in ('CHAR', 'VARCHAR', 'BINARY', 'VARBINARY', 'TEXT', 'BLOB', 'TINYTEXT', 'MEDIUMTEXT', 'LONGTEXT'):
                    count = prefix or col.length
                    charset = col.charset or (col.collation.split('_')[0] if col.collation else table.charset)
                    width = 1 if col.type in ('BINARY', 'VARBINARY', 'BLOB') else CHARSETS.get(charset)
                    if count and width:
                        total += count * width
                    else:
                        known = False
                elif col.type in ('TINYINT', 'SMALLINT', 'MEDIUMINT', 'INT', 'BIGINT', 'FLOAT', 'DOUBLE'):
                    total += {'TINYINT': 1, 'SMALLINT': 2, 'MEDIUMINT': 3, 'INT': 4, 'BIGINT': 8, 'FLOAT': 4, 'DOUBLE': 8}[col.type]
                else:
                    known = False
            if known:
                self.limit(table, total, 3072, 'max-index-length', message('Index length in bytes'), idx.tokens)
            else:
                self.add('LIMIT-001', stmt, table.name, message('The exact byte length of this index is outside the current calculation coverage.'), tokens=idx.tokens)
        self.limit(table, len(table.columns), 1017, 'table-column-count-limit', message('Column count'), stmt.tokens)
        index_columns = [[c[0] for c in idx.columns] for idx in table.indexes]
        for fk in sorted(table.foreign_keys, key=lambda fk: -len(fk.columns)):
            if not any(cols[:len(fk.columns)] == fk.columns for cols in index_columns):
                index_columns.append(fk.columns)
        self.limit(table, len(index_columns), 64, 'index-limit', message('Index count (including indexes required by foreign keys)'), stmt.tokens)
        partitions = option(table.options, ['PARTITIONS'])
        if partitions and partitions.isdigit():
            self.limit(table, int(partitions), 8192, None, message('Partition count'), table.options)
        else:
            # Explicit partition definitions (PARTITION BY is not a definition).
            count = sum(t.kw == 'PARTITION' and i + 1 < len(table.options) and table.options[i + 1].kw != 'BY'
                        for i, t in enumerate(table.options))
            self.limit(table, count, 8192, None, message('Partition count'), table.options)
        if any(t.kw == 'SUBPARTITION' for t in table.options):
            self.add('PART-001', stmt, table.name, message('The DDL uses subpartitioning.'), 'blocker', 'confirmed', table.options)
        engine = option(table.options, ['ENGINE'])
        if engine and engine != 'innodb':
            self.add('ENGINE-001', stmt, table.name, message('The source engine is {0}; verify engine-specific semantics.', engine), tokens=table.options)
        allowed_options = set('ENGINE DEFAULT CHARSET CHARACTER SET COLLATE AUTO_INCREMENT COMMENT ROW_FORMAT PARTITION'.split())
        # Parse common scalar options; partition expressions are separately scoped.
        i = 0
        while i < len(table.options):
            t = table.options[i]
            if t.kw == 'PARTITION':
                following = table.options[i + 1:]
                if len(following) < 2 or following[0].kw != 'BY' or following[1].kw not in ('HASH', 'KEY', 'RANGE', 'LIST', 'LINEAR'):
                    self.gap(stmt, message('Partition definition outside parser coverage.'), table.options[i:])
                break
            if t.kw == 'DEFAULT':
                i += 1
                continue
            if t.kw not in allowed_options:
                self.gap(stmt, message('Table option outside parser coverage.'), table.options[i:])
                break
            if t.kw == 'ROW_FORMAT':
                self.add('CONTEXT-002', stmt, table.name, message('Physical storage semantics of ROW_FORMAT have not been checked for equivalence.'), tokens=table.options[i:])
            i += 2 if t.kw == 'CHARACTER' else 1
            if i < len(table.options) and table.options[i].value == '=':
                i += 1
            i += 1

    def foreign_keys(self):
        for table in self.tables.values():
            for fk in table.foreign_keys:
                self.mark('FK-001')
                parent = self.tables.get(fk.parent)
                if parent and not self.ordered and fk.parent.startswith('?.') and parent.statement.file != table.statement.file:
                    parent = None
                if not parent or table.unknown or parent.unknown:
                    self.add('FK-001', table.statement, table.name, message('The parent table or relevant column definitions are incomplete; constraint validity cannot be established.'), tokens=fk.tokens)
                    continue
                problems = []
                if table.name == parent.name and any(a == b for a, b in zip(fk.columns, fk.parent_columns)):
                    problems.append(message('A foreign key column directly references itself'))
                if table.temporary or parent.temporary:
                    problems.append(message('The foreign key involves a temporary table'))
                if any(t.kw == 'PARTITION' for t in table.options + parent.options):
                    problems.append(message('The foreign key involves a partitioned table'))
                if not any([c[0] for c in idx.columns[:len(fk.parent_columns)]] == fk.parent_columns and
                           all(c[1] is None for c in idx.columns[:len(fk.parent_columns)]) for idx in parent.indexes):
                    problems.append(message('The parent lacks a matching index prefix of full columns'))
                missing = False
                for left, right in zip(fk.columns, fk.parent_columns):
                    a, b = table.columns.get(left), parent.columns.get(right)
                    if not a or not b:
                        missing = True
                        continue
                    if a.signature != b.signature:
                        problems.append(message('Parent and child column types, lengths, or signedness differ'))
                    if a.virtual or b.virtual or any('TEXT' in c.type or 'BLOB' in c.type for c in (a, b)):
                        problems.append(message('The foreign key involves a virtual generated column or TEXT/BLOB'))
                    if any(t.kw == 'AS' for t in a.tokens) and not a.virtual:
                        actions = [t.kw for t in fk.tokens]
                        if 'CASCADE' in actions or any(actions[i:i + 2] in (['SET', 'NULL'], ['SET', 'DEFAULT']) for i in range(len(actions))):
                            problems.append(message('A stored generated foreign key column uses an unsupported reference action'))
                    if a.type in STRING_TYPES:
                        for attr in ('charset', 'collation'):
                            av = getattr(a, attr) or getattr(table, attr)
                            bv = getattr(b, attr) or getattr(parent, attr)
                            if av is None or bv is None:
                                missing = True
                            elif av != bv:
                                problems.append(message('Parent and child character sets or collations differ'))
                if len(fk.columns) != len(fk.parent_columns):
                    problems.append(message('Parent and child column counts differ'))
                if problems:
                    self.add('FK-001', table.statement, table.name, message_join('; ', sorted(set(problems))) + message('. This restriction might also apply to the source MySQL database.'), 'blocker', 'confirmed', fk.tokens)
                elif missing:
                    self.add('FK-001', table.statement, table.name, message('Parent or child column definitions or effective character sets are incomplete.'), tokens=fk.tokens)

    def alter(self, stmt, database):
        tokens = stmt.tokens
        names, i = identifier(tokens, 2)
        name = qualified(names, database)
        table = self.tables.get(name)
        baseline_table = table if table and (self.ordered or table.statement.file == stmt.file) and not table.unknown else None
        for action in split_top(tokens[i:]):
            if not action:
                self.gap(stmt, message('Empty ALTER operation.'))
                continue
            first = action[0].kw
            if first in ('ADD', 'CHANGE') and any(t.kw == 'CHECK' for t in action):
                inline = first == 'CHANGE' or (len(action) > 1 and action[1].kw not in ('CONSTRAINT', 'CHECK'))
                if inline:
                    self.add('CHECK-002', stmt, name, message('Inline CHECK in ADD COLUMN is ignored.') if first == 'ADD' else message('Adding inline CHECK through CHANGE is unsupported.'),
                             'high' if first == 'ADD' else 'blocker', 'confirmed', action)
            if first in ('MODIFY', 'CHANGE'):
                j = 2 if len(action) > 1 and action[1].kw == 'COLUMN' else 1
                old = action[j].value if j < len(action) else ''
                if first == 'CHANGE':
                    j += 1
                try:
                    col = column(action[j:])
                    baseline = baseline_table.columns.get(old) if baseline_table else None
                    if col.auto and (not baseline or not baseline.auto):
                        self.add('AUTO-002', stmt, name + '.' + col.name, message('Adding auto-increment to an existing column.') if baseline else message('The column baseline is missing; adding auto-increment cannot be confirmed.'),
                                 'blocker' if baseline else 'medium', 'confirmed' if baseline else 'needs-confirmation', action)
                    if table:
                        table.columns.pop(old, None)
                        table.columns[col.name] = col
                except ValueError as exc:
                    self.gap(stmt, diagnostic(exc), action)
            if first == 'AUTO_INCREMENT' and len(action) >= 3 and action[1].value == '=' and action[2].kind == 'number':
                continue
            # This first release only assesses the two listed ALTER rules.
            self.gap(stmt, message('Only auto-increment attributes and inline CHECK were assessed for ALTER; other change semantics are not covered.'), action)
            if table:
                table.unknown.append((action, message('The schema after ALTER was not fully reconstructed')))

    def statement(self, stmt, database):
        tokens = stmt.tokens
        if stmt.error:
            self.gap(stmt, stmt.error)
            return database
        depth = 0
        for t in tokens:
            if t.kind == 'symbol':
                depth += (t.value == '(') - (t.value == ')')
                if depth < 0:
                    raise ValueError(message('Unexpected closing parenthesis'))
        if depth:
            raise ValueError(message('Unclosed parenthesis'))
        first = tokens[0].kw
        if first == 'USE':
            names, end = identifier(tokens, 1)
            if end != len(tokens) or len(names) != 1:
                raise ValueError(message('Unrecognized USE statement'))
            return names[0]
        if first == 'SET':
            names = []
            for group in split_top(tokens[1:]):
                eq = next((i for i, t in enumerate(group) if t.value == '='), None)
                names.append(''.join(t.value for t in group[:eq]).upper() if eq is not None else '')
            allowed = {'SQL_MODE', 'TIME_ZONE', 'FOREIGN_KEY_CHECKS', 'UNIQUE_CHECKS', 'CHARACTER_SET_CLIENT',
                       'CHARACTER_SET_RESULTS', 'COLLATION_CONNECTION', 'SQL_NOTES'}
            known = bool(names) and all(n.startswith('@') and not n.startswith('@@') or
                                       n.removeprefix('@@SESSION.').removeprefix('@@').removeprefix('SESSION').removeprefix('LOCAL') in allowed for n in names)
            if any(t.kind == 'symbol' and t.value == '(' for t in tokens):
                known = False  # Function/expression assignments are not save/restore wrappers.
            if len(tokens) > 1 and tokens[1].kw == 'NAMES':
                known = True
                self.charset(stmt, '', tokens[2].value.lower() if len(tokens) > 2 else None, option(tokens, ['COLLATE']), tokens)
            self.mark('CONTEXT-002')
            if not known:
                self.add('CONTEXT-002', stmt, '', message('The session statement is outside the verified dump wrapper subset.'), certainty='not-assessed')
            return database
        if first in ('LOCK', 'UNLOCK'):
            self.add('CONTEXT-002', stmt, '', message('Verify target settings and semantics for lock wrapper statements.'))
            return database
        if first in ('INSERT', 'REPLACE', 'UPDATE', 'DELETE'):
            self.gap(Statement(tokens[:1], stmt.file), message('The input contains DML; data values and application behavior were not assessed.'))
            return database
        if first == 'ALTER' and len(tokens) > 1 and tokens[1].kw == 'TABLE':
            self.alter(stmt, database)
            return database
        if first == 'DROP' and len(tokens) > 1 and tokens[1].kw in ('TABLE', 'VIEW'):
            i = 4 if [t.kw for t in tokens[2:4]] == ['IF', 'EXISTS'] else 2
            for group in split_top(tokens[i:]):
                names, end = identifier(group, 0)
                if end != len(group):
                    raise ValueError(message('DROP form outside parser coverage'))
                name = qualified(names, database)
                self.tables.pop(name, None)
                self.objects.pop(('relation', name), None)
            return database
        if first != 'CREATE':
            self.gap(stmt, message('SQL or client instruction outside parser coverage.'))
            return database
        kinds = {'TABLE', 'DATABASE', 'SCHEMA', 'VIEW', 'PROCEDURE', 'FUNCTION', 'TRIGGER', 'EVENT'}
        kind_index = next((i for i, t in enumerate(tokens[1:], 1) if t.kw in kinds), None)
        if kind_index is None:
            self.gap(stmt, message('CREATE object outside parser coverage.'))
            return database
        kind = tokens[kind_index].kw
        i = kind_index + 1
        if [t.kw for t in tokens[i:i + 3]] == ['IF', 'NOT', 'EXISTS']:
            i += 3
        names, end = identifier(tokens, i)
        name = qualified(names, database)
        if kind in ('DATABASE', 'SCHEMA'):
            self.defaults[names[0]] = {'charset': option(tokens[end:], ['CHARACTER SET', 'CHARSET']), 'collation': option(tokens[end:], ['COLLATE'])}
            values = self.defaults[names[0]]
            self.charset(stmt, names[0], values['charset'], values['collation'], tokens)
            return database
        if kind in ('PROCEDURE', 'FUNCTION', 'TRIGGER', 'EVENT'):
            udf = kind == 'FUNCTION' and any(t.kw == 'SONAME' for t in tokens[end:])
            rule = 'OBJ-004' if udf else {'PROCEDURE': 'OBJ-001', 'FUNCTION': 'OBJ-001', 'TRIGGER': 'OBJ-002', 'EVENT': 'OBJ-003'}[kind]
            impact = message('The target does not support this object definition. Its body and complete business dependencies were not semantically validated.')
            evidence_end = end
            if kind == 'TRIGGER':
                on = next((j for j in range(end, len(tokens)) if tokens[j].kw == 'ON'), None)
                if on is not None:
                    trigger_table, evidence_end = identifier(tokens, on + 1)
                    impact += message(' Trigger condition: {0}; owning table: {1}.', ' '.join(t.value for t in tokens[end:on]), qualified(trigger_table, database))
            self.add(rule, stmt, name, impact, 'blocker', 'confirmed', tokens[:evidence_end])
            self.objects[(kind.lower(), name)] = {'name': name, 'kind': kind.lower(), 'file': stmt.file, 'line': stmt.line}
            return database
        if kind == 'TABLE':
            table = parse_table(stmt, database, self.defaults)
            if name in self.tables:
                self.add('INPUT-004', stmt, name, message('Duplicate table definitions; replacement behavior or execution order cannot be assumed.'))
                table.unknown.append((tokens[:end], message('Duplicate table definitions leave the schema uncertain')))
            source_number = self.version[0] * 10000 + self.version[1] * 100 + self.version[2] if self.version else 0
            if any(g > source_number for g in stmt.guards):
                table.unknown.append((tokens[:end], message('A conditional table definition is not a confirmed dependency baseline')))
            self.tables[name] = table
            self.objects[('relation', name)] = {'name': name, 'kind': 'table', 'file': stmt.file, 'line': stmt.line}
            self.table_rules(table)
            return database
        if kind == 'VIEW':
            self.tables.pop(name, None)
            self.objects[('relation', name)] = {'name': name, 'kind': 'view', 'file': stmt.file, 'line': stmt.line}
            self.add('VIEW-001', stmt, name, message('Target views are not writable; DDL cannot establish whether the application relies on view writes.'), 'info', tokens=tokens[:end])
            if any(t.kw in ('DEFINER', 'SECURITY') for t in tokens[:kind_index]):
                self.add('CONTEXT-001', stmt, name, message('The view has an explicit security context; target accounts and privileges were not verified.'), tokens=tokens[:end])
            select = next((i for i, t in enumerate(tokens) if t.kw == 'SELECT'), None)
            if select is None:
                self.gap(stmt, message('The view lacks a recognizable SELECT.'))
            else:
                self.expressions(stmt, name, tokens[select + 1:])
                self.add('CONTEXT-001', stmt, name, message('Only functions were scanned in the view query and dependencies; verify full query semantics and cross-database privileges manually.'), tokens=tokens[:end])
            return database
        return database

    def run(self):
        source_number = self.version[0] * 10000 + self.version[1] * 100 + self.version[2] if self.version else None
        database, scanner = None, Scanner(source_number=source_number)
        for filename, text in self.sources.items():
            if not self.ordered:
                database, scanner = None, Scanner(source_number=source_number)
                self.defaults = {}
            for stmt in scanner.statements(text, filename):
                self.statement_count += 1
                if any(g > (source_number or 0) or g >= 90000 for g in stmt.guards):
                    self.add('INPUT-004', stmt, '', message('The executable comment version condition is unconfirmed; the definition is assessed conditionally.'))
                try:
                    database = self.statement(stmt, database)
                except (ValueError, IndexError, StopIteration) as exc:
                    self.gap(stmt, diagnostic(exc))
        self.foreign_keys()
        if not self.statement_count:
            self.gap(None, message('No SQL statements are available for assessment.'))
        return self.result()

    def result(self):
        self.findings.sort(key=lambda f: (f['location']['file'], f['location']['line_start'], f['object'], f['rule_id'], f['impact']))
        counts = Counter(f['severity'] for f in self.findings if not f['rule_id'].startswith('INPUT-'))
        incomplete = any(f['rule_id'].startswith('INPUT-') or f['certainty'] == 'not-assessed' for f in self.findings)
        return {'schema_version': 1, 'rules_version': '1', 'sources_checked_on': SNAPSHOT,
                'source': self.source, 'target': self.target, 'files': list(self.sources),
                'summary': {'complete': not incomplete, 'statements': self.statement_count,
                            'tables': sum(o['kind'] == 'table' for o in self.objects.values()),
                            'objects': len(self.objects), 'severity_counts': dict(sorted(counts.items())),
                            'input_issues': sum(f['rule_id'].startswith('INPUT-') for f in self.findings)},
                'inventory': sorted(self.objects.values(), key=lambda o: (o['name'], o['kind'])),
                'coverage': [{'rule_id': k, 'status': v} for k, v in self.coverage.items()],
                'findings': self.findings,
                'limitations': [message('Static structural checks do not validate SQL syntax; checked refers only to the implemented rule subset.'),
                                message('Application SQL, transactions, actual data, performance, and the migration pipeline were not assessed.'),
                                message('Verify Cloud capabilities against current product documentation; an offline snapshot does not establish current availability.')]}


def analyze(sources, source_version=None, target=None, export_scope=None, ordered=False, language='en'):
    """Analyze filename -> SQL text; insertion order is meaningful only with ordered=True."""
    validate_language(language)
    assessment = Assessment(sources, source_version, target, export_scope, ordered)
    if not sources or not any(text.strip() for text in sources.values()):
        assessment.add('INPUT-003', None, '', message('No SQL input is available for assessment.'), certainty='not-assessed')
    return localize_report(assessment.run(), language)


def md_escape(value):
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('`', '&#96;').replace('|', '&#124;').replace('\n', ' ')


def render_markdown(report):
    language = validate_language(report.get('language', 'en'))

    def text(template, *values):
        return message(template, *values).render(language)

    summary = report['summary']
    completeness = text('complete within rule coverage' if summary['complete'] else
                        'incomplete; input or assessment gaps remain')
    lines = ['# ' + text('MySQL to TiDB DDL Assessment'), '',
             text('Assessment completeness: {0}.', completeness),
             text('Source version: {0}; target: {1}.',
                  md_escape(report['source']['version'] or text('unknown')),
                  md_escape(json.dumps(report['target'], ensure_ascii=False))),
             text('Files: {0}; statements: {1}; final objects: {2}.',
                  len(report['files']), summary['statements'], summary['objects']), '',
             '## ' + text('Input files'), '']
    lines.extend('- ' + md_escape(name) for name in report['files'])
    lines.extend(['', '## ' + text('Findings'), ''])
    if not report['findings']:
        lines.append(text('No blockers were found within the parsed DDL and applicable rule coverage.'))
    priority = {'blocker': 0, 'high': 1, 'medium': 2, 'info': 3}
    findings = sorted(report['findings'], key=lambda f: (f['rule_id'].startswith('INPUT-'), priority[f['severity']]))
    for f in findings:
        loc = f['location']
        lines.extend([f"### {f['rule_id']} · {f['title']}", '',
                      f"{text(f['severity'])} / {text(f['certainty'])} · {md_escape(f['object'] or text('Input scope'))} · {md_escape(loc['file'])}:{loc['line_start']}", '',
                      text('Evidence: ') + md_escape(f['evidence'] or text('not provided')), '',
                      text('Impact: ') + md_escape(f['impact']), '',
                      text('Recommendation: ') + f['recommendation'], '',
                      text('References: ') + ', '.join(f"[{text('Official documentation {0}', i + 1)}]({url})" for i, url in enumerate(f['source_urls'])), ''])
    lines.extend(['## ' + text('Coverage and limitations'), '',
                  '| ' + text('Rule') + ' | ' + text('Status') + ' |', '| --- | --- |'])
    lines.extend(f"| {c['rule_id']} | {text(c['status'])} |" for c in report['coverage'])
    lines.append('')
    lines.extend('- ' + item for item in report['limitations'])
    lines.extend(['', text('Rule sources checked on: {0}.', report['sources_checked_on']), ''])
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='+', type=Path)
    parser.add_argument('--source-version')
    parser.add_argument('--language', choices=LANGUAGES, default='en', help='Report language: en (English), zh (Chinese), ja (Japanese); default: en')
    parser.add_argument('--target-config', type=Path, help='Target JSON; default: self-managed TiDB 8.5')
    parser.add_argument('--export-scope', default='', help='Comma-separated routines,events,triggers confirmed exported')
    parser.add_argument('--ordered', action='store_true', help='Explicit input files are in execution order; directories cannot be ordered')
    parser.add_argument('--format', choices=('json', 'markdown'), default='markdown')
    parser.add_argument('--output', type=Path, help='Create a NEW report file; existing files are never overwritten')
    args = parser.parse_args(argv)
    try:
        if args.ordered and any(p.is_dir() for p in args.inputs):
            raise ValueError('--ordered requires explicit files in execution order, not directories')
        files = []
        for path in args.inputs:
            candidates = sorted((p for p in path.rglob('*') if p.is_file() and p.suffix.lower() == '.sql')) if path.is_dir() else [path]
            for p in candidates:
                resolved = p.resolve()
                if resolved not in files:
                    files.append(resolved)
        if not files:
            raise ValueError('No SQL files found')
        if args.output and (args.output.exists() or args.output.resolve() in files):
            raise ValueError('Output must be a new file; input and existing files cannot be overwritten')
        target = json.loads(args.target_config.read_text(encoding='utf-8')) if args.target_config else None
        if target is not None and not isinstance(target, dict):
            raise ValueError('Target configuration must be a JSON object')
        sources, failures = {}, []
        for path in files:
            try:
                sources[str(path)] = path.read_text(encoding='utf-8-sig')
            except (OSError, UnicodeError):
                sources[str(path)] = ''
                failures.append(str(path))
        assessment = Assessment(sources, args.source_version, target, args.export_scope.split(','), args.ordered)
        for name in failures:
            assessment.gap(Statement([], name), message('The file cannot be read or is not valid UTF-8; provide a correctly encoded export.'))
        if not any(text.strip() for text in sources.values()):
            assessment.gap(None, message('No SQL content is available for assessment.'))
        report = localize_report(assessment.run(), args.language)
        output = json.dumps(report, ensure_ascii=False, indent=2) + '\n' if args.format == 'json' else render_markdown(report)
        if args.output:
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(output)
        else:
            print(output, end='')
        if failures:
            return 2
        if any(f['severity'] == 'blocker' and f['certainty'] == 'confirmed' for f in report['findings']):
            return 1
        return 0 if report['summary']['complete'] else 2
    except (OSError, ValueError, TypeError) as exc:
        print(f'Input error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
