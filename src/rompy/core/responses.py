"""Response schemas for rompy operations.

This module defines strongly-typed Pydantic response models for all major
rompy operations, replacing dictionary returns with validated schemas.

The schemas use discriminated unions with a `success` field as the discriminator,
enabling type narrowing and type-safe access to success/failure-specific fields.

Examples:
    Basic usage with type narrowing::

        from rompy.core.responses import PostprocessResult, PostprocessSuccess

        result: PostprocessResult = postprocessor.process(model_run)

        if result.success:
            # Type narrowed to PostprocessSuccess
            print(f"Generated {len(result.artifacts)} artifacts")
            print(f"Output dir: {result.output_dir}")
        else:
            # Type narrowed to PostprocessFailure
            print(f"Failed: {result.error}")

    Artifact tracking::

        artifacts = [
            Artifact(
                path="output.nc",
                artifact_type=ArtifactType.NETCDF,
                size_bytes=1024000,
                description="Model output NetCDF"
            ),
            Artifact(
                path="wave_height.png",
                artifact_type=ArtifactType.PLOT,
                size_bytes=51200
            )
        ]

    Timing information::

        from datetime import datetime, timezone

        start = datetime.now(timezone.utc)
        # ... do work ...
        end = datetime.now(timezone.utc)

        timing = TimingInfo(start_time=start, end_time=end)
        print(f"Took {timing.duration_seconds:.2f} seconds")
"""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import Field, computed_field

from rompy.core.types import RompyBaseModel


class PipelineStage(str, Enum):
    """Pipeline execution stages.

    Attributes:
        GENERATE: Template generation stage
        RUN: Model execution stage
        POSTPROCESS: Output postprocessing stage
    """

    GENERATE = "generate"
    RUN = "run"
    POSTPROCESS = "postprocess"


class ArtifactType(str, Enum):
    """Types of artifacts generated during postprocessing.

    Attributes:
        YAML: YAML configuration or metadata files
        NETCDF: NetCDF data files (model output)
        PLOT: Plot/visualization files (PNG, PDF, SVG, etc.)
        TEXT: Text files (logs, reports, etc.)
        RESTART: Restart/checkpoint files for continuing a run
        OTHER: Other file types
    """

    YAML = "yaml"
    NETCDF = "netcdf"
    PLOT = "plot"
    TEXT = "text"
    RESTART = "restart"
    OTHER = "other"


class Artifact(RompyBaseModel):
    """Represents a file artifact generated during processing.

    Attributes:
        path: Absolute or relative path to artifact
        artifact_type: Type of artifact (yaml, netcdf, plot, etc.)
        size_bytes: File size in bytes (if available)
        description: Human-readable description of the artifact
    """

    path: str = Field(..., description="Absolute or relative path to artifact")
    artifact_type: Optional[ArtifactType] = Field(
        None, description="Type of artifact (yaml, netcdf, plot, etc.)"
    )
    size_bytes: Optional[int] = Field(None, description="File size in bytes")
    description: Optional[str] = Field(None, description="Human-readable description")
    date: Optional[str] = Field(
        None, description="Artifact timestamp in ISO 8601 format"
    )


class TimingInfo(RompyBaseModel):
    """Execution timing information.

    Captures start and end times (UTC) with a computed duration.

    Attributes:
        start_time: Operation start time (UTC)
        end_time: Operation end time (UTC)
        duration_seconds: Computed duration in seconds (read-only)

    Examples:
        ::

            from datetime import datetime, timezone

            start = datetime.now(timezone.utc)
            # ... do work ...
            end = datetime.now(timezone.utc)

            timing = TimingInfo(start_time=start, end_time=end)
            print(f"Duration: {timing.duration_seconds:.2f}s")
    """

    start_time: datetime = Field(..., description="Operation start time (UTC)")
    end_time: datetime = Field(..., description="Operation end time (UTC)")

    @computed_field
    @property
    def duration_seconds(self) -> float:
        """Computed duration in seconds."""
        return (self.end_time - self.start_time).total_seconds()


