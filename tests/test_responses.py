"""Unit tests for rompy response schemas (src/rompy/core/responses.py)."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from rompy.core.responses import (
    Artifact,
    ArtifactType,
    ModelRunResult,
    PipelineFailure,
    PipelineResult,
    PipelineStage,
    PipelineSuccess,
    PostprocessFailure,
    PostprocessResult,
    PostprocessSuccess,
    TimingInfo,
)


class TestArtifactType:
    """Test ArtifactType enum."""

    def test_enum_values(self):
        """Test all enum values are present."""
        assert ArtifactType.YAML == "yaml"
        assert ArtifactType.NETCDF == "netcdf"
        assert ArtifactType.PLOT == "plot"
        assert ArtifactType.TEXT == "text"
        assert ArtifactType.RESTART == "restart"
        assert ArtifactType.OTHER == "other"

    def test_enum_iteration(self):
        """Test enum can be iterated."""
        values = [e.value for e in ArtifactType]
        assert values == ["yaml", "netcdf", "plot", "text", "restart", "other"]


class TestPipelineStage:
    """Test PipelineStage enum."""

    def test_enum_values(self):
        """Test all enum values are present."""
        assert PipelineStage.GENERATE == "generate"
        assert PipelineStage.RUN == "run"
        assert PipelineStage.POSTPROCESS == "postprocess"

    def test_enum_iteration(self):
        """Test enum can be iterated."""
        values = [e.value for e in PipelineStage]
        assert values == ["generate", "run", "postprocess"]


class TestArtifact:
    """Test Artifact class."""

    def test_minimal_artifact(self):
        """Test artifact with only required fields."""
        artifact = Artifact(path="/path/to/file.nc")
        assert artifact.path == "/path/to/file.nc"
        assert artifact.artifact_type is None
        assert artifact.size_bytes is None
        assert artifact.description is None

    def test_full_artifact(self):
        """Test artifact with all fields."""
        artifact = Artifact(
            path="/path/to/file.nc",
            artifact_type=ArtifactType.NETCDF,
            size_bytes=1024000,
            description="Model output NetCDF file",
        )
        assert artifact.path == "/path/to/file.nc"
        assert artifact.artifact_type == ArtifactType.NETCDF
        assert artifact.size_bytes == 1024000
        assert artifact.description == "Model output NetCDF file"

    def test_artifact_serialization(self):
        """Test artifact can be serialized to dict/JSON."""
        artifact = Artifact(
            path="output.nc",
            artifact_type=ArtifactType.NETCDF,
            size_bytes=2048,
        )
        data = artifact.model_dump()
        assert data["path"] == "output.nc"
        assert data["artifact_type"] == "netcdf"
        assert data["size_bytes"] == 2048

        # Test JSON serialization
        json_str = artifact.model_dump_json()
        assert '"path":"output.nc"' in json_str or '"path": "output.nc"' in json_str

    def test_artifact_deserialization(self):
        """Test artifact can be deserialized from dict."""
        data = {
            "path": "plot.png",
            "artifact_type": "plot",
            "size_bytes": 51200,
            "description": "Wave height plot",
        }
        artifact = Artifact.model_validate(data)
        assert artifact.path == "plot.png"
        assert artifact.artifact_type == ArtifactType.PLOT
        assert artifact.size_bytes == 51200


class TestTimingInfo:
    """Test TimingInfo class with computed duration."""

    def test_duration_computation(self):
        """Test duration_seconds is correctly computed."""
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 12, 5, 30, tzinfo=timezone.utc)
        timing = TimingInfo(start_time=start, end_time=end)

        assert timing.start_time == start
        assert timing.end_time == end
        assert timing.duration_seconds == 330.0  # 5 minutes 30 seconds

    def test_duration_milliseconds(self):
        """Test duration works with sub-second precision."""
        start = datetime(2024, 1, 1, 12, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 12, 0, 0, 500000, tzinfo=timezone.utc)
        timing = TimingInfo(start_time=start, end_time=end)

        assert timing.duration_seconds == 0.5

    def test_duration_serialization(self):
        """Test computed field is included in serialization."""
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 12, 1, 0, tzinfo=timezone.utc)
        timing = TimingInfo(start_time=start, end_time=end)

        data = timing.model_dump()
        assert "duration_seconds" in data
        assert data["duration_seconds"] == 60.0

    def test_timing_with_timedelta(self):
        """Test timing with various durations."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=2, minutes=30, seconds=45)
        timing = TimingInfo(start_time=start, end_time=end)

        expected = (2 * 3600) + (30 * 60) + 45
        assert timing.duration_seconds == expected


