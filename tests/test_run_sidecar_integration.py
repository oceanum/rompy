"""Integration tests for ModelRun.run() result sidecar persistence."""

import json

import pytest

from rompy.backends.config import LocalConfig
from rompy.model import ModelRun
from tests.test_helpers import DemoConfig


@pytest.mark.integration
def test_model_run_writes_run_result_sidecar(tmp_path):
    """Verify ModelRun.run() writes run_result.json sidecar file on execution."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    model = ModelRun(
        config=DemoConfig(arg1="foo", arg2="bar"),
        run_id="test-run-sidecar",
        output_dir=str(tmp_path / "output"),
    )

    backend = LocalConfig(command="exit 1", timeout=60)

    result = model.run(backend=backend, workspace_dir=str(workspace))

    assert result.success is False

    sidecar_path = workspace / "run_result.json"
    assert sidecar_path.exists(), "run_result.json should be written"

    sidecar_data = json.loads(sidecar_path.read_text())
    assert sidecar_data["kind"] == "run_result"
    assert sidecar_data["schema_version"] == 1
    assert sidecar_data["success"] is False
    assert sidecar_data["run_id"] == "test-run-sidecar"
    assert sidecar_data["staging_dir"] == str(workspace)
