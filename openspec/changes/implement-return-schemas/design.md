# Design: Implement Return Schemas

## Overview

This design implements strongly-typed Pydantic response schemas for rompy's key operations (`postprocess()`, `pipeline()`, `run_detailed()`), replacing untyped dictionaries with discriminated unions that provide type safety and IDE support.

## Architecture

### Component Structure

```
src/rompy/core/
├── types.py           # Existing RompyBaseModel base class
└── responses.py       # NEW: All response schema definitions (~400 lines)
    ├── PipelineStage (enum)
    ├── ArtifactType (enum)
    ├── TimingInfo
    ├── Artifact
    ├── PostprocessSuccess
    ├── PostprocessFailure
    ├── PostprocessResult (discriminated union)
    ├── PipelineSuccess
    ├── PipelineFailure
    ├── PipelineResult (discriminated union)
    └── ModelRunResult
```

**Note**: Following the GitHub issue recommendation, we'll use `responses.py` instead of `results.py` for consistency with the issue description.

### Key Design Decisions

**1. Discriminated Unions**

Use Pydantic v2 discriminated unions with `success: Literal[True/False]` as discriminator:

```python
from typing import Annotated, Union, Literal
from pydantic import Field

PostprocessResult = Annotated[
    Union[PostprocessSuccess, PostprocessFailure],
    Field(discriminator="success")
]
```

**Benefits**:
- Type narrowing: `if result.success:` automatically narrows to Success type
- No Optional field soup: success-only and failure-only fields are properly typed
- Runtime validation: Pydantic enforces mutually exclusive states

**2. Computed Duration Fields**

Use `@computed_field` to derive duration from timestamps:

```python
from pydantic import computed_field

class TimingInfo(RompyBaseModel):
    start_time: datetime
    end_time: datetime
    
    @computed_field
    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()
```

**Benefits**:
- Single source of truth (timestamps)
- No risk of inconsistent duration values
- Automatically included in serialization

**3. UTC Timestamps**

All timestamps use `datetime.now(timezone.utc)` to avoid timezone ambiguity.

**4. Nested Result Composition**

`PipelineResult` nests `PostprocessResult` to maintain full execution context:

```python
class PipelineSuccess(RompyBaseModel):
    postprocess_results: PostprocessSuccess  # Type-safe nesting
```

**5. Metadata Extensibility**

All result types include `metadata: Dict[str, Any]` for backend/processor-specific details without schema changes.

**6. Migration Strategy**

- **Phase 1** (Non-breaking): Add `ModelRun.run_detailed()` alongside existing `run() -> bool`
- **Phase 2** (Breaking, v2.0.0): Change `postprocess()` and `pipeline()` return types
- **Phase 3** (Future): Deprecate `run()` in favor of `run_detailed()`

## Implementation Details

### 1. Result Schema Definitions (`src/rompy/core/responses.py`)

**Module structure**:

```python
"""Response schemas for rompy operations.

This module defines strongly-typed Pydantic response models for all major
rompy operations, replacing dictionary returns with validated schemas.
"""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import Field, computed_field

from rompy.core.types import RompyBaseModel


class PipelineStage(str, Enum):
    """Pipeline execution stages."""
    GENERATE = "generate"
    RUN = "run"
    POSTPROCESS = "postprocess"


class ArtifactType(str, Enum):
    """Types of artifacts generated during postprocessing."""
    YAML = "yaml"
    NETCDF = "netcdf"
    PLOT = "plot"
    TEXT = "text"
    OTHER = "other"


class Artifact(RompyBaseModel):
    """Represents a file artifact generated during processing."""
    path: str = Field(..., description="Absolute or relative path to artifact")
    artifact_type: Optional[ArtifactType] = Field(
        None, 
        description="Type of artifact (yaml, netcdf, plot, etc.)"
    )
    size_bytes: Optional[int] = Field(None, description="File size in bytes")
    description: Optional[str] = Field(None, description="Human-readable description")


class TimingInfo(RompyBaseModel):
    """Execution timing information."""
    start_time: datetime = Field(..., description="Operation start time (UTC)")
    end_time: datetime = Field(..., description="Operation end time (UTC)")
    
    @computed_field
    @property
    def duration_seconds(self) -> float:
        """Computed duration in seconds."""
        return (self.end_time - self.start_time).total_seconds()


class PostprocessSuccess(RompyBaseModel):
    """Successful postprocessing result."""
    success: Literal[True] = Field(True, description="Always True for success")
    run_id: str = Field(..., description="Run identifier")
    output_dir: str = Field(..., description="Path to output directory")
    validated: bool = Field(..., description="Whether output validation was performed")
    file_count: Optional[int] = Field(None, description="Number of output files")
    artifacts: List[Artifact] = Field(
        default_factory=list,
        description="List of generated artifacts (YAML, NetCDF, plots, etc.)"
    )
    message: Optional[str] = Field(None, description="Status message")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Processor-specific metadata")
    timing: Optional[TimingInfo] = Field(None, description="Execution timing")


class PostprocessFailure(RompyBaseModel):
    """Failed postprocessing result."""
    success: Literal[False] = Field(False, description="Always False for failure")
    run_id: str = Field(..., description="Run identifier")
    error: str = Field(..., description="Error message")
    output_dir: Optional[str] = Field(None, description="Path to output directory if located")
    artifacts: List[Artifact] = Field(
        default_factory=list,
        description="Partial artifacts generated before failure"
    )
    message: Optional[str] = Field(None, description="Additional context")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Processor-specific metadata")
    timing: Optional[TimingInfo] = Field(None, description="Execution timing")


PostprocessResult = Annotated[
    Union[PostprocessSuccess, PostprocessFailure],
    Field(discriminator="success")
]


class PipelineSuccess(RompyBaseModel):
    """Fully successful pipeline execution."""
    success: Literal[True] = Field(True, description="Always True for success")
    run_id: str = Field(..., description="Run identifier")
    stages_completed: List[PipelineStage] = Field(..., description="All stages completed")
    backend: str = Field(..., description="Backend used for execution")
    processor: str = Field(..., description="Processor used for postprocessing")
    staging_dir: str = Field(..., description="Path to staging directory")
    workspace_dir: Optional[str] = Field(None, description="Workspace directory")
    output_dir: str = Field(..., description="Final output directory")
    postprocess_results: PostprocessSuccess = Field(..., description="Postprocessing results")
    timing: TimingInfo = Field(..., description="Total pipeline execution time")
    message: Optional[str] = Field("Pipeline completed successfully", description="Status message")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Pipeline-specific metadata")


class PipelineFailure(RompyBaseModel):
    """Failed pipeline execution."""
    success: Literal[False] = Field(False, description="Always False for failure")
    run_id: str = Field(..., description="Run identifier")
    stages_completed: List[PipelineStage] = Field(..., description="Stages completed before failure")
    backend: str = Field(..., description="Backend used for execution")
    processor: str = Field(..., description="Processor used for postprocessing")
    failed_stage: PipelineStage = Field(..., description="Stage where failure occurred")
    error: str = Field(..., description="Error message")
    message: Optional[str] = Field(None, description="Additional context")
    staging_dir: Optional[str] = Field(None, description="Staging directory if generated")
    workspace_dir: Optional[str] = Field(None, description="Workspace directory if created")
    output_dir: Optional[str] = Field(None, description="Output directory if any output generated")
    postprocess_results: Optional[PostprocessFailure] = Field(None, description="Postprocess failure details")
    timing: Optional[TimingInfo] = Field(None, description="Execution time until failure")
    cleaned_up: bool = Field(False, description="Whether output was cleaned up after failure")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Pipeline-specific metadata")


PipelineResult = Annotated[
    Union[PipelineSuccess, PipelineFailure],
    Field(discriminator="success")
]


class ModelRunResult(RompyBaseModel):
    """Result from model execution via a backend."""
    success: bool = Field(..., description="Whether execution succeeded")
    run_id: str = Field(..., description="Run identifier")
    backend_used: str = Field(..., description="Backend class name")
    output_dir: str = Field(..., description="Output directory path")
    workspace_dir: Optional[str] = Field(None, description="Workspace directory")
    timing: TimingInfo = Field(..., description="Execution timing")
    error: Optional[str] = Field(None, description="Error message if success=False")
    message: Optional[str] = Field(None, description="Additional context")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Backend-specific metadata")
```

**Key additions from GitHub issue**:
- **`Artifact` class**: Tracks generated files (YAML, NetCDF, plots) with type classification
- **`ArtifactType` enum**: Standard classification for output artifacts
- **`artifacts` field**: List of generated artifacts in both success and failure cases
- **Module name**: Using `responses.py` as recommended in issue #15

**Key implementation notes**:
- Import `timezone` from `datetime` for UTC timestamps
- Use `default_factory=dict` for `metadata` fields (avoid mutable defaults)
- All docstrings follow numpy-style convention
- Enums inherit from `str` for JSON serialization compatibility

