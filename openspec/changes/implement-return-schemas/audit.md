# Issue #2 Return-Schema Robustness Audit

**Audited repository:** `oceanum/rompy`
**Audited revision:** `dab2a1f6d5a81d3b2ec96850f6c3791602860094` (exact prerequisite `origin/return_schema` HEAD)
**Scope:** read-only contract and implementation audit for the return-schema change. No runtime source, tests, fixtures, dependencies, or plugins were changed by this audit.

## Executive verdict / Gate

**Historical audit gate:** BLOCK at the audited revision. The findings below
were recorded before issue #3 owner decisions. Issue #3 now freezes the
contract decisions for version rejection, numeric seconds, artifact identity,
typed generation, and observable persistence failure in the surrounding
OpenSpec documents. Runtime implementation remains the responsibility of #4
and #5, and fixture publication remains the responsibility of #6; this audit
does not claim those follow-ups are complete.

**Reconciliation note:** Findings that describe pending owner decisions or the
pre-decision API are historical evidence, not current contract requirements.
The authoritative requirements are `proposal.md`, `design.md`, `tasks.md`, and
`specs/**` in this change.

The audit examined discriminators, fields, timing, stage progression, cleanup, nested failures, partial evidence, direct Python, pipeline, CLI, and fresh-process contracts. Findings below are retained only where they have source evidence and a falsifiable test shape.

## Current strengths

- `PostprocessResult` and `PipelineResult` use true `success`-discriminated unions (`src/rompy/core/responses.py:232-269,398-401`).
- The current implementation's `ModelRun.run()` returns `ModelRunResult` (`src/rompy/model.py:533-746`); this is evidence of the implementation state, not owner approval of the public contract.
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

### 3. P1 — Version compatibility was ambiguous and asymmetric at audit time

**Evidence**

- Generate/run loaders accept versions 1 and 2 through the same current models; postprocess accepts only version 1 (`src/rompy/core/result_persistence.py:223-239,264-279,305-319`).
- `normalized_context` is optional for both run versions, while CLI rejects missing context as “v1” (`src/rompy/cli.py:947-959`).
- Envelope and generate payload versions are independent.
- JSON `true` passes the current membership test as integer version 1.

**Impact:** Hybrid v1/v2 documents validate differently between library and CLI, and released or future documents have no explicit migration/rejection contract.

**Smallest safe resolution:** Decide D1, then use strict version types and version-specific models or migration readers. Reject unsupported or ambiguous payloads with actionable errors.

**Test shape:** Feed each sidecar loader versions 1, 2, unsupported integers, booleans, missing versions, and mixed envelope/payload versions; assert only approved migrations load and all other cases fail consistently in library and CLI.

**Owner:** #3.

### 4. P1 — Artifact identity and expected/missing-output evidence were undefined at audit time

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

### 7. P1 — Persistence failures were hidden and successful writes were not crash-durable at audit time

**Evidence**

- Generate, run, and postprocess producers catch sidecar-write exceptions and continue; most paths do not log or attach diagnostics (`src/rompy/model.py:360-365,602-606,692-696,740-744,846-850,881-885`).
- CLI may exit successfully with `"Sidecar file not found"` (`src/rompy/cli.py:1077-1091`).
- `_atomic_write()` does not flush/fsync the file or parent directory (`src/rompy/core/result_persistence.py:64-88`).

**Impact:** An operation can report success while its canonical evidence was never persisted. A crash can lose content or rename durability despite successful return.

**Smallest safe resolution:** Approve one observable persistence-failure policy, preserve the primary operation error when both operation and persistence fail, and add file/directory fsync plus failure-injection tests if crash durability is required.

**Test shape:** Inject serialization, write, replace, file-sync, and directory-sync failures; assert the selected policy is observable, primary operation errors are retained with persistence diagnostics, and temporary files/previous valid bytes satisfy the promised atomicity level.

**Owner:** #3 for the persistence-failure contract decision; #4 for implementation and failure-injection testing.

### 8. P2 — OpenSpec and migration documentation described conflicting APIs at audit time

**Evidence**

- The audited OpenSpec and `ModelRunResult` documentation described an obsolete
  alternate/scalar API (`src/rompy/core/responses.py:412-436`).
- The audited implementation exposed typed `ModelRun.run()` (`src/rompy/model.py:533-746`).
- The audited OpenSpec claimed validation on a union alias rather than a concrete
  envelope (`src/rompy/core/responses.py:398-401`).  Issue #3 now requires an
  explicit concrete loader or union adapter.

**Impact:** Consumers following the documentation call nonexistent APIs or depend on obsolete return types.

**Smallest safe resolution:** Reconcile OpenSpec, migration material, docstrings, and public deserialization examples with the current implementation's `run() -> ModelRunResult` behavior; explicitly approve or revise that public contract in #3, and document an explicit union adapter.

**Test shape:** Add API characterization tests for typed `run()`, explicit
union-adapter deserialization, and all documented examples; run documentation
snippets against the public package.

**Owner:** #3.

## Contradiction and decision table

