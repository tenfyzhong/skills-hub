# Rules and implemented coverage

Rule version: 1. Official sources checked on 2026-09-16. The self-managed baseline is TiDB 8.5; Cloud decisions use applicable product documentation and supplied capability evidence.

The checker combines a position-preserving lexer with a bounded structural parser. It does not implement the entire MySQL grammar. All 25 rule IDs have handling paths, but not every DDL form is automated. Unrecognized structures, unknown statements, and incomplete expressions produce coverage gaps or confirmation requests.

## Compatibility rules

| ID | Implemented detection | Decision and boundaries |
| --- | --- | --- |
| OBJ-001 | CREATE PROCEDURE and stored functions | Unsupported objects are blockers; definitions are identified without validating bodies or all callers |
| OBJ-002 | CREATE TRIGGER, owning table, timing, and event | Blocker; preserves object relationships for further body analysis by the Agent |
| OBJ-003 | CREATE EVENT | Blocker even when disabled; actual business impact is assessed separately |
| OBJ-004 | CREATE FUNCTION ... SONAME | Blocker; ordinary built-in functions and strings are not UDFs |
| IDX-001 | FULLTEXT inside CREATE TABLE | Capability difference for self-managed 8.5; Cloud defaults to minimum regional capabilities when region is omitted; Starter/Essential/Premium/Dedicated FULLTEXT is high/confirmed incompatible under that policy. Explicit regional exceptions require verified capability evidence |
| TYPE-001 | Spatial column types and SPATIAL indexes | Blocker for a known unsupported target; ignores keywords inside comments or identifiers |
| IDX-002 | DESC in index columns | Index implementation difference; does not establish incorrect query results |
| AUTO-001 | Auto-increment columns in CREATE TABLE | Informational confirmation request; existence is not a blocker and does not justify automatically switching to AUTO_RANDOM |
| AUTO-002 | MODIFY / CHANGE adding auto-increment to an existing column | Requires a confirmed preceding ordinary column; missing baselines require confirmation; changing the starting value does not match |
| FK-001 | Parent tables/indexes, types and signedness, character sets, column counts, partitioned/temporary tables, virtual columns, TEXT/BLOB, same-column self-references, stored generated column reference actions | Ordinary foreign keys pass; missing parents or incomplete structures require confirmation; some restrictions also apply to source MySQL |
| CHECK-001 | CHECK, NOT ENFORCED, source version, and target enablement | Compares enforcement conditions; unknown settings require confirmation; confirmed enforcement differences are high severity |
| CHECK-002 | Inline CHECK in ALTER ADD COLUMN / CHANGE | Reports ignored or unsupported forms and records that other ALTER semantics remain unassessed |
| CHAR-001 | Explicit or known inherited database/table/column character sets and collations | Supported names are not falsely rejected; unknown collations need verification; implicit defaults and latin1 data semantics produce advice |
| PART-001 | SUBPARTITION | Blocker for a known target; ordinary HASH/KEY/RANGE/LIST partitioning is not rejected merely for being present; full partition expressions are not validated |
| LIMIT-001 | Column/index/index-column/partition counts and byte lengths of common integer, character, and binary prefix indexes | Includes indexes required by foreign keys; unknown configurable limits are not definite blockers; exact lengths for DECIMAL, date types, and other uncovered types require confirmation |
| VIEW-001 | CREATE VIEW | Informational confirmation request; target views being non-writable does not establish that the application writes through them |
| ENGINE-001 | Non-InnoDB ENGINE options | Source engine behavior needs confirmation; accepted syntax does not establish preserved behavior |
| EXPR-001 | Function scanning in defaults, generated columns, CHECK, and views | Explicit rules for XML functions; unknown functions and expression defaults require confirmation; not a complete expression validator |
| CONTEXT-001 | View DEFINER / SQL SECURITY and view-dependency advice | DEFINER alone is not a blocker; privileges, cross-database objects, and full SELECT semantics need manual review |
| CONTEXT-002 | SET, SET NAMES, LOCK/UNLOCK, and other wrappers | Classifies common save/restore statements; uncovered SET/GTID forms remain unassessed; never executes or automatically removes them |

Target capability decisions must meet their version conditions. Unknown targets cannot produce confirmed blockers. Severity is blocker/high/medium/info; certainty is confirmed/needs-confirmation/not-assessed. These dimensions are independent.

## Input-integrity rules

| ID | Check |
| --- | --- |
| INPUT-001 | Unknown, conflicting, uncovered, or forked source server versions |
| INPUT-002 | Unconfirmed routines/events/triggers export completeness |
| INPUT-003 | Read/encoding failures, truncation, unknown statements/options, lexical ambiguity, uncovered ALTER, mixed-in DML, or empty input |
| INPUT-004 | Unknown execution order, effective character sets, duplicate definitions, or executable-comment conditions |
| INPUT-005 | Missing Cloud profile details or a self-managed target not explicitly identified as 8.5 |