class PostprocessSuccess(RompyBaseModel):
    """Successful postprocessing result.

    Returned when postprocessing completes successfully, including validation
    of outputs and artifact tracking.

    Attributes:
        success: Always True for success cases
        run_id: Run identifier (from ModelRun)
        output_dir: Path to output directory
        validated: Whether output validation was performed
        file_count: Number of output files (if available)
        artifacts: List of generated artifacts with type classification
        message: Optional status message
        metadata: Processor-specific metadata (extensible dict)
        timing: Execution timing information
    """

    success: Literal[True] = Field(True, description="Always True for success")
    run_id: str = Field(..., description="Run identifier")
    output_dir: str = Field(..., description="Path to output directory")
    validated: bool = Field(..., description="Whether output validation was performed")
    file_count: Optional[int] = Field(None, description="Number of output files")
    artifacts: List[Artifact] = Field(
        default_factory=list,
        description="List of generated artifacts (YAML, NetCDF, plots, etc.)",
    )
    message: Optional[str] = Field(None, description="Status message")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Processor-specific metadata"
    )
    timing: Optional[TimingInfo] = Field(None, description="Execution timing")


class PostprocessFailure(RompyBaseModel):
    """Failed postprocessing result.

    Returned when postprocessing fails, including partial artifacts that may
    have been generated before the failure.

    Attributes:
        success: Always False for failure cases
        run_id: Run identifier (from ModelRun)
        error: Error message describing the failure
        output_dir: Path to output directory if located
        artifacts: Partial artifacts generated before failure
        message: Additional context about the failure
        metadata: Processor-specific metadata (extensible dict)
        timing: Execution timing information (if available)
    """

    success: Literal[False] = Field(False, description="Always False for failure")
    run_id: str = Field(..., description="Run identifier")
    error: str = Field(..., description="Error message")
    output_dir: Optional[str] = Field(
        None, description="Path to output directory if located"
    )
    artifacts: List[Artifact] = Field(
        default_factory=list, description="Partial artifacts generated before failure"
    )
    message: Optional[str] = Field(None, description="Additional context")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Processor-specific metadata"
    )
    timing: Optional[TimingInfo] = Field(None, description="Execution timing")


PostprocessResult = Annotated[
    Union[PostprocessSuccess, PostprocessFailure], Field(discriminator="success")
]
"""Discriminated union of PostprocessSuccess or PostprocessFailure.

The `success` field acts as a discriminator, enabling type narrowing:

Examples:
    ::
    
        result: PostprocessResult = postprocessor.process(model_run)
        
        if result.success:
            # Type checker knows this is PostprocessSuccess
            print(result.output_dir)  # OK
            print(result.artifacts)    # OK
        else:
            # Type checker knows this is PostprocessFailure
            print(result.error)        # OK
"""


class PipelineSuccess(RompyBaseModel):
    """Fully successful pipeline execution.

    Returned when all pipeline stages (generate → run → postprocess) complete
    successfully.

    Attributes:
        success: Always True for success cases
        run_id: Run identifier (from ModelRun)
        stages_completed: List of all completed stages (should be [GENERATE, RUN, POSTPROCESS])
        backend: Backend used for execution
        processor: Processor used for postprocessing
        staging_dir: Path to staging directory
        workspace_dir: Workspace directory (backend-specific)
        output_dir: Final output directory
        postprocess_results: Nested postprocessing results (PostprocessSuccess)
        timing: Total pipeline execution time
        message: Status message (default: "Pipeline completed successfully")
        metadata: Pipeline-specific metadata (extensible dict)
    """

    success: Literal[True] = Field(True, description="Always True for success")
    run_id: str = Field(..., description="Run identifier")
    stages_completed: List[PipelineStage] = Field(
        ..., description="All stages completed"
    )
    backend: str = Field(..., description="Backend used for execution")
    processor: str = Field(..., description="Processor used for postprocessing")
    staging_dir: str = Field(..., description="Path to staging directory")
    workspace_dir: Optional[str] = Field(None, description="Workspace directory")
    output_dir: str = Field(..., description="Final output directory")
    postprocess_results: PostprocessSuccess = Field(
        ..., description="Postprocessing results"
    )
    timing: TimingInfo = Field(..., description="Total pipeline execution time")
    message: Optional[str] = Field(
        "Pipeline completed successfully", description="Status message"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Pipeline-specific metadata"
    )


