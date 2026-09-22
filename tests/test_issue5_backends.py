"""Typed workspace generation coverage for all execution backends."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

from rompy.backends.config import DockerConfig, LocalConfig, SlurmConfig
from rompy.core.responses import GenerateFailure, GenerateSuccess, TimingInfo
from rompy.run import LocalRunBackend
from rompy.run.docker import DockerRunBackend
from rompy.run.slurm import SlurmRunBackend


def generated(path, failure=False):
    now = datetime.now(timezone.utc)
    if failure:
        return GenerateFailure(run_id="run-5", error="render failed", staging_dir=str(path), generated_files=[], timing=TimingInfo(start_time=now, end_time=now))
    return GenerateSuccess(run_id="run-5", staging_dir=str(path), generated_files=[], timing=TimingInfo(start_time=now, end_time=now))


def model(tmp_path):
    value = Mock(run_id="run-5", output_dir=tmp_path)
    value.generate.return_value = generated(tmp_path)
    return value


def test_local_backend_unwraps_typed_workspace_and_propagates_failure(tmp_path):
    value = model(tmp_path)
    (tmp_path / "run-5").mkdir()
    backend = LocalRunBackend()
    with patch.object(value, "generate", return_value=generated(tmp_path / "run-5")):
        assert backend.run(value, LocalConfig(command="true", working_dir=tmp_path / "run-5")) is True
    assert isinstance(backend.generate_result, GenerateSuccess)
    with patch.object(value, "generate", return_value=generated(tmp_path, failure=True)):
        assert backend.run(value, LocalConfig(command="true", working_dir=tmp_path)) is False
    assert backend.generate_result.error == "render failed"


def test_docker_backend_unwraps_typed_workspace_and_failure(tmp_path):
    value = model(tmp_path)
    backend = DockerRunBackend()
    config = DockerConfig(image="test-image")
    with patch.object(value, "generate", return_value=generated(tmp_path)), patch.object(backend, "_prepare_image", return_value="test-image"), patch.object(backend, "_run_container", return_value=True):
        assert backend.run(value, config) is True
    assert isinstance(backend.generate_result, GenerateSuccess)
    with patch.object(value, "generate", return_value=generated(tmp_path, failure=True)):
        assert backend.run(value, config) is False
    assert backend.generate_result.error == "render failed"


def test_slurm_backend_unwraps_typed_workspace_and_failure(tmp_path):
    value = model(tmp_path)
    backend = SlurmRunBackend()
    config = SlurmConfig(command="true")
    with patch.object(value, "generate", return_value=generated(tmp_path)), patch.object(backend, "_create_job_script", return_value="job.sh"), patch.object(backend, "_submit_job", return_value="42"), patch.object(backend, "_wait_for_completion", return_value=True):
        assert backend.run(value, config) is True
    assert isinstance(backend.generate_result, GenerateSuccess)
    with patch.object(value, "generate", return_value=generated(tmp_path, failure=True)):
        assert backend.run(value, config) is False
    assert backend.generate_result.error == "render failed"
