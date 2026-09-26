"""Typed contracts for composable postprocessing steps.

This module deliberately defines contracts, not a composition runner.  The
core runner remains the only owner of result construction and canonical
``postprocess_result.json`` persistence; a future runner can use these types
without giving a step filesystem or sidecar ownership.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Mapping, Protocol, TypeAlias, runtime_checkable

from pydantic import TypeAdapter

from rompy.core.responses import (
    ArtifactIdentity,
    ModelRunFailure,
    ModelRunResult,
    ModelRunSuccess,
    PostprocessFailure,
    PostprocessResult,
    PostprocessSuccess,
)

ModelRunResultValue: TypeAlias = ModelRunSuccess | ModelRunFailure
PostprocessResultValue: TypeAlias = PostprocessSuccess | PostprocessFailure
JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
OperationalState: TypeAlias = Mapping[str, Mapping[str, JSONValue]]


class PostprocessFailurePolicy(str, Enum):
    """Policy a future ordered runner applies when a step returns failure."""

    FAIL_FAST = "fail_fast"
    CONTINUE = "continue"


# Short spelling for callers that do not need the postprocess prefix.
FailurePolicy = PostprocessFailurePolicy


@dataclass(frozen=True)
class PostprocessContext:
    """Immutable handoff context owned by the core postprocess runner.

    ``run_result`` is the concrete, validated result from the run stage.  A
    step receives observed artifact evidence in ``artifacts`` plus the
    independent expected/missing evidence.  A future ordered runner creates a
    new context from each validated step result with :meth:`handoff`; steps do
    not mutate or replace another step's evidence.

    ``operational_state`` is an intentionally non-canonical, namespaced
    mapping.  A processor may read its own namespace and return updated state
    to a future runner, but it must not use this mapping as a result sidecar or
    write ``postprocess_result.json``.  The core runner owns failure handling,
    final result construction, and the one canonical sidecar.
    """

    run_result: ModelRunResultValue
    output_dir: Path | None = None
    staging_dir: Path | None = None
    artifacts: tuple[ArtifactIdentity, ...] = ()
    expected_outputs: tuple[ArtifactIdentity, ...] = ()
    missing_outputs: tuple[ArtifactIdentity, ...] = ()
    failure_policy: PostprocessFailurePolicy = PostprocessFailurePolicy.FAIL_FAST
    operational_state: OperationalState = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the public boundary and snapshot evidence collections."""
        validated_run = TypeAdapter(ModelRunResult).validate_python(self.run_result)
        object.__setattr__(self, "run_result", validated_run)
        adapter = TypeAdapter(ArtifactIdentity)
        for field_name in ("artifacts", "expected_outputs", "missing_outputs"):
            evidence = tuple(
                adapter.validate_python(item) for item in getattr(self, field_name)
            )
            object.__setattr__(self, field_name, evidence)
        if not isinstance(self.failure_policy, PostprocessFailurePolicy):
            object.__setattr__(
                self,
                "failure_policy",
                PostprocessFailurePolicy(self.failure_policy),
            )
        if any(
            not isinstance(namespace, str) or not namespace.strip()
            for namespace in self.operational_state
        ):
            raise ValueError("operational_state namespaces must be non-empty strings")

    @classmethod
    def from_run_result(
        cls,
        run_result: ModelRunResultValue,
        *,
        staging_dir: Path | str | None = None,
        failure_policy: PostprocessFailurePolicy = PostprocessFailurePolicy.FAIL_FAST,
        operational_state: OperationalState | None = None,
    ) -> "PostprocessContext":
        """Build initial context from a concrete validated run result.

        Existing run-stage evidence is copied into immutable tuples.  This is
        the only initial handoff needed by a processor; no live ``ModelRun``
        object or path-only substitute is accepted.
        """
        result = TypeAdapter(ModelRunResult).validate_python(run_result)
        return cls(
            run_result=result,
            output_dir=Path(result.output_dir) if result.output_dir else None,
            staging_dir=Path(staging_dir)
            if staging_dir is not None
            else (Path(result.workspace_dir) if result.workspace_dir else None),
            artifacts=tuple(result.artifacts),
            expected_outputs=tuple(result.expected_outputs),
            missing_outputs=tuple(result.missing_outputs),
            failure_policy=failure_policy,
            operational_state=operational_state or {},
        )

    def namespace(self, name: str) -> Mapping[str, JSONValue]:
        """Return one processor-owned operational-state namespace."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("operational-state namespace must be a non-empty string")
        return self.operational_state.get(name, {})

    def handoff(self, result: PostprocessResultValue) -> "PostprocessContext":
        """Create the next ordered-step context from a concrete step result.

        The core boundary validates the returned discriminated union before
        handoff.  Artifact evidence is replaced by the step's observed
        evidence while expected and missing evidence remain explicit.
        """
        validated = TypeAdapter(PostprocessResult).validate_python(result)
        return replace(
            self,
            output_dir=Path(validated.output_dir)
            if validated.output_dir
            else self.output_dir,
            artifacts=tuple(validated.artifacts),
            expected_outputs=tuple(validated.expected_outputs),
            missing_outputs=tuple(validated.missing_outputs),
        )


@runtime_checkable
class PostprocessStep(Protocol):
    """Minimal ordered step contract for a future composition runner."""

    name: str

    def process(self, context: PostprocessContext) -> PostprocessResultValue:
        """Process one context and return a concrete typed result."""
        ...


@runtime_checkable
class PostprocessProcessor(Protocol):
    """Single-processor compatibility contract used by ``ModelRun``.

    Existing processors continue to receive a concrete ``ModelRunResult`` and
    return a concrete ``PostprocessResult``.  Composition is deliberately not
    implemented here; a future adapter can expose steps through
    :class:`PostprocessStep` while retaining this boundary.
    """

    def process(
        self, model_run: ModelRunResultValue, **kwargs: object
    ) -> PostprocessResultValue:
        """Process a validated model-run result."""
        ...


# Discoverable aliases for users describing the protocol rather than the role.
PostprocessStepProtocol = PostprocessStep
PostprocessorProtocol = PostprocessProcessor
ProcessorProtocol = PostprocessProcessor

__all__ = [
    "FailurePolicy",
    "JSONValue",
    "OperationalState",
    "PostprocessContext",
    "PostprocessFailurePolicy",
    "PostprocessProcessor",
    "PostprocessResultValue",
    "PostprocessStep",
    "PostprocessStepProtocol",
    "PostprocessorProtocol",
    "ProcessorProtocol",
]
