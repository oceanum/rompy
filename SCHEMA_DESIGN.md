# Response Schema Design Document

**Issue**: #15 - Implement Well-Defined Return Schemas Using Pydantic Models  
**Status**: Design Phase  
**Date**: 2026-03-10

## Overview

This document defines the complete response schema system for rompy, replacing ad-hoc dictionary returns with strongly-typed Pydantic models.

## Design Philosophy

### 1. Discriminated Unions for Success/Failure

Use Pydantic's discriminated unions to represent mutually exclusive states:

```python
class Success(BaseModel):
    success: Literal[True]
    # success-specific fields

class Failure(BaseModel):
    success: Literal[False]
    # failure-specific fields
    
Result = Annotated[Union[Success, Failure], Field(discriminator="success")]
```

**Benefits**:
- Type narrowing: `if result.success:` narrows type to `Success`
- No `Optional` soup: fields that only exist on success/failure are properly typed
- Clear documentation: success and failure paths are explicit

### 2. Nested Composition

```python
class PipelineSuccess(RompyBaseModel):
    postprocess_results: PostprocessResult  # Nested Pydantic model
```

**Benefits**:
- Type safety propagates through the call stack
- Validation happens at construction
- Serialization works recursively

### 3. Rich Timing Metadata

All operations include timing information:

```python
class TimingInfo(RompyBaseModel):
    start_time: datetime
    end_time: datetime
    duration_seconds: float
```

### 4. Backward Compatibility via Serialization

```python
result = pipeline(...)  # Returns PipelineResult
legacy_dict = result.model_dump()  # Dict[str, Any] for backward compat
```

## Core Types

### Enums

```python
from enum import Enum

class PipelineStage(str, Enum):
    """Pipeline execution stages."""
    GENERATE = "generate"
    RUN = "run"
    POSTPROCESS = "postprocess"
```

### Timing Info

```python
from datetime import datetime
from pydantic import Field, computed_field

class TimingInfo(RompyBaseModel):
    """Execution timing information."""
    start_time: datetime = Field(..., description="Operation start time (UTC)")
    end_time: datetime = Field(..., description="Operation end time (UTC)")
    
    @computed_field
    @property
    def duration_seconds(self) -> float:
        """Duration in seconds."""
        return (self.end_time - self.start_time).total_seconds()
```

## Postprocess Results

### Design Decision: Discriminated Union

Postprocessing can succeed or fail independently of validation. We use a discriminated union to handle both states cleanly.

```python
class PostprocessSuccess(RompyBaseModel):
    """Successful postprocessing result."""
    success: Literal[True] = Field(
        True, 
        description="Always True for successful postprocessing"
    )
    run_id: str = Field(..., description="Run identifier")
    output_dir: str = Field(..., description="Path to output directory")
    validated: bool = Field(..., description="Whether output validation was performed")
    file_count: Optional[int] = Field(
        None, 
        description="Number of output files (if validation performed)"
    )
    message: Optional[str] = Field(None, description="Status message")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional processor-specific metadata"
    )
    timing: Optional[TimingInfo] = Field(None, description="Execution timing")


class PostprocessFailure(RompyBaseModel):
    """Failed postprocessing result."""
    success: Literal[False] = Field(
        False,
        description="Always False for failed postprocessing"
    )
    run_id: str = Field(..., description="Run identifier")
    error: str = Field(..., description="Error message")
    output_dir: Optional[str] = Field(
        None,
        description="Path to output directory (if it was located)"
    )
    message: Optional[str] = Field(None, description="Additional context")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional processor-specific metadata"
    )
    timing: Optional[TimingInfo] = Field(None, description="Execution timing")


# Discriminated union
PostprocessResult = Annotated[
    Union[PostprocessSuccess, PostprocessFailure],
    Field(discriminator="success")
]
```

### Usage Pattern

```python
def process(self, model_run, **kwargs) -> PostprocessResult:
    start = datetime.now(timezone.utc)
    
    try:
        # ... processing logic ...
        
        return PostprocessSuccess(
            run_id=model_run.run_id,
            output_dir=str(output_dir),
            validated=True,
            file_count=42,
            timing=TimingInfo(start_time=start, end_time=datetime.now(timezone.utc))
        )
    except Exception as e:
        return PostprocessFailure(
            run_id=model_run.run_id,
            error=str(e),
            timing=TimingInfo(start_time=start, end_time=datetime.now(timezone.utc))
        )
```

