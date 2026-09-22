## ADDED Requirements

### Requirement: Typed discriminated operation results
The system SHALL expose typed success/failure results for generation, execution,
pipeline, and postprocessing.  `PostprocessResult` SHALL be
`PostprocessSuccess | PostprocessFailure`; `PipelineResult` SHALL be
`PipelineSuccess | PipelineFailure`; `ModelRunResult` and `GenerateResult` SHALL
use the same discriminator pattern.

#### Scenario: Successful postprocessing
- **WHEN** postprocessing completes successfully
- **THEN** the result is `PostprocessSuccess` with `success=true`, `run_id`, output location, timing, observed artifacts, and validation evidence.

#### Scenario: Failed postprocessing
- **WHEN** postprocessing fails
- **THEN** the result is `PostprocessFailure` with `success=false`, `run_id`, an error, timing, and any known paths/artifacts/evidence.

#### Scenario: Typed model execution
- **WHEN** `run(backend, workspace_dir=None)` completes or fails
- **THEN** it returns `ModelRunResult`, not a boolean and not an untyped dictionary.

#### Scenario: Typed generation
- **WHEN** generation completes or fails at the canonical boundary
- **THEN** it produces a typed `GenerateResult` and canonical sidecar evidence.

#### Scenario: Invalid discriminator state
- **WHEN** a result claims success while carrying a failure error, or claims failure without an error
- **THEN** validation rejects the result with an actionable validation error.

### Requirement: Coherent sidecar envelopes
Each canonical sidecar SHALL contain one supported `kind`, the strict current
integer `schema_version` (`2`), `run_id`, `status`, `success`, and a matching
payload.  Envelope and payload identity/state SHALL agree.

#### Scenario: Coherent success envelope
- **WHEN** a successful sidecar is loaded
- **THEN** kind, version, run ID, `status="success"`, `success=true`, and payload success/run ID all agree.

#### Scenario: Coherent failure envelope
- **WHEN** a failed sidecar is loaded
- **THEN** kind, version, run ID, `status="failed"`, `success=false`, and payload error/run ID all agree.

#### Scenario: Contradictory envelope
- **WHEN** kind, version, run ID, status, success, payload family, or payload identity disagree
- **THEN** loading fails rather than normalizing or silently accepting the document.

### Requirement: UTC timing and numeric seconds
All result timing SHALL use timezone-aware UTC timestamps with `end_time >=
start_time`.  Duration, interval, and stage-duration wire values SHALL be
numeric seconds; duration SHALL be derived from timestamps and preserve
sub-second precision.

#### Scenario: Valid interval
- **WHEN** a result contains `start_time="2026-03-10T10:00:00Z"`, `end_time="2026-03-10T10:00:02.25Z"`, and `duration_seconds=2.25`
- **THEN** validation succeeds and the computed duration is `2.25`.

#### Scenario: Invalid timing
- **WHEN** timestamps are naïve, non-UTC, reversed, or duration is a nonnumeric human-readable string
- **THEN** validation fails.

### Requirement: Typed artifact identity and output evidence
Artifacts SHALL be typed local or remote identities.  Local identity SHALL be a
normalized staging-relative path with no absolute or traversal component. Remote
identity SHALL be an explicit URI variant and SHALL NOT be interpreted as a
local path. `artifacts` SHALL contain observed outputs only; expected and
missing outputs SHALL be separate structured collections.

#### Scenario: Local and remote observed outputs
- **WHEN** a processor observes a local NetCDF and an S3 summary
- **THEN** artifacts preserve `{kind:"local", path:"outputs/waves.nc"}` and `{kind:"remote", uri:"s3://..."}` as distinct identities.

#### Scenario: Unsafe or ambiguous identity
- **WHEN** an artifact path is absolute, contains `..`, is URI-like while marked local, or a remote URI is treated as a path
- **THEN** validation rejects it.

#### Scenario: Missing expected output
- **WHEN** an expected output is not observed
- **THEN** it remains in `missing_outputs` with structured identity/reason evidence and is not silently removed from the result.

### Requirement: Pipeline progression and failure evidence
Pipeline stages SHALL be ordered `GENERATE`, `RUN`, `POSTPROCESS`.  Successful
stages SHALL form a strict prefix before a failure; `failed_stage` SHALL NOT be
present in `stages_completed`.

#### Scenario: Full success
- **WHEN** all stages succeed
- **THEN** `stages_completed` is exactly `[GENERATE, RUN, POSTPROCESS]` and nested postprocess evidence is successful.

#### Scenario: Stage failure
- **WHEN** generate, run, or postprocess fails
- **THEN** `stages_completed` is respectively `[]`, `[GENERATE]`, or `[GENERATE, RUN]`, and the failed stage's typed error/evidence is retained.

#### Scenario: Cleanup truthfulness
- **WHEN** cleanup is disabled, succeeds, or fails
- **THEN** `cleaned_up` is respectively false, true, or false, with cleanup diagnostics preserved without replacing the primary error.

### Requirement: Canonical persistence failures are observable
Canonical sidecar persistence SHALL be required for reported operation success.
A write/serialization/replace failure SHALL produce an observable typed failure
with sidecar kind/path and persistence error evidence.  If a primary operation
also failed, both primary and persistence errors SHALL remain available.

#### Scenario: Persistence fails after operation success
- **WHEN** the operation succeeds but its canonical sidecar cannot be persisted
- **THEN** the returned typed result does not claim canonical success and exposes a persistence failure diagnostic.

#### Scenario: Operation and persistence both fail
- **WHEN** an operation error and sidecar write error occur
- **THEN** the typed failure preserves the primary operation error and the persistence error.