class TestPostprocessResult:
    """Test PostprocessResult discriminated union."""

    def test_success_discriminator(self):
        """Test discriminator enables type narrowing with success=True."""
        result = PostprocessSuccess(
            run_id="test-123",
            output_dir="/output",
            validated=True,
            file_count=5,
        )

        assert result.success is True
        assert isinstance(result, PostprocessSuccess)
        # Type narrowing: can access success-specific fields
        assert result.output_dir == "/output"
        assert result.file_count == 5

    def test_failure_discriminator(self):
        """Test discriminator enables type narrowing with success=False."""
        result = PostprocessFailure(
            run_id="test-123",
            error="Validation failed",
        )

        assert result.success is False
        assert isinstance(result, PostprocessFailure)
        # Type narrowing: can access failure-specific fields
        assert result.error == "Validation failed"

    def test_success_with_artifacts(self):
        """Test PostprocessSuccess with artifacts."""
        artifacts = [
            Artifact(path="output.nc", artifact_type=ArtifactType.NETCDF),
            Artifact(path="plot.png", artifact_type=ArtifactType.PLOT),
        ]
        result = PostprocessSuccess(
            run_id="test-123",
            output_dir="/output",
            validated=True,
            artifacts=artifacts,
        )

        assert len(result.artifacts) == 2
        assert result.artifacts[0].artifact_type == ArtifactType.NETCDF
        assert result.artifacts[1].artifact_type == ArtifactType.PLOT

    def test_failure_with_partial_artifacts(self):
        """Test PostprocessFailure can include partial artifacts."""
        partial_artifacts = [
            Artifact(path="partial.nc", artifact_type=ArtifactType.NETCDF),
        ]
        result = PostprocessFailure(
            run_id="test-123",
            error="Processing failed midway",
            artifacts=partial_artifacts,
        )

        assert len(result.artifacts) == 1
        assert result.error == "Processing failed midway"

    def test_success_with_timing(self):
        """Test PostprocessSuccess with timing information."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(seconds=45)
        timing = TimingInfo(start_time=start, end_time=end)

        result = PostprocessSuccess(
            run_id="test-123",
            output_dir="/output",
            validated=True,
            timing=timing,
        )

        assert result.timing is not None
        assert result.timing.duration_seconds == 45.0

    def test_postprocess_serialization_roundtrip(self):
        """Test PostprocessResult can be serialized and deserialized."""
        original = PostprocessSuccess(
            run_id="test-123",
            output_dir="/output",
            validated=True,
            file_count=3,
            message="All good",
        )

        # Serialize to dict
        data = original.model_dump()
        assert data["success"] is True
        assert data["run_id"] == "test-123"

        # Deserialize back (Pydantic will use discriminator)
        reconstructed = PostprocessSuccess.model_validate(data)
        assert reconstructed.run_id == original.run_id
        assert reconstructed.success is True


class TestPipelineResult:
    """Test PipelineResult discriminated union."""

    def test_pipeline_success(self):
        """Test PipelineSuccess with nested postprocess results."""
        postprocess_result = PostprocessSuccess(
            run_id="test-123",
            output_dir="/output",
            validated=True,
        )

        start = datetime.now(timezone.utc)
        end = start + timedelta(minutes=5)
        timing = TimingInfo(start_time=start, end_time=end)

        result = PipelineSuccess(
            run_id="test-123",
            stages_completed=[
                PipelineStage.GENERATE,
                PipelineStage.RUN,
                PipelineStage.POSTPROCESS,
            ],
            backend="LocalRunBackend",
            processor="NoopPostprocessor",
            staging_dir="/staging",
            output_dir="/output",
            postprocess_results=postprocess_result,
            timing=timing,
        )

        assert result.success is True
        assert len(result.stages_completed) == 3
        assert PipelineStage.POSTPROCESS in result.stages_completed
        assert result.postprocess_results.validated is True

    def test_pipeline_failure_at_run_stage(self):
        """Test PipelineFailure when run stage fails."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(seconds=30)
        timing = TimingInfo(start_time=start, end_time=end)

        result = PipelineFailure(
            run_id="test-123",
            stages_completed=[PipelineStage.GENERATE],
            backend="DockerRunBackend",
            processor="NoopPostprocessor",
            failed_stage=PipelineStage.RUN,
            error="Docker container failed",
            timing=timing,
        )

        assert result.success is False
        assert result.failed_stage == PipelineStage.RUN
        assert PipelineStage.RUN not in result.stages_completed
        assert result.postprocess_results is None

    def test_pipeline_failure_at_postprocess_stage(self):
        """Test PipelineFailure when postprocess stage fails."""
        postprocess_failure = PostprocessFailure(
            run_id="test-123",
            error="Validation failed",
        )

        result = PipelineFailure(
            run_id="test-123",
            stages_completed=[PipelineStage.GENERATE, PipelineStage.RUN],
            backend="LocalRunBackend",
            processor="NoopPostprocessor",
            failed_stage=PipelineStage.POSTPROCESS,
            error="Postprocessing failed",
            postprocess_results=postprocess_failure,
        )

        assert result.success is False
        assert result.failed_stage == PipelineStage.POSTPROCESS
        assert result.postprocess_results is not None
        assert result.postprocess_results.error == "Validation failed"

    def test_pipeline_cleanup_tracking(self):
        """Test pipeline tracks cleanup status."""
        result = PipelineFailure(
            run_id="test-123",
            stages_completed=[],
            backend="LocalRunBackend",
            processor="NoopPostprocessor",
            failed_stage=PipelineStage.GENERATE,
            error="Template generation failed",
            cleaned_up=True,
        )

        assert result.cleaned_up is True

    def test_pipeline_stages_enum_serialization(self):
        """Test PipelineStage enum serializes correctly."""
        result = PipelineSuccess(
            run_id="test-123",
            stages_completed=[PipelineStage.GENERATE, PipelineStage.RUN],
            backend="LocalRunBackend",
            processor="NoopPostprocessor",
            staging_dir="/staging",
            output_dir="/output",
            postprocess_results=PostprocessSuccess(
                run_id="test-123",
                output_dir="/output",
                validated=False,
            ),
            timing=TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            ),
        )

        data = result.model_dump()
        assert data["stages_completed"] == ["generate", "run"]

    def test_nested_postprocess_artifact_access(self):
        """Test accessing artifacts through nested postprocess results."""
        artifacts = [
            Artifact(path="output1.nc", artifact_type=ArtifactType.NETCDF),
            Artifact(path="output2.nc", artifact_type=ArtifactType.NETCDF),
        ]

        postprocess_result = PostprocessSuccess(
            run_id="test-123",
            output_dir="/output",
            validated=True,
            artifacts=artifacts,
        )

        pipeline_result = PipelineSuccess(
            run_id="test-123",
            stages_completed=[
                PipelineStage.GENERATE,
                PipelineStage.RUN,
                PipelineStage.POSTPROCESS,
            ],
            backend="LocalRunBackend",
            processor="NoopPostprocessor",
            staging_dir="/staging",
            output_dir="/output",
            postprocess_results=postprocess_result,
            timing=TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            ),
        )

        # Access artifacts through nesting
        assert len(pipeline_result.postprocess_results.artifacts) == 2


