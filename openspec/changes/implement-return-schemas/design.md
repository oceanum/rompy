# Design: Canonical return-schema contracts

## Status and ownership

This document is the contract authority for issue #3.  It describes shapes,
invariants, and execution boundaries; it is not an implementation plan for
runtime source.  #4 owns schema validators, serialization, and persistence
implementation; #5 owns equivalent processor/pipeline/CLI handoffs; #6 owns
frozen executable fixtures and adversarial replay.  None of those follow-ups is
complete merely because this document is complete.

## Contract vocabulary

`PostprocessResult` is the discriminated union
`PostprocessSuccess | PostprocessFailure`.  `PipelineResult` is
`PipelineSuccess | PipelineFailure`.  `ModelRunResult` and `GenerateResult` are
likewise typed success/failure results, using `success` as the discriminator;
consumers never infer state from optional fields.

The canonical execution API is:

```python
run(backend, workspace_dir=None) -> ModelRunResult
```

There is no alternate execution method or scalar-return execution contract.
The typed `run()` already present in the current implementation is the evidence
that this is the intended public direction.  Generation likewise moves toward a
typed `GenerateResult`; its compatibility transition is implementation work,
not a second API in this change.

## Normative result fields and requiredness

The following field contract is normative.  `required` means every instance of
that variant carries the field; `optional` means the field may be absent or
null.  Defaults such as an empty evidence list are still canonical values, not
an excuse to omit required evidence from a serialized result.

Shared types:

- `TimingInfo` requires `start_time: UTC datetime`, `end_time: UTC datetime`,
  and derived numeric `duration_seconds: float`; `end_time >= start_time`.
- `ArtifactIdentity` is either `{kind: "local", path: str}` or
  `{kind: "remote", uri: str}`.  Local paths are normalized staging-relative
  paths; remote URIs are explicit non-file URI identities.
- `PersistenceDiagnostic` is optional on operation results and, when present,
  requires exactly `status: Literal["failed"]`, `sidecar_kind: str`,
  `sidecar_path: str`, `error: str`, and `primary_error: str | None`.
  `primary_error` preserves the original operation error when persistence also
  fails.  It is absent on an ordinary failure whose sidecar was persisted.
- `StageTiming` requires `stage: PipelineStage` and `timing: TimingInfo`.
  `stage_timings: list[StageTiming]` contains every completed stage and the
  attempted failed stage, when a failed stage started.
- `artifacts`, `expected_outputs`, and `missing_outputs` are typed lists.  The
  first contains observed outputs only; the latter two are validation
  evidence.  `metadata` is an optional JSON-safe mapping.

Variant fields:

| Variant | Required fields | Optional fields and constraints |
|---|---|---|
| `GenerateSuccess` | `success=true`, `run_id`, `staging_dir`, `generated_files`, `timing` | `config_file`, `metadata`, `persistence_diagnostic` (must be absent for persisted success) |
| `GenerateFailure` | `success=false`, `run_id`, `error`, `timing`, `generated_files` | `staging_dir`, `config_file`, `metadata`, `persistence_diagnostic`; a persistence failure uses the exact diagnostic above |
| `ModelRunSuccess` | `success=true`, `run_id`, `backend_used`, `output_dir`, `timing`, `artifacts`, `expected_outputs`, `missing_outputs` | `workspace_dir`, `message`, `metadata`, `persistence_diagnostic` (must be absent for persisted success) |
| `ModelRunFailure` | `success=false`, `run_id`, `backend_used`, `error`, `timing`, `artifacts`, `expected_outputs`, `missing_outputs` | `output_dir`, `workspace_dir`, `message`, `metadata`, `persistence_diagnostic`; `output_dir` is optional because execution may fail before one exists |
| `PostprocessSuccess` | `success=true`, `run_id`, `output_dir`, `validated`, `timing`, `artifacts`, `expected_outputs`, `missing_outputs` | `file_count`, `message`, `metadata`, `persistence_diagnostic` (must be absent for persisted success) |
| `PostprocessFailure` | `success=false`, `run_id`, `error`, `timing`, `artifacts`, `expected_outputs`, `missing_outputs` | `output_dir`, `message`, `metadata`, `persistence_diagnostic` |
| `PipelineSuccess` | `success=true`, `run_id`, `stages_completed=[GENERATE,RUN,POSTPROCESS]`, `backend`, `processor`, `staging_dir`, `output_dir`, `postprocess_results: PostprocessSuccess`, `timing`, `stage_timings` | `workspace_dir`, `message`, `metadata`, `persistence_diagnostic` (must be absent for persisted success) |
| `PipelineFailure` | `success=false`, `run_id`, `stages_completed` (strict prefix), `backend`, `processor`, `failed_stage`, `error`, `timing`, `stage_timings`, `cleaned_up` | `staging_dir`, `workspace_dir`, `output_dir`, `postprocess_results: PostprocessFailure` only when `failed_stage=POSTPROCESS`, `message`, `metadata`, `persistence_diagnostic` |

