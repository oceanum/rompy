# Issue #2 Return-Schema Robustness Audit

**Audited repository:** `oceanum/rompy`
**Audited revision:** `dab2a1f6d5a81d3b2ec96850f6c3791602860094` (exact prerequisite `origin/return_schema` HEAD)
**Scope:** read-only contract and implementation audit for the return-schema change. No runtime source, tests, fixtures, dependencies, or plugins were changed by this audit.

## Executive verdict / Gate

**Gate: BLOCK.** The substantive audit is complete, but Gate 1 cannot pass yet. The current implementation has P1 contract defects, and compatibility/version policy (D1), artifact identity and expected/missing-output policy (D2), and persistence-failure behavior remain owner decisions. Core schema implementation and downstream plugin adaptation must remain blocked until the contract is frozen.

The audit examined discriminators, fields, timing, stage progression, cleanup, nested failures, partial evidence, direct Python, pipeline, CLI, and fresh-process contracts. Findings below are retained only where they have source evidence and a falsifiable test shape.

## Current strengths

- `PostprocessResult` and `PipelineResult` use true `success`-discriminated unions (`src/rompy/core/responses.py:232-269,398-401`).
- `ModelRun.run()` returns `ModelRunResult`, matching the execution plan's fixed rule (`src/rompy/model.py:533-746`).
- Runtime producers generally create UTC-aware timestamps.
- Sidecar filenames and loaders are centralized (`src/rompy/core/result_persistence.py:51-53,199-319`).
- Persistence uses a same-directory temporary file and `os.replace`, providing atomic reader visibility for successful writes (`src/rompy/core/result_persistence.py:64-88`).
- Loaders check sidecar kind and an explicit version allowlist.
- Run failures block postprocessing, and postprocess failures can preserve partial artifacts and diagnostics.
- The supplied baseline has substantial coverage: 111 tests pass.
- All audit reports attest that the working tree was unchanged against the reviewer-launch HEAD.

## Retained findings

### 1. P1 — Canonical models permit contradictory states

**Evidence**

- `ModelRunResult` and `GenerateResult` use unrestricted `success: bool` with optional `error` (`src/rompy/core/responses.py:443-457,492-507`).
- All three sidecars independently carry envelope `run_id`, `status`, `success`, and `error` alongside equivalent payload state without coherence validators (`src/rompy/core/responses.py:548-568,607-627,667-685`).
- Pipeline stage sequences have no schema validation (`src/rompy/core/responses.py:308-311,354-359`).
- The OpenSpec requires invalid discriminator combinations to be rejected (`openspec/changes/implement-return-schemas/specs/result-schemas/spec.md:45-65`).

**Impact:** A successful envelope can contain a failed payload, a different run ID, or an error; failures can omit errors; and pipelines can claim impossible completed/failed-stage combinations. Loaders accept these states silently.

**Smallest safe resolution:** After contract approval, introduce discriminated run/generate variants or shared validators covering success/error, envelope/payload identity, status, run ID, and canonical stage sequences.

**Test shape:** Parameterize success/failure payloads and mutate each discriminator, error, status, run ID, and stage sequence independently; assert `ValidationError` for every contradictory combination and successful round-trip for each canonical variant.

**Owner:** #4 (invariant implementation), with contract decisions in #3.

### 2. P1 — Timing is neither invariant nor losslessly round-trippable

**Evidence**

- `TimingInfo` accepts naïve, non-UTC, and reversed datetimes (`src/rompy/core/responses.py:164-194`).
- Timing remains optional on postprocess results and pipeline failures (`src/rompy/core/responses.py:228,261,375-377`).
- `duration_seconds` is a serialized computed field, but models forbid extra input; persistence works around this by deleting it (`src/rompy/core/result_persistence.py:91-116,134-192`).
- OpenSpec requires UTC timing, computed duration, and operation/stage/nested timing (`openspec/changes/implement-return-schemas/specs/timing-metadata/spec.md:3-45`).

**Impact:** Direct model dump/load can fail, negative durations validate, mixed aware/naïve timestamps can fail incidentally, and completed generate/run stage timing is lost from pipeline results.

**Smallest safe resolution:** Freeze one duration wire policy, validate UTC awareness and `end >= start`, require timing where the contract demands it, preserve stage timing, and remove persistence-only dictionary surgery.

**Test shape:** Reject naïve/non-UTC and reversed intervals; assert computed duration precision; run model→JSON→model and writer→loader round trips without removing fields; assert operation, stage, and nested timings survive.

**Owner:** #4.

### 3. P1 — Version compatibility is ambiguous and asymmetric

**Evidence**