Input gaps are counted separately from database incompatibilities. Missing definitions do not prove objects are absent from the source database.

## Parser boundaries

- Handles custom DELIMITER, single/double quotes, backticks, escapes, ordinary comments, and MySQL executable comments. Preserves line numbers and redacts string values in reports.
- Handles explicit-column CREATE TABLE, common column attributes, inline indexes/constraints, database defaults, USE, DROP TABLE/VIEW, view placeholder tables, and final view definitions.
- Does not cover CREATE TABLE LIKE/AS SELECT, standalone CREATE INDEX, general ALTER, every column/index/table option, complete partition syntax, or stored-program bodies. Uncovered input must not be assumed to pass.
- Recognizing part of a structure does not prove SQL validity. `checked` refers only to the implemented rule subset; gaps and report limitations still apply.
- A supported name does not establish equivalent comparisons on real data. Source export privileges and actual post-import constraint enforcement are not verified.
- Saved string-valued SQL modes can be restored; unknown restoration values are not guessed. Other session variables are classified without simulating server behavior.

## Report contract

JSON contains `schema_version`, `rules_version`, `language`, source-check date, source version evidence, target configuration, file inventory, counts, object inventory, rule coverage, and findings.

Each finding contains `rule_id`, `title`, `object`, `location.file/line_start/line_end`, redacted `evidence`, `severity`, `certainty`, `impact`, `recommendation`, and `source_urls`.

Coverage states are checked / not-applicable / needs-confirmation / not-assessed. Completeness describes assessment coverage, not business compatibility. Read high-severity and unconfirmed findings even when the exit code is 0.

JSON findings are ordered by file, location, object, and rule. Markdown presents higher-severity findings first and input gaps afterward. Output excludes the current run time. Both formats use the same assessment result. The CLI creates new report files without overwriting existing files.

## Official sources

The following sources support capability facts. Advice and remediation strategies describe the assessment method. Versioned links might redirect; verify the resolved documentation version rather than treating future stable changes as TiDB 8.5 behavior.

- [TiDB 8.5 MySQL compatibility](https://docs.pingcap.com/tidb/v8.5/mysql-compatibility/): objects, indexes, engines, and selected DDL differences.
- [TiDB Cloud MySQL compatibility](https://docs.pingcap.com/tidbcloud/mysql-compatibility/) and [Cloud features](https://docs.pingcap.com/tidbcloud/features/): product differences.
- [Full-text search with SQL](https://docs.pingcap.com/ai/vector-search-full-text-search-sql/): Cloud full-text prerequisites.
- [AUTO_INCREMENT](https://docs.pingcap.com/tidb/v8.5/auto-increment/): allocation behavior, compatibility mode, and ALTER restrictions.
- [Constraints](https://docs.pingcap.com/tidb/v8.5/constraints/) and [Foreign keys](https://docs.pingcap.com/tidb/v8.5/foreign-key/): CHECK and foreign-key restrictions.
- [MySQL CHECK constraints](https://dev.mysql.com/doc/refman/8.0/en/create-table-check-constraints.html): source-version enforcement differences.
- [Character sets and collations](https://docs.pingcap.com/tidb/v8.5/character-set-and-collation/): supported names, defaults, and encoding differences.
- [TiDB limitations](https://docs.pingcap.com/tidb/v8.5/tidb-limitations/): limits and configurable settings.
- [Views](https://docs.pingcap.com/tidb/v8.5/views/): view capabilities and privilege context.
- [Default values](https://docs.pingcap.com/tidb/v8.5/data-type-default-values/): type-specific expression-default support.
- [MySQL comments](https://dev.mysql.com/doc/refman/8.4/en/comments.html) and [Dumping stored programs](https://dev.mysql.com/doc/refman/8.4/en/mysqldump-stored-programs.html): executable comments and export completeness.

## Report languages

Use `--language en`, `--language zh`, or `--language ja` for English (default), Simplified Chinese, or Japanese. Both JSON prose and Markdown output use the selected language. Markdown also translates severity, certainty, and coverage display labels; their JSON enum values remain unchanged for automation. Source SQL, identifiers, paths, URLs, and target configuration are never translated. Changing the language does not change finding order, rule decisions, or exit codes.

The bundled `scripts/messages.json` catalog contains Chinese and Japanese translations keyed by English templates. Add translations and matching format placeholders for every new report message. Use deferred messages so parameter values remain literal. CLI help and argument/input error messages remain English; diagnostics inside assessment reports are localized.