### Consumer Pattern

```python
result = model_run.postprocess(processor=config)

if result.success:
    # Type checker knows: PostprocessSuccess
    print(f"Processed {result.file_count} files")
    print(f"Output: {result.output_dir}")
else:
    # Type checker knows: PostprocessFailure
    print(f"Error: {result.error}")
    if result.output_dir:
        print(f"Partial output in: {result.output_dir}")
```

## Pipeline Results

### Design Decision: Multi-State Discriminated Union

Pipeline execution has multiple failure modes:
1. Generation failure
2. Run failure (but generation succeeded)
3. Postprocess failure (but generation + run succeeded)
4. Full success

We could model this as:
- **Option A**: Single discriminator with Optional fields
- **Option B**: Discriminated union with distinct types
- **Option C**: Nested result objects

**Chosen: Option B** - Clearest for consumers, best type safety.

```python
class PipelineSuccess(RompyBaseModel):
    """Fully successful pipeline execution."""
    success: Literal[True] = Field(True, description="Always True for success")
    run_id: str = Field(..., description="Run identifier")
    stages_completed: List[PipelineStage] = Field(
        ...,
        description="All stages completed (should be [GENERATE, RUN, POSTPROCESS])"
    )
    backend: str = Field(..., description="Backend used for execution")
    processor: str = Field(..., description="Processor used for postprocessing")
    staging_dir: str = Field(..., description="Path to staging directory")
    workspace_dir: Optional[str] = Field(None, description="Workspace directory (if different from staging)")
    output_dir: str = Field(..., description="Final output directory")
    
    # Nested results
    postprocess_results: PostprocessSuccess = Field(
        ...,
        description="Postprocessing results (always success in this variant)"
    )
    
    # Timing
    timing: TimingInfo = Field(..., description="Total pipeline execution time")
    
    message: Optional[str] = Field(
        "Pipeline completed successfully",
        description="Status message"
    )


class PipelineFailure(RompyBaseModel):
    """Failed pipeline execution."""
    success: Literal[False] = Field(False, description="Always False for failure")
    run_id: str = Field(..., description="Run identifier")
    stages_completed: List[PipelineStage] = Field(
        ...,
        description="Stages completed before failure"
    )
    backend: str = Field(..., description="Backend used for execution")
    processor: str = Field(..., description="Processor used for postprocessing")
    
    # Failure details
    failed_stage: PipelineStage = Field(
        ...,
        description="Stage where failure occurred"
    )
    error: str = Field(..., description="Error message")
    message: Optional[str] = Field(None, description="Additional context")
    
    # Partial results (what was completed before failure)
    staging_dir: Optional[str] = Field(
        None,
        description="Staging directory (if generation succeeded)"
    )
    workspace_dir: Optional[str] = Field(
        None,
        description="Workspace directory (if created)"
    )
    output_dir: Optional[str] = Field(
        None,
        description="Output directory (if any output was generated)"
    )
    
    # If postprocessing failed, include the postprocess failure details
    postprocess_results: Optional[PostprocessFailure] = Field(
        None,
        description="Postprocessing failure details (if postprocess stage failed)"
    )
    
    # Timing (partial)
    timing: Optional[TimingInfo] = Field(
        None,
        description="Execution time until failure"
    )
    
    # Cleanup info
    cleaned_up: bool = Field(
        False,
        description="Whether output was cleaned up after failure"
    )


# Discriminated union
PipelineResult = Annotated[
    Union[PipelineSuccess, PipelineFailure],
    Field(discriminator="success")
]
```

### Usage Pattern