- Generate/run loaders accept versions 1 and 2 through the same current models; postprocess accepts only version 1 (`src/rompy/core/result_persistence.py:223-239,264-279,305-319`).
- `normalized_context` is optional for both run versions, while CLI rejects missing context as “v1” (`src/rompy/cli.py:947-959`).
- Envelope and generate payload versions are independent.
- JSON `true` passes the current membership test as integer version 1.

**Impact:** Hybrid v1/v2 documents validate differently between library and CLI, and released or future documents have no explicit migration/rejection contract.

**Smallest safe resolution:** Decide D1, then use strict version types and version-specific models or migration readers. Reject unsupported or ambiguous payloads with actionable errors.

**Test shape:** Feed each sidecar loader versions 1, 2, unsupported integers, booleans, missing versions, and mixed envelope/payload versions; assert only approved migrations load and all other cases fail consistently in library and CLI.

**Owner:** #3.

### 4. P1 — Artifact identity and expected/missing-output evidence are undefined

**Evidence**

- `Artifact.path` accepts arbitrary absolute, relative, traversal, and URI-like strings (`src/rompy/core/responses.py:143-161`).
- Run normalization retains paths outside the output root (`src/rompy/model.py:632-649`).
- CLI interprets every artifact as a local path and drops it if it does not currently exist (`src/rompy/cli.py:61-85`).
- `validate_outputs()` returns discovered files while expected-but-missing outputs remain warnings rather than typed evidence (`src/rompy/core/config.py:69-154`).

**Impact:** `../` and external absolute paths can escape staging, URIs are misinterpreted, local and fresh-process inputs differ, and missing expected outputs disappear from durable evidence.

**Smallest safe resolution:** Approve D2: staging-relative local identities, separately typed remote URIs/external locations, observed artifacts in `artifacts`, and structured expected/missing validation evidence.

**Test shape:** Validate traversal, absolute, URI, missing, and outside-root artifact inputs; compare direct and fresh-process loads; assert observed, expected, and missing collections remain distinct and are not silently filtered by CLI.

**Owner:** #3 (identity contract), #4 (schema/validation implementation).

### 5. P1 — Processor handoffs differ across Python, pipeline, and CLI

**Evidence**

- Pipeline creates `run_result` but calls postprocessing without it (`src/rompy/pipeline/__init__.py:199-203,250-252`).
- `ModelRun.postprocess()` therefore defaults to the live `ModelRun` (`src/rompy/model.py:827-828`).
- CLI builds a mutated `SimpleNamespace`, rewrites `output_dir`, and filters artifacts (`src/rompy/cli.py:61-85`).
- Plugin returns are inspected through `.success`/`.error` before canonical validation (`src/rompy/model.py:827-845`).
- Processor construction uses a no-argument constructor plus flattened process kwargs (`src/rompy/model.py:811-828`).

**Impact:** A processor cannot rely on one input type or equivalent evidence across execution modes. Arbitrary duck-typed outputs fail incidentally, and fresh-process behavior differs from local behavior.

**Smallest safe resolution:** Pass the exact typed `ModelRunResult` in every path, validate output immediately through a `TypeAdapter(PostprocessResult)`, and freeze one processor construction/configuration protocol.

**Test shape:** Use a recording processor across direct Python, local pipeline, CLI, and fresh process; assert exact `ModelRunResult` type and semantic equality, then reject dict, `None`, malformed union, and arbitrary duck-typed returns before persistence.

**Owner:** #5.

### 6. P1 — Pipeline failure progression, evidence, cleanup, and path handling are inconsistent

**Evidence**

- `POSTPROCESS` is appended before checking for `PostprocessFailure` (`src/rompy/pipeline/__init__.py:250-261`).
- Run failures are replaced by generic `"Model run failed"` and lose nested error, timing, artifacts, and paths (`src/rompy/pipeline/__init__.py:199-221`).
- Returned/raised postprocess failures do not invoke cleanup (`src/rompy/pipeline/__init__.py:250-296`).
- Cleanup exceptions are swallowed while callers unconditionally set `cleaned_up=True` (`src/rompy/pipeline/__init__.py:203-230,319-357`).
- Pipeline paths always use `output_dir/run_id`, ignoring `run_id_subdir=False` (`src/rompy/pipeline/__init__.py:174-179,303-314,341-349`).

**Impact:** A stage can be both completed and failed; partial-run evidence is lost; cleanup can be falsely reported; and valid non-subdirectory runs can fail validation or clean the wrong location.

**Smallest safe resolution:** Append stages only after success, retain the failed run result or equivalent evidence, return explicit cleanup outcome/diagnostics, and use the actual generated staging path throughout.

**Test shape:** Inject failure at generate, run, and postprocess; assert completed stages are the strict prefix and failed stage is excluded, nested evidence is retained, cleanup success/failure is truthful, and `run_id_subdir=False` uses the actual path.