| Area | Current contradiction | Required disposition |
|---|---|---|
| Execution API | Audited OpenSpec described an obsolete alternate/scalar API while implementation evidence was typed | Resolved by #3: `run() -> ModelRunResult`; #4/#5 implement and validate. |
| Generate API | Audited direct Python and sidecar paths differed | Resolved by #3: generation moves toward typed results; #4 implements. |
| Versions | Audited loaders accepted mixed versions asymmetrically | Resolved by #3: strict current version and actionable rejection; #4 implements. |
| Interval encoding | Audited producers/tests disagreed on duration text | Resolved by #3: numeric seconds on the wire; #4 implements. |
| Artifacts | Audited paths and expected outputs were conflated | Resolved by #3: typed local/remote identity and separate evidence; #4/#5 implement. |
| Processor input | Execution plan already mandates `ModelRunResult`; local and CLI implementations diverge | No new decision: implement fixed rule in #5. |
| Stage completion | OpenSpec excludes a failed stage; one test expects failed postprocess as completed | Treat implementation and that test as stale; use OpenSpec sequence. |
| Persistence failure | Producers hid failures; epic requires observable failures | Resolved by #3; #4 implements typed diagnostics. |
| Atomicity | Current code provides atomic replacement visibility, not crash durability | #4 defines and validates the promised durability level. |

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

1. **#3 — Contract characterization and decisions:** **Complete in this change.** The surrounding OpenSpec documents freeze the generate/run API, processor protocol boundary, duration encoding, version behavior, artifact identity, and persistence-failure policy.
2. **#4 — Schema coherence, timing, round trips, and persistence implementation:** Add mutation matrices, model/JSON and writer/loader round trips, UTC/order/duration/version/metadata tests, and implementation/failure-injection tests for the #3-approved persistence policy.
3. **#5 — Typed processor equivalence and pipeline semantics:** Test exact processor input across direct Python, pipeline, CLI, and fresh process; reject malformed outputs; test strict stage prefixes, nested failures, cleanup, and `run_id_subdir=False`.
4. **#6 — CLI parity, fixtures, and adversarial freeze:** Establish one JSON/exit policy, repair obsolete invocations, publish stable success/failure fixtures and hashes, and test malformed/unsupported-version and fresh-subprocess replay behavior.

## Baseline command and failure classification

**Supplied baseline log:** `/tmp/rompy-wave0.log` (review evidence; not a repository artifact).
**Exact invocation run by the parent Wave 0 baseline (not rerun in this lane):**

```text
uv run --no-sync --directory rompy pytest -q tests/test_responses.py tests/test_result_persistence.py tests/test_generate_result_sidecar.py tests/test_run_sidecar_integration.py tests/test_postprocess_sidecar_integration.py tests/test_output_validation.py tests/test_cli_json_output.py tests/test_cli_postprocess_consume.py tests/test_cli_t7_idempotency.py
```

**Result:** **111 passed, 7 failed, 6 warnings.** This is the parent Wave 0 baseline result; this documentation lane does not claim an independent rerun.

| Failures | Classification | Disposition |
|---|---|---|
| Three normalized-context interval assertions | Contract drift: tests expect timedelta text while producers deliberately emit seconds strings | Decide canonical duration encoding, then update assertions; not an environment failure. |
| Four CLI postprocess JSON tests | Stale tests use model-configuration YAML where current CLI requires a staging directory or `run_result.json` | Repair invocation and retain JSON/exit assertions. |
| Setup/environment failures | None evidenced | No action. |
| Unrelated failures | None evidenced | No action. |

Warnings are not causes of the seven failures. The unknown integration mark and unrelated WW3 Pydantic deprecation should be tracked separately if desired.

## Owner decisions still pending (maximum three)

1. **Compatibility/versioning (D1):** Resolved by #3: reject legacy/ambiguous core-v1 and flat WW3-v1 artifacts with actionable kind/version errors; no migration reader now. Wire intervals/durations are numeric seconds.
2. **Artifact identity (D2):** Resolved by #3: use staging-relative local paths, an explicit remote URI variant, observed-only `artifacts`, and structured expected/missing evidence.
3. **Failure policy:** Resolved by #3: generation moves toward typed results and required canonical persistence failure is observable while retaining any primary operation error. #4 defines the promised durability details during implementation.

Processor input is now an issue #3 contract requirement for #5 to implement.
The current typed `run()` return is implementation evidence and is explicitly
approved as the public direction; #5 must make equivalent handoffs true across
all execution paths.

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
- [x] D1 compatibility/version policy approved by issue #3.
- [x] D2 artifact identity and expected/missing policy approved by issue #3.
- [x] Persistence-failure and generate-failure policy approved by issue #3.
- [x] Canonical schema/version/artifact/processor contract documented in this change.
- [ ] Runtime P1 implementation findings remain for #4/#5; they are not contract blockers for issue #3.

## Residual risks

- This audit is documentation-only; conclusions rely on the supplied baseline log and evidence synthesis rather than a new test run.
- Compatibility cannot be finalized without evidence identifying which legacy formats were actually released or persisted.
- Fixture hashes and fresh-process validation belong to #6 and do not yet exist.
- The historical Gate BLOCK was cleared for contract definition by issue #3;
  runtime schema/plugin implementation remains out of scope here and belongs to
  #4/#5.

## Scope and impact note

GitNexus symbol-impact analysis is **N/A**: issue #2 changes no source symbols and only adds this audit document. No runtime behavior changed.
