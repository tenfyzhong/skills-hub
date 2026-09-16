import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_ddl import analyze, render_markdown


class LanguageTests(unittest.TestCase):
    def test_localized_reports_preserve_machine_fields_and_evidence(self):
        sql = 'CREATE PROCEDURE `unknown` () SELECT 1; CREATE TABLE t (id INT AUTO_INCREMENT PRIMARY KEY);'
        source = {'unknown.sql': sql}
        english = analyze(source, language='en')
        expected = {'zh': ('存储过程或存储函数', '建议：'), 'ja': ('ストアドプロシージャまたはストアド関数', '推奨対応：')}
        for language, (title, label) in expected.items():
            with self.subTest(language=language):
                report = analyze(source, language=language)
                self.assertEqual(report['language'], language)
                for key in ('summary', 'coverage', 'source', 'target', 'inventory', 'files'):
                    self.assertEqual(report[key], english[key])
                for actual, original in zip(report['findings'], english['findings']):
                    for key in ('rule_id', 'object', 'location', 'evidence', 'severity', 'certainty', 'source_urls'):
                        self.assertEqual(actual[key], original[key])
                    for key in ('title', 'impact', 'recommendation'):
                        self.assertNotEqual(actual[key], original[key])
                self.assertIn(title, render_markdown(report))
                self.assertIn(label, render_markdown(report))
                self.assertIn('unknown.sql', render_markdown(report))
                self.assertNotEqual(report['limitations'], english['limitations'])

    def test_default_language_is_english(self):
        self.assertEqual(analyze({}), analyze({}, language='en'))

    def test_invalid_language_is_rejected(self):
        with self.assertRaises(ValueError):
            analyze({}, language='fr')

    def test_parser_diagnostics_and_dynamic_values_are_localized(self):
        for language, expected in [('zh', '括号未闭合'), ('ja', '閉じ括弧がありません')]:
            report = analyze({'schema.sql': 'CREATE TABLE t (id INT;'}, language=language)
            self.assertTrue(any(expected in f['impact'] for f in report['findings']))
            report = analyze({'schema.sql': 'CREATE TABLE t (id INT AS (`unknown`(1)));'}, language=language)
            finding = next(f for f in report['findings'] if f['rule_id'] == 'EXPR-001')
            self.assertIn('UNKNOWN', finding['impact'])
            self.assertNotIn('outside the verified', finding['impact'])

    def test_composed_and_parameterized_findings(self):
        cases = [
            ('CREATE TABLE p(id INT); CREATE TABLE c(id BIGINT, FOREIGN KEY(id) REFERENCES p(id));',
             {}, 'FK-001', ('父子列', '参照元と参照先'), ('might also apply',)),
            ('CREATE TRIGGER tr AFTER INSERT ON `unknown` FOR EACH ROW SET @x=1;',
             {}, 'OBJ-002', ('触发条件', 'トリガー条件'), ('Trigger condition',)),
            ('CREATE TABLE t(a INT, b INT);',
             {'target': {'product': 'self-managed', 'version': '8.5', 'settings': {'table-column-count-limit': 1}}},
             'LIMIT-001', ('列数=2', '列数=2'), ('target limit',)),
            ('/*!80099 CREATE PROCEDURE p() SELECT 1 */;',
             {'source_version': '8.0.36'}, 'OBJ-001', ('版本条件', 'バージョン条件'), ('needs verification',)),
            ('CREATE TABLE t(id INT CHECK(id > 0));',
             {'source_version': '5.7.44'}, 'CHECK-001', ('早于 8.0.16', '8.0.16 より前'), ('source predates',)),
        ]
        for sql, options, rule, expected, absent in cases:
            for language, text in zip(('zh', 'ja'), expected):
                with self.subTest(rule=rule, language=language):
                    report = analyze({'schema.sql': sql}, language=language, **options)
                    finding = next(f for f in report['findings'] if f['rule_id'] == rule)
                    self.assertIn(text, finding['impact'])
                    for fragment in absent:
                        self.assertNotIn(fragment, finding['impact'])
                    if rule == 'OBJ-002':
                        self.assertIn('?.unknown', finding['impact'])
                        self.assertIn('AFTER INSERT', finding['impact'])

    def test_all_rule_titles_and_advice_have_translations(self):
        from check_ddl import RULES
        from i18n import render
        for rule, (title, advice, _) in RULES.items():
            for language in ('zh', 'ja'):
                with self.subTest(rule=rule, language=language):
                    for value in (title, advice):
                        self.assertNotEqual(render(value, language), str(value))
                        self.assertRegex(render(value, language), r'[\u3040-\u9fff]')

    def test_catalog_placeholders_match_and_user_values_are_literal(self):
        from string import Formatter
        from i18n import CATALOG, message
        formatter = Formatter()
        fields = lambda value: sorted(field for _, field, _, _ in formatter.parse(value) if field is not None)
        for template, translations in CATALOG.items():
            self.assertEqual(set(translations), {'zh', 'ja'})
            for translated in translations.values():
                self.assertEqual(fields(template), fields(translated), template)
        for language in ('zh', 'ja'):
            # Values that look like catalog keys or format fields must remain literal.
            value = 'Unclosed parenthesis {0} unknown'
            rendered = message('Function {0} is outside the verified function subset.', value).render(language)
            self.assertIn(value, rendered)

    def test_language_selection_does_not_leak_between_reports(self):
        source = {'schema.sql': 'CREATE PROCEDURE p() SELECT 1;'}
        before = analyze(source)
        for language in ('zh', 'ja'):
            analyze(source, language=language)
        self.assertEqual(analyze(source), before)

    def test_localized_success_empty_and_unreadable_reports(self):
        import tempfile
        for language, empty_text in [('zh', '未发现阻断项'), ('ja', '問題は見つかりませんでした')]:
            report = analyze({'schema.sql': 'CREATE TABLE t(id INT);'}, source_version='8.0.36',
                             export_scope=['routines', 'events', 'triggers'], language=language)
            self.assertTrue(report['summary']['complete'])
            self.assertIn(empty_text, render_markdown(report))
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'input.sql'
                for contents, status in [('CREATE TABLE t(id INT);', 0), ('', 2)]:
                    path.write_text(contents)
                    result = subprocess.run([sys.executable, str(ROOT / 'scripts/check_ddl.py'), str(path),
                                             '--language', language, '--source-version', '8.0.36',
                                             '--export-scope', 'routines,events,triggers', '--format', 'json'],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, status, result.stderr)
                    self.assertEqual(json.loads(result.stdout)['language'], language)
                path.write_bytes(b'\xff')
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/check_ddl.py'), str(path),
                                         '--language', language, '--format', 'json'], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                report = json.loads(result.stdout)
                for finding in report['findings']:
                    self.assertRegex(finding['impact'], r'[\u3040-\u9fff]')

    def test_unexpected_parser_errors_are_localized(self):
        for language, expected in [('zh', 'DDL 结构不完整'), ('ja', 'DDL 構造が不完全')]:
            with patch('check_ddl.Assessment.statement', side_effect=IndexError('list index out of range')):
                report = analyze({'schema.sql': 'CREATE TABLE t(id INT);'}, language=language)
            gaps = [f for f in report['findings'] if f['rule_id'] == 'INPUT-003']
            self.assertTrue(gaps)
            self.assertIn(expected, gaps[0]['impact'])

    def test_cli_language_and_exit_codes(self):
        fixture = ROOT / 'tests/fixtures/mysql57.sql'
        for language in ('en', 'zh', 'ja'):
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/check_ddl.py'), str(fixture),
                                     '--language', language, '--format', 'json'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(json.loads(result.stdout)['language'], language)
            markdown = subprocess.run([sys.executable, str(ROOT / 'scripts/check_ddl.py'), str(fixture),
                                       '--language', language], capture_output=True, text=True)
            self.assertEqual(markdown.returncode, 1, markdown.stderr)
            self.assertIn({'en': 'Recommendation:', 'zh': '建议：', 'ja': '推奨対応：'}[language], markdown.stdout)
        invalid = subprocess.run([sys.executable, str(ROOT / 'scripts/check_ddl.py'), str(fixture),
                                  '--language', 'fr'], capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2)


if __name__ == '__main__':
    unittest.main()
