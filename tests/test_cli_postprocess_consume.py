"""Tests for postprocess command's run_result.json consumption."""

import json
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from rompy.cli import cli
from rompy.core.responses import (
    Artifact,
    ArtifactType,
    ModelRunResult,
    RunResultSidecar,
    TimingInfo,
)
from rompy.core.result_persistence import write_run_result
from rompy.model import ModelRun


@pytest.fixture
def cli_runner():
    return CliRunner()


@pytest.fixture
def staging_dir_with_success_sidecar(tmp_path):
    model = ModelRun(
        run_id="test-postprocess-cli",
        output_dir=tmp_path / "output",
        run_id_subdir=True,
    )
    staging_dir = model.staging_dir
    staging_dir.mkdir(parents=True, exist_ok=True)

    timing = TimingInfo(
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
    )
    run_result = ModelRunResult(
        success=True,
        run_id="test-postprocess-cli",
        backend_used="LocalBackend",
        output_dir=str(staging_dir),
        timing=timing,
    )
    from rompy.core.responses import NormalizedContext

    normalized = NormalizedContext(
        model_type="modelrun",
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        period_interval="2h",
        output_dir=str(model.output_dir),
        staging_dir=str(staging_dir),
        config_hash="",
        extensions={},
    )

    sidecar = RunResultSidecar(
        created_at=datetime.now(timezone.utc),
        run_id="test-postprocess-cli",
        staging_dir=str(staging_dir),
        status="success",
        success=True,
        normalized_context=normalized,
        payload=run_result,
    )
    write_run_result(staging_dir, sidecar)

    return staging_dir, model


@pytest.fixture
def staging_dir_with_failed_sidecar(tmp_path):
    model = ModelRun(
        run_id="test-postprocess-cli-failed",
        output_dir=tmp_path / "output",
        run_id_subdir=True,
    )
    staging_dir = model.staging_dir
    staging_dir.mkdir(parents=True, exist_ok=True)

    timing = TimingInfo(
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
    )
    run_result = ModelRunResult(
        success=False,
        run_id="test-postprocess-cli-failed",
        backend_used="LocalBackend",
        output_dir=str(staging_dir),
        timing=timing,
        error="Simulated backend failure",
    )
    from rompy.core.responses import NormalizedContext

    normalized = NormalizedContext(
        model_type="modelrun",
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        period_interval="2h",
        output_dir=str(model.output_dir),
        staging_dir=str(staging_dir),
        config_hash="",
        extensions={},
    )

    sidecar = RunResultSidecar(
        created_at=datetime.now(timezone.utc),
        run_id="test-postprocess-cli-failed",
        staging_dir=str(staging_dir),
        status="failed",
        success=False,
        error="Simulated backend failure",
        normalized_context=normalized,
        payload=run_result,
    )
    write_run_result(staging_dir, sidecar)

    return staging_dir, model