class TestModelRunResult:
    """Test ModelRunResult schema."""

    def test_successful_run(self):
        """Test ModelRunResult for successful execution."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(minutes=2)
        timing = TimingInfo(start_time=start, end_time=end)

        result = ModelRunResult(
            success=True,
            run_id="test-123",
            backend_used="LocalRunBackend",
            output_dir="/output",
            timing=timing,
        )

        assert result.success is True
        assert result.backend_used == "LocalRunBackend"
        assert result.error is None

    def test_failed_run(self):
        """Test ModelRunResult for failed execution."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(seconds=10)
        timing = TimingInfo(start_time=start, end_time=end)

        result = ModelRunResult(
            success=False,
            run_id="test-123",
            backend_used="DockerRunBackend",
            output_dir="/output",
            timing=timing,
            error="Container failed to start",
        )

        assert result.success is False
        assert result.error == "Container failed to start"

    def test_run_with_metadata(self):
        """Test ModelRunResult with backend metadata."""
        result = ModelRunResult(
            success=True,
            run_id="test-123",
            backend_used="SlurmRunBackend",
            output_dir="/output",
            timing=TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            ),
            metadata={
                "job_id": "12345",
                "partition": "compute",
                "nodes": 2,
            },
        )

        assert result.metadata["job_id"] == "12345"
        assert result.metadata["nodes"] == 2

    def test_artifacts_default_empty(self):
        """Test ModelRunResult artifacts defaults to empty list."""
        result = ModelRunResult(
            success=True,
            run_id="test-123",
            backend_used="LocalRunBackend",
            output_dir="/output",
            timing=TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            ),
        )

        assert result.artifacts == []


