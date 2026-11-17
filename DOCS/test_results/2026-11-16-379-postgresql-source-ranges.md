---
title: "#379 PostgreSQL stored-source range assessment"
date: 2026-11-16
type: test-result
status: complete
summary: "Read-only Linux PostgreSQL measurements support bounded source access at observed sizes, with explicit scan-work limits. No source exceeded 604 KiB; cold-cache and backend peak-memory claims remain unverified. No endpoints implemented."
tags: [ag0, postgres, source-navigation, performance, issue-379]
related:
  - "[Issue #379](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/379)"
  - "[Frozen protocol](/DOCS/evaluations/2026-11-16-379-source-range-protocol.md)"
  - "[ADR-055 supplement](/DOCS/adr/ADR-055-source-navigation-supplement.md)"
  - "[Implementation contract](/DOCS/proposals/2026-11-16-ag0-source-navigation-issue.md)"
  - "[Raw evidence index](/DOCS/test_results/raw-index.json)"
---

# #379 PostgreSQL stored-source range assessment

**Recommendation: proceed toward implementation with an explicit scan-work
budget added to the read contract.** Keep response limits and the five-second
logical-read deadline; do not restore a blanket 4 MiB artifact cap. Bounded
responses do not imply bounded database materialization or constant-time line
lookup. Multi-megabyte sources remain unmeasured because none exist in the
available code-file module corpus. This report does not authorize endpoint work.

## Environment and provenance

Owner-authorized direct read-only connection from Windows to the actual Linux
database; no production fixtures, data writes, DDL, restarts, cache eviction or
deployment. The timed run occurred 2026-11-17 04:08:34–04:08:51 UTC
(2026-11-16 evening in America/New_York).

| Item | Recorded value |
| --- | --- |
| Database | PostgreSQL 15.15, Debian build, x86_64 Linux |
| Encoding / default compression | UTF8 / pglz |
| Shared buffers / I/O timing | 128 MB / `track_io_timing=off` |
| Transaction | Verified `read_only=on`, repeatable read |
| Timeouts | Statement 5 s; lock 1 s; idle transaction 30 s |
| Client | Windows, Python 3.12.0; psycopg version in raw capture |
| Local checkout | `87379aa05c5f74d94eff63f050549608fa97fd7d` plus the uncommitted diagnostic |
| GitHub main, separately observed | `cd52434e153905067bf0f01edd87c32e740484bc` |
| Ingestion and orchestrator `/version` | Both report `9f039c43604b2e96a6f96351e00afa178c9c81f8`, release `prod-2026-11-13-806am` |

Runtime SHAs are self-reported, not independent image attestation. No parity
between local, main and deployed code/configuration is assumed. Each sampled
file's actual ingestion generation and source commit are retained in the raw
capture. All six owners remained unchanged in a fresh snapshot after their run.

## Corpus and methodology

Inventory found **5,640** eligible code-file module records in ready single-owner
repositories: 4,449 pglz-compressed and 1,191 without compression. The largest
decoded source was **618,498 bytes (604.0 KiB)**; **zero exceeded 4 MiB**.
These counts describe persisted eligible modules, not every file on disk.

The [protocol](/DOCS/evaluations/2026-11-16-379-source-range-protocol.md) fixed
automatic selection after metadata inspection and before timed queries:
largest source, nearest 8 KiB and 64 KiB, largest uncompressed source, and all
`codebase_utils.py` module matches. Six files were selected. No artificial data
was inserted to satisfy a size target.

For each, select early/middle/late ranges of up to 100 lines and compare:

- **Known-offset substring:** exact `substring(text FROM offset FOR count)`,
  using offsets derived from a full-text oracle. This does not solve line lookup.
- **Window scan:** 32,768-character SQL substrings from the beginning, locating LF
  boundaries in the client while retaining only requested characters.
- **Full SQL array:** construct all lines in SQL and return a slice. This is a
  rejected comparator, not the recommended implementation.
- **Full fetch:** transfer all source and split locally. This is also a rejected
  comparator and its Python allocation includes the whole line list.

Five repetitions per method/range yielded **360 logical measurements**. Every
returned range matched the stored-text oracle exactly. Query plans, timing,
buffer activity, transferred UTF-8 bytes and Python traced allocations were
captured. SELECT-only `EXPLAIN ANALYZE` actually executed these read queries.

