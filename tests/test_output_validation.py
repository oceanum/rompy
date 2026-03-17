from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from rompy.core.config import BaseConfig
from rompy.core.responses import Artifact, ArtifactType, PostprocessSuccess
from rompy.core.time import TimeRange
from rompy.model import ModelRun
from rompy.postprocess import NoopPostprocessor
from tests.test_helpers import DemoConfig


def test_base_expected_artifacts_warns_and_returns_empty_list():
    config = BaseConfig()

    with pytest.warns(UserWarning, match="expected_artifacts"):
        artifacts = config.expected_artifacts()

    assert artifacts == []


def test_base_validate_outputs_warns_and_discovers_artifacts(tmp_path):
    (tmp_path / "a.yaml").write_text("x")
    (tmp_path / "b.nc").write_text("x")
    (tmp_path / "c.png").write_text("x")
    (tmp_path / "d.txt").write_text("x")
    (tmp_path / "e.bin").write_text("x")

    config = BaseConfig()
    with pytest.warns(UserWarning) as warning_records:
        artifacts = config.validate_outputs(tmp_path)

    assert any("validate_outputs" in str(w.message) for w in warning_records)
    assert any("expected_artifacts" in str(w.message) for w in warning_records)

    by_name = {Path(a.path).name: a for a in artifacts}
    assert by_name["a.yaml"].artifact_type == ArtifactType.YAML
    assert by_name["b.nc"].artifact_type == ArtifactType.NETCDF
    assert by_name["c.png"].artifact_type == ArtifactType.PLOT
    assert by_name["d.txt"].artifact_type == ArtifactType.TEXT
    assert by_name["e.bin"].artifact_type == ArtifactType.OTHER
    assert all(a.size_bytes is not None for a in artifacts)


def test_validate_outputs_warns_for_missing_expected_artifact(tmp_path):
    class ExpectedConfig(BaseConfig):
        def expected_artifacts(self):
            return [
                Artifact(
                    path="expected_restart.nc",
                    artifact_type=ArtifactType.RESTART,
                )
            ]

    config = ExpectedConfig()

    with pytest.warns(UserWarning) as warning_records:
        _ = config.validate_outputs(tmp_path)

    assert any(
        "Expected artifact not found: expected_restart.nc" in str(w.message)
        for w in warning_records
    )


def test_noop_postprocessor_delegates_to_config_validate_outputs(tmp_path):
    model_run = ModelRun(
        run_id="test_run",
        period=TimeRange(
            start=datetime(2020, 2, 21, 4),
            end=datetime(2020, 2, 24, 4),
            interval="15M",
        ),
        output_dir=str(tmp_path),
        config=DemoConfig(arg1="foo", arg2="bar"),
    )

    check_dir = tmp_path / model_run.run_id
    check_dir.mkdir(parents=True, exist_ok=True)

    delegated_artifacts = [
        Artifact(
            path=str(check_dir / "from_delegate.txt"),
            artifact_type=ArtifactType.TEXT,
            size_bytes=12,
        )
    ]

    processor = NoopPostprocessor()
    with patch.object(
        DemoConfig, "validate_outputs", return_value=delegated_artifacts
    ) as mock_validate:
        result = processor.process(model_run, validate_outputs=True)

    assert isinstance(result, PostprocessSuccess)
    assert result.success is True
    assert result.artifacts == delegated_artifacts
    assert result.file_count == len(delegated_artifacts)
    mock_validate.assert_called_once_with(check_dir)