For a failed pipeline, `failed_stage`, `error`, operation `timing`, and
`stage_timings` are the failed-stage evidence.  A postprocess failure also
retains its nested `PostprocessFailure` and timing.  A generate or run failure
retains any known generated path and run result evidence in the corresponding
failure fields.  No failed stage is included in `stages_completed`.

## Sidecar envelope

The three canonical files remain `generate_result.json`, `run_result.json`,
and `postprocess_result.json`.  Each completed sidecar uses exactly the current
integer `schema_version` (currently `2`) and one canonical `kind`:
`generate_result`, `run_result`, or `postprocess_result`.  A loader MUST reject
missing, boolean, non-integer, unsupported, or mixed versions.  It MUST reject
legacy/ambiguous core-v1 and flat WW3-v1 documents; no compatibility reader is
part of this change.  Errors identify the file, expected kind, current version,
and observed kind/version, and tell the caller to regenerate a canonical
sidecar.

An envelope and its payload are coherent:

- envelope and payload `run_id` are equal;
- envelope `success` equals payload `success`;
- `status` is `success` when success is true and `failed` when success is false;
- a failed result has an error, and a successful result has no operation error;
- the envelope kind selects the payload family; and
- an envelope cannot claim a completed result while its payload is absent or a
  different result family.

An in-progress marker is not a completed result and MUST NOT be consumed as a
success or failure payload.  Envelope/payload validation is required on every
load path, including CLI and fresh-process loading.

## Timing and wire values

All timestamps are timezone-aware UTC values.  The canonical JSON form is an
RFC 3339 timestamp carrying UTC (`Z` or `+00:00`).  For every interval,
`end_time >= start_time`; reversed, naïve, or non-UTC values fail validation.
`duration_seconds` is derived from the timestamps, has sub-second `float`
precision, and when present on the wire is a numeric seconds value equal to the
derived value.  It is never a `timedelta` string or a human-readable value.
The same rule applies to `period_interval` and any stage duration: wire values
are numeric seconds.  Human-readable formatting belongs only to logs/UI.

Completed operation results and pipeline failures carry operation timing.
Pipeline timing covers the whole operation, nested postprocess timing covers
postprocessing, and stage evidence records each completed stage's timing.  A
failure retains timing up to the failure point.

## Typed artifact and output evidence contract

An artifact is observed output, not an expected-output declaration.  Its
identity is a discriminated local/remote variant:

- a local identity is a normalized POSIX staging-relative `path`; it is
  non-empty, non-absolute, contains no `.` or `..` traversal component, and is
  not URI-like;
- a remote identity is an explicit `uri` variant with a valid non-file URI
  scheme; it is never treated as a local filesystem path; and
- type, byte size, description, and observation metadata are optional evidence
  and do not change identity.

`artifacts` contains only outputs actually observed by the producer.  Expected
outputs and missing outputs are separate structured collections (for example,
`expected_outputs` and `missing_outputs`) using the same typed identity shape.
A missing expected output remains evidence even when it has no local path on
disk.  Consumers MUST NOT filter artifacts by current filesystem existence or
rewrite a remote URI as a local path.

## Processor protocol

A processor is constructed through the validated postprocessor configuration
using one canonical factory/constructor path.  The selected processor class
receives that validated configuration as its required configuration input; its
processor-specific options are not silently flattened into a different
constructor in one execution mode.  The protocol is:

```python
processor = validated_config.build_processor()  # equivalent to ProcessorClass(config)
result = processor.process(model_result, **validated_process_options)
# result: PostprocessSuccess | PostprocessFailure
```

`build_processor()` is the narrow factory seam for #5; whichever concrete
spelling is retained, it MUST have the constructor semantics shown above.
Direct Python, local pipeline, CLI, and fresh-process paths use the same
validated configuration and construction rules.  Every processor receives one
unchanged, validated `ModelRunResult` produced by the run stage.  It does
not receive a live `ModelRun`, a namespace assembled by the CLI, a path-only
substitute, or a partially reconstructed dictionary.  Every return is validated
as `PostprocessSuccess | PostprocessFailure` immediately at the boundary;
dicts, `None`, arbitrary duck-typed objects, and malformed union states are
failures, not accepted results.

## Generation, pipeline, and failure semantics

Generation exposes typed success/failure evidence and persists its canonical
sidecar.  An operation cannot report canonical success if required persistence
fails.  Persistence failure is represented by the operation's typed failure
variant with an observable persistence diagnostic (sidecar kind/path and write
error).  If the primary operation also failed, the diagnostic preserves both
the primary error and persistence error; persistence handling MUST NOT erase the
primary cause.

Pipeline stages are ordered `GENERATE -> RUN -> POSTPROCESS`.  A successful
pipeline has exactly this completed-stage list.  On failure, `failed_stage` is
excluded and `stages_completed` is the strict successful prefix before it:

- generate failure: `[]`;
- run failure: `[GENERATE]`; and
- postprocess failure: `[GENERATE, RUN]`.

The failed stage's typed evidence, known paths, timing, artifacts, and nested
postprocess result remain available.  Cleanup is explicit: `cleaned_up` is true
only after confirmed cleanup, false when disabled or unsuccessful, and cleanup
diagnostics do not replace the stage's primary error.  Actual generated paths,
including a non-subdirectory run, are authoritative; consumers MUST NOT
recompute them from `output_dir/run_id`.

## Representative bounded contract fixtures

These examples are normative shape illustrations, not the frozen executable
fixture corpus owned by #6.  They use abbreviated optional metadata.

Canonical successful run sidecar:

```json
{
  "kind": "run_result",
  "schema_version": 2,
  "run_id": "run-42",
  "status": "success",
  "success": true,
  "error": null,
  "payload": {
    "run_id": "run-42",
    "success": true,
    "backend_used": "local",
    "output_dir": "results/run-42",
    "workspace_dir": "staging/run-42",
    "timing": {
      "start_time": "2026-03-10T10:00:00Z",
      "end_time": "2026-03-10T10:00:02.250000Z",
      "duration_seconds": 2.25
    },
    "artifacts": [
      {"kind": "local", "path": "outputs/waves.nc", "artifact_type": "netcdf"},
      {"kind": "remote", "uri": "s3://bucket/run-42/summary.json", "artifact_type": "text"}
    ],
    "expected_outputs": [
      {"kind": "local", "path": "outputs/waves.nc"},
      {"kind": "local", "path": "outputs/wind.nc"}
    ],
    "missing_outputs": [
      {"kind": "local", "path": "outputs/wind.nc", "reason": "not produced"}
    ],
    "metadata": {}
  }
}
```

Canonical failed postprocess result:

```json
{
  "kind": "postprocess_result",
  "schema_version": 2,
  "run_id": "run-42",
  "status": "failed",
  "success": false,
  "error": "postprocess validation failed",
  "payload": {
    "run_id": "run-42",
    "success": false,
    "error": "postprocess validation failed",
    "output_dir": "results/run-42",
    "timing": {
      "start_time": "2026-03-10T10:00:00Z",
      "end_time": "2026-03-10T10:00:01.250000Z",
      "duration_seconds": 1.25
    },
    "artifacts": [
      {"kind": "local", "path": "outputs/waves.nc", "artifact_type": "netcdf"}
    ],
    "expected_outputs": [
      {"kind": "local", "path": "outputs/waves.nc"},
      {"kind": "local", "path": "outputs/wind.nc"}
    ],
    "missing_outputs": [
      {"kind": "local", "path": "outputs/wind.nc", "reason": "not produced"}
    ],
    "metadata": {}
  }
}
```

The following bounded malformed example is syntactically valid JSON but is
rejected because the envelope and payload disagree on `run_id` and `success`:

```json
{
  "kind": "run_result",
  "schema_version": 2,
  "run_id": "run-42",
  "status": "success",
  "success": true,
  "error": null,
  "payload": {
    "run_id": "run-99",
    "success": false,
    "error": "model failed",
    "backend_used": "local",
    "output_dir": "results/run-42",
    "timing": {
      "start_time": "2026-03-10T10:00:00Z",
      "end_time": "2026-03-10T10:00:01Z",
      "duration_seconds": 1.0
    },
    "artifacts": [],
    "expected_outputs": [],
    "missing_outputs": []
  }
}
```

A conforming loader rejects it with an actionable envelope/payload coherence
error identifying both mismatched fields.  #4 must implement model, JSON, and
sidecar round trips and the rejection matrix; #6 will execute those examples
and publish frozen hashes after #4/#5 implement the contract.

The exact syntax-validation command for these bounded JSON examples is:

```sh
python3 - <<'PY'
from pathlib import Path
import json, re
for path in (Path('openspec/changes/implement-return-schemas/design.md'), Path('SCHEMA_DESIGN.md')):
    for match in re.finditer(r'```json\n(.*?)\n```', path.read_text(), re.S):
        json.loads(match.group(1))
print('all bounded JSON examples are syntactically valid')
PY
```

A persistence failure uses the same typed failure shape, with
`persistence_diagnostic.status = "failed"`, the sidecar path/kind and write
error, and (when applicable) `persistence_diagnostic.primary_error` retaining
the original generate/run/postprocess error.  The operation is never silently
reported as successfully persisted.

## Validation boundary and follow-ups

#4 must implement discriminators, envelope/payload coherence, timing/order,
strict version checks, numeric wire values, round trips, and observable atomic
persistence.  #5 must enforce the processor boundary, strict stage prefixes,
evidence preservation, cleanup truthfulness, and parity across execution paths.
#6 must turn the bounded examples and malformed/legacy cases into the frozen
fixture corpus and fresh-process tests.  This design intentionally does not
claim any of those implementation or test outcomes.
