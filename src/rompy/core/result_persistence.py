"""Atomic sidecar persistence for result objects.

This module provides atomic write and typed load operations for sidecar JSON files:
- generate_result.json: GenerateResult sidecars
- run_result.json: ModelRunResult sidecars
- postprocess_result.json: PostprocessResult sidecars

All write operations use atomic temp-file-then-rename to prevent corruption.
All load operations validate schema_version and kind fields.

Examples:
    Write a generate result sidecar::

        from pathlib import Path
        from datetime import datetime, timezone
        from rompy.core.responses import GenerateResultSidecar, GenerateResult

        sidecar = GenerateResultSidecar(
            created_at=datetime.now(timezone.utc),
            run_id="run-123",
            staging_dir="/path/to/staging",
            status="success",
            success=True,
            payload=GenerateResult(...)
        )

        path = write_generate_result(Path("/path/to/staging"), sidecar)

    Load a run result sidecar::

        from pathlib import Path
        from rompy.core.result_persistence import load_run_result

        # Can pass directory (auto-appends run_result.json)
        sidecar = load_run_result(Path("/path/to/staging"))

        # Or pass file path directly
        sidecar = load_run_result(Path("/path/to/staging/run_result.json"))

        if sidecar.success:
            print(f"Run succeeded: {sidecar.payload.run_id}")
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from rompy.core.responses import (
    GenerateResultSidecar,
    PostprocessResultSidecar,
    RunResultSidecar,
)

# Canonical sidecar filenames
GENERATE_RESULT_FILENAME = "generate_result.json"
RUN_RESULT_FILENAME = "run_result.json"
POSTPROCESS_RESULT_FILENAME = "postprocess_result.json"


def _atomic_write(path: Path, data: bytes) -> None:
    """Atomically write bytes to path using a temp file and os.replace.

    Ensures the target directory exists and that the replace is atomic on POSIX.
    Uses tempfile.mkstemp in the same directory to avoid cross-device issues.

    Args:
        path: Destination file path
        data: Bytes to write

    Raises:
        OSError: If directory creation or write fails
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except Exception:
                pass