### 2. Postprocess Method Updates (`src/rompy/model.py`)

**Current signature** (line ~387):
```python
def postprocess(
    self, processor: PostprocessorConfig, **kwargs
) -> Dict[str, Any]:
```

**New signature**:
```python
from rompy.core.responses import PostprocessResult, PostprocessSuccess, PostprocessFailure, TimingInfo

def postprocess(
    self, processor: PostprocessorConfig, **kwargs
) -> PostprocessResult:
    """
    Postprocess model run outputs.
    
    Returns:
        PostprocessResult: Discriminated union of PostprocessSuccess or PostprocessFailure
    """
    from datetime import datetime, timezone
    
    start_time = datetime.now(timezone.utc)
    
    try:
        # Existing logic to load processor and call process()
        postprocessor = load_entry_point(...)
        result = postprocessor.process(self, **kwargs)
        
        # result is already PostprocessResult from processor
        return result
        
    except Exception as e:
        logger.exception(f"Postprocessing failed: {e}")
        return PostprocessFailure(
            run_id=self.run_id,
            error=str(e),
            message="Exception during postprocessing",
            timing=TimingInfo(start_time=start_time, end_time=datetime.now(timezone.utc))
        )
```

**Key changes**:
- Import result types from `rompy.core.responses`
- Change return type annotation
- Wrap top-level exceptions in `PostprocessFailure`
- Pass through processor results (processors return `PostprocessResult`)

### 3. Pipeline Method Updates (`src/rompy/model.py`)

**Current signature** (line ~397):
```python
def pipeline(
    self,
    pipeline_backend: str = "local",
    backend_config: Optional[BackendConfig] = None,
    processor: Optional[PostprocessorConfig] = None,
    cleanup_on_failure: bool = False,
    **kwargs,
) -> Dict[str, Any]:
```

**New signature**:
```python
from rompy.core.responses import PipelineResult, PipelineSuccess, PipelineFailure, PipelineStage, TimingInfo

def pipeline(
    self,
    pipeline_backend: str = "local",
    backend_config: Optional[BackendConfig] = None,
    processor: Optional[PostprocessorConfig] = None,
    cleanup_on_failure: bool = False,
    **kwargs,
) -> PipelineResult:
    """
    Execute full pipeline: generate → run → postprocess.
    
    Returns:
        PipelineResult: Discriminated union of PipelineSuccess or PipelineFailure
    """
    from datetime import datetime, timezone
    
    start_time = datetime.now(timezone.utc)
    
    # Load pipeline backend
    pipeline = load_entry_point(...)
    
    # Execute pipeline (returns PipelineResult)
    result = pipeline.execute(
        self, 
        backend_config, 
        processor, 
        cleanup_on_failure=cleanup_on_failure,
        **kwargs
    )
    
    return result
```

**Key changes**:
- Import result types
- Change return type annotation
- Pipeline backends now return `PipelineResult` directly (implementation in pipeline backend)

### 4. Pipeline Backend Updates (`src/rompy/pipeline/__init__.py`)

**Current signature** (line ~114):
```python
def execute(
    self, 
    model_run: ModelRun, 
    backend_config: Optional[BackendConfig], 
    processor: Optional[PostprocessorConfig],
    cleanup_on_failure: bool = False,
    **kwargs
) -> Dict[str, Any]:
```

