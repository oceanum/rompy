"""
Postprocessor module for ROMPY.

This module provides postprocessor classes and their configurations for
processing model outputs after execution.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from rompy.core.responses import (
    Artifact,
    ArtifactType,
    PostprocessFailure,
    PostprocessResult,
    PostprocessSuccess,
    TimingInfo,
)

from .config import (
    BasePostprocessorConfig,
    NoopPostprocessorConfig,
    ProcessorConfig,
)

logger = logging.getLogger(__name__)

__all__ = [
    "NoopPostprocessor",
    "NoopPostprocessorConfig",
    "BasePostprocessorConfig",
    "ProcessorConfig",
]


class NoopPostprocessor:
    """A postprocessor that does nothing.

    This is a placeholder implementation that simply returns a success message.
    It's useful as a base class or for testing.
    """

    def process(
        self,
        model_run,
        validate_outputs: bool = True,
        output_dir: Optional[Union[str, Path]] = None,
        **kwargs,
    ) -> PostprocessResult:
        """Process the output of a model run (does nothing).

        Args:
            model_run: The ModelRun instance whose outputs to process
            validate_outputs: Whether to validate that output directory exists
            output_dir: Override output directory to check (defaults to model_run output)
            **kwargs: Additional parameters (unused)

        Returns:
            PostprocessResult: Discriminated union of PostprocessSuccess or PostprocessFailure

        Raises:
            ValueError: If model_run is invalid

        Examples:
            ::

                result = processor.process(model_run, validate_outputs=True)
                if result.success:
                    print(f"Found {len(result.artifacts)} artifacts")
                else:
                    print(f"Failed: {result.error}")
        """
        start_time = datetime.now(timezone.utc)

        # Validate input parameters
        if not model_run:
            return PostprocessFailure(
                run_id="unknown",
                error="model_run cannot be None",
                message="Invalid input parameters",
                timing=TimingInfo(
                    start_time=start_time, end_time=datetime.now(timezone.utc)
                ),
            )

        if not hasattr(model_run, "run_id"):
            return PostprocessFailure(
                run_id="unknown",
                error="model_run must have a run_id attribute",
                message="Invalid input parameters",
                timing=TimingInfo(
                    start_time=start_time, end_time=datetime.now(timezone.utc)
                ),
            )

        logger.info(f"Starting no-op postprocessing for run_id: {model_run.run_id}")

        try:
            # Determine output directory
            if output_dir:
                check_dir = Path(output_dir)
            else:
                check_dir = Path(model_run.output_dir) / model_run.run_id

            # Validate outputs if requested
            if validate_outputs:
                if not check_dir.exists():
                    logger.warning(f"Output directory does not exist: {check_dir}")
                    return PostprocessFailure(
                        run_id=model_run.run_id,
                        error=f"Output directory not found: {check_dir}",
                        output_dir=str(check_dir),
                        message="Validation failed",
                        timing=TimingInfo(
                            start_time=start_time, end_time=datetime.now(timezone.utc)
                        ),
                    )

                discovered_files = sorted(check_dir.rglob("*"), key=lambda f: str(f))

                ext_map = {
                    ".yaml": ArtifactType.YAML,
                    ".yml": ArtifactType.YAML,
                    ".nc": ArtifactType.NETCDF,
                    ".png": ArtifactType.PLOT,
                    ".jpg": ArtifactType.PLOT,
                    ".jpeg": ArtifactType.PLOT,
                    ".pdf": ArtifactType.PLOT,
                    ".svg": ArtifactType.PLOT,
                    ".txt": ArtifactType.TEXT,
                }

                artifacts = [
                    Artifact(
                        path=str(f),
                        artifact_type=ext_map.get(f.suffix.lower(), ArtifactType.OTHER),
                        size_bytes=f.stat().st_size,
                    )
                    for f in discovered_files
                    if f.is_file()
                ]
                file_count = len(artifacts)
                logger.info(f"Found {file_count} output files in {check_dir}")

                logger.info(
                    f"No-op postprocessing completed for run_id: {model_run.run_id}"
                )

                return PostprocessSuccess(
                    run_id=model_run.run_id,
                    output_dir=str(check_dir),
                    validated=True,
                    file_count=file_count,
                    artifacts=artifacts,
                    message="No postprocessing requested - validation only",
                    timing=TimingInfo(
                        start_time=start_time, end_time=datetime.now(timezone.utc)
                    ),
                )
            else:
                # No validation requested
                logger.info(
                    f"No-op postprocessing completed for run_id: {model_run.run_id} (no validation)"
                )

                return PostprocessSuccess(
                    run_id=model_run.run_id,
                    output_dir=str(check_dir),
                    validated=False,
                    message="No postprocessing requested - validation skipped",
                    timing=TimingInfo(
                        start_time=start_time, end_time=datetime.now(timezone.utc)
                    ),
                )

        except Exception as e:
            logger.exception(f"Error in no-op postprocessor: {e}")
            return PostprocessFailure(
                run_id=getattr(model_run, "run_id", "unknown"),
                error=str(e),
                message="Exception during postprocessing",
                timing=TimingInfo(
                    start_time=start_time, end_time=datetime.now(timezone.utc)
                ),
            )
