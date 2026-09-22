"""Canonical issue #4 sidecar persistence tests."""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from rompy.core import result_persistence
from rompy.core.responses import (
    GenerateResultSidecar,
    GenerateSuccess,
    LocalArtifact,
    ModelRunSuccess,
    NormalizedContext,
    PostprocessResultSidecar,
    PostprocessSuccess,
    RunResultSidecar,
    TimingInfo,
)

START = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)


def timing(seconds: float = 1.0) -> TimingInfo:
    return TimingInfo(start_time=START, end_time=START + timedelta(seconds=seconds))


def generate_sidecar() -> GenerateResultSidecar:
    return GenerateResultSidecar(
        run_id="run-generate",
        status="success",
        success=True,
        staging_dir="staging/run-generate",
        payload=GenerateSuccess(
            run_id="run-generate",
            staging_dir="staging/run-generate",
            generated_files=["config.nml"],
            timing=timing(),
        ),
    )


def run_sidecar() -> RunResultSidecar:
    payload = ModelRunSuccess(
        run_id="run-1",
        backend_used="local",
        output_dir="results/run-1",
        timing=timing(2.25),
        artifacts=[LocalArtifact(path="outputs/waves.nc")],
        expected_outputs=[LocalArtifact(path="outputs/waves.nc")],
        missing_outputs=[LocalArtifact(path="outputs/wind.nc", reason="not produced")],
        metadata={"attempt": 1, "labels": ["canonical"]},
    )
    return RunResultSidecar(
        run_id="run-1", status="success", success=True, payload=payload
    )


def postprocess_sidecar() -> PostprocessResultSidecar:
    payload = PostprocessSuccess(
        run_id="run-1",
        output_dir="results/run-1",
        validated=True,
        timing=timing(),
        artifacts=[LocalArtifact(path="outputs/waves.nc")],
    )
    return PostprocessResultSidecar(
        run_id="run-1", status="success", success=True, payload=payload
    )


@pytest.mark.parametrize(
    ("writer", "loader", "sidecar", "filename"),
    [
        (
            result_persistence.write_generate_result,
            result_persistence.load_generate_result,
            generate_sidecar,
            result_persistence.GENERATE_RESULT_FILENAME,
        ),
        (
            result_persistence.write_run_result,
            result_persistence.load_run_result,
            run_sidecar,
            result_persistence.RUN_RESULT_FILENAME,
        ),
        (
            result_persistence.write_postprocess_result,
            result_persistence.load_postprocess_result,
            postprocess_sidecar,
            result_persistence.POSTPROCESS_RESULT_FILENAME,
        ),
    ],
)
def test_each_canonical_sidecar_round_trips(tmp_path, writer, loader, sidecar, filename):
    value = sidecar()
    path = writer(tmp_path, value)
    assert path == tmp_path / filename
    assert loader(path).model_dump(mode="json") == value.model_dump(mode="json")


def test_wire_json_has_numeric_duration_and_metadata(tmp_path):
    path = result_persistence.write_run_result(tmp_path, run_sidecar())
    raw = json.loads(path.read_text())
    assert raw["schema_version"] == 2
    assert raw["payload"]["timing"]["duration_seconds"] == 2.25
    assert raw["payload"]["metadata"] == {"attempt": 1, "labels": ["canonical"]}


def test_repeated_writes_are_byte_deterministic(tmp_path):
    sidecar = run_sidecar()
    path = result_persistence.write_run_result(tmp_path, sidecar)
    first = path.read_bytes()
    result_persistence.write_run_result(tmp_path, sidecar)
    assert path.read_bytes() == first
    assert result_persistence.load_run_result(path).model_dump(mode="json") == sidecar.model_dump(mode="json")


def test_loaders_reject_malformed_missing_kind_version_and_legacy(tmp_path):
    path = tmp_path / result_persistence.RUN_RESULT_FILENAME
    path.write_text("not-json")
    with pytest.raises(ValueError, match="Invalid JSON"):
        result_persistence.load_run_result(path)

    path.write_text(json.dumps({"kind": "run_result", "schema_version": 2}))
    with pytest.raises(ValueError, match="Invalid canonical"):
        result_persistence.load_run_result(path)

    for version in (None, True, 1, 3):
        raw = run_sidecar().model_dump(mode="json")
        raw["schema_version"] = version
        path.write_text(json.dumps(raw))
        with pytest.raises(ValueError, match="schema_version"):
            result_persistence.load_run_result(path)

    raw = run_sidecar().model_dump(mode="json")
    raw["kind"] = "legacy_result"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="kind"):
        result_persistence.load_run_result(path)