**New signature and implementation**:
```python
from rompy.core.responses import (
    PipelineResult, PipelineSuccess, PipelineFailure, 
    PipelineStage, TimingInfo, PostprocessSuccess, PostprocessFailure
)

def execute(
    self, 
    model_run: ModelRun, 
    backend_config: Optional[BackendConfig], 
    processor: Optional[PostprocessorConfig],
    cleanup_on_failure: bool = False,
    **kwargs
) -> PipelineResult:
    """
    Execute pipeline stages: generate → run → postprocess.
    
    Returns:
        PipelineResult: Success or failure with stage tracking
    """
    from datetime import datetime, timezone
    
    start_time = datetime.now(timezone.utc)
    stages_completed: List[PipelineStage] = []
    staging_dir: Optional[str] = None
    backend_name = backend_config.__class__.__name__ if backend_config else "LocalConfig"
    processor_name = processor.type if processor else "noop"
    
    try:
        # Stage 1: Generate
        logger.info("Pipeline stage: GENERATE")
        staging_dir = model_run.generate()
        stages_completed.append(PipelineStage.GENERATE)
        
        # Stage 2: Run
        logger.info("Pipeline stage: RUN")
        run_success = model_run.run(backend=backend_config, workspace_dir=staging_dir)
        if not run_success:
            return PipelineFailure(
                run_id=model_run.run_id,
                stages_completed=stages_completed,
                backend=backend_name,
                processor=processor_name,
                failed_stage=PipelineStage.RUN,
                error="Model run returned False",
                staging_dir=staging_dir,
                timing=TimingInfo(start_time=start_time, end_time=datetime.now(timezone.utc))
            )
        stages_completed.append(PipelineStage.RUN)
        
        # Stage 3: Postprocess
        logger.info("Pipeline stage: POSTPROCESS")
        postprocess_result = model_run.postprocess(processor=processor, **kwargs)
        
        if not postprocess_result.success:
            # Postprocessing failed
            if cleanup_on_failure:
                self._cleanup_outputs(model_run)
                cleaned_up = True
            else:
                cleaned_up = False
                
            return PipelineFailure(
                run_id=model_run.run_id,
                stages_completed=stages_completed,
                backend=backend_name,
                processor=processor_name,
                failed_stage=PipelineStage.POSTPROCESS,
                error=postprocess_result.error,
                message=postprocess_result.message,
                staging_dir=staging_dir,
                output_dir=postprocess_result.output_dir,
                postprocess_results=postprocess_result,  # Nest failure details
                timing=TimingInfo(start_time=start_time, end_time=datetime.now(timezone.utc)),
                cleaned_up=cleaned_up
            )
        
        stages_completed.append(PipelineStage.POSTPROCESS)
        
        # Full success
        return PipelineSuccess(
            run_id=model_run.run_id,
            stages_completed=stages_completed,
            backend=backend_name,
            processor=processor_name,
            staging_dir=staging_dir,
            output_dir=postprocess_result.output_dir,
            postprocess_results=postprocess_result,  # Nest success details
            timing=TimingInfo(start_time=start_time, end_time=datetime.now(timezone.utc))
        )
        
    except Exception as e:
        logger.exception(f"Pipeline exception: {e}")
        
        if cleanup_on_failure:
            self._cleanup_outputs(model_run)
            cleaned_up = True
        else:
            cleaned_up = False
        
        return PipelineFailure(
            run_id=model_run.run_id,
            stages_completed=stages_completed,
            backend=backend_name,
            processor=processor_name,
            failed_stage=stages_completed[-1] if stages_completed else PipelineStage.GENERATE,
            error=str(e),
            message=f"Exception during pipeline execution",
            staging_dir=staging_dir,
            timing=TimingInfo(start_time=start_time, end_time=datetime.now(timezone.utc)),
            cleaned_up=cleaned_up
        )
```

**Key changes**:
- Track `stages_completed` list as we progress
- Return appropriate `PipelineFailure` at each failure point with correct `failed_stage`
- Nest `PostprocessResult` inside `PipelineResult` (both success and failure variants)
- Handle cleanup tracking with `cleaned_up` field
- Capture timing at start, use current time for end_time

### 5. Postprocessor Updates (`src/rompy/postprocess/__init__.py`)

**Current signature** (line ~35):
```python
def process(
    self, model_run: ModelRun, validate_outputs: bool = True, **kwargs
) -> Dict[str, Any]:
```