**Owner:** #5.

### 7. P1 — Persistence failures are hidden and successful writes are not crash-durable

**Evidence**

- Generate, run, and postprocess producers catch sidecar-write exceptions and continue; most paths do not log or attach diagnostics (`src/rompy/model.py:360-365,602-606,692-696,740-744,846-850,881-885`).
- CLI may exit successfully with `"Sidecar file not found"` (`src/rompy/cli.py:1077-1091`).
- `_atomic_write()` does not flush/fsync the file or parent directory (`src/rompy/core/result_persistence.py:64-88`).

**Impact:** An operation can report success while its canonical evidence was never persisted. A crash can lose content or rename durability despite successful return.

**Smallest safe resolution:** Approve one observable persistence-failure policy, preserve the primary operation error when both operation and persistence fail, and add file/directory fsync plus failure-injection tests if crash durability is required.

**Test shape:** Inject serialization, write, replace, file-sync, and directory-sync failures; assert the selected policy is observable, primary operation errors are retained with persistence diagnostics, and temporary files/previous valid bytes satisfy the promised atomicity level.

**Owner:** #4.

### 8. P2 — OpenSpec and migration documentation describe conflicting APIs

**Evidence**

- OpenSpec and `ModelRunResult` documentation refer to `run_detailed()` and boolean `run()` (`openspec/changes/implement-return-schemas/specs/result-schemas/spec.md:41-53`; `src/rompy/core/responses.py:412-436`).
- Implementation exposes typed `ModelRun.run()` and no `run_detailed()` (`src/rompy/model.py:533-746`).
- OpenSpec claims `PipelineResult.model_validate(...)`, although `PipelineResult` is an `Annotated` alias rather than a model class (`src/rompy/core/responses.py:398-401`; `openspec/changes/implement-return-schemas/specs/result-serialization/spec.md:47-57`).

**Impact:** Consumers following the documentation call nonexistent APIs or depend on obsolete return types.

**Smallest safe resolution:** Reconcile OpenSpec, migration material, docstrings, and public deserialization examples with the already-fixed `run() -> ModelRunResult` contract and an explicit union adapter.

**Test shape:** Add API characterization tests for `run()`, absence/presence of `run_detailed()`, union adapter deserialization, and all documented examples; run documentation snippets against the public package.

**Owner:** #3.

## Contradiction and decision table

| Area | Current contradiction | Required disposition |
|---|---|---|
| Run API | OpenSpec says boolean `run()` plus `run_detailed()`; implementation and execution plan require typed `run()` | No new decision: update documents to `run() -> ModelRunResult`. |
| Generate API | Direct Python returns a path/raises while a typed result exists only in a sidecar | Owner decision 3: approve typed migration or explicitly retain path/raise compatibility. |
| Versions | Generate/run accept v1/v2 as one shape; CLI imposes a separate context rule; postprocess is v1-only | Owner decision 1. |
| Interval encoding | Producers emit `3600s`; three tests expect `1:00:00`; no controlling spec fixes either | Freeze one representation under owner decision 1. |
| Artifacts | Model accepts local/absolute/URI-like strings; CLI treats all as local and drops missing entries | Owner decision 2. |
| Processor input | Execution plan already mandates `ModelRunResult`; local and CLI implementations diverge | No new decision: implement fixed rule in #5. |
| Stage completion | OpenSpec excludes a failed stage; one test expects failed postprocess as completed | Treat implementation and that test as stale; use OpenSpec sequence. |
| Persistence failure | Producers hide failures; epic requires observable failures | Owner decision 3. |
| Atomicity | Current code provides atomic replacement visibility, not crash durability | Define durability level with persistence policy. |

## Proposed invariant matrix (not yet approved)

| Concern | Proposed canonical invariant |
|---|---|
| Result discriminator | Every operation has explicit success/failure variants; success cannot carry an error and failure requires one. |
| Sidecar coherence | Envelope kind, version, run ID, success/status/error, and payload identity must agree. |
| Timing | UTC-aware timestamps only; `end >= start`; timing required for completed operations and failures. |
| Duration | Derived from timestamps; one documented JSON representation; model and JSON round trips are lossless. |
| Pipeline success | Completed stages exactly `[GENERATE, RUN, POSTPROCESS]`. |
| Pipeline failure | Completed stages are the strict prefix preceding `failed_stage`. |
| Partial evidence | Failures retain known paths, timing, artifacts, diagnostics, and nested stage results. |
| Cleanup | `cleaned_up=True` only after confirmed cleanup; failure details remain observable. |
| Paths | Actual staging path is authoritative; `run_id_subdir` is never recomputed elsewhere. |
| Artifact identity | Local artifacts are normalized staging-relative paths; remote identities use a distinct URI form. |
| Output evidence | `artifacts` means observed outputs; expected and missing outputs are recorded separately. |
| Processor input | Every processor receives an unchanged, validated `ModelRunResult`. |
| Processor output | Every processor returns validated `PostprocessSuccess | PostprocessFailure`. |
| Versioning | Strict version type; version-specific validation; migration only for approved released formats. |
| Persistence | Canonical writes have a defined atomicity/durability level; write failure is observable. |
| Metadata | Only explicitly approved JSON-safe values; unsupported and non-finite values fail deterministically. |
| CLI parity | Python and CLI preserve equivalent typed fields; JSON shape and exit behavior follow one policy. |

