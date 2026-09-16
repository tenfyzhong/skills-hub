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
  "plan": "starter"
}
```

Add `version` when the service version is known. Do not invent values to suppress findings. Collect the plan; do not request a cloud provider or region. Omitting either or both is valid and does not produce INPUT-005. Use the minimum capability set across providers and regions for that plan: known incompatibility in any applicable provider or region means incompatible under this policy, not merely unknown. Supplying only `product: cloud` still enables common object checks and produces INPUT-005.

The 2026-09-16 documentation snapshot limits Starter FULLTEXT to selected regions; Essential and Dedicated list it as unavailable, and Premium as under development. With either provider or region omitted, the checker therefore reports IDX-001 as high/confirmed for these four plans, explaining the minimum capability assumption across providers and regions. It does so even when `fulltext: true` is supplied without both provider and region. Unknown plans retain uncertainty; absence of evidence alone does not establish incompatibility. FULLTEXT is currently the only automated capability with a default across providers and regions. Apply the same policy to documented provider or regional differences identified during manual review.

If the customer voluntarily supplies both provider and region and explicitly wants a deployment-specific assessment, include verified capability evidence as follows:

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

`fulltext: true` suppresses only the missing-or-unknown-capability finding. It does not prove equivalent tokenization, query results, or MySQL full-text semantics. For an explicit deployment-specific assessment, false means unsupported and omission means unknown; true requires plan, provider, and region. A region alone does not establish feature support. With either provider or region omitted, the minimum capability policy takes precedence for known plans. The report preserves the complete target configuration for review.

Check the [Cloud feature matrix](https://docs.pingcap.com/tidbcloud/features/), [Cloud compatibility documentation](https://docs.pingcap.com/tidbcloud/mysql-compatibility/), and [full-text availability](https://docs.pingcap.com/ai/vector-search-full-text-search-sql/). The script does not access the network. Its conservative defaults are a dated snapshot; verify these sources when using the skill and update the snapshot and tests when availability changes. Other version-dependent Cloud rules generally require confirmation. Common unsupported-object findings use the documented snapshot; verify current sources before delivering an assessment.

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