**New signature**:
```python
from rompy.core.responses import (
    PostprocessResult, PostprocessSuccess, PostprocessFailure, 
    TimingInfo, Artifact, ArtifactType
)

def process(
    self, model_run: ModelRun, validate_outputs: bool = True, **kwargs
) -> PostprocessResult:
    """
    Process model run outputs with optional validation.
    
    Returns:
        PostprocessResult: Success or failure with validation details and artifacts
    """
    from datetime import datetime, timezone
    from pathlib import Path
    
    start_time = datetime.now(timezone.utc)
    
    try:
        output_dir = Path(model_run.output_dir) / model_run.run_id
        
        if validate_outputs:
            if not output_dir.exists():
                return PostprocessFailure(
                    run_id=model_run.run_id,
                    error=f"Output directory not found: {output_dir}",
                    message="Validation failed",
                    timing=TimingInfo(start_time=start_time, end_time=datetime.now(timezone.utc))
                )
            
            # Collect output files and classify as artifacts
            output_files = list(output_dir.glob("*"))
            file_count = len(output_files)
            
            artifacts = []
            for file_path in output_files:
                # Classify artifact type by extension
                artifact_type = None
                suffix = file_path.suffix.lower()
                if suffix in ['.yaml', '.yml']:
                    artifact_type = ArtifactType.YAML
                elif suffix == '.nc':
                    artifact_type = ArtifactType.NETCDF
                elif suffix in ['.png', '.jpg', '.pdf', '.svg']:
                    artifact_type = ArtifactType.PLOT
                elif suffix == '.txt':
                    artifact_type = ArtifactType.TEXT
                else:
                    artifact_type = ArtifactType.OTHER
                
                artifacts.append(Artifact(
                    path=str(file_path),
                    artifact_type=artifact_type,
                    size_bytes=file_path.stat().st_size if file_path.is_file() else None
                ))
            
            return PostprocessSuccess(
                run_id=model_run.run_id,
                output_dir=str(output_dir),
                validated=True,
                file_count=file_count,
                artifacts=artifacts,
                message="Validation passed",
                timing=TimingInfo(start_time=start_time, end_time=datetime.now(timezone.utc))
            )
        else:
            return PostprocessSuccess(
                run_id=model_run.run_id,
                output_dir=str(output_dir),
                validated=False,
                message="No validation performed",
                timing=TimingInfo(start_time=start_time, end_time=datetime.now(timezone.utc))
            )
            
    except Exception as e:
        logger.exception(f"Postprocessing failed: {e}")
        return PostprocessFailure(
            run_id=model_run.run_id,
            error=str(e),
            message="Exception during postprocessing",
            timing=TimingInfo(start_time=start_time, end_time=datetime.now(timezone.utc))
        )
```

**Key changes**:
- Import result types including `Artifact` and `ArtifactType`
- Change return type annotation
- **Track generated artifacts** with type classification (YAML, NetCDF, plots, etc.)
- Return `PostprocessSuccess` with artifacts list
- Return `PostprocessFailure` for validation failures and exceptions
- Include timing information in all paths

### 6. Add run_detailed() Method (`src/rompy/model.py`)

**Add new method alongside existing `run()`**:

```python
from rompy.core.responses import ModelRunResult, TimingInfo

def run_detailed(
    self, backend: Optional[BackendConfig] = None, workspace_dir: Optional[str] = None
) -> ModelRunResult:
    """
    Execute model run with detailed result information.
    
    This method provides structured result objects with timing, metadata, and error details.
    For backward compatibility, use run() which returns bool.
    
    Args:
        backend: Backend configuration (defaults to LocalConfig)
        workspace_dir: Workspace directory path
        
    Returns:
        ModelRunResult: Detailed execution result with timing and metadata
    """
    from datetime import datetime, timezone
    from pathlib import Path
    
    start_time = datetime.now(timezone.utc)
    
    if backend is None:
        backend = LocalConfig()
    
    backend_name = backend.__class__.__name__
    output_dir_path = Path(self.output_dir) / self.run_id
    
    try:
        # Call existing run() implementation
        success = self.run(backend=backend, workspace_dir=workspace_dir)
        
        return ModelRunResult(
            success=success,
            run_id=self.run_id,
            backend_used=backend_name,
            output_dir=str(output_dir_path),
            workspace_dir=workspace_dir,
            timing=TimingInfo(start_time=start_time, end_time=datetime.now(timezone.utc)),
            message="Execution completed" if success else "Execution returned False"
        )
        
    except Exception as e:
        logger.exception(f"Run failed: {e}")
        return ModelRunResult(
            success=False,
            run_id=self.run_id,
            backend_used=backend_name,
            output_dir=str(output_dir_path),
            workspace_dir=workspace_dir,
            error=str(e),
            message="Exception during execution",
            timing=TimingInfo(start_time=start_time, end_time=datetime.now(timezone.utc))
        )
```

**Key points**:
- Non-breaking: Existing `run() -> bool` unchanged
- Wraps existing `run()` method for timing capture
- Provides migration path for future versions

### 7. CLI Updates (`src/rompy/cli.py`)

**Current pattern** (lines ~810-850):
```python
results = model_run.pipeline(...)
if results.get("success"):
    logger.info(f"Stages: {results.get('stages_completed')}")
else:
    logger.error(f"Failed: {results.get('message')}")
```