## Prioritized TDD slices and ownership

1. **#3 — Contract characterization and decisions:** Freeze D1/D2, generate/run API, processor protocol, duration encoding, and version behavior. Add tests for approved deserialization APIs.
2. **#4 — Schema coherence, timing, round trips, and persistence:** Add mutation matrices, model/JSON and writer/loader round trips, UTC/order/duration/version/metadata tests, and persistence failure injection.
3. **#5 — Typed processor equivalence and pipeline semantics:** Test exact processor input across direct Python, pipeline, CLI, and fresh process; reject malformed outputs; test strict stage prefixes, nested failures, cleanup, and `run_id_subdir=False`.
4. **#6 — CLI parity, fixtures, and adversarial freeze:** Establish one JSON/exit policy, repair obsolete invocations, publish stable success/failure fixtures and hashes, and test malformed/unsupported-version and fresh-subprocess replay behavior.

## Baseline command and failure classification

**Supplied baseline log:** `/tmp/rompy-wave0.log` (review evidence; not a repository artifact).
**Result:** **111 passed, 7 failed, 6 warnings.** The baseline was supplied by the audit run; this documentation lane does not claim an independent rerun.

| Failures | Classification | Disposition |
|---|---|---|
| Three normalized-context interval assertions | Contract drift: tests expect timedelta text while producers deliberately emit seconds strings | Decide canonical duration encoding, then update assertions; not an environment failure. |
| Four CLI postprocess JSON tests | Stale tests use model-configuration YAML where current CLI requires a staging directory or `run_result.json` | Repair invocation and retain JSON/exit assertions. |
| Setup/environment failures | None evidenced | No action. |
| Unrelated failures | None evidenced | No action. |

Warnings are not causes of the seven failures. The unknown integration mark and unrelated WW3 Pydantic deprecation should be tracked separately if desired.

## Owner decisions still pending (maximum three)

1. **Compatibility/versioning (D1):** Migrate only demonstrably released core-v1 or WW3-flat-v1 artifacts through an explicit one-way reader; reject all other legacy/ambiguous documents. Also freeze one interval encoding.
2. **Artifact identity (D2):** Use staging-relative local paths, a separate remote URI/external-location variant, observed-only `artifacts`, and structured expected/missing evidence.
3. **Failure policy:** Decide the direct-generate compatibility transition and make persistence failure observable—prefer a typed persistence diagnostic/failure rather than silent operational success. Define whether crash durability requires file and directory fsync.

Processor input and `run()` return type do not require further owner decisions; the execution plan already fixes both as `ModelRunResult`.

## Acceptance checklist

- [x] Exact audited revision recorded.
- [x] Discriminators, fields, timing, stage ordering, cleanup, nested failures, and partial evidence audited.
- [x] Direct Python, pipeline, CLI, and fresh-process contracts compared.
- [x] Findings include source evidence, observable impact, smallest resolution, falsifiable test shape, and follow-up ownership.
- [x] Focused baseline failures classified with command/log reference.
- [x] Contradiction/decision table recorded.
- [x] Proposed invariant matrix recorded and explicitly marked pending approval.
- [x] Prioritized TDD slices mapped to #3–#6.
- [x] No source behavior changed; plugins remain unchanged.
- [ ] D1 compatibility/version policy approved.
- [ ] D2 artifact identity and expected/missing policy approved.
- [ ] Persistence-failure and generate-failure policy approved.
- [ ] Canonical schema/version/artifact/processor contract committed.
- [ ] No unresolved P1 contract findings remain before schema freeze.

## Residual risks

- This audit is documentation-only; conclusions rely on the supplied baseline log and evidence synthesis rather than a new test run.
- Compatibility cannot be finalized without evidence identifying which legacy formats were actually released or persisted.
- Fixture hashes and fresh-process validation belong to #6 and do not yet exist.
- The current Gate BLOCK means this artifact should not be read as approval to implement schemas or adapt plugins.

## Scope and impact note

GitNexus symbol-impact analysis is **N/A**: issue #2 changes no source symbols and only adds this audit document. No runtime behavior changed.
