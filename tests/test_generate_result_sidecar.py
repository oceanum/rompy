"""Tests for generate result sidecar writing in ModelRun.generate().

Tests that generate() writes generate_result.json sidecar with:
- Success case: sidecar contains generated_files list and success=True
- Failure case: sidecar with success=False (if staging_dir is resolved)
- File discovery: generated_files contains actual files in staging_dir
- Atomic write: sidecar persisted via result_persistence helpers
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from rompy.core.result_persistence import GENERATE_RESULT_FILENAME, load_generate_result
from rompy.model import ModelRun
from rompy.core.config import BaseConfig
from rompy.core.time import TimeRange


@pytest.fixture
def tmp_model_run(tmp_path):
    """Create a ModelRun instance with tmp_path as output_dir."""
    return ModelRun(
        run_id="test-generate-123",
        period=TimeRange(
            start=datetime(2020, 1, 1, 0, 0, 0),
            end=datetime(2020, 1, 2, 0, 0, 0),
            interval="1H",
        ),
        output_dir=tmp_path / "output",
        config=BaseConfig(),
    )


def test_generate_writes_sidecar_on_success(tmp_model_run):
    """Test that successful generate() writes generate_result.json."""
    with patch.object(tmp_model_run.config.__class__, "render", return_value=None):
        staging_dir = tmp_model_run.staging_dir
        (staging_dir / "config.nml").write_text("test config")
        (staging_dir / "input.dat").write_text("test data")

        result_path = tmp_model_run.generate()

        sidecar_path = result_path / GENERATE_RESULT_FILENAME
        assert sidecar_path.exists(), "generate_result.json should be written"

        sidecar = load_generate_result(result_path)

        assert sidecar.success is True
        assert sidecar.run_id == "test-generate-123"
        assert sidecar.staging_dir == str(result_path)
        assert sidecar.status == "success"
        assert sidecar.kind == "generate_result"
        assert sidecar.schema_version == 1

        assert sidecar.payload.success is True
        assert sidecar.payload.staging_dir == str(result_path)
        assert len(sidecar.payload.generated_files) >= 2
        assert "config.nml" in sidecar.payload.generated_files
        assert "input.dat" in sidecar.payload.generated_files


def test_generate_sidecar_contains_all_generated_files(tmp_model_run):
    """Test that generated_files list contains all files in staging_dir."""
    with patch.object(tmp_model_run.config.__class__, "render", return_value=None):
        staging_dir = tmp_model_run.staging_dir

        test_files = ["file1.txt", "file2.nml", "file3.dat", "file4.nc"]
        for filename in test_files:
            (staging_dir / filename).write_text(f"content of {filename}")

        tmp_model_run.generate()

        sidecar = load_generate_result(staging_dir)

        for filename in test_files:
            assert filename in sidecar.payload.generated_files


def test_generate_sidecar_has_timestamps(tmp_model_run):
    """Test that sidecar contains UTC timestamps."""
    with patch.object(tmp_model_run.config.__class__, "render", return_value=None):
        before_generate = datetime.now(timezone.utc)

        staging_dir = tmp_model_run.staging_dir
        (staging_dir / "test.txt").write_text("test")

        tmp_model_run.generate()

        after_generate = datetime.now(timezone.utc)

        sidecar = load_generate_result(staging_dir)

        assert before_generate <= sidecar.created_at <= after_generate
        assert before_generate <= sidecar.payload.generated_at <= after_generate


def test_generate_sidecar_failure_resilience(tmp_model_run):
    """Test that generate doesn't fail if sidecar writing fails."""
    with patch.object(tmp_model_run.config.__class__, "render", return_value=None):
        staging_dir = tmp_model_run.staging_dir
        (staging_dir / "test.txt").write_text("test")

        with patch(
            "rompy.core.result_persistence.write_generate_result",
            side_effect=OSError("Disk full"),
        ):
            result_path = tmp_model_run.generate()

            assert result_path == staging_dir
            assert not (staging_dir / GENERATE_RESULT_FILENAME).exists()


def test_generate_returns_path_not_result_object(tmp_model_run):
    """Test that generate() returns Path, not result object (backward compat)."""
    with patch.object(tmp_model_run.config.__class__, "render", return_value=None):
        staging_dir = tmp_model_run.staging_dir
        (staging_dir / "test.txt").write_text("test")

        result = tmp_model_run.generate()

        assert isinstance(result, Path)
        assert result == staging_dir


def test_generate_sidecar_json_structure(tmp_model_run):
    """Test that sidecar JSON has correct structure for external consumers."""
    with patch.object(tmp_model_run.config.__class__, "render", return_value=None):
        staging_dir = tmp_model_run.staging_dir
        (staging_dir / "test.txt").write_text("test")

        tmp_model_run.generate()

        sidecar_path = staging_dir / GENERATE_RESULT_FILENAME
        raw_json = json.loads(sidecar_path.read_text())

        assert "kind" in raw_json
        assert raw_json["kind"] == "generate_result"
        assert "schema_version" in raw_json
        assert raw_json["schema_version"] == 1
        assert "created_at" in raw_json
        assert "run_id" in raw_json
        assert "staging_dir" in raw_json
        assert "status" in raw_json
        assert "success" in raw_json
        assert "payload" in raw_json

        payload = raw_json["payload"]
        assert "generated_at" in payload
        assert "staging_dir" in payload
        assert "success" in payload
        assert "generated_files" in payload
        assert isinstance(payload["generated_files"], list)


def test_generate_sidecar_with_empty_staging_dir(tmp_model_run):
    """Test sidecar writing when no files are generated."""
    with patch.object(tmp_model_run.config.__class__, "render", return_value=None):
        staging_dir = tmp_model_run.staging_dir

        tmp_model_run.generate()

        sidecar = load_generate_result(staging_dir)

        assert sidecar.success is True
        assert len(sidecar.payload.generated_files) == 0


def test_generate_sidecar_staging_dir_matches_model_run(tmp_model_run):
    """Test that sidecar staging_dir matches ModelRun.staging_dir."""
    with patch.object(tmp_model_run.config.__class__, "render", return_value=None):
        staging_dir = tmp_model_run.staging_dir
        (staging_dir / "test.txt").write_text("test")

        tmp_model_run.generate()

        sidecar = load_generate_result(staging_dir)

        assert sidecar.staging_dir == str(staging_dir)
        assert sidecar.payload.staging_dir == str(staging_dir)


def test_generate_multiple_calls_overwrites_sidecar(tmp_model_run):
    """Test that calling generate() multiple times overwrites the sidecar."""
    with patch.object(tmp_model_run.config.__class__, "render", return_value=None):
        staging_dir = tmp_model_run.staging_dir
        (staging_dir / "test1.txt").write_text("test1")

        tmp_model_run.generate()
        sidecar1 = load_generate_result(staging_dir)
        first_created_at = sidecar1.created_at

        (staging_dir / "test2.txt").write_text("test2")
        tmp_model_run.generate()

        sidecar2 = load_generate_result(staging_dir)

        assert sidecar2.created_at >= first_created_at

        assert "test1.txt" in sidecar2.payload.generated_files
        assert "test2.txt" in sidecar2.payload.generated_files
