import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_ddl import analyze, render_markdown  # noqa: E402


class CheckerTests(unittest.TestCase):
    def report(self, sql, **options):
        defaults = dict(source_version='8.0.36', export_scope=['routines', 'events', 'triggers'])
        defaults.update(options)
        return analyze({'schema.sql': sql}, **defaults)

    def findings(self, sql, rule, **options):
        return [f for f in self.report(sql, **options)['findings'] if f['rule_id'] == rule]

    def test_plain_table_has_no_compatibility_findings(self):
        r = self.report('CREATE TABLE t (id INT PRIMARY KEY, n INT) ENGINE=InnoDB;')
        self.assertEqual(r['findings'], [])
        self.assertEqual(r['summary']['tables'], 1)
        self.assertEqual(len(r['coverage']), 25)

    def test_stored_objects_and_delimiters(self):
        sql = """-- heading
DELIMITER $$
CREATE PROCEDURE p() BEGIN SELECT 'a;$$'; SELECT 2; END$$
CREATE FUNCTION f() RETURNS INT RETURN 1$$
CREATE TRIGGER tr AFTER INSERT ON t FOR EACH ROW BEGIN SET @n=1; END$$
CREATE EVENT ev ON SCHEDULE EVERY 1 DAY DO SELECT 1$$
DELIMITER ;
CREATE FUNCTION udf RETURNS STRING SONAME 'private_library.so';
"""
        r = self.report(sql)
        fs = [f for f in r['findings'] if f['rule_id'].startswith('OBJ-')]
        self.assertEqual([f['rule_id'] for f in fs], ['OBJ-001', 'OBJ-001', 'OBJ-002', 'OBJ-003', 'OBJ-004'])
        self.assertEqual(fs[0]['location']['line_start'], 3)
        self.assertTrue(all(f['severity'] == 'blocker' for f in fs))
        self.assertNotIn('private_library.so', json.dumps(r))

    def test_keywords_in_identifiers_strings_and_comments_are_not_objects(self):
        sql = "CREATE TABLE `trigger` (`procedure` INT, x VARCHAR(99) DEFAULT 'FULLTEXT CREATE EVENT'); /* CREATE TRIGGER x */"
        r = self.report(sql)
        self.assertFalse(any(f['rule_id'].startswith(('OBJ-', 'IDX-')) for f in r['findings']))

    def test_adjacent_executable_comments(self):
        sql = """DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER tr BEFORE INSERT ON t FOR EACH ROW SET @a=1 */;;
DELIMITER ;
"""
        fs = self.findings(sql, 'OBJ-002')
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]['object'], '?.tr')
        self.assertEqual(fs[0]['location']['line_start'], 2)

    def test_future_executable_comment_does_not_claim_confirmed(self):
        fs = self.findings('/*!99999 CREATE PROCEDURE p() SELECT 1 */;', 'OBJ-001')
        self.assertEqual(fs[0]['certainty'], 'needs-confirmation')

    def test_autoincrement_is_advisory(self):
        f = self.findings('CREATE TABLE t(id BIGINT PRIMARY KEY AUTO_INCREMENT);', 'AUTO-001')[0]
        self.assertEqual((f['severity'], f['certainty']), ('info', 'needs-confirmation'))

    def test_add_autoincrement_requires_baseline(self):
        alter = 'ALTER TABLE t MODIFY id INT AUTO_INCREMENT;'
        for prefix, expected in [('', 'needs-confirmation'), ('CREATE TABLE t(id INT);', 'confirmed')]:
            with self.subTest(prefix=prefix):
                self.assertEqual(self.findings(prefix + alter, 'AUTO-002')[0]['certainty'], expected)
        self.assertFalse(self.findings('CREATE TABLE t(id INT AUTO_INCREMENT);' + alter, 'AUTO-002'))
        self.assertFalse(self.findings('ALTER TABLE t AUTO_INCREMENT=100;', 'AUTO-002'))

    def test_cloud_region_is_optional_for_complete_basic_assessment(self):
        target = dict(product='cloud', plan='essential', provider='aws')
        report = self.report('CREATE TABLE t(id INT PRIMARY KEY);', target=target)
        self.assertEqual(report['findings'], [])
        self.assertTrue(report['summary']['complete'])
        self.assertNotIn('region', report['target'])

    def test_cloud_minimum_regional_fulltext_capability(self):
        sql = 'CREATE TABLE t(body TEXT, FULLTEXT KEY ft(body));'
        for plan in ('starter', 'essential', 'premium', 'dedicated'):
            for capability in (None, True, False):
                with self.subTest(plan=plan, capability=capability):
                    target = dict(product='cloud', plan=plan, provider='aws')
                    if capability is not None:
                        target['capabilities'] = {'fulltext': capability}
                    f = self.findings(sql, 'IDX-001', target=target)[0]
                    self.assertEqual((f['severity'], f['certainty']), ('high', 'confirmed'))
                    self.assertIn('minimum', f['impact'])

    def test_unknown_cloud_plan_keeps_capability_uncertainty(self):
        target = dict(product='cloud', plan='future-plan', provider='aws')
        f = self.findings('CREATE TABLE t(body TEXT, FULLTEXT KEY ft(body));',
                          'IDX-001', target=target)[0]
        self.assertEqual(f['certainty'], 'needs-confirmation')

    def test_minimum_regional_finding_is_localized(self):
        sql = 'CREATE TABLE t(body TEXT, FULLTEXT KEY ft(body));'
        target = dict(product='cloud', plan='starter', provider='aws')
        for language, phrase in [('en', 'minimum'), ('zh', '最小'), ('ja', '最小')]:
            with self.subTest(language=language):
                f = self.findings(sql, 'IDX-001', target=target, language=language)[0]
                self.assertEqual(f['certainty'], 'confirmed')
                self.assertIn(phrase, f['impact'])

    def test_fulltext_target_profiles(self):
        sql = 'CREATE TABLE t(body TEXT, FULLTEXT KEY ft(body));'
        self.assertEqual(self.findings(sql, 'IDX-001')[0]['certainty'], 'confirmed')
        targets = [dict(product='cloud'), dict(product='cloud', plan='starter', provider='aws', region='us-west-2')]
        for target in targets:
            f = self.findings(sql, 'IDX-001', target=target)[0]
            self.assertEqual(f['certainty'], 'needs-confirmation')
        target = dict(product='cloud', plan='starter', provider='aws', region='us-west-2', capabilities={'fulltext': True})
        self.assertFalse(self.findings(sql, 'IDX-001', target=target))
        target['capabilities']['fulltext'] = False
        self.assertEqual(self.findings(sql, 'IDX-001', target=target)[0]['certainty'], 'confirmed')

    def test_spatial_and_desc(self):
        sql = 'CREATE TABLE t(id INT, g GEOMETRY, SPATIAL KEY s(g), KEY k(id DESC));'
        self.assertTrue(self.findings(sql, 'TYPE-001'))
        self.assertTrue(self.findings(sql, 'IDX-002'))
        self.assertFalse(self.findings('CREATE TABLE t(`geometry` INT, `desc` INT);', 'TYPE-001'))

    def test_valid_foreign_key(self):
        sql = 'CREATE TABLE p(id INT PRIMARY KEY); CREATE TABLE c(pid INT, FOREIGN KEY(pid) REFERENCES p(id));'
        self.assertFalse(self.findings(sql, 'FK-001'))

    def test_foreign_key_missing_parent_is_not_blocker(self):
        f = self.findings('CREATE TABLE c(pid INT, FOREIGN KEY(pid) REFERENCES outside.p(id));', 'FK-001')[0]
        self.assertEqual(f['certainty'], 'needs-confirmation')
        self.assertNotEqual(f['severity'], 'blocker')

    def test_foreign_key_restrictions_and_type_mismatch(self):
        for child in ['pid BIGINT', 'pid INT GENERATED ALWAYS AS (1) VIRTUAL']:
            with self.subTest(child=child):
                sql = f'CREATE TABLE p(id INT PRIMARY KEY); CREATE TABLE c({child}, FOREIGN KEY(pid) REFERENCES p(id));'
                self.assertEqual(self.findings(sql, 'FK-001')[0]['certainty'], 'confirmed')

    def test_check_settings_and_source_versions(self):
        sql = 'CREATE TABLE t(n INT CHECK(n>0));'
        self.assertEqual(self.findings(sql, 'CHECK-001')[0]['certainty'], 'needs-confirmation')
        target = dict(product='self-managed', version='8.5.3', settings={'tidb_enable_check_constraint': True})
        self.assertFalse(self.findings(sql, 'CHECK-001', target=target))
        self.assertTrue(self.findings(sql, 'CHECK-001', source_version='5.7.44', target=target))
        self.assertFalse(self.findings('CREATE TABLE t(n INT CHECK(n>0) NOT ENFORCED);', 'CHECK-001', target=target))

    def test_check_alter_forms(self):
        for form, severity in [('ADD COLUMN n INT CHECK(n>0)', 'high'), ('CHANGE n m INT CHECK(m>0)', 'blocker')]:
            self.assertEqual(self.findings('ALTER TABLE t ' + form + ';', 'CHECK-002')[0]['severity'], severity)

    def test_charset_support_and_inheritance(self):
        sql = 'CREATE DATABASE d DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci; USE d; CREATE TABLE t(s VARCHAR(10));'
        self.assertFalse(self.findings(sql, 'CHAR-001'))
        findings = self.findings('CREATE TABLE t(s VARCHAR(10)) CHARSET=utf16;', 'CHAR-001')
        self.assertTrue(any(f['severity'] == 'blocker' and f['certainty'] == 'confirmed' for f in findings))
        self.assertTrue(self.findings('CREATE TABLE t(s VARCHAR(10));', 'INPUT-004'))

    def test_supported_0900_and_unknown_collation(self):
        for collation, expected in [('utf8mb4_0900_ai_ci', False), ('utf8mb4_0900_bin', False), ('utf8mb4_madeup_ci', True)]:
            with self.subTest(collation=collation):
                self.assertEqual(bool(self.findings(f'CREATE TABLE t(s TEXT) COLLATE={collation};', 'CHAR-001')), expected)

    def test_partition_detection(self):
        sql = 'CREATE TABLE t(id INT) PARTITION BY HASH(id) PARTITIONS 4;'
        self.assertFalse(self.findings(sql, 'PART-001'))
        self.assertTrue(self.findings(sql.replace('PARTITIONS 4', 'SUBPARTITION BY HASH(id) SUBPARTITIONS 2'), 'PART-001'))

    def test_limits_use_bytes_and_config(self):
        sql = 'CREATE TABLE t(s VARCHAR(800), KEY k(s)) CHARSET=utf8mb4 COLLATE=utf8mb4_bin;'
        f = self.findings(sql, 'LIMIT-001')[0]
        self.assertEqual(f['certainty'], 'needs-confirmation')
        target = dict(product='self-managed', version='8.5', settings={'max-index-length': 3072})
        self.assertEqual(self.findings(sql, 'LIMIT-001', target=target)[0]['certainty'], 'confirmed')
        self.assertFalse(self.findings(sql.replace('KEY k(s)', 'KEY k(s(100))'), 'LIMIT-001'))

    def test_index_column_count(self):
        cols = ','.join(f'c{i} INT' for i in range(17))
        keys = ','.join(f'c{i}' for i in range(17))
        self.assertEqual(self.findings(f'CREATE TABLE t({cols}, KEY k({keys}));', 'LIMIT-001')[0]['severity'], 'blocker')

    def test_view_engine_expression_and_definer(self):
        self.assertTrue(self.findings('CREATE VIEW v AS SELECT 1;', 'VIEW-001'))
        self.assertTrue(self.findings('CREATE TABLE t(n INT) ENGINE=MyISAM;', 'ENGINE-001'))
        self.assertTrue(self.findings("CREATE VIEW v AS SELECT EXTRACTVALUE(x, '/a') FROM t;", 'EXPR-001'))
        self.assertFalse(self.findings('CREATE TABLE t(x TIMESTAMP DEFAULT CURRENT_TIMESTAMP);', 'EXPR-001'))
        self.assertTrue(self.findings('CREATE DEFINER=`u`@`h` SQL SECURITY DEFINER VIEW v AS SELECT 1;', 'CONTEXT-001'))

    def test_unknown_expression_is_not_confirmed(self):
        f = self.findings('CREATE TABLE t(a INT, b INT AS (mystery(a)));', 'EXPR-001')[0]
        self.assertEqual(f['certainty'], 'needs-confirmation')

    def test_dump_wrappers_known_and_unknown(self):
        sql = "SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO'; SET SQL_MODE=@OLD_SQL_MODE; SET @@GLOBAL.GTID_PURGED='secret';"
        r = self.report(sql)
        self.assertTrue(any(f['rule_id'] == 'CONTEXT-002' for f in r['findings']))
        self.assertNotIn('secret', json.dumps(r))

    def test_unknown_sql_is_visible(self):
        r = self.report('CREATE TABLE t(id INT); FROBNICATE t;')
        self.assertFalse(r['summary']['complete'])
        self.assertTrue(any(f['rule_id'] == 'INPUT-003' for f in r['findings']))

    def test_truncation_and_unclosed_string(self):
        for sql in ['CREATE TABLE t(id INT', "CREATE TABLE t(s TEXT DEFAULT 'unterminated"]:
            with self.subTest(sql=sql):
                self.assertTrue(self.findings(sql, 'INPUT-003'))

    def test_source_version_detection(self):
        sql = '-- MySQL dump 10.13 Distrib 8.0.36\n-- Server version 5.7.44\nCREATE TABLE t(id INT);'
        r = self.report(sql, source_version=None)
        self.assertEqual(r['source']['version'], '5.7.44')
        self.assertFalse(any(f['rule_id'] == 'INPUT-001' for f in r['findings']))
        self.assertTrue(self.findings(sql, 'INPUT-001', source_version='8.0.36'))
        self.assertTrue(self.findings('-- MySQL dump 10.13 Distrib 8.4.0\nCREATE TABLE t(id INT);', 'INPUT-001', source_version=None))

    def test_all_supported_source_families(self):
        for version in ['5.7.44', '8.0.36', '8.4.0']:
            self.assertFalse(self.findings('CREATE TABLE t(id INT);', 'INPUT-001', source_version=version))
        self.assertTrue(self.findings('CREATE TABLE t(id INT);', 'INPUT-001', source_version='10.11.0-MariaDB'))

    def test_export_scope_missing(self):
        self.assertTrue(self.findings('CREATE TABLE t(id INT);', 'INPUT-002', export_scope=None))

    def test_cloud_profile_missing(self):
        self.assertTrue(self.findings('CREATE TABLE t(id INT);', 'INPUT-005', target={'product': 'cloud'}))

    def test_ansi_quotes_and_escaped_identifiers(self):
        sql = 'SET SQL_MODE=\'ANSI_QUOTES\'; CREATE TABLE "d"."t" ("trigger" INT, "a""b" INT);'
        r = self.report(sql)
        self.assertIn('d.t', [o['name'] for o in r['inventory']])
        self.assertFalse(any(f['rule_id'].startswith('OBJ-') for f in r['findings']))

    def test_no_backslash_escapes(self):
        sql = "SET SQL_MODE='NO_BACKSLASH_ESCAPES'; CREATE TABLE t(s TEXT DEFAULT 'a\\'); CREATE PROCEDURE p() SELECT 1;"
        self.assertEqual(len(self.findings(sql, 'OBJ-001')), 1)

    def test_unknown_sql_mode_does_not_claim_precise_parsing(self):
        sql = 'SET SQL_MODE=@unknown; CREATE TABLE "t" (id INT);'
        self.assertTrue(self.findings(sql, 'INPUT-003'))

    def test_multifile_context_and_order(self):
        sources = {'a.sql': 'USE a; CREATE TABLE t(id INT);', 'b.sql': 'CREATE TABLE t(id INT);'}
        r = analyze(sources, source_version='8.0.36', export_scope=['routines', 'events', 'triggers'])
        self.assertEqual({o['name'] for o in r['inventory']}, {'a.t', '?.t'})
        r = analyze(sources, source_version='8.0.36', ordered=True)
        self.assertTrue(any(f['rule_id'] == 'INPUT-004' for f in r['findings']))

    def test_distinct_schemas_and_cross_file_fk(self):
        r = analyze({'a.sql': 'CREATE TABLE a.p(id INT PRIMARY KEY);', 'b.sql': 'CREATE TABLE b.p(id INT); CREATE TABLE b.c(id INT, FOREIGN KEY(id) REFERENCES a.p(id));'}, source_version='8.0.36')
        self.assertFalse(any(f['rule_id'] == 'FK-001' for f in r['findings']))

    def test_view_placeholder_is_not_final_table(self):
        r = self.report('CREATE TABLE v(id INT); DROP TABLE IF EXISTS v; CREATE VIEW v AS SELECT 1;')
        self.assertEqual([(o['name'], o['kind']) for o in r['inventory']], [('?.v', 'view')])

    def test_data_and_comments_are_not_leaked(self):
        sql = "INSERT INTO t VALUES ('customer-secret'); -- run rm -rf /\nCREATE TABLE t(s TEXT DEFAULT 'password-secret');"
        r = self.report(sql)
        output = json.dumps(r, ensure_ascii=False) + render_markdown(r)
        self.assertNotIn('customer-secret', output)
        self.assertNotIn('password-secret', output)
        self.assertNotIn('rm -rf', output)
        self.assertTrue(any(f['rule_id'] == 'INPUT-003' for f in r['findings']))

    def test_report_is_deterministic_and_has_evidence(self):
        sql = '\nCREATE TABLE t(id INT AUTO_INCREMENT);'
        a, b = self.report(sql), self.report(sql)
        self.assertEqual(a, b)
        f = a['findings'][0]
        for field in ['rule_id', 'object', 'location', 'evidence', 'severity', 'certainty', 'impact', 'recommendation', 'source_urls']:
            self.assertIn(field, f)
        self.assertTrue(f['source_urls'])
        md = render_markdown(a)
        self.assertIn('AUTO-001', md)
        self.assertIn('schema.sql:2', md)

    def test_comment_only_dump_is_incomplete(self):
        r = self.report('-- empty dump\n/* no objects */')
        self.assertFalse(r['summary']['complete'])

    def test_unknown_column_index_and_table_syntax_is_not_passed(self):
        for sql in [
            'CREATE TABLE t(id INT INVISIBLE);',
            'CREATE TABLE t(id INT, KEY k(id) INVISIBLE);',
            'CREATE TABLE t(id INT) COMPRESSION="zlib";',
            'CREATE TABLE t(id INT CHECK);',
            'CREATE TABLE t(id INT DEFAULT);',
            'CREATE TABLE t(id INT) PARTITION BY madeup(id);',
        ]:
            with self.subTest(sql=sql):
                self.assertFalse(self.report(sql)['summary']['complete'])

    def test_parenthesized_default_expressions(self):
        f = self.findings('CREATE TABLE t(a INT DEFAULT (mystery(1)));', 'EXPR-001')
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]['certainty'], 'needs-confirmation')

    def test_check_known_enforcement_mismatch(self):
        target = dict(product='self-managed', version='8.5', settings={'tidb_enable_check_constraint': False})
        f = self.findings('CREATE TABLE t(id INT CHECK(id > 0));', 'CHECK-001', target=target)[0]
        self.assertEqual((f['severity'], f['certainty']), ('high', 'confirmed'))

    def test_future_comment_multiple_statements_stay_conditional(self):
        r = self.report('/*!99999 CREATE PROCEDURE p() SELECT 1; CREATE PROCEDURE q() SELECT 2; */')
        fs = [f for f in r['findings'] if f['rule_id'] == 'OBJ-001']
        self.assertEqual(len(fs), 2)
        self.assertTrue(all(f['certainty'] == 'needs-confirmation' for f in fs))
        self.assertFalse(r['summary']['complete'])

    def test_unordered_cross_file_alter_has_no_confirmed_baseline(self):
        r = analyze({'a.sql': 'CREATE TABLE t(id INT);', 'b.sql': 'ALTER TABLE t MODIFY id INT AUTO_INCREMENT;'}, source_version='8.0.36')
        fs = [f for f in r['findings'] if f['rule_id'] == 'AUTO-002']
        self.assertEqual(fs[0]['certainty'], 'needs-confirmation')

    def test_qualified_identifier_with_embedded_dot(self):
        r = self.report('CREATE TABLE `a.b`.c(id INT); CREATE TABLE a.`b.c`(id INT);')
        self.assertEqual(r['summary']['tables'], 2)

    def test_unknown_alter_invalidates_later_fk_conclusion(self):
        sql = 'CREATE TABLE p(id INT PRIMARY KEY); ALTER TABLE p DROP PRIMARY KEY; CREATE TABLE c(id INT, FOREIGN KEY(id) REFERENCES p(id));'
        f = self.findings(sql, 'FK-001')[0]
        self.assertEqual(f['certainty'], 'needs-confirmation')

    def test_cross_schema_table_fk_has_correct_database(self):
        sql = 'USE a; CREATE TABLE b.p(id INT PRIMARY KEY); CREATE TABLE b.c(id INT, FOREIGN KEY(id) REFERENCES p(id));'
        self.assertFalse(self.findings(sql, 'FK-001'))

    def test_cloud_cannot_claim_partial_profile_support(self):
        sql = 'CREATE TABLE t(body TEXT, FULLTEXT KEY ft(body));'
        f = self.findings(sql, 'IDX-001', target={'product': 'cloud', 'capabilities': {'fulltext': True}})
        self.assertTrue(f)

    def test_conditional_set_does_not_silently_change_lexical_mode(self):
        sql = '/*!99999 SET SQL_MODE=\'ANSI_QUOTES\' */; CREATE TABLE "t"(id INT);'
        self.assertTrue(self.findings(sql, 'INPUT-003'))

    def test_supported_temporal_defaults_and_named_constraints(self):
        sql = "CREATE TABLE t(id INT, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, CONSTRAINT positive CHECK(id > 0), UNIQUE KEY uk(id));"
        self.assertFalse(self.findings(sql, 'INPUT-003'))

    def test_source_header_in_routine_string_is_not_version_evidence(self):
        sql = "CREATE PROCEDURE p() SELECT '\n-- Server version 5.7.44\n';"
        r = self.report(sql, source_version=None)
        self.assertIsNone(r['source']['version'])

    def test_trigger_report_contains_trigger_table_and_event(self):
        f = self.findings('CREATE TRIGGER tr AFTER INSERT ON orders FOR EACH ROW SET @x=1;', 'OBJ-002')[0]
        self.assertIn('orders', f['impact'])
        self.assertIn('INSERT', f['impact'])

    def test_generated_and_default_expression_contexts(self):
        for sql in ['CREATE TABLE t(n INT DEFAULT (1+1));', 'CREATE TABLE t(n INT DEFAULT (ABS(1)));', 'CREATE TABLE t(n INT, m INT AS (NULLIF(n,0)));']:
            with self.subTest(sql=sql):
                self.assertTrue(self.findings(sql, 'EXPR-001'))

    def test_self_reference_does_not_ban_tree_relationship(self):
        valid = 'CREATE TABLE t(id INT PRIMARY KEY, parent INT, FOREIGN KEY(parent) REFERENCES t(id));'
        invalid = 'CREATE TABLE t(id INT PRIMARY KEY, FOREIGN KEY(id) REFERENCES t(id));'
        self.assertFalse(self.findings(valid, 'FK-001'))
        self.assertTrue(self.findings(invalid, 'FK-001'))

    def test_stored_generated_foreign_key_cascade(self):
        sql = 'CREATE TABLE p(id INT PRIMARY KEY); CREATE TABLE c(a INT, b INT AS (a+1) STORED, FOREIGN KEY(b) REFERENCES p(id) ON DELETE CASCADE);'
        self.assertTrue(self.findings(sql, 'FK-001'))

    def test_explicit_btree_prefix_and_unknown_index_method(self):
        sql = 'CREATE TABLE t(n INT, KEY k USING BTREE(n));'
        self.assertFalse(self.findings(sql, 'INPUT-003'))
        self.assertTrue(self.findings(sql.replace('BTREE', 'HASH'), 'INPUT-003'))

    def test_limit_counts_implicit_child_fk_indexes(self):
        sql = 'CREATE TABLE p(id INT PRIMARY KEY); CREATE TABLE c(a INT,b INT, FOREIGN KEY(a) REFERENCES p(id), FOREIGN KEY(b) REFERENCES p(id));'
        target = {'product': 'self-managed', 'version': '8.5', 'settings': {'index-limit': 1}}
        self.assertTrue(self.findings(sql, 'LIMIT-001', target=target))

    def test_drop_and_recreate_duplicate_order_is_not_guessed(self):
        sources = {'a.sql': 'CREATE TABLE p(id INT PRIMARY KEY);', 'b.sql': 'CREATE TABLE p(id INT);', 'c.sql': 'CREATE TABLE c(id INT, FOREIGN KEY(id) REFERENCES p(id));'}
        r = analyze(sources, source_version='8.0.36')
        fs = [f for f in r['findings'] if f['rule_id'] == 'FK-001']
        self.assertTrue(fs)
        self.assertTrue(all(f['certainty'] == 'needs-confirmation' for f in fs))

    def test_cli_report_does_not_execute_client_source_directive(self):
        self.assertTrue(self.findings('SOURCE /tmp/private.sql;', 'INPUT-003'))

    def test_no_false_cloud_object_support_for_unrecognized_product(self):
        with self.assertRaises(ValueError):
            self.report('CREATE TABLE t(id INT);', target={'product': 'other'})

    def test_inline_key_is_a_parent_index(self):
        sql = 'CREATE TABLE p(id INT KEY); CREATE TABLE c(id INT, FOREIGN KEY(id) REFERENCES p(id));'
        self.assertFalse(self.findings(sql, 'FK-001'))

    def test_unqualified_cross_file_parent_is_not_assumed_same_database(self):
        r = analyze({'a.sql': 'CREATE TABLE p(id INT PRIMARY KEY);', 'b.sql': 'CREATE TABLE c(id INT, FOREIGN KEY(id) REFERENCES p(id));'}, source_version='8.0.36')
        fs = [f for f in r['findings'] if f['rule_id'] == 'FK-001']
        self.assertTrue(fs)
        self.assertEqual(fs[0]['certainty'], 'needs-confirmation')

    def test_session_sql_mode_is_known_wrapper(self):
        r = self.report('SET SESSION SQL_MODE=\'ANSI_QUOTES\'; CREATE TABLE "t"(id INT);')
        self.assertFalse(any(f['certainty'] == 'not-assessed' for f in r['findings']))

    def test_routine_and_table_same_name_remain_distinct(self):
        r = self.report('CREATE TABLE p(id INT); CREATE PROCEDURE p() SELECT 1;')
        self.assertEqual(r['summary']['objects'], 2)
        self.assertEqual(r['summary']['tables'], 1)

    def test_reordered_directory_inputs_have_stable_output(self):
        a = {'z.sql': 'CREATE TABLE z(id INT);', 'a.sql': 'CREATE TABLE a(id INT);'}
        b = dict(reversed(list(a.items())))
        self.assertEqual(analyze(a, source_version='8.0.36'), analyze(b, source_version='8.0.36'))

    def test_set_function_is_not_a_known_dump_wrapper(self):
        sql = "SET @x=EXTRACTVALUE('<a/>', '/a');"
        fs = self.findings(sql, 'CONTEXT-002')
        self.assertTrue(fs)
        self.assertEqual(fs[0]['certainty'], 'not-assessed')

    def test_markdown_shows_blockers_before_advice(self):
        report = self.report('CREATE TABLE t(id INT AUTO_INCREMENT);\nCREATE TRIGGER tr AFTER INSERT ON t FOR EACH ROW SET @x=1;')
        md = render_markdown(report)
        self.assertLess(md.index('### OBJ-002'), md.index('### AUTO-001'))

    def test_reports_use_english(self):
        report = self.report('CREATE TABLE t(id INT AUTO_INCREMENT); CREATE PROCEDURE p() SELECT 1;')
        md = render_markdown(report)
        self.assertIn('## Findings', md)
        self.assertIn('Evidence:', md)
        self.assertIn('Recommendation:', md)
        self.assertNotRegex(md + json.dumps(report, ensure_ascii=False), r'[\u3400-\u9fff]')

    def test_parser_diagnostics_use_english(self):
        for sql in ['CREATE TABLE t(id INT', "CREATE TABLE t(s TEXT DEFAULT 'unfinished", 'CREATE TABLE t(id UNKNOWN_TYPE);']:
            with self.subTest(sql=sql):
                report = self.report(sql)
                self.assertTrue(any(f['rule_id'] == 'INPUT-003' for f in report['findings']))
                self.assertNotRegex(json.dumps(report, ensure_ascii=False), r'[\u3400-\u9fff]')

    def test_english_messages_preserve_original_object_names(self):
        name = '\u8ba2\u5355'
        finding = self.findings(f'CREATE TABLE `{name}`(id INT AUTO_INCREMENT);', 'AUTO-001')[0]
        self.assertEqual(finding['object'], '?.' + name + '.id')
        for field in ['title', 'impact', 'recommendation']:
            self.assertNotRegex(finding[field], r'[\u3400-\u9fff]')


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/check_ddl.py'), *map(str, args)], capture_output=True, text=True)

    def test_cli_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'schema.sql'
            path.write_text('CREATE PROCEDURE p() SELECT 1;')
            result = self.run_cli(path, '--source-version', '8.0.36', '--format', 'json')
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertTrue(any(f['rule_id'] == 'OBJ-001' for f in json.loads(result.stdout)['findings']))
            self.assertIn('OBJ-001', self.run_cli(path).stdout)

    def test_cli_invalid_encoding_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.sql'
            path.write_bytes(b'\xff\xfe\x80')
            result = self.run_cli(path, '--format', 'json')
            self.assertEqual(result.returncode, 2)
            self.assertTrue(any(f['rule_id'] == 'INPUT-003' for f in json.loads(result.stdout)['findings']))
            self.assertEqual(self.run_cli(path.with_name('missing.sql')).returncode, 2)

    def test_cli_empty_directory_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.run_cli(directory).returncode, 2)

    def test_cli_errors_use_english(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli(directory)
            self.assertEqual(result.returncode, 2)
            self.assertIn('Input error:', result.stderr)
            self.assertNotRegex(result.stderr, r'[\u3400-\u9fff]')

    def test_cli_does_not_overwrite_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'schema.sql'
            sql = 'CREATE TABLE t(id INT);'
            path.write_text(sql)
            result = self.run_cli(path, '--output', path)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_text(), sql)

    def test_cli_target_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'schema.sql'
            profile = Path(directory) / 'target.json'
            path.write_text('CREATE TABLE t(id INT);')
            profile.write_text(json.dumps({'product': 'self-managed', 'version': '8.5.3'}))
            result = self.run_cli(path, '--target-config', profile, '--source-version', '8.4.0', '--export-scope', 'routines,events,triggers', '--format', 'json')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['target']['version'], '8.5.3')
            profile.write_text('{"product":"self-managed","settings":{"max-index-length":true}}')
            self.assertEqual(self.run_cli(path, '--target-config', profile).returncode, 2)


