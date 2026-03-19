"""Tests for rompy.core.result_persistence module.

Tests atomic write/read operations, schema validation, and error handling
for all three sidecar types (generate, run, postprocess).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rompy.core.responses import (
    Artifact,
    ArtifactType,
    GenerateResult,
    GenerateResultSidecar,
    ModelRunResult,
    NormalizedContext,
    PostprocessFailure,
    PostprocessResultSidecar,
    PostprocessSuccess,
    RunResultSidecar,
    TimingInfo,
)
from rompy.core.result_persistence import (
    GENERATE_RESULT_FILENAME,
    POSTPROCESS_RESULT_FILENAME,
    RUN_RESULT_FILENAME,
    load_generate_result,
    load_postprocess_result,
    load_run_result,
    write_generate_result,
    write_postprocess_result,
    write_run_result,
)


@pytest.fixture
def staging_dir(tmp_path):
    return tmp_path / "staging"


@pytest.fixture
def sample_generate_sidecar():
    return GenerateResultSidecar(
        created_at=datetime.now(timezone.utc),
        run_id="test-run-123",
        staging_dir="/tmp/staging",
        status="success",
        success=True,
        payload=GenerateResult(
            generated_at=datetime.now(timezone.utc),
            staging_dir="/tmp/staging",
            config_file="ww3_shel.nml",
            success=True,
            generated_files=["ww3_shel.nml", "mod_def.ww3"],
        ),
    )


@pytest.fixture
def sample_run_sidecar():
    return RunResultSidecar(
        created_at=datetime.now(timezone.utc),
        run_id="test-run-456",
        staging_dir="/tmp/staging",
        status="success",
        success=True,
        payload=ModelRunResult(
            run_id="test-run-456",
            success=True,
            backend_used="LocalBackend",
            output_dir="/tmp/staging",
            timing=TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            ),
        ),
    )


@pytest.fixture
def sample_postprocess_sidecar_success():
    return PostprocessResultSidecar(
        created_at=datetime.now(timezone.utc),
        run_id="test-run-789",
        staging_dir="/tmp/staging",
        status="success",
        success=True,
        payload=PostprocessSuccess(
            success=True,
            run_id="test-run-789",
            output_dir="/tmp/staging",
            validated=True,
            file_count=5,
            artifacts=[
                Artifact(
                    path="output.nc",
                    artifact_type=ArtifactType.NETCDF,
                    size_bytes=1024,
                    description="Model output",
                )
            ],
            timing=TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            ),
        ),
    )


@pytest.fixture
def sample_postprocess_sidecar_failure():
    return PostprocessResultSidecar(
        created_at=datetime.now(timezone.utc),
        run_id="test-run-999",
        staging_dir="/tmp/staging",
        status="failed",
        success=False,
        error="Transfer failed",
        payload=PostprocessFailure(
            success=False,
            run_id="test-run-999",
            error="Transfer failed",
            output_dir="/tmp/staging",
            timing=TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            ),
        ),
    )


def test_write_and_load_generate_result(staging_dir, sample_generate_sidecar):
    written_path = write_generate_result(staging_dir, sample_generate_sidecar)

    assert written_path.exists()
    assert written_path.name == GENERATE_RESULT_FILENAME

    loaded = load_generate_result(staging_dir)

    assert loaded.run_id == sample_generate_sidecar.run_id
    assert loaded.success == sample_generate_sidecar.success
    assert loaded.payload.success == sample_generate_sidecar.payload.success
    assert loaded.payload.config_file == sample_generate_sidecar.payload.config_file


def test_write_and_load_run_result(staging_dir, sample_run_sidecar):
    written_path = write_run_result(staging_dir, sample_run_sidecar)

    assert written_path.exists()
    assert written_path.name == RUN_RESULT_FILENAME

    loaded = load_run_result(staging_dir)

    assert loaded.run_id == sample_run_sidecar.run_id
    assert loaded.success == sample_run_sidecar.success
    assert loaded.payload.run_id == sample_run_sidecar.payload.run_id
    assert loaded.payload.success == sample_run_sidecar.payload.success


def test_write_and_load_postprocess_success(
    staging_dir, sample_postprocess_sidecar_success
):
    written_path = write_postprocess_result(
        staging_dir, sample_postprocess_sidecar_success
    )

    assert written_path.exists()
    assert written_path.name == POSTPROCESS_RESULT_FILENAME

    loaded = load_postprocess_result(staging_dir)

    assert loaded.run_id == sample_postprocess_sidecar_success.run_id
    assert loaded.success == sample_postprocess_sidecar_success.success
    assert loaded.payload.success is True
    assert loaded.payload.run_id == sample_postprocess_sidecar_success.payload.run_id


def test_write_and_load_postprocess_failure(
    staging_dir, sample_postprocess_sidecar_failure
):
    written_path = write_postprocess_result(
        staging_dir, sample_postprocess_sidecar_failure
    )

    assert written_path.exists()
    assert written_path.name == POSTPROCESS_RESULT_FILENAME

    loaded = load_postprocess_result(staging_dir)

    assert loaded.run_id == sample_postprocess_sidecar_failure.run_id
    assert loaded.success is False
    assert loaded.payload.success is False
    assert loaded.payload.error == "Transfer failed"


def test_load_from_file_path_directly(staging_dir, sample_generate_sidecar):
    written_path = write_generate_result(staging_dir, sample_generate_sidecar)

    loaded = load_generate_result(written_path)

    assert loaded.run_id == sample_generate_sidecar.run_id


def test_load_missing_file_raises_file_not_found(staging_dir):
    with pytest.raises(FileNotFoundError, match="Generate result sidecar not found"):
        load_generate_result(staging_dir)


def test_load_wrong_schema_version_raises_value_error(
    staging_dir, sample_generate_sidecar
):
    written_path = write_generate_result(staging_dir, sample_generate_sidecar)

    raw = json.loads(written_path.read_text())
    raw["schema_version"] = 99
    written_path.write_text(json.dumps(raw, indent=2))

    with pytest.raises(ValueError, match="Unsupported schema_version: 99"):
        load_generate_result(staging_dir)


def test_load_wrong_kind_raises_value_error(staging_dir, sample_generate_sidecar):
    written_path = write_generate_result(staging_dir, sample_generate_sidecar)

    raw = json.loads(written_path.read_text())
    raw["kind"] = "wrong_kind"
    written_path.write_text(json.dumps(raw, indent=2))

    with pytest.raises(ValueError, match="Invalid kind field: 'wrong_kind'"):
        load_generate_result(staging_dir)


def test_written_file_is_valid_json(staging_dir, sample_generate_sidecar):
    written_path = write_generate_result(staging_dir, sample_generate_sidecar)

    raw = json.loads(written_path.read_text())

    assert raw["kind"] == "generate_result"
    assert raw["schema_version"] == 2
    assert raw["run_id"] == "test-run-123"
    assert raw["success"] is True


def test_duration_seconds_stripped_from_timing(staging_dir, sample_run_sidecar):
    written_path = write_run_result(staging_dir, sample_run_sidecar)

    raw = json.loads(written_path.read_text())

    payload_timing = raw.get("payload", {}).get("timing", {})
    assert "duration_seconds" not in payload_timing


def test_atomic_write_creates_parent_directory():
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        deep_path = Path(tmpdir) / "a" / "b" / "c" / "staging"

        sidecar = GenerateResultSidecar(
            created_at=datetime.now(timezone.utc),
            run_id="test-deep",
            staging_dir=str(deep_path),
            status="success",
            success=True,
            payload=GenerateResult(
                generated_at=datetime.now(timezone.utc),
                staging_dir=str(deep_path),
                success=True,
                generated_files=[],
            ),
        )

        written_path = write_generate_result(deep_path, sidecar)

        assert written_path.exists()
        assert written_path.parent == deep_path


def test_run_result_loader_accepts_directory(staging_dir, sample_run_sidecar):
    write_run_result(staging_dir, sample_run_sidecar)

    loaded = load_run_result(staging_dir)

    assert loaded.run_id == sample_run_sidecar.run_id


def test_postprocess_result_loader_accepts_file(
    staging_dir, sample_postprocess_sidecar_success
):
    written_path = write_postprocess_result(
        staging_dir, sample_postprocess_sidecar_success
    )

    loaded = load_postprocess_result(written_path)

    assert loaded.run_id == sample_postprocess_sidecar_success.run_id


def test_v2_generate_result_with_normalized_context(staging_dir):
    """Test v2 GenerateResultSidecar with NormalizedContext roundtrip."""
    normalized_ctx = NormalizedContext(
        model_type="ww3",
        period_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2024, 1, 2, tzinfo=timezone.utc),
        output_dir="/tmp/output",
        staging_dir="/tmp/staging",
        config_hash="abc123def456",
        extensions={"ww3_version": "6.07.1", "custom_field": "value"},
    )

    sidecar = GenerateResultSidecar(
        created_at=datetime.now(timezone.utc),
        run_id="test-v2-gen",
        staging_dir="/tmp/staging",
        status="success",
        success=True,
        normalized_context=normalized_ctx,
        payload=GenerateResult(
            generated_at=datetime.now(timezone.utc),
            staging_dir="/tmp/staging",
            config_file="ww3_shel.nml",
            success=True,
            generated_files=["ww3_shel.nml"],
        ),
    )

    written_path = write_generate_result(staging_dir, sidecar)
    assert written_path.exists()

    raw = json.loads(written_path.read_text())
    assert raw["schema_version"] == 2
    assert raw["normalized_context"] is not None
    assert raw["normalized_context"]["model_type"] == "ww3"
    assert raw["normalized_context"]["config_hash"] == "abc123def456"

    loaded = load_generate_result(staging_dir)
    assert loaded.schema_version == 2
    assert loaded.normalized_context is not None
    assert loaded.normalized_context.model_type == "ww3"
    assert loaded.normalized_context.period_start == normalized_ctx.period_start
    assert loaded.normalized_context.period_end == normalized_ctx.period_end
    assert loaded.normalized_context.output_dir == "/tmp/output"
    assert loaded.normalized_context.staging_dir == "/tmp/staging"
    assert loaded.normalized_context.config_hash == "abc123def456"
    assert loaded.normalized_context.extensions == {
        "ww3_version": "6.07.1",
        "custom_field": "value",
    }


def test_v2_run_result_with_normalized_context(staging_dir):
    """Test v2 RunResultSidecar with NormalizedContext roundtrip."""
    normalized_ctx = NormalizedContext(
        model_type="swan",
        period_start=datetime(2024, 2, 1, tzinfo=timezone.utc),
        period_end=datetime(2024, 2, 3, tzinfo=timezone.utc),
        output_dir="/tmp/run_output",
        staging_dir="/tmp/run_staging",
        config_hash="fedcba654321",
        extensions={"swan_version": "41.31"},
    )

    sidecar = RunResultSidecar(
        created_at=datetime.now(timezone.utc),
        run_id="test-v2-run",
        staging_dir="/tmp/run_staging",
        status="success",
        success=True,
        normalized_context=normalized_ctx,
        payload=ModelRunResult(
            run_id="test-v2-run",
            success=True,
            backend_used="LocalBackend",
            output_dir="/tmp/run_output",
            timing=TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            ),
        ),
    )

    written_path = write_run_result(staging_dir, sidecar)
    assert written_path.exists()

    raw = json.loads(written_path.read_text())
    assert raw["schema_version"] == 2
    assert raw["normalized_context"] is not None
    assert raw["normalized_context"]["model_type"] == "swan"

    loaded = load_run_result(staging_dir)
    assert loaded.schema_version == 2
    assert loaded.normalized_context is not None
    assert loaded.normalized_context.model_type == "swan"
    assert loaded.normalized_context.config_hash == "fedcba654321"
    assert loaded.normalized_context.extensions == {"swan_version": "41.31"}


def test_v1_backward_compatibility_run_result(staging_dir):
    """Test that v1 RunResultSidecar JSON loads correctly without normalized_context."""
    v1_json = {
        "kind": "run_result",
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id": "test-v1-compat",
        "staging_dir": "/tmp/v1_staging",
        "status": "success",
        "success": True,
        "payload": {
            "run_id": "test-v1-compat",
            "success": True,
            "backend_used": "LocalBackend",
            "output_dir": "/tmp/v1_staging",
            "timing": {
                "start_time": datetime.now(timezone.utc).isoformat(),
                "end_time": datetime.now(timezone.utc).isoformat(),
            },
            "artifacts": [],
            "metadata": {},
        },
    }

    staging_dir.mkdir(parents=True, exist_ok=True)
    v1_path = staging_dir / RUN_RESULT_FILENAME
    v1_path.write_text(json.dumps(v1_json, indent=2))

    loaded = load_run_result(staging_dir)
    assert loaded.schema_version == 1
    assert loaded.normalized_context is None
    assert loaded.success is True
    assert loaded.run_id == "test-v1-compat"


def test_v1_backward_compatibility_generate_result(staging_dir):
    """Test that v1 GenerateResultSidecar JSON loads correctly without normalized_context."""
    v1_json = {
        "kind": "generate_result",
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id": "test-v1-gen-compat",
        "staging_dir": "/tmp/v1_gen_staging",
        "status": "success",
        "success": True,
        "payload": {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "staging_dir": "/tmp/v1_gen_staging",
            "config_file": "test.nml",
            "success": True,
            "generated_files": ["test.nml"],
        },
    }

    staging_dir.mkdir(parents=True, exist_ok=True)
    v1_path = staging_dir / GENERATE_RESULT_FILENAME
    v1_path.write_text(json.dumps(v1_json, indent=2))

    loaded = load_generate_result(staging_dir)
    assert loaded.schema_version == 1
    assert loaded.normalized_context is None
    assert loaded.success is True
    assert loaded.run_id == "test-v1-gen-compat"
