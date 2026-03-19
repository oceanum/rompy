import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from rompy.cli import cli
from rompy.core.responses import (
    GenerateResult,
    GenerateResultSidecar,
    ModelRunResult,
    PostprocessSuccess,
    PostprocessResultSidecar,
    RunResultSidecar,
    TimingInfo,
)
from rompy.core.result_persistence import (
    write_generate_result,
    write_run_result,
    write_postprocess_result,
)
from rompy.model import ModelRun
from rompy.postprocess.config import NoopPostprocessorConfig


@pytest.fixture
def cli_runner():
    return CliRunner()


@pytest.fixture
def model_config_file(tmp_path):
    config_content = """
    model_type: mock
    run_id: test-json-output
    """
    config_file = tmp_path / "config.yml"
    config_file.write_text(config_content)
    return config_file


@pytest.fixture
def backend_config_file(tmp_path):
    backend_content = """
    type: local
    """
    backend_file = tmp_path / "backend.yml"
    backend_file.write_text(backend_content)
    return backend_file


@pytest.fixture
def processor_config_file(tmp_path):
    processor_content = """
    type: noop
    """
    processor_file = tmp_path / "processor.yml"
    processor_file.write_text(processor_content)
    return processor_file


class TestGenerateJsonOutput:
    def test_generate_with_json_flag_emits_valid_json(
        self, cli_runner, model_config_file, tmp_path
    ):
        with patch("rompy.cli.ModelRun") as mock_model_run_class:
            mock_instance = mock_model_run_class.return_value
            staging_dir = tmp_path / "output" / "test-json-output"
            staging_dir.mkdir(parents=True)
            mock_instance.generate.return_value = staging_dir
            mock_instance.config.model_type = "mock"
            mock_instance.run_id = "test-json-output"

            sidecar = GenerateResultSidecar(
                created_at=datetime.now(timezone.utc),
                run_id="test-json-output",
                staging_dir=str(staging_dir),
                status="success",
                success=True,
                payload=GenerateResult(
                    generated_at=datetime.now(timezone.utc),
                    staging_dir=str(staging_dir),
                    config_file="config.nml",
                    success=True,
                    generated_files=["config.nml", "mod_def.ww3"],
                ),
            )
            write_generate_result(staging_dir, sidecar)

            result = cli_runner.invoke(
                cli,
                ["generate", str(model_config_file), "--json"],
            )

            assert result.exit_code == 0
            output_json = json.loads(result.output)
            assert output_json["success"] is True
            assert output_json["kind"] == "generate_result"
            assert output_json["run_id"] == "test-json-output"

    def test_generate_without_json_flag_no_json_in_stdout(
        self, cli_runner, model_config_file, tmp_path
    ):
        with patch("rompy.cli.ModelRun") as mock_model_run_class:
            mock_instance = mock_model_run_class.return_value
            staging_dir = tmp_path / "output" / "test-json-output"
            staging_dir.mkdir(parents=True)
            mock_instance.generate.return_value = staging_dir
            mock_instance.config.model_type = "mock"
            mock_instance.run_id = "test-json-output"

            result = cli_runner.invoke(
                cli,
                ["generate", str(model_config_file)],
            )

            assert result.exit_code == 0
            try:
                json.loads(result.output)
                pytest.fail("Expected non-JSON output but got valid JSON")
            except json.JSONDecodeError:
                pass

    def test_generate_json_flag_on_error_emits_error_json(
        self, cli_runner, model_config_file
    ):
        with patch("rompy.cli.ModelRun") as mock_model_run_class:
            mock_model_run_class.side_effect = ValueError("Invalid configuration")

            result = cli_runner.invoke(
                cli,
                ["generate", str(model_config_file), "--json"],
            )

            assert result.exit_code == 1

            lines = result.output.strip().split("\n")
            json_line = next(
                (line for line in reversed(lines) if line.startswith("{")), None
            )
            assert json_line is not None, "No JSON line found in output"

            output_json = json.loads(json_line)
            assert output_json["success"] is False
            assert "Invalid configuration" in output_json["error"]