def test_loader_rejects_envelope_payload_mismatches(tmp_path):
    path = result_persistence.write_run_result(tmp_path, run_sidecar())
    raw = json.loads(path.read_text())
    raw["payload"]["run_id"] = "different"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="run_id"):
        result_persistence.load_run_result(path)

    raw = run_sidecar().model_dump(mode="json")
    raw["status"] = "failed"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="status"):
        result_persistence.load_run_result(path)


def test_write_failure_cleans_temp_and_preserves_existing_destination(tmp_path, monkeypatch):
    path = result_persistence.write_run_result(tmp_path, run_sidecar())
    previous = path.read_bytes()
    real_fdopen = result_persistence.os.fdopen

    class FailingStream:
        def __init__(self, fd):
            self.fd = fd

        def __enter__(self):
            return self

        def __exit__(self, *_):
            os.close(self.fd)

        def write(self, _data):
            raise OSError("interrupted temp write")

        def flush(self):
            return None

        def fileno(self):
            return self.fd

    monkeypatch.setattr(result_persistence.os, "fdopen", lambda fd, mode: FailingStream(fd))
    with pytest.raises(OSError, match="interrupted temp write"):
        result_persistence.write_run_result(tmp_path, run_sidecar())
    assert path.read_bytes() == previous
    assert list(tmp_path.glob(".run_result.json.*")) == []
    monkeypatch.setattr(result_persistence.os, "fdopen", real_fdopen)


def test_replace_failure_cleans_temp_and_preserves_existing_destination(tmp_path, monkeypatch):
    path = result_persistence.write_run_result(tmp_path, run_sidecar())
    previous = path.read_bytes()
    monkeypatch.setattr(
        result_persistence.os,
        "replace",
        lambda *_: (_ for _ in ()).throw(OSError("replace failed")),
    )
    with pytest.raises(OSError, match="replace failed"):
        result_persistence.write_run_result(tmp_path, run_sidecar())
    assert path.read_bytes() == previous
    assert list(tmp_path.glob(".run_result.json.*")) == []


def test_directory_fsync_failure_is_observable_and_cleans_temp(tmp_path, monkeypatch):
    path = result_persistence.write_run_result(tmp_path, run_sidecar())
    previous = path.read_bytes()
    calls = 0
    real_fsync = result_persistence.os.fsync

    def fail_directory_sync(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("directory fsync failed")
        return real_fsync(fd)

    monkeypatch.setattr(result_persistence.os, "fsync", fail_directory_sync)
    with pytest.raises(OSError, match="directory fsync failed"):
        result_persistence.write_run_result(tmp_path, run_sidecar())
    assert path.exists()
    assert path.read_bytes() != b""
    assert list(tmp_path.glob(".run_result.json.*")) == []
    assert path.read_bytes() != previous or calls == 2


def test_non_serializable_metadata_is_rejected_before_filesystem_write(tmp_path):
    with pytest.raises(ValidationError, match="JSON-safe"):
        ModelRunSuccess(
            run_id="run-1",
            backend_used="local",
            output_dir="results/run-1",
            timing=timing(),
            metadata={"bad": object()},
        )
    assert list(tmp_path.iterdir()) == []


def test_normalized_context_uses_numeric_interval():
    context = NormalizedContext(
        model_type="ww3",
        period_start=START,
        period_end=START + timedelta(days=1),
        period_interval=3600,
        output_dir="results",
        staging_dir="staging",
        config_hash="abc",
    )
    assert context.period_interval == 3600.0
    with pytest.raises(ValidationError, match="numeric"):
        NormalizedContext(
            model_type="ww3",
            period_start=START,
            period_end=START + timedelta(days=1),
            period_interval="1h",
            output_dir="results",
            staging_dir="staging",
            config_hash="abc",
        )