**New pattern**:
```python
from rompy.core.responses import PipelineSuccess, PipelineFailure

results = model_run.pipeline(...)

if results.success:
    # Type checker knows: PipelineSuccess
    logger.info(f"Pipeline completed in {results.timing.duration_seconds:.2f}s")
    logger.info(f"Stages: {', '.join(s.value for s in results.stages_completed)}")
    logger.info(f"Output: {results.output_dir}")
    if results.postprocess_results.file_count:
        logger.info(f"Files processed: {results.postprocess_results.file_count}")
else:
    # Type checker knows: PipelineFailure
    logger.error(f"Pipeline failed at {results.failed_stage.value}")
    logger.error(f"Error: {results.error}")
    logger.info(f"Completed stages: {', '.join(s.value for s in results.stages_completed)}")
    if results.staging_dir:
        logger.info(f"Partial output in: {results.staging_dir}")
    sys.exit(1)
```

**Changes needed**:
- Import result types
- Replace `.get()` calls with direct attribute access
- Use `.value` for enum fields
- Use `.timing.duration_seconds` for timing
- Handle nested `postprocess_results` properly

### 8. Test Updates

**Unit tests** (`tests/test_results.py` - NEW FILE):

```python
"""Unit tests for result schemas."""

import pytest
from datetime import datetime, timezone

from rompy.core.responses import (
    TimingInfo, PipelineStage,
    PostprocessSuccess, PostprocessFailure, PostprocessResult,
    PipelineSuccess, PipelineFailure, PipelineResult,
    ModelRunResult
)


def test_timing_info_duration_computed():
    """Duration is computed from timestamps."""
    start = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 3, 10, 10, 5, 30, tzinfo=timezone.utc)
    
    timing = TimingInfo(start_time=start, end_time=end)
    
    assert timing.duration_seconds == 330.0


def test_postprocess_success_discriminator():
    """PostprocessSuccess has success=True."""
    result = PostprocessSuccess(
        run_id="test_run",
        output_dir="/output",
        validated=True,
        file_count=42
    )
    
    assert result.success is True
    assert result.file_count == 42


def test_postprocess_failure_discriminator():
    """PostprocessFailure has success=False."""
    result = PostprocessFailure(
        run_id="test_run",
        error="Test error"
    )
    
    assert result.success is False
    assert result.error == "Test error"


def test_postprocess_result_type_narrowing():
    """Type narrowing works with discriminator."""
    result: PostprocessResult = PostprocessSuccess(
        run_id="test", output_dir="/out", validated=True
    )
    
    if result.success:
        # Type checker knows: PostprocessSuccess
        assert result.validated is True
    else:
        # Type checker knows: PostprocessFailure
        pytest.fail("Should not reach here")


def test_pipeline_success_nests_postprocess_success():
    """PipelineSuccess nests PostprocessSuccess."""
    postprocess = PostprocessSuccess(
        run_id="test", output_dir="/out", validated=True
    )
    
    pipeline = PipelineSuccess(
        run_id="test",
        stages_completed=[PipelineStage.GENERATE, PipelineStage.RUN, PipelineStage.POSTPROCESS],
        backend="LocalConfig",
        processor="noop",
        staging_dir="/staging",
        output_dir="/out",
        postprocess_results=postprocess,
        timing=TimingInfo(
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc)
        )
    )
    
    assert pipeline.success is True
    assert pipeline.postprocess_results.success is True


def test_pipeline_failure_tracks_completed_stages():
    """PipelineFailure tracks which stages completed."""
    result = PipelineFailure(
        run_id="test",
        stages_completed=[PipelineStage.GENERATE],
        backend="LocalConfig",
        processor="noop",
        failed_stage=PipelineStage.RUN,
        error="Run failed"
    )
    
    assert result.success is False
    assert PipelineStage.GENERATE in result.stages_completed
    assert result.failed_stage == PipelineStage.RUN


def test_result_serialization_roundtrip():
    """Results can be serialized and deserialized."""
    original = PostprocessSuccess(
        run_id="test",
        output_dir="/out",
        validated=True,
        file_count=10
    )
    
    # Serialize to dict
    data = original.model_dump()
    assert data["success"] is True
    assert data["file_count"] == 10
    
    # Deserialize back
    reconstructed = PostprocessSuccess.model_validate(data)
    assert reconstructed.run_id == original.run_id
    assert reconstructed.file_count == original.file_count
```

**Integration tests** - Update existing tests in:
- `tests/test_model.py`: Update assertions for `postprocess()` and `pipeline()` return types
- `tests/test_pipeline.py`: Update pipeline execution tests
- `tests/test_postprocess.py`: Update postprocessor tests

**Example integration test update**:

```python
# Before
def test_pipeline_success(model_run, backend_config):
    results = model_run.pipeline(backend_config=backend_config)
    assert results.get("success") is True
    assert "stages_completed" in results

# After
from rompy.core.responses import PipelineSuccess

def test_pipeline_success(model_run, backend_config):
    result = model_run.pipeline(backend_config=backend_config)
    assert isinstance(result, PipelineSuccess)
    assert result.success is True
    assert PipelineStage.POSTPROCESS in result.stages_completed
    assert result.timing.duration_seconds > 0
```

## Migration Path

### For Internal Code (rompy itself)

**Step 1**: Create result schemas (`src/rompy/core/responses.py`)

**Step 2**: Update postprocessors first (smallest blast radius)
- Change `NoopPostprocessor.process()` return type
- Update any plugin postprocessors

**Step 3**: Update pipeline backends
- Change `LocalPipelineBackend.execute()` implementation

**Step 4**: Update ModelRun methods
- Add `run_detailed()` (non-breaking)
- Change `postprocess()` return type (breaking)
- Change `pipeline()` return type (breaking)

**Step 5**: Update CLI
- Replace `.get()` calls with attribute access
- Update logging statements

**Step 6**: Update tests
- Add unit tests for schemas
- Update integration test assertions

### For External Consumers

**Immediate** (v2.0.0):
- Calling `pipeline()` or `postprocess()` returns Pydantic models instead of dicts
- Use `.model_dump()` for backward compatibility if needed:
  ```python
  result = model_run.pipeline(...)
  legacy_dict = result.model_dump()  # Temporary migration aid
  ```

**Recommended Migration**:
```python
# Old code
results = model_run.pipeline(...)
if results.get("success"):
    output = results.get("postprocess_results", {}).get("output_dir")
    artifacts = results.get("postprocess_results", {}).get("artifacts", [])

# New code (type-safe)
results = model_run.pipeline(...)
if results.success:
    output = results.postprocess_results.output_dir
    artifacts = results.postprocess_results.artifacts
    
    # Access artifact details
    for artifact in artifacts:
        print(f"{artifact.artifact_type}: {artifact.path}")
```

