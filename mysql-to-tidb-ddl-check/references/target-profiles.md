# Target configuration and input evidence

The script runs entirely offline. Target JSON represents facts supplied by the user or verified during the current assessment, not connection details. Do not include credentials.

## TiDB 8.5

Minimal configuration:

```json
{
  "product": "self-managed",
  "version": "8.5.3"
}
```

Optional settings should be included only after verification. These values illustrate the fields; they do not describe the defaults of every cluster:

```json
{
  "product": "self-managed",
  "version": "8.5.3",
  "settings": {
    "tidb_enable_check_constraint": true,
    "new_collations_enabled_on_first_bootstrap": true,
    "max-index-length": 3072,
    "table-column-count-limit": 1017,
    "index-limit": 64
  }
}
```

Use JSON booleans, not ON/OFF strings. Limits must be positive integers. Unknown settings are rejected to avoid silently accepting misspelled configuration keys. When an actual configurable limit is unavailable, exceeding the documented default produces a confirmation request rather than a definite blocker.

The script defaults to self-managed TiDB 8.5. Other or unknown versions can be supplied, but version-dependent confirmed findings are downgraded to require confirmation.

## TiDB Cloud

```json
{
  "product": "cloud",
  "plan": "starter",
  "provider": "aws",
  "region": "us-west-2"
}
```

Add `version` when the service version is known. Do not invent values to suppress findings. Plan, provider, and region are all required for product-specific decisions. Supplying only `product: cloud` still enables common object checks and produces INPUT-005.

FULLTEXT availability depends on the plan, region, and current feature rollout. Include the following capability only after verifying the actual target:

```json
{
  "product": "cloud",
  "plan": "starter",
  "provider": "aws",
  "region": "us-west-2",
  "capabilities": {
    "fulltext": true
  }
}
```

`fulltext: true` suppresses only the missing-or-unknown-capability finding. It does not prove equivalent tokenization, query results, or MySQL full-text semantics. False means the target is confirmed not to support the capability; omission means unknown. Even with true, missing plan, provider, or region still requires confirmation. The report preserves the complete target configuration for review.

Check the [Cloud feature matrix](https://docs.pingcap.com/tidbcloud/features/), [Cloud compatibility documentation](https://docs.pingcap.com/tidbcloud/mysql-compatibility/), and [full-text availability](https://docs.pingcap.com/ai/vector-search-full-text-search-sql/). The script does not access the network or treat a rolling documentation snapshot as a permanent capability matrix. Other version-dependent Cloud rules generally require confirmation. Common unsupported-object findings use the documented snapshot; verify current sources before delivering an assessment.

## Source version and execution context

- `--source-version 5.7.44`, `8.0.36`, or `8.4.0` refers to the server version.
- Without an explicit version, only a leading `-- Server version ...` comment is recognized. Client Distrib versions and fake headers inside strings are ignored.
- Conflicting user and header versions, conflicting file headers, and forks such as MariaDB produce INPUT-001.
- Executable comments retain their conditions and original line numbers. Unknown source versions or conditions beyond the source version do not establish definite execution.
- Known `SET SQL_MODE` assignments and saved values affect subsequent lexical analysis. An unknown restored value combined with ambiguous quotes or escapes leaves the affected statement unassessed.
- Without an explicit SQL mode, the lexer starts with ordinary MySQL quoting rules. This does not prove that the actual import session uses those settings.

When export completeness has been confirmed:

```bash
python3 scripts/check_ddl.py schema.sql --export-scope routines,events,triggers
```

To declare an explicit execution order:

```bash
python3 scripts/check_ddl.py 01-schema.sql 02-tables.sql 03-alter.sql --ordered
```

Without `--ordered`, each file has independent USE, database-default, and SQL-mode context. Clearly identified parent tables can be linked across files, but another file's definition is not treated as a confirmed preceding ALTER baseline. Duplicate definitions, unknown ALTER operations, and conditional definitions are not confirmed foreign-key baselines.