```python
def execute(self, model_run, backend_config, processor, **kwargs) -> PipelineResult:
    start = datetime.now(timezone.utc)
    stages = []
    staging_dir = None
    
    try:
        # Stage 1: Generate
        staging_dir = model_run.generate()
        stages.append(PipelineStage.GENERATE)
        
        # Stage 2: Run
        run_success = model_run.run(backend=backend_config, workspace_dir=staging_dir)
        if not run_success:
            return PipelineFailure(
                run_id=model_run.run_id,
                stages_completed=stages,
                backend=backend_config.__class__.__name__,
                processor=processor.type,
                failed_stage=PipelineStage.RUN,
                error="Model run returned False",
                staging_dir=str(staging_dir),
                timing=TimingInfo(start_time=start, end_time=datetime.now(timezone.utc))
            )
        stages.append(PipelineStage.RUN)
        
        # Stage 3: Postprocess
        postprocess_result = model_run.postprocess(processor=processor)
        
        if not postprocess_result.success:
            # Postprocessing failed but run succeeded
            return PipelineFailure(
                run_id=model_run.run_id,
                stages_completed=stages,
                backend=backend_config.__class__.__name__,
                processor=processor.type,
                failed_stage=PipelineStage.POSTPROCESS,
                error=postprocess_result.error,
                staging_dir=str(staging_dir),
                postprocess_results=postprocess_result,  # Include failure details
                timing=TimingInfo(start_time=start, end_time=datetime.now(timezone.utc))
            )
        
        stages.append(PipelineStage.POSTPROCESS)
        
        # Full success
        return PipelineSuccess(
            run_id=model_run.run_id,
            stages_completed=stages,
            backend=backend_config.__class__.__name__,
            processor=processor.type,
            staging_dir=str(staging_dir),
            output_dir=postprocess_result.output_dir,
            postprocess_results=postprocess_result,  # PostprocessSuccess
            timing=TimingInfo(start_time=start, end_time=datetime.now(timezone.utc))
        )
        
    except Exception as e:
        return PipelineFailure(
            run_id=model_run.run_id,
            stages_completed=stages,
            backend=backend_config.__class__.__name__,
            processor=processor.type,
            failed_stage=stages[-1] if stages else PipelineStage.GENERATE,
            error=str(e),
            message=f"Exception during {stages[-1] if stages else 'generate'}: {e}",
            staging_dir=str(staging_dir) if staging_dir else None,
            timing=TimingInfo(start_time=start, end_time=datetime.now(timezone.utc))
        )
```

### Consumer Pattern

```python
result = model_run.pipeline(
    pipeline_backend="local",
    backend_config=LocalConfig(),
    processor=NoopPostprocessorConfig()
)

match result:
    case PipelineSuccess():
        logger.info(f"✅ Pipeline completed in {result.timing.duration_seconds:.2f}s")
        logger.info(f"Stages: {', '.join(s.value for s in result.stages_completed)}")
        logger.info(f"Output: {result.output_dir}")
        logger.info(f"Files processed: {result.postprocess_results.file_count}")
        
    case PipelineFailure():
        logger.error(f"❌ Pipeline failed at {result.failed_stage.value}")
        logger.error(f"Error: {result.error}")
        logger.info(f"Completed stages: {', '.join(s.value for s in result.stages_completed)}")
        if result.staging_dir:
            logger.info(f"Partial output in: {result.staging_dir}")
        sys.exit(1)
```

## Model Run Results

### Design Decision: Simple Success/Failure Model

Unlike pipeline, `run()` is a lower-level operation. We keep it simple with a single model that has optional error field.

**Open Question**: Should we change the return type from `bool` to `ModelRunResult`?

**Recommendation**: Keep `run() -> bool` unchanged for now, but add optional detailed result capture:

```python
class ModelRunResult(RompyBaseModel):
    """Result from model execution via a backend."""
    success: bool = Field(..., description="Whether execution succeeded")
    run_id: str = Field(..., description="Run identifier")
    backend_used: str = Field(..., description="Backend class name")
    output_dir: str = Field(..., description="Output directory path")
    workspace_dir: Optional[str] = Field(None, description="Workspace directory")
    timing: TimingInfo = Field(..., description="Execution timing")
    
    # Error details (if failed)
    error: Optional[str] = Field(None, description="Error message if success=False")
    message: Optional[str] = Field(None, description="Additional context")
    
    # Backend-specific metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Backend-specific execution details (e.g., container ID, job ID)"
    )
```

### Migration Strategy for run()

