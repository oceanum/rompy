## ADDED Requirements

### Requirement: Postprocess operations return structured results
The system SHALL return `PostprocessResult` from all postprocess operations instead of untyped dictionaries.

#### Scenario: Successful postprocessing
- **WHEN** a postprocess operation completes successfully
- **THEN** system returns `PostprocessSuccess` with success=True, run_id, output_dir, validated flag, and optional file_count

#### Scenario: Failed postprocessing
- **WHEN** a postprocess operation fails
- **THEN** system returns `PostprocessFailure` with success=False, run_id, error message, and optional output_dir

#### Scenario: Type narrowing on success field
- **WHEN** consumer checks `result.success == True`
- **THEN** type checker narrows type to `PostprocessSuccess` and allows access to success-only fields

### Requirement: Pipeline operations return structured results
The system SHALL return `PipelineResult` from all pipeline operations instead of untyped dictionaries.

#### Scenario: Fully successful pipeline
- **WHEN** all pipeline stages (generate, run, postprocess) complete successfully
- **THEN** system returns `PipelineSuccess` with all stages in stages_completed list and nested PostprocessSuccess

#### Scenario: Pipeline fails at generation stage
- **WHEN** the generate stage fails
- **THEN** system returns `PipelineFailure` with failed_stage=GENERATE, empty stages_completed, and no staging_dir

#### Scenario: Pipeline fails at run stage
- **WHEN** the run stage fails but generation succeeded
- **THEN** system returns `PipelineFailure` with failed_stage=RUN, stages_completed=[GENERATE], and staging_dir populated

#### Scenario: Pipeline fails at postprocess stage
- **WHEN** the postprocess stage fails but generate and run succeeded
- **THEN** system returns `PipelineFailure` with failed_stage=POSTPROCESS, stages_completed=[GENERATE, RUN], and nested PostprocessFailure

#### Scenario: Type narrowing on pipeline success
- **WHEN** consumer checks `result.success == True`
- **THEN** type checker narrows type to `PipelineSuccess` and postprocess_results is guaranteed to be PostprocessSuccess

### Requirement: Model run operations return structured results
The system SHALL provide a method that returns `ModelRunResult` from run operations with detailed execution information.

#### Scenario: Successful model run with details
- **WHEN** a model run completes successfully via run_detailed()
- **THEN** system returns ModelRunResult with success=True, backend_used, timing info, and output paths

#### Scenario: Failed model run with details
- **WHEN** a model run fails via run_detailed()
- **THEN** system returns ModelRunResult with success=False, backend_used, error message, and partial timing

#### Scenario: Backward compatibility of run() method
- **WHEN** existing code calls run() method
- **THEN** system continues to return boolean without breaking existing consumers

### Requirement: Results use discriminated unions
The system SHALL use Pydantic discriminated unions with 'success' field as discriminator for result types.

#### Scenario: Discriminator enables type narrowing
- **WHEN** result object is created with success=True
- **THEN** Pydantic validates it as the Success variant and rejects failure-only fields

#### Scenario: Discriminator prevents invalid states
- **WHEN** attempting to create result with success=True but error field populated
- **THEN** Pydantic validation fails with clear error message

### Requirement: Results include execution context
The system SHALL include run_id, backend/processor names, and directory paths in all result objects.

#### Scenario: Pipeline result contains full execution context
- **WHEN** pipeline completes (success or failure)
- **THEN** result includes run_id, backend name, processor name, and all relevant directory paths

#### Scenario: Postprocess result contains output location
- **WHEN** postprocessing completes
- **THEN** result includes output_dir path for locating processed files

### Requirement: Results include stage progression tracking
The system SHALL track which pipeline stages completed before any failure.

#### Scenario: Tracking completed stages on success
- **WHEN** pipeline succeeds
- **THEN** stages_completed contains [GENERATE, RUN, POSTPROCESS] in order

#### Scenario: Tracking completed stages on partial failure
- **WHEN** pipeline fails at run stage
- **THEN** stages_completed contains only [GENERATE] and failed_stage is RUN

### Requirement: Results support metadata extension
The system SHALL include a metadata dictionary field for backend and processor-specific details.

#### Scenario: Docker backend includes container metadata
- **WHEN** Docker backend executes a run
- **THEN** result metadata includes container_id and image name

#### Scenario: Postprocessor includes validation details
- **WHEN** postprocessor performs validation
- **THEN** result metadata includes list of validated files

### Requirement: Pipeline failures indicate cleanup status
The system SHALL indicate whether output cleanup occurred after pipeline failure.

#### Scenario: Cleanup performed on failure
- **WHEN** pipeline fails with cleanup_on_failure=True
- **THEN** result includes cleaned_up=True

#### Scenario: No cleanup on failure
- **WHEN** pipeline fails with cleanup_on_failure=False
- **THEN** result includes cleaned_up=False and staging_dir/output_dir paths are preserved

### Requirement: Results track generated artifacts
The system SHALL track file artifacts generated during postprocessing operations.

#### Scenario: Postprocess generates output artifacts
- **WHEN** postprocessor creates output files (YAML, NetCDF, plots, etc.)
- **THEN** result includes list of generated artifact paths with types

#### Scenario: No artifacts generated
- **WHEN** postprocessing completes without generating artifacts
- **THEN** result includes empty artifacts list

#### Scenario: Artifact type classification
- **WHEN** artifacts are tracked
- **THEN** each artifact includes file path and optional type classification (yaml, netcdf, plot, etc.)