def test_postprocess_happy_path_autodiscover(
    cli_runner, staging_dir_with_success_sidecar, tmp_path
):
    staging_dir, model = staging_dir_with_success_sidecar

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"model_type: modelrun\nrun_id: {model.run_id}\noutput_dir: {model.output_dir}\nrun_id_subdir: true\n"
    )

    processor_config = tmp_path / "processor.yml"
    processor_config.write_text("type: noop\n")

    result = cli_runner.invoke(
        cli,
        [
            "postprocess",
            str(config_path),
            "--processor-config",
            str(processor_config),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, (
        f"Unexpected failure: {result.output or result.exception}"
    )


def test_postprocess_explicit_run_result_path(
    cli_runner, staging_dir_with_success_sidecar, tmp_path
):
    staging_dir, model = staging_dir_with_success_sidecar

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"model_type: modelrun\nrun_id: {model.run_id}\noutput_dir: {model.output_dir}\nrun_id_subdir: true\n"
    )

    processor_config = tmp_path / "processor.yml"
    processor_config.write_text("type: noop\n")

    explicit_path = staging_dir / "run_result.json"

    result = cli_runner.invoke(
        cli,
        [
            "postprocess",
            str(config_path),
            "--processor-config",
            str(processor_config),
            "--run-result",
            str(explicit_path),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, (
        f"Unexpected failure: {result.output or result.exception}"
    )


def test_postprocess_explicit_run_result_passes_artifacts_to_processor(
    cli_runner, tmp_path, monkeypatch
):
    from rompy.postprocess.config import NoopPostprocessorConfig

    model = ModelRun(
        run_id="test-postprocess-artifacts",
        output_dir=tmp_path / "output",
        run_id_subdir=True,
    )
    staging_dir = model.staging_dir
    staging_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = staging_dir / "restart001.ww3"
    artifact_path.write_text("restart")

    timing = TimingInfo(
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
    )
    run_result = ModelRunResult(
        success=True,
        run_id=model.run_id,
        backend_used="LocalBackend",
        output_dir=str(staging_dir),
        timing=timing,
        artifacts=[
            Artifact(
                path="restart001.ww3",
                artifact_type=ArtifactType.RESTART,
                size_bytes=artifact_path.stat().st_size,
                description="restart file",
            )
        ],
    )
    from rompy.core.responses import NormalizedContext

    normalized = NormalizedContext(
        model_type="modelrun",
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        period_interval="3h",
        output_dir=str(model.output_dir),
        staging_dir=str(staging_dir),
        config_hash="",
        extensions={"ww3": {"restart_stride_seconds": 3600}},
    )

    sidecar = RunResultSidecar(
        created_at=datetime.now(timezone.utc),
        run_id=model.run_id,
        staging_dir=str(staging_dir),
        status="success",
        success=True,
        normalized_context=normalized,
        payload=run_result,
    )
    write_run_result(staging_dir, sidecar)

    captured = {}

    class ArtifactExpectingProcessor:
        def process(self, processor_input, **kwargs):
            captured["processor_input"] = processor_input
            from rompy.core.responses import PostprocessSuccess

            return PostprocessSuccess(
                success=True,
                run_id=processor_input.run_id,
                output_dir=processor_input.output_dir,
                validated=True,
                file_count=len(processor_input.artifacts),
                artifacts=processor_input.artifacts,
                message=None,
                timing=timing,
            )

    processor_config = tmp_path / "processor.yml"
    processor_config.write_text("type: noop\n")

    monkeypatch.setattr(
        "rompy.postprocess.config._load_processor_config",
        lambda _path: NoopPostprocessorConfig(),
    )
    monkeypatch.setattr(
        NoopPostprocessorConfig,
        "get_postprocessor_class",
        lambda self: ArtifactExpectingProcessor,
    )

    result = cli_runner.invoke(
        cli,
        [
            "postprocess",
            "--run-result",
            str(staging_dir / "run_result.json"),
            "--processor-config",
            str(processor_config),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, (
        f"Unexpected failure: {result.output or result.exception}"
    )
    assert captured["processor_input"].run_id == model.run_id
    assert len(captured["processor_input"].artifacts) == 1
    assert captured["processor_input"].normalized_context is not None


def test_postprocess_explicit_run_result_filters_missing_legacy_artifacts(
    cli_runner, tmp_path, monkeypatch
):
    from rompy.postprocess.config import NoopPostprocessorConfig

    model = ModelRun(
        run_id="test-postprocess-legacy-filter",
        output_dir=tmp_path / "output",
        run_id_subdir=True,
    )
    staging_dir = model.staging_dir
    staging_dir.mkdir(parents=True, exist_ok=True)

    good_artifact = staging_dir / "restart001.ww3"
    good_artifact.write_text("restart")

    timing = TimingInfo(
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
    )
    run_result = ModelRunResult(
        success=True,
        run_id=model.run_id,
        backend_used="LocalBackend",
        output_dir=str(model.output_dir),
        timing=timing,
        artifacts=[
            Artifact(
                path=str(good_artifact),
                artifact_type=ArtifactType.RESTART,
                size_bytes=good_artifact.stat().st_size,
                description="restart file",
            ),
            Artifact(
                path="simulations/other-run/postprocess_result.json",
                artifact_type=ArtifactType.OTHER,
                size_bytes=1,
                description="stale sidecar",
            ),
        ],
    )
    from rompy.core.responses import NormalizedContext

    normalized = NormalizedContext(
        model_type="modelrun",
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        period_interval="3h",
        output_dir=str(model.output_dir),
        staging_dir=str(staging_dir),
        config_hash="",
        extensions={"ww3": {"restart_stride_seconds": 3600}},
    )

    sidecar = RunResultSidecar(
        created_at=datetime.now(timezone.utc),
        run_id=model.run_id,
        staging_dir=str(staging_dir),
        status="success",
        success=True,
        normalized_context=normalized,
        payload=run_result,
    )
    write_run_result(staging_dir, sidecar)

    captured = {}

    class ArtifactExpectingProcessor:
        def process(self, processor_input, **kwargs):
            captured["artifact_paths"] = [a.path for a in processor_input.artifacts]
            from rompy.core.responses import PostprocessSuccess

            return PostprocessSuccess(
                success=True,
                run_id=processor_input.run_id,
                output_dir=processor_input.output_dir,
                validated=True,
                file_count=len(processor_input.artifacts),
                artifacts=processor_input.artifacts,
                message=None,
                timing=timing,
            )

    processor_config = tmp_path / "processor.yml"
    processor_config.write_text("type: noop\n")

    monkeypatch.setattr(
        "rompy.postprocess.config._load_processor_config",
        lambda _path: NoopPostprocessorConfig(),
    )
    monkeypatch.setattr(
        NoopPostprocessorConfig,
        "get_postprocessor_class",
        lambda self: ArtifactExpectingProcessor,
    )

    result = cli_runner.invoke(
        cli,
        [
            "postprocess",
            "--run-result",
            str(staging_dir / "run_result.json"),
            "--processor-config",
            str(processor_config),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, (
        f"Unexpected failure: {result.output or result.exception}"
    )
    assert captured["artifact_paths"] == ["restart001.ww3"]


def test_postprocess_missing_sidecar_fails(cli_runner, tmp_path):
    model = ModelRun(
        run_id="test-missing-sidecar",
        output_dir=tmp_path / "output",
        run_id_subdir=True,
    )
    staging_dir = model.staging_dir
    staging_dir.mkdir(parents=True, exist_ok=True)

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"model_type: modelrun\nrun_id: {model.run_id}\noutput_dir: {model.output_dir}\nrun_id_subdir: true\n"
    )

    processor_config = tmp_path / "processor.yml"
    processor_config.write_text("type: noop\n")

    result = cli_runner.invoke(
        cli,
        [
            "postprocess",
            str(config_path),
            "--processor-config",
            str(processor_config),
        ],
    )

    assert result.exit_code == 1
    assert "Run result sidecar not found" in result.output
    assert "The model must be executed before postprocessing" in result.output


def test_postprocess_corrupt_json_fails(cli_runner, tmp_path):
    model = ModelRun(
        run_id="test-corrupt-sidecar",
        output_dir=tmp_path / "output",
        run_id_subdir=True,
    )
    staging_dir = model.staging_dir
    staging_dir.mkdir(parents=True, exist_ok=True)

    sidecar_path = staging_dir / "run_result.json"
    sidecar_path.write_text("{invalid json!!")

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"model_type: modelrun\nrun_id: {model.run_id}\noutput_dir: {model.output_dir}\nrun_id_subdir: true\n"
    )

    processor_config = tmp_path / "processor.yml"
    processor_config.write_text("type: noop\n")

    result = cli_runner.invoke(
        cli,
        [
            "postprocess",
            str(config_path),
            "--processor-config",
            str(processor_config),
        ],
    )

    assert result.exit_code == 1
    # JSON parse error should be surfaced as postprocessing failure
    assert "Postprocessing failed" in result.output
    assert "Expecting property name" in result.output


def test_postprocess_schema_mismatch_fails(cli_runner, tmp_path):
    model = ModelRun(
        run_id="test-schema-mismatch",
        output_dir=tmp_path / "output",
        run_id_subdir=True,
    )
    staging_dir = model.staging_dir
    staging_dir.mkdir(parents=True, exist_ok=True)

    sidecar_path = staging_dir / "run_result.json"
    sidecar_path.write_text(
        json.dumps(
            {
                "kind": "generate_result",
                "schema_version": 1,
                "success": True,
            }
        )
    )

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"model_type: modelrun\nrun_id: {model.run_id}\noutput_dir: {model.output_dir}\nrun_id_subdir: true\n"
    )

    processor_config = tmp_path / "processor.yml"
    processor_config.write_text("type: noop\n")

    result = cli_runner.invoke(
        cli,
        [
            "postprocess",
            str(config_path),
            "--processor-config",
            str(processor_config),
        ],
    )

    assert result.exit_code == 1
    # Schema mismatch should be surfaced as postprocessing failure
    assert "Postprocessing failed" in result.output
    assert "generate_result" in result.output


def test_postprocess_success_false_no_force_fails(
    cli_runner, staging_dir_with_failed_sidecar, tmp_path
):
    staging_dir, model = staging_dir_with_failed_sidecar

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"model_type: modelrun\nrun_id: {model.run_id}\noutput_dir: {model.output_dir}\nrun_id_subdir: true\n"
    )

    processor_config = tmp_path / "processor.yml"
    processor_config.write_text("type: noop\n")

    result = cli_runner.invoke(
        cli,
        [
            "postprocess",
            str(config_path),
            "--processor-config",
            str(processor_config),
        ],
    )

    assert result.exit_code == 1
    assert "Run result shows success=false" in result.output
    assert "Cannot postprocess failed run" in result.output
    assert "Use --force to override" in result.output


def test_postprocess_success_false_with_force_succeeds(
    cli_runner, staging_dir_with_failed_sidecar, tmp_path
):
    staging_dir, model = staging_dir_with_failed_sidecar

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"model_type: modelrun\nrun_id: {model.run_id}\noutput_dir: {model.output_dir}\nrun_id_subdir: true\n"
    )

    processor_config = tmp_path / "processor.yml"
    processor_config.write_text("type: noop\n")

    result = cli_runner.invoke(
        cli,
        [
            "postprocess",
            str(config_path),
            "--processor-config",
            str(processor_config),
            "--force",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, (
        f"Unexpected failure: {result.output or result.exception}"
    )
    assert "Run result shows success=false but --force specified" in result.output
    assert "Proceeding anyway" in result.output


def test_postprocess_force_does_not_bypass_missing_sidecar(cli_runner, tmp_path):
    model = ModelRun(
        run_id="test-force-missing",
        output_dir=tmp_path / "output",
        run_id_subdir=True,
    )
    staging_dir = model.staging_dir
    staging_dir.mkdir(parents=True, exist_ok=True)

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"model_type: modelrun\nrun_id: {model.run_id}\noutput_dir: {model.output_dir}\nrun_id_subdir: true\n"
    )

    processor_config = tmp_path / "processor.yml"
    processor_config.write_text("type: noop\n")

    result = cli_runner.invoke(
        cli,
        [
            "postprocess",
            str(config_path),
            "--processor-config",
            str(processor_config),
            "--force",
        ],
    )

    assert result.exit_code == 1
    assert "Run result sidecar not found" in result.output
    assert "The model must be executed before postprocessing" in result.output


def test_postprocess_force_does_not_bypass_corrupt_sidecar(cli_runner, tmp_path):
    model = ModelRun(
        run_id="test-force-corrupt",
        output_dir=tmp_path / "output",
        run_id_subdir=True,
    )
    staging_dir = model.staging_dir
    staging_dir.mkdir(parents=True, exist_ok=True)

    sidecar_path = staging_dir / "run_result.json"
    sidecar_path.write_text("{invalid json!!")

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"model_type: modelrun\nrun_id: {model.run_id}\noutput_dir: {model.output_dir}\nrun_id_subdir: true\n"
    )

    processor_config = tmp_path / "processor.yml"
    processor_config.write_text("type: noop\n")

    result = cli_runner.invoke(
        cli,
        [
            "postprocess",
            str(config_path),
            "--processor-config",
            str(processor_config),
            "--force",
        ],
    )

    assert result.exit_code == 1
    assert "Postprocessing failed" in result.output
    assert "Expecting property name" in result.output