**Phase 1** (Non-breaking): Add parallel method
```python
class ModelRun:
    def run(self, backend: BackendConfig, workspace_dir: Optional[str] = None) -> bool:
        """Existing method, unchanged."""
        # ... existing implementation ...
        
    def run_detailed(self, backend: BackendConfig, workspace_dir: Optional[str] = None) -> ModelRunResult:
        """New method that returns detailed result."""
        start = datetime.now(timezone.utc)
        
        try:
            success = self.run(backend, workspace_dir)  # Call existing implementation
            
            return ModelRunResult(
                success=success,
                run_id=self.run_id,
                backend_used=backend.__class__.__name__,
                output_dir=str(Path(self.output_dir) / self.run_id),
                workspace_dir=workspace_dir,
                timing=TimingInfo(start_time=start, end_time=datetime.now(timezone.utc))
            )
        except Exception as e:
            return ModelRunResult(
                success=False,
                run_id=self.run_id,
                backend_used=backend.__class__.__name__,
                output_dir=str(Path(self.output_dir) / self.run_id),
                error=str(e),
                timing=TimingInfo(start_time=start, end_time=datetime.now(timezone.utc))
            )
```

**Phase 2** (Major version bump): Deprecate `run()`, rename `run_detailed()` → `run()`

## Edge Cases & Design Decisions

### 1. Postprocess "Warning" State

Current code does:
```python
if not postprocess_results.get("success", True):
    logger.warning("Postprocessing reported failure but pipeline will continue")
```

**Decision**: This is a smell. Either postprocessing succeeds or fails. If there are warnings, they should be in `metadata` or `message` field, not a separate success state.

**Recommendation**: Remove the "warning continue" pattern. Postprocessing either:
- Succeeds → `PostprocessSuccess`
- Fails → `PostprocessFailure` → Pipeline returns `PipelineFailure`

### 2. Validation Failure vs Processing Failure

Should validation failures be separate from processing failures?

**Decision**: No. Validation is part of postprocessing. If validation fails, postprocessing fails.

```python
if validate_outputs and not output_dir.exists():
    return PostprocessFailure(
        run_id=model_run.run_id,
        error=f"Output directory not found: {output_dir}",
        message="Validation failed"
    )
```

### 3. Cleanup on Failure

`cleanup_on_failure` parameter removes outputs. Should this be in the result?

**Decision**: Yes, include in `PipelineFailure.cleaned_up` field.

```python
if cleanup_on_failure:
    self._cleanup_outputs(model_run)
    cleaned_up = True
else:
    cleaned_up = False

return PipelineFailure(
    ...,
    cleaned_up=cleaned_up
)
```

### 4. Timing When Failure Occurs

If a stage fails, we still want timing info up to that point.

**Decision**: Always include `TimingInfo` in failures, representing time until failure.

### 5. Metadata Extensibility

Different backends and processors may want to include additional info.

**Decision**: Include `metadata: Dict[str, Any]` field in all result types for extensibility.

Examples:
- Docker backend: `{"container_id": "abc123", "image": "swan:latest"}`
- Slurm backend: `{"job_id": "12345", "partition": "compute"}`
- Postprocessor: `{"files_validated": [...], "skipped_files": [...]}`

## Serialization Examples

### Pipeline Success

```python
result = PipelineSuccess(...)
result.model_dump()
```

Produces:
```json
{
  "success": true,
  "run_id": "test_run_001",
  "stages_completed": ["generate", "run", "postprocess"],
  "backend": "LocalConfig",
  "processor": "noop",
  "staging_dir": "/tmp/staging",
  "output_dir": "/output/test_run_001",
  "postprocess_results": {
    "success": true,
    "run_id": "test_run_001",
    "output_dir": "/output/test_run_001",
    "validated": true,
    "file_count": 42,
    "message": "Processing complete",
    "metadata": {},
    "timing": {
      "start_time": "2026-03-10T10:00:00Z",
      "end_time": "2026-03-10T10:05:00Z",
      "duration_seconds": 300.0
    }
  },
  "timing": {
    "start_time": "2026-03-10T10:00:00Z",
    "end_time": "2026-03-10T10:05:30Z",
    "duration_seconds": 330.0
  },
  "message": "Pipeline completed successfully"
}
```