def _strip_duration_seconds(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove timing.duration_seconds from payload if present.

    The TimingInfo.duration_seconds field is a @computed_field that blocks
    round-trip deserialization. We must strip it before writing to avoid
    validation failures on load (RompyBaseModel has extra="forbid").

    Args:
        payload: Dictionary representation of a sidecar model

    Returns:
        Payload with timing.duration_seconds removed if present
    """
    # Check if payload has a nested payload.timing structure
    inner_payload = payload.get("payload")
    if inner_payload and isinstance(inner_payload, dict):
        timing = inner_payload.get("timing")
        if timing and isinstance(timing, dict):
            timing.pop("duration_seconds", None)

    # Also check top-level timing (for consistency)
    timing = payload.get("timing")
    if timing and isinstance(timing, dict):
        timing.pop("duration_seconds", None)

    return payload


def write_generate_result(staging_dir: Path, sidecar: GenerateResultSidecar) -> Path:
    """Write GenerateResultSidecar to staging_dir/generate_result.json atomically.

    Args:
        staging_dir: Directory to write the sidecar file
        sidecar: GenerateResultSidecar instance to persist

    Returns:
        Path to the written file

    Raises:
        OSError: If write fails
    """
    dest = Path(staging_dir) / GENERATE_RESULT_FILENAME

    # Serialize to JSON, then strip duration_seconds
    json_text = sidecar.model_dump_json(indent=2)
    payload = json.loads(json_text)
    payload = _strip_duration_seconds(payload)
    json_text = json.dumps(payload, indent=2)

    data = json_text.encode("utf-8")
    _atomic_write(dest, data)
    return dest


def write_run_result(staging_dir: Path, sidecar: RunResultSidecar) -> Path:
    """Write RunResultSidecar to staging_dir/run_result.json atomically.

    Args:
        staging_dir: Directory to write the sidecar file
        sidecar: RunResultSidecar instance to persist

    Returns:
        Path to the written file

    Raises:
        OSError: If write fails
    """
    dest = Path(staging_dir) / RUN_RESULT_FILENAME

    # Serialize to JSON, then strip duration_seconds
    json_text = sidecar.model_dump_json(indent=2)
    payload = json.loads(json_text)
    payload = _strip_duration_seconds(payload)
    json_text = json.dumps(payload, indent=2)

    data = json_text.encode("utf-8")
    _atomic_write(dest, data)
    return dest


def write_postprocess_result(
    staging_dir: Path, sidecar: PostprocessResultSidecar
) -> Path:
    """Write PostprocessResultSidecar to staging_dir/postprocess_result.json atomically.

    Args:
        staging_dir: Directory to write the sidecar file
        sidecar: PostprocessResultSidecar instance to persist

    Returns:
        Path to the written file

    Raises:
        OSError: If write fails
    """
    dest = Path(staging_dir) / POSTPROCESS_RESULT_FILENAME

    # Serialize to JSON, then strip duration_seconds
    json_text = sidecar.model_dump_json(indent=2)
    payload = json.loads(json_text)
    payload = _strip_duration_seconds(payload)
    json_text = json.dumps(payload, indent=2)

    data = json_text.encode("utf-8")
    _atomic_write(dest, data)
    return dest


def load_generate_result(path_or_dir: Path) -> GenerateResultSidecar:
    """Load a GenerateResultSidecar from a file or directory.

    Args:
        path_or_dir: Either a path to generate_result.json or a directory
            containing it

    Returns:
        Validated GenerateResultSidecar instance

    Raises:
        FileNotFoundError: If the sidecar file does not exist
        ValueError: If schema_version != 1 or kind != "generate_result"
        ValidationError: If JSON structure is invalid
    """
    p = Path(path_or_dir)
    if p.is_dir():
        p = p / GENERATE_RESULT_FILENAME
    if not p.exists():
        raise FileNotFoundError(
            f"Generate result sidecar not found: {p}\n"
            f"Expected file: {GENERATE_RESULT_FILENAME}"
        )

    raw = json.loads(p.read_text())

    # Validate schema_version
    version = raw.get("schema_version")
    if version != 1:
        raise ValueError(f"Unsupported schema_version: {version} (expected 1) in {p}")

    # Validate kind field
    kind = raw.get("kind")
    if kind != "generate_result":
        raise ValueError(
            f"Invalid kind field: {kind!r} (expected 'generate_result') in {p}"
        )

    return GenerateResultSidecar.model_validate(raw)


def load_run_result(path_or_dir: Path) -> RunResultSidecar:
    """Load a RunResultSidecar from a file or directory.

    Args:
        path_or_dir: Either a path to run_result.json or a directory containing it

    Returns:
        Validated RunResultSidecar instance

    Raises:
        FileNotFoundError: If the sidecar file does not exist
        ValueError: If schema_version != 1 or kind != "run_result"
        ValidationError: If JSON structure is invalid
    """
    p = Path(path_or_dir)
    if p.is_dir():
        p = p / RUN_RESULT_FILENAME
    if not p.exists():
        raise FileNotFoundError(
            f"Run result sidecar not found: {p}\nExpected file: {RUN_RESULT_FILENAME}"
        )

    raw = json.loads(p.read_text())

    # Validate schema_version
    version = raw.get("schema_version")
    if version != 1:
        raise ValueError(f"Unsupported schema_version: {version} (expected 1) in {p}")

    # Validate kind field
    kind = raw.get("kind")
    if kind != "run_result":
        raise ValueError(f"Invalid kind field: {kind!r} (expected 'run_result') in {p}")

    return RunResultSidecar.model_validate(raw)


def load_postprocess_result(path_or_dir: Path) -> PostprocessResultSidecar:
    """Load a PostprocessResultSidecar from a file or directory.

    Args:
        path_or_dir: Either a path to postprocess_result.json or a directory
            containing it

    Returns:
        Validated PostprocessResultSidecar instance

    Raises:
        FileNotFoundError: If the sidecar file does not exist
        ValueError: If schema_version != 1 or kind != "postprocess_result"
        ValidationError: If JSON structure is invalid
    """
    p = Path(path_or_dir)
    if p.is_dir():
        p = p / POSTPROCESS_RESULT_FILENAME
    if not p.exists():
        raise FileNotFoundError(
            f"Postprocess result sidecar not found: {p}\n"
            f"Expected file: {POSTPROCESS_RESULT_FILENAME}"
        )

    raw = json.loads(p.read_text())

    # Validate schema_version
    version = raw.get("schema_version")
    if version != 1:
        raise ValueError(f"Unsupported schema_version: {version} (expected 1) in {p}")

    # Validate kind field
    kind = raw.get("kind")
    if kind != "postprocess_result":
        raise ValueError(
            f"Invalid kind field: {kind!r} (expected 'postprocess_result') in {p}"
        )

    return PostprocessResultSidecar.model_validate(raw)