**Gradual Migration Strategy** (as recommended in issue #15):

The GitHub issue recommends maintaining both dictionary and Pydantic return options initially. We propose:

1. **v2.0.0-alpha**: Full Pydantic returns, use `.model_dump()` for legacy code
2. **v2.0.0-beta**: Deprecation warnings for dict-based code patterns
3. **v2.0.0**: Stable release with Pydantic returns

**Alternative (more conservative)**: Add `return_format` parameter
```python
# Conservative backward-compat approach (optional, not recommended)
def pipeline(
    self,
    return_format: Literal["pydantic", "dict"] = "pydantic",
    **kwargs
) -> Union[PipelineResult, Dict[str, Any]]:
    result = self._execute_pipeline(...)
    if return_format == "dict":
        return result.model_dump()
    return result
```

**Recommendation**: Skip the `return_format` parameter approach. It adds complexity and delays migration. The `.model_dump()` method provides sufficient backward compatibility.

### For Plugin Authors (Postprocessors)

**Required changes**:

```python
# Old signature
def process(self, model_run, **kwargs) -> Dict[str, Any]:
    return {"success": True, "output_dir": "/out"}

# New signature
from rompy.core.responses import PostprocessResult, PostprocessSuccess

def process(self, model_run, **kwargs) -> PostprocessResult:
    return PostprocessSuccess(
        run_id=model_run.run_id,
        output_dir="/out",
        validated=True
    )
```

## Validation Strategy

### Schema Validation (Pydantic)

- Discriminator prevents invalid states (success=True with error field)
- Required fields enforced at construction
- Type validation for all fields

### Runtime Validation

- Pipeline backends validate stage progression (GENERATE → RUN → POSTPROCESS)
- Postprocessors validate output directories exist when validation enabled
- Timing validation: end_time >= start_time

### Test Coverage

1. **Unit tests** (new file `tests/test_results.py`):
   - Schema construction with valid data
   - Validation errors with invalid data
   - Discriminator-based type narrowing
   - Serialization/deserialization round-trips
   - Computed field calculations

2. **Integration tests** (update existing):
   - `tests/test_model.py`: ModelRun.postprocess(), .pipeline()
   - `tests/test_pipeline.py`: LocalPipelineBackend.execute()
   - `tests/test_postprocess.py`: NoopPostprocessor.process()
   - Test all failure modes (generate, run, postprocess failures)
   - Test cleanup tracking

3. **Type checking**:
   - Run mypy on updated code to verify type narrowing works
   - Ensure no type: ignore comments needed

## Performance Considerations

### Memory Overhead

Pydantic models have slightly higher memory overhead than raw dicts, but:
- Result objects are short-lived (single operation lifecycle)
- Nesting depth is shallow (max 2 levels: Pipeline → Postprocess)
- No performance-sensitive hot paths

**Verdict**: Negligible impact.

### Validation Overhead

Pydantic validates fields at construction:
- Only happens once per operation (not in loops)
- Most fields are simple types (str, bool, int)
- No external I/O during validation

**Verdict**: Negligible impact (<1ms per result object).

### Serialization Overhead

`.model_dump()` is slower than dict copy, but:
- Only needed for external consumers
- Internal code uses typed objects directly
- Can use `model_dump(mode='json')` for faster JSON-compatible output

**Verdict**: Acceptable for external API boundaries.

## Documentation Updates

### API Documentation

**Update docstrings**:
- `ModelRun.postprocess()`: Document `PostprocessResult` return type
- `ModelRun.pipeline()`: Document `PipelineResult` return type
- `ModelRun.run_detailed()`: Document new method

**Add module docstring** to `src/rompy/core/responses.py`:
```python
"""
Result schemas for rompy operations.

This module defines Pydantic models for structured result objects returned by
pipeline, postprocess, and run operations. All results use discriminated unions
to represent success/failure states with proper type safety.

Example:
    >>> result = model_run.pipeline(...)
    >>> if result.success:
    ...     print(f"Output: {result.postprocess_results.output_dir}")
    ... else:
    ...     print(f"Failed at {result.failed_stage.value}: {result.error}")
"""
```

### Migration Guide

**Add to docs/migration-v2.md** (new file):

- Breaking changes summary
- Code examples (before/after)
- Backward compatibility via `.model_dump()`
- Plugin author guidance

### User Documentation

**Update docs/usage.md**:
- Show new result object patterns
- Document type narrowing benefits
- Show serialization options

**Update docs/plugins.md**:
- Document `PostprocessResult` return requirement for postprocessors
- Provide base class example

## Backward Compatibility

### What Breaks

1. **Direct dict access**: `results["success"]` → `results.success`
2. **Postprocessor plugins**: Must return `PostprocessResult` instead of dict
3. **Type expectations**: Code expecting `Dict[str, Any]` must adapt

### Mitigation

1. **Temporary dict access**:
   ```python
   legacy_dict = result.model_dump()
   value = legacy_dict.get("key")  # Works during migration
   ```

2. **Plugin compatibility**:
   - Document migration path in CHANGELOG
   - Provide example conversions
   - Version constraint: rompy 2.x requires updated plugins

3. **Version signaling**:
   - Bump to v2.0.0 (major version change)
   - Update CHANGELOG with breaking changes
   - Tag release as v2.0.0-alpha for early testing

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Plugin breakage | High | Medium | Document migration, provide examples |
| Type checker false positives | Low | Low | Comprehensive type testing with mypy |
| Performance regression | Very Low | Low | Benchmark critical paths |
| Serialization format changes | Medium | Low | Test round-trip compatibility |
| External API breakage | High | Medium | `.model_dump()` backward compat |

## Open Questions

1. **Should we support `exclude_none=True` by default in serialization?**
   - Recommendation: No, let consumers specify when calling `.model_dump()`

2. **Should enum serialization use `.value` automatically?**
   - Recommendation: Yes, Pydantic handles this automatically for `str` enums

3. **Should we provide a base class for custom postprocessors?**
   - Recommendation: Yes, add `BasePostprocessor` abstract class in future PR

4. **Should `ModelRun.run()` eventually be deprecated?**
   - Recommendation: Not in v2.0.0. Consider for v3.0.0 or v2.1.0 after stabilization

## Success Criteria

- All result schemas defined in `src/rompy/core/responses.py`
- All method signatures updated with correct return types
- All existing tests pass with updated assertions
- New unit tests for result schemas achieve >95% coverage
- CLI successfully uses typed result objects
- No mypy type errors in updated code
- Documentation updated with migration guide
- CHANGELOG documents breaking changes

## References

- Issue #15: Implement Well-Defined Return Schemas Using Pydantic Models
- `SCHEMA_DESIGN.md`: Detailed schema design document
- Pydantic v2 docs: https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions
- rompy existing patterns: `RompyBaseModel` in `src/rompy/core/types.py`