### Pipeline Failure

```python
result = PipelineFailure(...)
result.model_dump()
```

Produces:
```json
{
  "success": false,
  "run_id": "test_run_002",
  "stages_completed": ["generate", "run"],
  "backend": "DockerConfig",
  "processor": "noop",
  "failed_stage": "postprocess",
  "error": "Output directory not found",
  "message": "Postprocessing validation failed",
  "staging_dir": "/tmp/staging",
  "output_dir": "/output/test_run_002",
  "postprocess_results": {
    "success": false,
    "run_id": "test_run_002",
    "error": "Output directory not found",
    "message": "Validation failed",
    "metadata": {},
    "timing": {
      "start_time": "2026-03-10T10:05:00Z",
      "end_time": "2026-03-10T10:05:01Z",
      "duration_seconds": 1.0
    }
  },
  "timing": {
    "start_time": "2026-03-10T10:00:00Z",
    "end_time": "2026-03-10T10:05:01Z",
    "duration_seconds": 301.0
  },
  "cleaned_up": false
}
```

## Testing Strategy

### Unit Tests

Each result type should have tests for:
1. Successful construction with valid data
2. Validation failures with invalid data
3. Serialization/deserialization round-trips
4. Discriminator-based type narrowing

### Integration Tests

Pipeline tests should verify:
1. Success path returns `PipelineSuccess` with nested `PostprocessSuccess`
2. Generate failure returns `PipelineFailure` with `failed_stage=GENERATE`
3. Run failure returns `PipelineFailure` with `failed_stage=RUN` and `staging_dir` present
4. Postprocess failure returns `PipelineFailure` with nested `PostprocessFailure`

## Migration Guide (for Users)

### Before (Dict-based)

```python
results = model_run.pipeline(...)
if results.get("success"):
    print(f"Completed stages: {results.get('stages_completed')}")
    output = results.get("postprocess_results", {}).get("output_dir")
else:
    print(f"Failed: {results.get('message')}")
```

### After (Pydantic-based)

```python
results = model_run.pipeline(...)
if results.success:
    print(f"Completed stages: {[s.value for s in results.stages_completed]}")
    output = results.postprocess_results.output_dir
else:
    print(f"Failed at {results.failed_stage.value}: {results.error}")
```

### Backward Compatibility (Temporary)

```python
results = model_run.pipeline(...)
legacy_dict = results.model_dump()  # Get dict for legacy code
if legacy_dict.get("success"):
    # Works like before
    pass
```

## Open Questions

1. **Should `ModelRun.run()` change signature?**
   - Recommendation: Add `run_detailed()` in parallel, deprecate later
   
2. **Should we support `return_format="dict"` parameter?**
   - Recommendation: No. Users can call `.model_dump()` if needed.
   
3. **Should generate() return a GenerateResult?**
   - Recommendation: No. It's simple enough as `str`. If we need more, make it a Path object.
   
4. **What about plugin postprocessors?**
   - Recommendation: Document that all processors must return `PostprocessResult`. Provide base class.

5. **Version bump strategy?**
   - Recommendation: Major version bump (e.g., 1.x → 2.0). This is breaking.

## Implementation Checklist

- [ ] Create `src/rompy/core/results.py` with schema definitions
- [ ] Update `ModelRun.postprocess()` return type
- [ ] Update `ModelRun.pipeline()` return type  
- [ ] Update `LocalPipelineBackend.execute()` implementation
- [ ] Add `ModelRun.run_detailed()` method
- [ ] Update CLI to handle new result types
- [ ] Update all postprocessor implementations
- [ ] Update tests (unit + integration)
- [ ] Write migration guide
- [ ] Update documentation
- [ ] Bump version to 2.0.0-alpha

## File Structure

```
src/rompy/core/
├── types.py           # RompyBaseModel (existing)
└── results.py         # NEW: All result schemas
    ├── TimingInfo
    ├── PipelineStage (enum)
    ├── PostprocessSuccess
    ├── PostprocessFailure
    ├── PostprocessResult (union)
    ├── PipelineSuccess
    ├── PipelineFailure
    ├── PipelineResult (union)
    └── ModelRunResult
```

---

**End of Design Document**