class TestRunJsonOutput:
    def test_run_with_json_flag_emits_valid_json(
        self, cli_runner, model_config_file, backend_config_file, tmp_path
    ):
        with patch("rompy.cli.ModelRun") as mock_model_run_class:
            mock_instance = mock_model_run_class.return_value
            staging_dir = tmp_path / "output" / "test-json-output"
            staging_dir.mkdir(parents=True)
            mock_instance.staging_dir = staging_dir
            mock_instance.generate.return_value = staging_dir
            mock_instance.config.model_type = "mock"
            mock_instance.run_id = "test-json-output"

            timing = TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            )
            run_result = ModelRunResult(
                success=True,
                run_id="test-json-output",
                backend_used="LocalBackend",
                output_dir=str(staging_dir),
                timing=timing,
            )
            mock_instance.run.return_value = run_result

            sidecar = RunResultSidecar(
                created_at=datetime.now(timezone.utc),
                run_id="test-json-output",
                staging_dir=str(staging_dir),
                status="success",
                success=True,
                payload=run_result,
            )
            write_run_result(staging_dir, sidecar)

            result = cli_runner.invoke(
                cli,
                [
                    "run",
                    str(model_config_file),
                    "--backend-config",
                    str(backend_config_file),
                    "--json",
                ],
            )

            assert result.exit_code == 0
            output_json = json.loads(result.output)
            assert output_json["success"] is True
            assert output_json["kind"] == "run_result"
            assert output_json["run_id"] == "test-json-output"

    def test_run_without_json_flag_no_json_in_stdout(
        self, cli_runner, model_config_file, backend_config_file, tmp_path
    ):
        with patch("rompy.cli.ModelRun") as mock_model_run_class:
            mock_instance = mock_model_run_class.return_value
            staging_dir = tmp_path / "output" / "test-json-output"
            staging_dir.mkdir(parents=True)
            mock_instance.staging_dir = staging_dir
            mock_instance.generate.return_value = staging_dir
            mock_instance.config.model_type = "mock"
            mock_instance.run_id = "test-json-output"

            timing = TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            )
            mock_instance.run.return_value = ModelRunResult(
                success=True,
                run_id="test-json-output",
                backend_used="LocalBackend",
                output_dir=str(staging_dir),
                timing=timing,
            )

            result = cli_runner.invoke(
                cli,
                [
                    "run",
                    str(model_config_file),
                    "--backend-config",
                    str(backend_config_file),
                ],
            )

            assert result.exit_code == 0
            try:
                json.loads(result.output)
                pytest.fail("Expected non-JSON output but got valid JSON")
            except json.JSONDecodeError:
                pass

    def test_run_json_flag_on_error_emits_error_json(
        self, cli_runner, model_config_file, backend_config_file
    ):
        with patch("rompy.cli.ModelRun") as mock_model_run_class:
            mock_model_run_class.side_effect = ValueError("Backend configuration error")

            result = cli_runner.invoke(
                cli,
                [
                    "run",
                    str(model_config_file),
                    "--backend-config",
                    str(backend_config_file),
                    "--json",
                ],
            )

            assert result.exit_code == 1

            lines = result.output.strip().split("\n")
            json_line = next(
                (line for line in reversed(lines) if line.startswith("{")), None
            )
            assert json_line is not None, "No JSON line found in output"

            output_json = json.loads(json_line)
            assert output_json["success"] is False
            assert "Backend configuration error" in output_json["error"]


