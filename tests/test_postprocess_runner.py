"""Focused coverage for ordered composition and generic transfer."""
from datetime import datetime, timezone
from rompy.core.responses import (
    ArtifactType,
    LocalArtifact,
    ModelRunSuccess,
    PostprocessFailure,
    PostprocessSuccess,
    TimingInfo,
)
from rompy.postprocess import PostprocessContext, PostprocessFailurePolicy
from rompy.postprocess.runner import run_postprocess_pipeline
from rompy.postprocess.transfer import TransferPostprocessor, TransferPostprocessorConfig

NOW = datetime.now(timezone.utc)


def _run(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "result.txt").write_text("result")
    artifact = LocalArtifact(path="result.txt", artifact_type=ArtifactType.TEXT)
    return ModelRunSuccess(
        run_id="runner-test",
        backend_used="test",
        output_dir=str(output),
        workspace_dir=str(tmp_path),
        artifacts=[artifact],
        expected_outputs=[artifact],
        missing_outputs=[],
        timing=TimingInfo(start_time=NOW, end_time=NOW),
    )


class _Step:
    def __init__(self, name, fail=False):
        self.name = name
        self.fail = fail

    def process(self, context):
        if self.fail:
            return PostprocessFailure(
                run_id=context.run_result.run_id,
                error=f"{self.name} failed",
                output_dir=str(context.output_dir),
                artifacts=list(context.artifacts),
                expected_outputs=list(context.expected_outputs),
                missing_outputs=list(context.missing_outputs),
                timing=TimingInfo(start_time=NOW, end_time=NOW),
            )
        return PostprocessSuccess(
            run_id=context.run_result.run_id,
            output_dir=str(context.output_dir),
            validated=True,
            artifacts=list(context.artifacts),
            expected_outputs=list(context.expected_outputs),
            missing_outputs=list(context.missing_outputs),
            timing=TimingInfo(start_time=NOW, end_time=NOW),
        )


def test_fail_fast_retains_unattempted_and_one_sidecar(tmp_path):
    result = run_postprocess_pipeline(
        _run(tmp_path), [_Step("first", True), _Step("second")], staging_dir=tmp_path
    )
    assert not result.success
    assert [item["status"] for item in result.metadata["postprocess_pipeline"]["steps"]] == [
        "failed",
        "unattempted",
    ]
    assert (tmp_path / "postprocess_result.json").exists()


def test_continue_retains_primary_and_secondary_errors(tmp_path):
    result = run_postprocess_pipeline(
        _run(tmp_path),
        [_Step("first", True), _Step("second", True)],
        staging_dir=tmp_path,
        failure_policy=PostprocessFailurePolicy.CONTINUE,
    )
    assert not result.success
    evidence = result.metadata["postprocess_pipeline"]
    assert evidence["primary_error"] == "first failed"
    assert evidence["secondary_errors"] == ["second failed"]


def test_transfer_redacts_credentials_and_reuses_success(monkeypatch, tmp_path):
    import rompy.postprocess.transfer as transfer_module

    calls = []

    class Destination:
        def put(self, source, destination):
            calls.append((source, destination))

    monkeypatch.setattr(transfer_module, "get_transfer", lambda _: Destination())
    context = PostprocessContext.from_run_result(_run(tmp_path), staging_dir=tmp_path)
    processor = TransferPostprocessor(
        TransferPostprocessorConfig(
            destinations=["file://user:secret@example.test/archive"],
            artifact_types=[ArtifactType.TEXT],
        )
    )
    first = processor.process(context)
    assert first.success
    assert "secret" not in first.model_dump_json()
    context = context.with_state("transfer", processor._state_updates)
    second = processor.process(context)
    assert second.success
    assert len(calls) == 1
    assert all("secret" not in str(item) for item in calls)
