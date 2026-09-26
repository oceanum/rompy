"""Focused coverage for ordered composition and generic transfer."""
import json
from datetime import datetime, timezone

import pytest

from rompy.core.responses import (
    ArtifactType,
    LocalArtifact,
    ModelRunSuccess,
    PostprocessFailure,
    PostprocessSuccess,
    TimingInfo,
)
from rompy.model import ModelRun
from rompy.postprocess import PostprocessContext, PostprocessFailurePolicy
from rompy.postprocess.runner import run_postprocess_pipeline
from rompy.postprocess.transfer import (
    TransferPostprocessor,
    TransferPostprocessorConfig,
)

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


def test_signed_url_is_live_only_and_fragments_are_not_evidence(monkeypatch, tmp_path):
    import rompy.postprocess.transfer as transfer_module

    calls = []
    destination = "https://user:password@example.test/archive?token=secret-token&X-Amz-Signature=sig#fragment"

    class Destination:
        def put(self, source, target):
            calls.append(target)

    monkeypatch.setattr(transfer_module, "get_transfer", lambda value: Destination())
    result = TransferPostprocessor(
        TransferPostprocessorConfig(destinations=[destination], artifact_types=[ArtifactType.TEXT])
    ).process(PostprocessContext.from_run_result(_run(tmp_path), staging_dir=tmp_path))

    assert result.success
    assert "secret-token" in calls[0]
    evidence = result.model_dump_json()
    assert all(secret not in evidence for secret in ("password", "secret-token", "X-Amz-Signature", "fragment"))
    state = next((tmp_path / ".rompy-postprocess").rglob("transfer-state.json")).read_text()
    assert all(secret not in state for secret in ("password", "secret-token", "X-Amz-Signature", "fragment"))


def test_successful_pairs_replay_from_disk_after_partial_failure(monkeypatch, tmp_path):
    import rompy.postprocess.transfer as transfer_module

    calls = []
    failed_once = {"value": True}
    destinations = ["s3://bucket/first?token=one", "s3://bucket/second?token=two"]

    class Destination:
        def __init__(self, target):
            self.target = target

        def put(self, source, target):
            calls.append(target)
            if "second" in target and failed_once["value"]:
                raise RuntimeError(f"upload failed for {target}")

    monkeypatch.setattr(transfer_module, "get_transfer", lambda value: Destination(value))
    config = TransferPostprocessorConfig(
        destinations=destinations,
        artifact_types=[ArtifactType.TEXT],
        failure_policy=PostprocessFailurePolicy.CONTINUE,
    )
    context = PostprocessContext.from_run_result(_run(tmp_path), staging_dir=tmp_path)
    first = TransferPostprocessor(config).process(context)
    assert not first.success
    failed_once["value"] = False
    second = TransferPostprocessor(config).process(context)

    assert second.success
    assert len(calls) == 3
    assert sum("first" in target for target in calls) == 1
    assert second.metadata["transfer"]["replayed_pairs"] == 1
    assert "token=one" not in json.dumps(second.model_dump(mode="json"))


def test_state_namespace_rejects_traversal_and_absolute_values():
    for namespace in ("../escape", "/absolute", "nested/name", ".", ".."):
        with pytest.raises(ValueError, match="state_namespace"):
            TransferPostprocessorConfig(destinations=["file:///tmp"], state_namespace=namespace)


def test_named_legacy_plugin_uses_explicit_result_protocol(tmp_path):
    class NamedLegacy:
        name = "named-legacy"
        input_protocol = "model_run_result"

        def process(self, result):
            assert isinstance(result, ModelRunSuccess)
            return PostprocessSuccess(
                run_id=result.run_id,
                output_dir=result.output_dir,
                validated=True,
                artifacts=list(result.artifacts),
                expected_outputs=list(result.expected_outputs),
                missing_outputs=list(result.missing_outputs),
                timing=TimingInfo(start_time=NOW, end_time=NOW),
            )

    result = run_postprocess_pipeline(_run(tmp_path), [NamedLegacy()], staging_dir=tmp_path)
    assert result.success


def test_standalone_transfer_uses_legacy_adapter(monkeypatch, tmp_path):
    import rompy.postprocess.transfer as transfer_module

    calls = []

    class Destination:
        def put(self, source, target):
            calls.append(target)

    monkeypatch.setattr(transfer_module, "get_transfer", lambda _: Destination())
    run_result = _run(tmp_path)
    model = ModelRun(run_id=run_result.run_id, output_dir=tmp_path)
    model.staging_dir.mkdir(parents=True, exist_ok=True)
    result = model.postprocess(
        TransferPostprocessorConfig(destinations=["file:///archive"], artifact_types=[ArtifactType.TEXT]),
        processor_input=run_result,
    )
    assert result.success
    assert calls == ["file:///archive/result.txt"]