class PipelineFailure(RompyBaseModel):
    """Failed pipeline execution.

    Returned when any pipeline stage fails. Tracks which stage failed and which
    stages completed before the failure.

    Attributes:
        success: Always False for failure cases
        run_id: Run identifier (from ModelRun)
        stages_completed: Stages completed before failure
        backend: Backend used for execution
        processor: Processor used (or intended for) postprocessing
        failed_stage: Stage where failure occurred
        error: Error message describing the failure
        message: Additional context about the failure
        staging_dir: Staging directory if generated
        workspace_dir: Workspace directory if created
        output_dir: Output directory if any output generated
        postprocess_results: Postprocess failure details (if failed at postprocess stage)
        timing: Execution time until failure
        cleaned_up: Whether output was cleaned up after failure
        metadata: Pipeline-specific metadata (extensible dict)
    """

    success: Literal[False] = Field(False, description="Always False for failure")
    run_id: str = Field(..., description="Run identifier")
    stages_completed: List[PipelineStage] = Field(
        ..., description="Stages completed before failure"
    )
    backend: str = Field(..., description="Backend used for execution")
    processor: str = Field(..., description="Processor used for postprocessing")
    failed_stage: PipelineStage = Field(..., description="Stage where failure occurred")
    error: str = Field(..., description="Error message")
    message: Optional[str] = Field(None, description="Additional context")
    staging_dir: Optional[str] = Field(
        None, description="Staging directory if generated"
    )
    workspace_dir: Optional[str] = Field(
        None, description="Workspace directory if created"
    )
    output_dir: Optional[str] = Field(
        None, description="Output directory if any output generated"
    )
    postprocess_results: Optional[PostprocessFailure] = Field(
        None, description="Postprocess failure details"
    )
    timing: Optional[TimingInfo] = Field(
        None, description="Execution time until failure"
    )
    cleaned_up: bool = Field(
        False, description="Whether output was cleaned up after failure"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Pipeline-specific metadata"
    )


PipelineResult = Annotated[
    Union[PipelineSuccess, PipelineFailure], Field(discriminator="success")
]
"""Discriminated union of PipelineSuccess or PipelineFailure.

The `success` field acts as a discriminator, enabling type narrowing:

Examples:
    ::
    
        result: PipelineResult = model_run.pipeline()
        
        if result.success:
            # Type checker knows this is PipelineSuccess
            print(f"Stages: {[s.value for s in result.stages_completed]}")
            print(f"Output: {result.output_dir}")
            print(f"Artifacts: {len(result.postprocess_results.artifacts)}")
        else:
            # Type checker knows this is PipelineFailure
            print(f"Failed at stage: {result.failed_stage.value}")
            print(f"Error: {result.error}")
            if result.postprocess_results:
                print(f"Postprocess error: {result.postprocess_results.error}")
"""


class ModelRunResult(RompyBaseModel):
    """Result from model execution via a backend.

    Returned by `ModelRun.run_detailed()` to provide structured information
    about model execution (without postprocessing).

    Attributes:
        success: Whether execution succeeded
        run_id: Run identifier (from ModelRun)
        backend_used: Backend class name
        output_dir: Output directory path
        workspace_dir: Workspace directory (backend-specific)
        timing: Execution timing
        artifacts: List of output artifacts discovered after execution
        error: Error message if success=False
        message: Additional context
        metadata: Backend-specific metadata (extensible dict)

    Examples:
        ::

            result = model_run.run_detailed(backend_config)

            if result.success:
                print(f"Run completed in {result.timing.duration_seconds:.1f}s")
                print(f"Output: {result.output_dir}")
                print(f"Artifacts: {len(result.artifacts)}")
            else:
                print(f"Run failed: {result.error}")
    """

    success: bool = Field(..., description="Whether execution succeeded")
    run_id: str = Field(..., description="Run identifier")
    backend_used: str = Field(..., description="Backend class name")
    output_dir: str = Field(..., description="Output directory path")
    workspace_dir: Optional[str] = Field(None, description="Workspace directory")
    timing: TimingInfo = Field(..., description="Execution timing")
    artifacts: List[Artifact] = Field(
        default_factory=list,
        description="Output artifacts discovered after execution",
    )
    error: Optional[str] = Field(None, description="Error message if success=False")
    message: Optional[str] = Field(None, description="Additional context")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Backend-specific metadata"
    )