class TestPostprocessJsonOutput:
    def test_postprocess_with_json_flag_emits_valid_json(
        self, cli_runner, model_config_file, processor_config_file, tmp_path
    ):
        with patch("rompy.cli.ModelRun") as mock_model_run_class:
            mock_instance = mock_model_run_class.return_value
            staging_dir = tmp_path / "output" / "test-json-output"
            staging_dir.mkdir(parents=True)
            mock_instance.staging_dir = staging_dir
            mock_instance.config.model_type = "mock"
            mock_instance.run_id = "test-json-output"

            timing = TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            )
            run_result = ModelRunResult(
                success=True,
                run_id="test-json-output",
                backend_used="LocalBackend",
                output_dir=str(staging_dir),
                timing=timing,
            )
            run_sidecar = RunResultSidecar(
                created_at=datetime.now(timezone.utc),
                run_id="test-json-output",
                staging_dir=str(staging_dir),
                status="success",
                success=True,
                payload=run_result,
            )
            write_run_result(staging_dir, run_sidecar)

            postprocess_result = PostprocessSuccess(
                success=True,
                run_id="test-json-output",
                output_dir=str(staging_dir),
                validated=True,
                file_count=5,
                artifacts=[],
                timing=timing,
            )
            mock_instance.postprocess.return_value = postprocess_result

            postprocess_sidecar = PostprocessResultSidecar(
                created_at=datetime.now(timezone.utc),
                run_id="test-json-output",
                staging_dir=str(staging_dir),
                status="success",
                success=True,
                payload=postprocess_result,
            )
            write_postprocess_result(staging_dir, postprocess_sidecar)

            result = cli_runner.invoke(
                cli,
                [
                    "postprocess",
                    str(model_config_file),
                    "--processor-config",
                    str(processor_config_file),
                    "--json",
                ],
            )

            assert result.exit_code == 0
            output_json = json.loads(result.output)
            assert output_json["success"] is True
            assert output_json["kind"] == "postprocess_result"
            assert output_json["run_id"] == "test-json-output"

    def test_postprocess_without_json_flag_no_json_in_stdout(
        self, cli_runner, model_config_file, processor_config_file, tmp_path
    ):
        with patch("rompy.cli.ModelRun") as mock_model_run_class:
            mock_instance = mock_model_run_class.return_value
            staging_dir = tmp_path / "output" / "test-json-output"
            staging_dir.mkdir(parents=True)
            mock_instance.staging_dir = staging_dir
            mock_instance.config.model_type = "mock"
            mock_instance.run_id = "test-json-output"

            timing = TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            )
            run_result = ModelRunResult(
                success=True,
                run_id="test-json-output",
                backend_used="LocalBackend",
                output_dir=str(staging_dir),
                timing=timing,
            )
            run_sidecar = RunResultSidecar(
                created_at=datetime.now(timezone.utc),
                run_id="test-json-output",
                staging_dir=str(staging_dir),
                status="success",
                success=True,
                payload=run_result,
            )
            write_run_result(staging_dir, run_sidecar)

            mock_instance.postprocess.return_value = PostprocessSuccess(
                success=True,
                run_id="test-json-output",
                output_dir=str(staging_dir),
                validated=True,
                file_count=5,
                artifacts=[],
                timing=timing,
            )

            result = cli_runner.invoke(
                cli,
                [
                    "postprocess",
                    str(model_config_file),
                    "--processor-config",
                    str(processor_config_file),
                ],
            )

            assert result.exit_code == 0
            try:
                json.loads(result.output)
                pytest.fail("Expected non-JSON output but got valid JSON")
            except json.JSONDecodeError:
                pass

    def test_postprocess_json_flag_on_missing_run_result_emits_error_json(
        self, cli_runner, model_config_file, processor_config_file, tmp_path
    ):
        with patch("rompy.cli.ModelRun") as mock_model_run_class:
            mock_instance = mock_model_run_class.return_value
            staging_dir = tmp_path / "output" / "test-json-output"
            staging_dir.mkdir(parents=True)
            mock_instance.staging_dir = staging_dir
            mock_instance.config.model_type = "mock"
            mock_instance.run_id = "test-json-output"

            result = cli_runner.invoke(
                cli,
                [
                    "postprocess",
                    str(model_config_file),
                    "--processor-config",
                    str(processor_config_file),
                    "--json",
                ],
            )

            assert result.exit_code == 1

            lines = result.output.strip().split("\n")
            json_line = next(
                (line for line in reversed(lines) if line.startswith("{")), None
            )
            assert json_line is not None, "No JSON line found in output"

            output_json = json.loads(json_line)
            assert output_json["success"] is False
            assert "Run result sidecar not found" in output_json["error"]

    def test_postprocess_json_flag_idempotency_exit_emits_existing_sidecar(
        self, cli_runner, model_config_file, processor_config_file, tmp_path
    ):
        with patch("rompy.cli.ModelRun") as mock_model_run_class:
            mock_instance = mock_model_run_class.return_value
            staging_dir = tmp_path / "output" / "test-json-output"
            staging_dir.mkdir(parents=True)
            mock_instance.staging_dir = staging_dir
            mock_instance.config.model_type = "mock"
            mock_instance.run_id = "test-json-output"

            timing = TimingInfo(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            )
            run_result = ModelRunResult(
                success=True,
                run_id="test-json-output",
                backend_used="LocalBackend",
                output_dir=str(staging_dir),
                timing=timing,
            )
            run_sidecar = RunResultSidecar(
                created_at=datetime.now(timezone.utc),
                run_id="test-json-output",
                staging_dir=str(staging_dir),
                status="success",
                success=True,
                payload=run_result,
            )
            write_run_result(staging_dir, run_sidecar)

            postprocess_result = PostprocessSuccess(
                success=True,
                run_id="test-json-output",
                output_dir=str(staging_dir),
                validated=True,
                file_count=5,
                artifacts=[],
                timing=timing,
            )
            postprocess_sidecar = PostprocessResultSidecar(
                created_at=datetime.now(timezone.utc),
                run_id="test-json-output",
                staging_dir=str(staging_dir),
                status="success",
                success=True,
                payload=postprocess_result,
            )
            write_postprocess_result(staging_dir, postprocess_sidecar)

            result = cli_runner.invoke(
                cli,
                [
                    "postprocess",
                    str(model_config_file),
                    "--processor-config",
                    str(processor_config_file),
                    "--json",
                ],
            )

            assert result.exit_code == 0
            output_json = json.loads(result.output)
            assert output_json["success"] is True
            assert output_json["kind"] == "postprocess_result"
