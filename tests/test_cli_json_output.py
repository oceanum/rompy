"""Issue #5 CLI canonical JSON and exit-code tests."""

import json
from datetime import datetime, timezone

from click.testing import CliRunner

from rompy.cli import cli
from rompy.core.responses import (
    LocalArtifact,
    ModelRunFailure,
    ModelRunSuccess,
    RunResultSidecar,
    TimingInfo,
    NormalizedContext,
)
from rompy.core.result_persistence import write_run_result


def timing():
    now = datetime.now(timezone.utc)
    return TimingInfo(start_time=now, end_time=now)


def write_run(tmp_path, success=True):
    output = tmp_path / "outputs"
    output.mkdir()
    payload_cls = ModelRunSuccess if success else ModelRunFailure
    fields = dict(
        run_id="cli-run",
        backend_used="local",
        output_dir=str(output),
        timing=timing(),
        artifacts=[LocalArtifact(path="waves.nc")],
        expected_outputs=[LocalArtifact(path="waves.nc")],
        missing_outputs=[],
    )
    if not success:
        fields["error"] = "run failed"
    payload = payload_cls(**fields)
    context = NormalizedContext(
        model_type="base", period_start=datetime(2020, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2020, 1, 2, tzinfo=timezone.utc), period_interval=3600,
        output_dir=str(output), staging_dir=str(tmp_path), config_hash="",
    )
    sidecar = RunResultSidecar(
        run_id="cli-run", staging_dir=str(tmp_path), normalized_context=context,
        status="success" if success else "failed", success=success,
        error=None if success else payload.error, payload=payload,
    )
    write_run_result(tmp_path, sidecar)
    return output


def processor_config(tmp_path):
    config = tmp_path / "processor.yml"
    config.write_text("type: noop\nvalidate_outputs: false\n")
    return config


def json_lines(output):
    start = output.find('{\n  "kind"')
    if start >= 0:
        return [json.loads(output[start:])]
    start = output.rfind('{')
    return [json.loads(output[start:])]


def test_postprocess_json_success_is_canonical_and_exits_zero(tmp_path):
    write_run(tmp_path)
    result = CliRunner().invoke(cli, ["postprocess", str(tmp_path), "--processor-config", str(processor_config(tmp_path)), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads((tmp_path / "postprocess_result.json").read_text())
    assert payload["kind"] == "postprocess_result"
    assert payload["schema_version"] == 2
    assert payload["success"] is True


def test_postprocess_failed_run_has_canonical_json_and_nonzero_exit(tmp_path):
    write_run(tmp_path, success=False)
    result = CliRunner().invoke(cli, ["postprocess", str(tmp_path), "--processor-config", str(processor_config(tmp_path)), "--json"])
    assert result.exit_code == 1
    payload = json_lines(result.output)[-1]
    assert payload["success"] is False
    assert "success=false" in payload["error"]


def test_postprocess_json_missing_sidecar_is_failure(tmp_path):
    result = CliRunner().invoke(cli, ["postprocess", str(tmp_path), "--processor-config", str(processor_config(tmp_path)), "--json"])
    assert result.exit_code == 1
    payload = json_lines(result.output)[-1]
    assert payload["success"] is False
    assert "Run result sidecar not found" in payload["error"]
