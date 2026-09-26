"""Contract tests for the typed postprocessor context and step protocol."""

from datetime import datetime, timezone

from rompy.core.responses import (
    ArtifactType,
    LocalArtifact,
    ModelRunSuccess,
    PostprocessSuccess,
    TimingInfo,
)
from rompy.postprocess import (
    PostprocessContext,
    PostprocessFailurePolicy,
    PostprocessProcessor,
    PostprocessStep,
)
from rompy.postprocess import NoopPostprocessor, NoopPostprocessorConfig


class EvidenceStep:
    """Minimal in-tree step used to exercise the public protocol."""

    name = "evidence"

    def process(self, context: PostprocessContext) -> PostprocessSuccess:
        return PostprocessSuccess(
            run_id=context.run_result.run_id,
            output_dir=str(context.output_dir or "outputs"),
            validated=True,
            artifacts=list(context.artifacts),
            expected_outputs=list(context.expected_outputs),
            missing_outputs=list(context.missing_outputs),
            timing=TimingInfo(start_time=NOW, end_time=NOW),
        )


NOW = datetime.now(timezone.utc)


def run_result(tmp_path):
    artifact = LocalArtifact(path="waves.nc", artifact_type=ArtifactType.NETCDF)
    return ModelRunSuccess(
        run_id="protocol-run",
        backend_used="local",
        output_dir=str(tmp_path),
        artifacts=[artifact],
        expected_outputs=[artifact],
        missing_outputs=[],
        timing=TimingInfo(start_time=NOW, end_time=NOW),
    )


def test_context_and_step_use_concrete_typed_handoff(tmp_path):
    context = PostprocessContext.from_run_result(
        run_result(tmp_path),
        staging_dir=tmp_path / "staging",
        failure_policy=PostprocessFailurePolicy.CONTINUE,
        operational_state={"example": {"attempt": 1}},
    )

    step = EvidenceStep()
    assert isinstance(step, PostprocessStep)
    assert context.namespace("example")["attempt"] == 1
    result = step.process(context)
    next_context = context.handoff(result)

    assert isinstance(result, PostprocessSuccess)
    assert next_context.artifacts == tuple(result.artifacts)
    assert next_context.failure_policy is PostprocessFailurePolicy.CONTINUE


def test_existing_single_processor_conforms_without_composition(tmp_path):
    processor = NoopPostprocessor(NoopPostprocessorConfig(validate_outputs=False))
    assert isinstance(processor, PostprocessProcessor)
    result = processor.process(run_result(tmp_path))
    assert result.success is True
