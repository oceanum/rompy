"""Ordered postprocessing composition owned by ROMPy core.

Steps are deliberately small: they receive a typed :class:`PostprocessContext`
and return a typed result.  This module is the only place where steps are
ordered, failures are interpreted, and the canonical postprocess sidecar is
written.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path

from pydantic import TypeAdapter

from rompy.core.responses import (
    PostprocessFailure,
    PostprocessResult,
    PostprocessResultSidecar,
    PostprocessSuccess,
    TimingInfo,
)
from rompy.core.result_persistence import persist_result

from .protocol import (
    PostprocessContext,
    PostprocessFailurePolicy,
    PostprocessResultValue,
    PostprocessStep,
)


def _message(error: BaseException, fallback: str) -> str:
    text = str(error)
    return text.strip() or fallback


def _step_name(step: object, index: int) -> str:
    value = getattr(step, "name", None) or getattr(step, "type", None)
    return str(value or f"step-{index + 1}")


def _evidence(name: str, status: str, **values: object) -> dict[str, object]:
    result: dict[str, object] = {"name": name, "status": status}
    result.update(values)
    return result


def run_postprocess_pipeline(
    run_result,
    steps: Iterable[PostprocessStep],
    *,
    staging_dir: Path | str | None = None,
    failure_policy: PostprocessFailurePolicy = PostprocessFailurePolicy.FAIL_FAST,
    operational_state: Mapping[str, Mapping[str, object]] | None = None,
) -> PostprocessResultValue:
    """Execute ordered steps and persist one final canonical result.

    Exceptions at a step boundary are converted to failure evidence.  A
    failure in ``CONTINUE`` mode is handed to the next step as context, while
    ``FAIL_FAST`` records the remaining steps as unattempted.  Step metadata is
    intentionally ordinary JSON metadata so the existing result schema remains
    backwards compatible.
    """
    start = datetime.now(timezone.utc)
    policy = PostprocessFailurePolicy(failure_policy)
    context = PostprocessContext.from_run_result(
        run_result,
        staging_dir=staging_dir,
        failure_policy=policy,
        operational_state=operational_state or {},
    )
    step_list = list(steps)
    evidence: list[dict[str, object]] = []
    current: PostprocessResultValue | None = None
    primary_error: str | None = None
    secondary_errors: list[str] = []

    for index, step in enumerate(step_list):
        name = _step_name(step, index)
        if primary_error is not None and policy is PostprocessFailurePolicy.FAIL_FAST:
            evidence.append(_evidence(name, "unattempted"))
            continue
        try:
            # Dispatch is explicit: context-capable processors advertise the
            # context protocol or expose a dedicated context method.  Every
            # other processor remains on the legacy ModelRunResult seam;
            # structural name/process presence is not a context capability.
            if getattr(step, "input_protocol", None) == "model_run_result":
                value = step.process(context.run_result)
            elif getattr(step, "input_protocol", None) == "context":
                value = step.process(context)
            elif callable(getattr(step, "process_context", None)):
                value = step.process_context(context)
            else:
                adapter = getattr(step, "process_legacy", None)
                value = (
                    adapter(context.run_result)
                    if callable(adapter)
                    else step.process(context.run_result)
                )
            current = TypeAdapter(PostprocessResult).validate_python(value)
        except Exception as exc:  # noqa: BLE001 - plugin boundary evidence
            message = _message(exc, f"postprocess step {name} failed")
            current = PostprocessFailure(
                run_id=context.run_result.run_id,
                error=message,
                output_dir=str(context.output_dir) if context.output_dir else None,
                artifacts=list(context.artifacts),
                expected_outputs=list(context.expected_outputs),
                missing_outputs=list(context.missing_outputs),
                timing=TimingInfo(start_time=start, end_time=datetime.now(timezone.utc)),
            )
        if current.success:
            evidence.append(_evidence(name, "succeeded"))
            context = context.handoff(current)
            updates = getattr(step, "_state_updates", None)
            namespace = getattr(getattr(step, "config", None), "state_namespace", None)
            if updates and namespace:
                context = context.with_state(namespace, updates)
        else:
            evidence.append(_evidence(name, "failed", error=current.error))
            if primary_error is None:
                primary_error = current.error
            else:
                secondary_errors.append(current.error)
            # A failure result is still a typed artifact handoff in CONTINUE.
            context = context.handoff(current)

    if current is None:
        current = PostprocessSuccess(
            run_id=context.run_result.run_id,
            output_dir=str(context.output_dir or ""),
            validated=False,
            artifacts=list(context.artifacts),
            expected_outputs=list(context.expected_outputs),
            missing_outputs=list(context.missing_outputs),
            message="No postprocessing steps configured",
            timing=TimingInfo(start_time=start, end_time=datetime.now(timezone.utc)),
        )
    elif primary_error is not None and current.success:
        # CONTINUE still reports an aggregate failure: successful later work is
        # retained as evidence, but callers must not mistake partial output for
        # an all-step success.
        current = PostprocessFailure(
            run_id=current.run_id,
            error=primary_error,
            output_dir=current.output_dir,
            artifacts=list(current.artifacts),
            expected_outputs=list(current.expected_outputs),
            missing_outputs=list(current.missing_outputs),
            message="One or more postprocessing steps failed",
            metadata={
                **current.metadata,
                "postprocess_pipeline": {
                    "failure_policy": policy.value,
                    "steps": evidence,
                    "primary_error": primary_error,
                    "secondary_errors": secondary_errors,
                },
            },
            timing=current.timing,
        )
    elif primary_error is not None:
        current = current.model_copy(
            update={
                "metadata": {
                    **current.metadata,
                    "postprocess_pipeline": {
                        "failure_policy": policy.value,
                        "steps": evidence,
                        "primary_error": primary_error,
                        "secondary_errors": secondary_errors,
                    },
                }
            }
        )
    else:
        current = current.model_copy(
            update={
                "metadata": {
                    **current.metadata,
                    "postprocess_pipeline": {
                        "failure_policy": policy.value,
                        "steps": evidence,
                    },
                }
            }
        )

    # One sidecar, owned here rather than by a step.  A persistence error is a
    # secondary error when an operation already failed.
    directory = Path(staging_dir or context.staging_dir or context.output_dir or ".")
    sidecar = PostprocessResultSidecar(
        created_at=datetime.now(timezone.utc),
        run_id=current.run_id,
        staging_dir=str(directory),
        status="success" if current.success else "failed",
        success=current.success,
        error=None if current.success else current.error,
        payload=current,
    )
    return persist_result(
        current,
        sidecar,
        directory,
        primary_error=primary_error or (None if current.success else current.error),
    )


# Clear names for callers and compatibility with likely integrations.
PostprocessPipelineRunner = run_postprocess_pipeline
compose_postprocessors = run_postprocess_pipeline

__all__ = ["PostprocessPipelineRunner", "compose_postprocessors", "run_postprocess_pipeline"]