class DumpFixtureTests(unittest.TestCase):
    def test_versioned_dumps(self):
        expectations = {
            'mysql57.sql': ('5.7.44', {'OBJ-002', 'AUTO-001'}),
            'mysql80.sql': ('8.0.36', {'IDX-001', 'CHECK-001'}),
            'mysql84.sql': ('8.4.0', {'VIEW-001', 'CONTEXT-001'}),
        }
        for filename, (version, required) in expectations.items():
            with self.subTest(filename=filename):
                report = analyze({filename: (ROOT / 'tests/fixtures' / filename).read_text()}, export_scope=['routines', 'events', 'triggers'])
                self.assertEqual(report['source']['version'], version)
                ids = {f['rule_id'] for f in report['findings']}
                self.assertTrue(required.issubset(ids), ids)
                self.assertNotIn('INPUT-003', ids)
                self.assertNotIn('FK-001', ids)
                self.assertNotIn('order;created', json.dumps(report))

    def test_full_cli_report_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.md'
            run = subprocess.run([sys.executable, str(ROOT / 'scripts/check_ddl.py'),
                                  str(ROOT / 'tests/fixtures/mysql57.sql'), '--export-scope', 'routines,events,triggers',
                                  '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 1, run.stderr)
            self.assertEqual(run.stdout, '')
            report = output.read_text()
            self.assertIn('OBJ-002', report)
            self.assertIn('shop.orders', report)
            self.assertNotIn('order;created', report)


if __name__ == '__main__':
    unittest.main()