The diagnostic runner is
[`source_range_assessment_379.py`](/scripts/source_range_assessment_379.py).
Reproduce using `.venv/Scripts/python.exe scripts/source_range_assessment_379.py
--existing-connection --out DOCS/test_results/_raw/379-repeat.json`, or supply a
DSN through an environment variable named by `--dsn-env`. Do not place a DSN,
address or password in evidence files. Live reruns warm caches and are separate
observations, not replacements for this recorded first access.

## Latency and transfer results

Median **client** times in milliseconds, including network/driver and Python
tracing overhead. This is a Windows-to-Linux diagnostic, not co-located service
latency or a load test.

| Source file / repository prefix | Decoded bytes | Lines | Compression | Window early | Window middle | Window late |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| `codebase_rag/parsers/call_processor.py` / `4a0af55f` | 618,498 | 13,800 | pglz | 16.69 | 291.25 | 589.27 |
| `tests/cli/check/test_check_group.py` / `15f342ab` | 8,190 | 209 | pglz | 9.83 | 15.36 | 12.59 |
| `codebase_rag/tests/test_java_nested_structures.py` / `4a0af55f` | 65,415 | 1,952 | pglz | 12.46 | 38.01 | 28.84 |
| `lightrag_webui/src/test/happydom.ts` / `4f76a36f` | 1,993 | 43 | none | 4.22 | 6.42 | 5.42 |
| `codebase_utils.py` / `a6e336ef` | 11,892 | 295 | pglz | 22.58 | 11.72 | 12.51 |
| `codebase_utils.py` / `f7641840` | 10,479 | 274 | pglz | 9.89 | 6.53 | 6.94 |

For the largest file, physically stored compressed text occupied 218,972 bytes.
The 100-line ranges show the cost of locating lines separately from their size:

| Range | Output bytes | Known-offset client ms | Window queries | Window transfer bytes | Window client ms | Full-array client ms | Full-fetch client ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Lines 1–100 | 3,457 | 6.51 | 1 | 32,768 | 16.69 | 16.73 | 194.65 |
| Lines 6,851–6,950 | 4,277 | 12.94 | 10 | 327,684 | 291.25 | 12.19 | 148.16 |
| Lines 13,701–13,800 | 4,589 | 15.38 | 19 | 618,498 | 589.27 | 19.69 | 135.72 |

The late scanner's five observed times ranged **398.74–647.02 ms**. It transferred
the entire file through bounded windows. Smaller requests therefore reduce
retained application data, but do not necessarily reduce total transfer or work.
The direct-offset comparison assumes information the present schema does not
store as a line index. A small full SQL line array was fast here, but its cost and
allocation scale with the whole source, so it does not satisfy the contract.

## Plans, cache and memory

Direct file lookups used `ix_repo_canonical`; the array comparator added a CTE
scan. For the largest file, one warm known-offset plan per range reported
**0.496 / 5.161 / 5.572 ms** server execution. Those plans touched
**10 / 39 / 39 shared-hit blocks** respectively. Target-window plans are individual
queries, not summed costs of the complete scanner.

Do not use the full-fetch EXPLAIN's approximately 0.04–0.13 ms executor time as
the cost of decoding/transmitting the file: a plain text-column projection can
pass a TOAST pointer through the executor, and this PostgreSQL EXPLAIN mode does
not serialize the result to the client. The full-fetch client measurements do
include actual retrieval and local splitting.

The largest file's first-observed window plan took **39.823 ms** and reported
27 shared reads and 25 shared hits. Every subsequently captured warm plan had
zero shared reads; no captured plan reported temporary reads/writes. This is
**not a cold/warm experiment**: shared-buffer misses can hit the OS cache, earlier
metadata inspection and other clients affect residency, and the correctness
oracle deliberately warms text. I/O timing was disabled. True cold-cache and
physical-disk latency remain unknown; production caches were not evicted.

For the largest file, peak **Python-traced** allocations were about **68–168 KB**
for window scanning, versus **3.89 MB** for full fetch plus splitting. These are
not RSS measurements and exclude native driver/libpq memory. Own-backend memory
contexts were readable: allocated totals went from 1,999,312 to 2,118,096 bytes,
and used totals from 1,238,376 to 1,328,048 bytes. These snapshots occur after
queries; they **do not measure transient detoast/executor peaks**. No server
peak-RSS or concurrent-load capacity claim follows from them.

## PostgreSQL implementation interpretation, not a measured peak