class TestValidation:
    """Test validation errors for invalid data."""

    def test_postprocess_success_requires_run_id(self):
        """Test PostprocessSuccess requires run_id."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            PostprocessSuccess(
                output_dir="/output",
                validated=True,
                # Missing run_id
            )

    def test_timing_requires_both_times(self):
        """Test TimingInfo requires both start and end times."""
        with pytest.raises(Exception):
            TimingInfo(
                start_time=datetime.now(timezone.utc),
                # Missing end_time
            )

    def test_pipeline_failure_requires_failed_stage(self):
        """Test PipelineFailure requires failed_stage."""
        with pytest.raises(Exception):
            PipelineFailure(
                run_id="test-123",
                stages_completed=[],
                backend="LocalRunBackend",
                processor="NoopPostprocessor",
                error="Some error",
                # Missing failed_stage
            )

    def test_artifact_requires_path(self):
        """Test Artifact requires path field."""
        with pytest.raises(Exception):
            Artifact(
                artifact_type=ArtifactType.NETCDF,
                # Missing path
            )


class TestTypeNarrowing:
    """Test discriminator enables type narrowing."""

    def test_postprocess_type_narrowing_success(self):
        """Test type narrowing with success=True."""
        result: PostprocessResult = PostprocessSuccess(
            run_id="test-123",
            output_dir="/output",
            validated=True,
        )

        # Type narrowing based on success field
        if result.success:
            # Type checker knows this is PostprocessSuccess
            assert result.output_dir == "/output"
            assert result.validated is True
        else:
            # This branch shouldn't execute
            pytest.fail("Should not reach here")

    def test_postprocess_type_narrowing_failure(self):
        """Test type narrowing with success=False."""
        result: PostprocessResult = PostprocessFailure(
            run_id="test-123",
            error="Something went wrong",
        )

        # Type narrowing based on success field
        if result.success:
            # This branch shouldn't execute
            pytest.fail("Should not reach here")
        else:
            # Type checker knows this is PostprocessFailure
            assert result.error == "Something went wrong"

    def test_pipeline_type_narrowing(self):
        """Test type narrowing for PipelineResult."""
        failure: PipelineResult = PipelineFailure(
            run_id="test-123",
            stages_completed=[],
            backend="LocalRunBackend",
            processor="NoopPostprocessor",
            failed_stage=PipelineStage.RUN,
            error="Run failed",
        )

        if failure.success:
            pytest.fail("Should not reach here")
        else:
            # Type narrowed to PipelineFailure
            assert failure.failed_stage == PipelineStage.RUN


class TestSerialization:
    """Test serialization and deserialization."""

    def test_json_serialization(self):
        """Test all schemas can serialize to JSON."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(seconds=30)

        postprocess = PostprocessSuccess(
            run_id="test-123",
            output_dir="/output",
            validated=True,
            timing=TimingInfo(start_time=start, end_time=end),
        )

        json_str = postprocess.model_dump_json()
        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["run_id"] == "test-123"
        assert data["success"] is True

    def test_dict_serialization(self):
        """Test all schemas can serialize to dict."""
        pipeline = PipelineSuccess(
            run_id="test-123",
            stages_completed=[PipelineStage.GENERATE],
            backend="LocalRunBackend",
            processor="NoopPostprocessor",
            staging_dir="/staging",
            output_dir="/output",
            postprocess_results=PostprocessSuccess(
                run_id="test-123",
                output_dir="/output",
                validated=True,
            ),
            timing=TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            ),
        )

        data = pipeline.model_dump()
        assert data["backend"] == "LocalRunBackend"
        assert "postprocess_results" in data

    def test_deserialization_from_dict(self):
        """Test deserialization from dict preserves structure."""
        original = PostprocessSuccess(
            run_id="test-123",
            output_dir="/output",
            validated=True,
            artifacts=[Artifact(path="file.nc", artifact_type=ArtifactType.NETCDF)],
        )

        # Serialize and deserialize
        data = original.model_dump()
        reconstructed = PostprocessSuccess.model_validate(data)

        assert reconstructed.run_id == original.run_id
        assert len(reconstructed.artifacts) == len(original.artifacts)
        assert reconstructed.artifacts[0].path == "file.nc"
