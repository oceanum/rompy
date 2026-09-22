"""Focused issue #5 runtime handoff tests."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pydantic import TypeAdapter

from rompy.backends.config import LocalConfig
from rompy.cli import _build_postprocess_processor_input
from rompy.core.responses import (
    GenerateFailure,
    GenerateSuccess,
    LocalArtifact,
    ModelRunFailure,
    ModelRunResult,
    ModelRunSuccess,
    PipelineStage,
    PostprocessFailure,
    PostprocessSuccess,
    TimingInfo,
)
from rompy.model import ModelRun
from rompy.pipeline import LocalPipelineBackend
from rompy.postprocess.config import BasePostprocessorConfig


def timing():
    now = datetime.now(timezone.utc)
    return TimingInfo(start_time=now, end_time=now)


def run_success(tmp_path):
    return ModelRunSuccess(
        run_id="run-5",
        backend_used="local",
        output_dir=str(tmp_path),
        timing=timing(),
        artifacts=[LocalArtifact(path="outputs/waves.nc")],
        expected_outputs=[LocalArtifact(path="outputs/waves.nc")],
        missing_outputs=[],
    )


class RecordingProcessor:
    received = None

    def __init__(self, config):
        self.config = config

    def process(self, result, **options):
        self.received = result
        type(self).received = result
        return PostprocessSuccess(
            run_id=result.run_id,
            output_dir=result.output_dir,
            validated=True,
            timing=timing(),
            artifacts=result.artifacts,
            expected_outputs=result.expected_outputs,
            missing_outputs=result.missing_outputs,
        )


class RecordingConfig(BasePostprocessorConfig):
    type: str = "recording"

    def get_postprocessor_class(self):
        return RecordingProcessor


def test_processor_constructor_and_exact_typed_input(tmp_path):
    model = ModelRun(run_id="run-5", output_dir=tmp_path)
    source = run_success(tmp_path)
    result = model.postprocess(RecordingConfig(), processor_input=source)
    assert isinstance(result, PostprocessSuccess)
    assert RecordingProcessor.received == source
    assert isinstance(RecordingProcessor.received, (ModelRunSuccess, ModelRunFailure))


@pytest.mark.parametrize("bad_input", [SimpleNamespace(run_id="run-5"), object()])
def test_processor_rejects_non_model_result_before_persistence(tmp_path, bad_input):
    model = ModelRun(run_id="run-5", output_dir=tmp_path)
    result = model.postprocess(RecordingConfig(), processor_input=bad_input)
    assert isinstance(result, PostprocessFailure)
    assert "processor protocol failure" in result.error.lower()
    assert not (model.staging_dir / "postprocess_result.json").exists()


def test_processor_rejects_arbitrary_return_before_persistence(tmp_path):
    class BadProcessor(RecordingProcessor):
        def process(self, result, **options):
            return SimpleNamespace(success=True, run_id=result.run_id)

    class BadConfig(RecordingConfig):
        def get_postprocessor_class(self):
            return BadProcessor

    model = ModelRun(run_id="run-5", output_dir=tmp_path)
    result = model.postprocess(BadConfig(), processor_input=run_success(tmp_path))
    assert isinstance(result, PostprocessFailure)
    assert "processor protocol failure" in result.error.lower()
    assert not (model.staging_dir / "postprocess_result.json").exists()


def test_generate_failure_preserves_path_timing_and_primary_error(tmp_path):
    model = ModelRun(run_id="run-5", output_dir=tmp_path)
    with patch.object(model.config.__class__, "render", side_effect=RuntimeError("render failed")):
        result = model.generate()
    assert isinstance(result, GenerateFailure)
    assert result.error == "render failed"
    assert result.staging_dir == str(model.staging_dir)
    assert result.timing.start_time.tzinfo is not None
    assert result.timing.end_time >= result.timing.start_time


def test_run_and_generate_results_are_typed_and_persist_failures_are_observable(tmp_path, monkeypatch):
    model = ModelRun(run_id="run-5", output_dir=tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(model.config.__class__, "render", lambda *_args, **_kwargs: None)
        generated = model.generate()
    assert isinstance(generated, GenerateSuccess)
    assert generated.timing.start_time.tzinfo is not None

    patch = pytest.MonkeyPatch()
    patch.setattr("rompy.core.result_persistence._atomic_write", Mock(side_effect=OSError("disk full")))
    try:
        failed = model.run(LocalConfig(command="exit 0", timeout=60), workspace_dir=str(model.staging_dir))
    finally:
        patch.undo()
    assert isinstance(failed, ModelRunFailure)
    assert failed.persistence_diagnostic is not None
    assert failed.persistence_diagnostic.error == "disk full"


def test_pipeline_strict_prefix_nested_failure_and_cleanup_precedence(tmp_path):
    generated = GenerateSuccess(run_id="run-5", staging_dir=str(tmp_path), generated_files=[], timing=timing())
    run = ModelRunFailure(
        run_id="run-5", backend_used="local", error="primary run failure", timing=timing(),
        output_dir=str(tmp_path), artifacts=[LocalArtifact(path="outputs/waves.nc")],
        expected_outputs=[LocalArtifact(path="outputs/waves.nc")], missing_outputs=[],
    )
    model = Mock(run_id="run-5", output_dir=tmp_path)
    model.generate.return_value = generated
    model.run.return_value = run
    model.postprocess = Mock(side_effect=AssertionError("postprocess must not run"))
    backend = LocalPipelineBackend()
    backend._cleanup_outputs = Mock(return_value=False)
    result = backend.execute(model, backend_config=LocalConfig(command="exit 0"), processor=RecordingConfig(), cleanup_on_failure=True)
    assert result.success is False
    assert result.failed_stage is PipelineStage.RUN
    assert result.stages_completed == [PipelineStage.GENERATE]
    assert result.stage_timings[-1].stage is PipelineStage.RUN
    assert result.error == "primary run failure"
    assert result.cleaned_up is False


def test_pipeline_postprocess_failure_retains_nested_evidence_and_prefix(tmp_path):
    generated = GenerateSuccess(run_id="run-5", staging_dir=str(tmp_path), generated_files=[], timing=timing())
    run = run_success(tmp_path)
    post = PostprocessFailure(
        run_id="run-5", error="postprocess failed", output_dir=str(tmp_path), timing=timing(),
        artifacts=run.artifacts, expected_outputs=run.expected_outputs, missing_outputs=[],
    )
    model = Mock(run_id="run-5", output_dir=tmp_path)
    model.generate.return_value = generated
    model.run.return_value = run
    model.postprocess.return_value = post
    backend = LocalPipelineBackend()
    result = backend.execute(model, backend_config=LocalConfig(command="exit 0"), processor=RecordingConfig())
    assert result.success is False
    assert result.failed_stage is PipelineStage.POSTPROCESS
    assert result.stages_completed == [PipelineStage.GENERATE, PipelineStage.RUN]
    assert result.postprocess_results is post
    assert [stage.stage for stage in result.stage_timings] == [PipelineStage.GENERATE, PipelineStage.RUN]
    assert result.error == "postprocess failed"


def test_cli_sidecar_input_preserves_typed_evidence(tmp_path):
    payload = run_success(tmp_path)
    sidecar = Mock(payload=payload)
    restored = _build_postprocess_processor_input(sidecar)
    assert restored is payload
    assert restored.artifacts == payload.artifacts
    assert TypeAdapter(ModelRunResult).validate_python(restored) == payload