The matching [15.15 substring implementation](https://github.com/postgres/postgres/blob/REL_15_15/src/backend/utils/adt/varlena.c#L867-L992)
handles multibyte encodings by taking a prefix from byte zero, with a conservative
upper bound based on encoding width and the requested character end. It then
walks character boundaries to find the slice. For these UTF-8 middle/late offsets
that bound can exceed the file length, requiring the full decoded value even
though the returned substring is small.

The [15.15 detoast implementation](https://github.com/postgres/postgres/blob/REL_15_15/src/backend/access/common/detoast.c#L212-L278)
can fetch/decompress prefixes for pglz-compressed data; it also falls back to
full decompression when the prefix covers the logical value. Thus the correct
answer is **sometimes the entire value, sometimes a prefix**, not that every
substring always fully materializes source. Repeated windows can repeatedly
decode overlapping prefixes. This interpretation is from upstream code, not
instrumentation of Debian's allocator. See also the
[TOAST documentation](https://www.postgresql.org/docs/15/storage-toast.html) and
[memory-context view limitations](https://www.postgresql.org/docs/15/view-pg-backend-memory-contexts.html).

## Confirmed motivating case

For repository `f7641840-ba13-5f9d-9ae6-87e1f924709d`, ready ingestion
`8cbedbb9-9ad6-4c63-83f7-2b7d7659f7e5`, the persisted module
`rag_orchestrator/src/retrieval/codebase_utils.py` has **10,479 UTF-8 bytes,
274 lines and 13 Python function definitions**. All three range positions matched
the complete stored text. Its SHA-256 is
`f1a037bab5dee68db183b8c9b64ea6e434194ed13a5b6e79719b0f2bc8877bf1`.
That hash matches the decoded/newline-normalized Git object at its recorded
source commit `9f039c43604b2e96a6f96351e00afa178c9c81f8`.

This independently verifies complete source retention for the user's example.
It does not reconstruct the earlier query trace or prove its precise loss stage.
The same path in repository `a6e336ef` has different source/generation/length;
this reinforces the need for explicit repository and generation addressing.

## Recommended contract adjustment and remaining limits

Propose adding **`SCAN_LIMIT_EXCEEDED` (`413`)** with documented budgets for
cumulative scanned UTF-8 text and number of database windows. Starting values:
**1 MiB cumulative text transfer, 32 windows of at most 32,768 characters,
and a five-second deadline for the entire logical read**, with remaining time
propagated into each SQL statement. These are conservative policy proposals,
not demonstrated maximum safe capacity. Enforce the byte budget before returning
each window from SQL where practical; character count alone is not a UTF-8 byte
bound. No response succeeds partially when a budget is exceeded.

Keep the proposed **500 returned lines, 128 KiB returned UTF-8 text and 256 KiB
serialized-response limit** as initial policy values. This run measured 100-line
ranges; it does not validate all 500-line, escaping-expansion, timeout or giant-line
API cases. Those remain implementation contract tests. Prefer bounded discovery
and scanning over whole-file arrays or fetching full text merely to compute
range metadata. Whole-file hash/line count may remain null on range responses.

Do not add a blanket file-size rejection: large files can have readable early
ranges. A late range beyond the scan budget may fail explicitly; there is no
promise of cheap random line access for arbitrary-size sources. If unrestricted
late reads are required, return that requirement for separate design review.

The **above-4-MiB acceptance criterion is unfulfilled**, not passed or waived.
Validate it later using an isolated local PostgreSQL fixture with explicit
authorization, or a genuine persisted source when one is available. Cold-cache,
backend peak memory, co-located latency, concurrency/load and fault handling
also remain unmeasured. The supported evidence is practicality at current corpus
sizes with bounded work, not an unlimited large-source performance guarantee.

## Evidence and checks

Raw captures are registered in the [raw index](/DOCS/test_results/raw-index.json):
`2026-11-16-379-source-ranges.json` (measurements/plans) and
`2026-11-16-379-provenance.json` (Git comparison and runner/protocol hashes).
No source bodies, credentials or private endpoint addresses are captured.

Nine offline diagnostic tests passed; scoped Ruff and Pyright checks passed
(Pyright explicitly used the workspace Python environment). Type annotations
were tightened after the measurement without changing the query/scanner design;
both measured and final runner hashes are retained in provenance. Endpoint
tests were not run because no endpoints exist. Two inventory-probe setup errors
(UUID JSON serialization and unsupported `min(uuid)`) were fixed before the timed
run; no timed result was discarded or selected around a performance outcome.
