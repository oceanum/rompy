"""Model-neutral, retry-safe transfer postprocessor.

The implementation consumes only canonical artifact identities.  It has no
knowledge of model plugins, restart conventions, or production credentials.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import re
from typing import Callable, Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, model_validator

from rompy.core.artifacts import compute_source_checksum, stable_artifact_identity
from rompy.core.responses import ArtifactType, LocalArtifact, RemoteArtifact, PostprocessFailure, PostprocessSuccess, TimingInfo
from rompy.transfer.registry import get_transfer
from .config import BasePostprocessorConfig
from .protocol import PostprocessContext, PostprocessFailurePolicy


def normalize_destination(destination: str) -> str:
    """Remove userinfo from a destination while preserving its address."""
    value = str(destination).strip()
    parsed = urlsplit(value)
    if not parsed.scheme or parsed.username is None:
        return value
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))


def _redact(value: object, destinations: tuple[str, ...]) -> str:
    text = str(value)
    for original in destinations:
        text = text.replace(original, normalize_destination(original))
    # Also protect credentials that came from backend exception messages.
    return re.sub(r"(://)([^/@\s]+)@", r"\1<redacted>@", text)


def _join(destination: str, name: str) -> str:
    return normalize_destination(destination).rstrip("/") + "/" + name.lstrip("/")


def _remote_evidence(uri: str, artifact_type: ArtifactType | None):
    # file:// is a local test/backup destination, not a canonical remote URI.
    if urlsplit(uri).scheme.lower() == "file":
        return None
    return RemoteArtifact(uri=uri, artifact_type=artifact_type)


def _default_name(artifact: LocalArtifact) -> str:
    return Path(artifact.path).name


class TransferPostprocessorConfig(BasePostprocessorConfig):
    """Configuration for generic destination fan-out."""

    type: str = "transfer"
    destinations: list[str] = Field(min_length=1)
    artifact_types: list[ArtifactType] | None = None
    required: bool = True
    # Alias retained as a readable spelling for configuration authors.
    required_outputs: bool | None = None
    failure_policy: PostprocessFailurePolicy = PostprocessFailurePolicy.CONTINUE
    max_retries: int = Field(0, ge=0, le=20)
    state_namespace: str = "transfer"

    @model_validator(mode="after")
    def apply_required_alias(self):
        if self.required_outputs is not None:
            self.required = self.required_outputs
        return self

    def get_postprocessor_class(self):
        return TransferPostprocessor


class TransferPostprocessor:
    """Transfer local artifacts to every configured destination.

    ``target_naming`` is intentionally injected at runtime, not serialized in
    config.  It receives a canonical local artifact and returns a basename.
    """

    name = "transfer"

    def __init__(self, config: TransferPostprocessorConfig, target_naming: Callable[[LocalArtifact], str] | None = None):
        self.config = config
        self.target_naming = target_naming or _default_name
        self._state_updates: dict[str, dict[str, Any]] = {}

    def _lock(self, context: PostprocessContext):
        root = context.staging_dir or context.output_dir
        if root is None:
            return None
        directory = Path(root) / ".rompy-postprocess" / self.config.state_namespace
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "transfer.lock"
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError("transfer state is locked") from exc
        os.close(fd)
        return path

    def _source_path(self, context: PostprocessContext, artifact: LocalArtifact) -> Path:
        root = context.output_dir or context.staging_dir
        if root is None:
            raise FileNotFoundError("no output workspace is available")
        path = (Path(root) / artifact.path).resolve(strict=False)
        workspace = Path(root).resolve(strict=False)
        try:
            path.relative_to(workspace)
        except ValueError as exc:
            raise ValueError("local artifact escapes output workspace") from exc
        return path

    def process(self, context: PostprocessContext):
        start = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        destinations = tuple(self.config.destinations)
        lock = self._lock(context)
        try:
            reconciliation = context.reconcile_artifacts(artifact_types=self.config.artifact_types)
            required_missing = reconciliation.missing
            if self.config.artifact_types:
                allowed = set(self.config.artifact_types)
                required_missing = [item for item in required_missing if item.artifact_type in allowed]
            if self.config.required and required_missing:
                missing = ", ".join(stable_artifact_identity(item) for item in required_missing)
                return PostprocessFailure(
                    run_id=context.run_result.run_id,
                    error=f"required source artifacts are missing: {missing}",
                    output_dir=str(context.output_dir) if context.output_dir else None,
                    artifacts=list(context.artifacts), expected_outputs=list(context.expected_outputs),
                    missing_outputs=list(context.missing_outputs),
                    timing=TimingInfo(start_time=start, end_time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)),
                )
            sources = [item for item in reconciliation.selected if isinstance(item, LocalArtifact)]
            if not sources:
                return PostprocessSuccess(
                    run_id=context.run_result.run_id,
                    output_dir=str(context.output_dir or ""), validated=True,
                    artifacts=list(context.artifacts), expected_outputs=list(context.expected_outputs),
                    missing_outputs=list(context.missing_outputs), file_count=0,
                    message="No transferable artifacts selected",
                    timing=TimingInfo(start_time=start, end_time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)),
                )
            prior = dict(context.namespace(self.config.state_namespace))
            # A direct processor retry has no runner to hand back a context;
            # retain only redacted request records locally as a convenience.
            prior.update(self._state_updates)
            pairs: list[dict[str, Any]] = []
            transferred: list[RemoteArtifact] = []
            failures = []
            for source_index, source in enumerate(sources):
                source_path = self._source_path(context, source)
                checksum = compute_source_checksum(source, context.output_dir or context.staging_dir)
                name = self.target_naming(source)
                if not isinstance(name, str) or not name or Path(name).name != name:
                    raise ValueError("target naming strategy must return a safe basename")
                for destination_index, destination in enumerate(destinations):
                    clean_destination = normalize_destination(destination)
                    target = _join(clean_destination, name)
                    request_id = hashlib.sha256(json.dumps({"source": stable_artifact_identity(source), "checksum": checksum, "target": target}, sort_keys=True).encode()).hexdigest()
                    state_key = f"{stable_artifact_identity(source)}|{checksum}|{target}"
                    if prior.get(state_key, {}).get("request_id") == request_id and prior.get(state_key, {}).get("status") == "succeeded":
                        pairs.append({"source": stable_artifact_identity(source), "destination": target, "request_id": request_id, "status": "skipped"})
                        evidence = _remote_evidence(target, source.artifact_type)
                        if evidence is not None:
                            transferred.append(evidence)
                        continue
                    attempt = 0
                    error = None
                    while attempt <= self.config.max_retries:
                        attempt += 1
                        try:
                            get_transfer(clean_destination).put(source_path, target)
                            error = None
                            break
                        except Exception as exc:
                            error = _redact(exc, destinations)
                    if error is None:
                        pairs.append({"source": stable_artifact_identity(source), "destination": target, "request_id": request_id, "status": "succeeded", "attempts": attempt})
                        self._state_updates[state_key] = {"request_id": request_id, "status": "succeeded"}
                        evidence = _remote_evidence(target, source.artifact_type)
                        if evidence is not None:
                            transferred.append(evidence)
                    else:
                        pair = {"source": stable_artifact_identity(source), "destination": target, "request_id": request_id, "status": "failed", "attempts": attempt, "error": error}
                        pairs.append(pair)
                        failures.append(pair)
                        if self.config.failure_policy == PostprocessFailurePolicy.FAIL_FAST:
                            # Preserve complete per-pair evidence even though
                            # execution stops at the first failed pair.
                            for skipped_destination in destinations[destination_index + 1:]:
                                skipped_target = _join(skipped_destination, name)
                                pairs.append({"source": stable_artifact_identity(source), "destination": skipped_target, "status": "unattempted"})
                            for skipped_source in sources[source_index + 1:]:
                                skipped_name = self.target_naming(skipped_source)
                                for skipped_destination in destinations:
                                    pairs.append({"source": stable_artifact_identity(skipped_source), "destination": _join(skipped_destination, skipped_name), "status": "unattempted"})
                            break
                if failures and self.config.failure_policy == PostprocessFailurePolicy.FAIL_FAST:
                    break
            metadata = {"transfer": {"pairs": pairs, "state_namespace": self.config.state_namespace}}
            if failures:
                return PostprocessFailure(
                    run_id=context.run_result.run_id,
                    error=f"{len(failures)} transfer pair(s) failed",
                    output_dir=str(context.output_dir) if context.output_dir else None,
                    artifacts=list(context.artifacts) + transferred,
                    expected_outputs=list(context.expected_outputs), missing_outputs=list(context.missing_outputs),
                    metadata=metadata,
                    timing=TimingInfo(start_time=start, end_time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)),
                )
            # Operational state is kept in the processor and consumed by a
            # runner adapter; it never contains raw destinations or credentials.
            return PostprocessSuccess(
                run_id=context.run_result.run_id, output_dir=str(context.output_dir or ""), validated=True,
                artifacts=list(context.artifacts) + transferred, expected_outputs=list(context.expected_outputs),
                missing_outputs=list(context.missing_outputs), file_count=len(sources), metadata=metadata,
                timing=TimingInfo(start_time=start, end_time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)),
            )
        finally:
            if lock is not None:
                try:
                    lock.unlink()
                except FileNotFoundError:
                    pass

    def process_legacy(self, run_result):
        context = PostprocessContext.from_run_result(run_result)
        return self.process(context)


__all__ = ["TransferPostprocessor", "TransferPostprocessorConfig", "normalize_destination"]
