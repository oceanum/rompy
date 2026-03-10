"""
Local pipeline backend for model execution.

This module provides the local pipeline backend implementation.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from rompy.backends import DockerConfig, LocalConfig
from rompy.core.responses import (
    PipelineFailure,
    PipelineResult,
    PipelineStage,
    PipelineSuccess,
    PostprocessFailure,
    TimingInfo,
)

if TYPE_CHECKING:
    from rompy.backends.config import SlurmConfig
    from rompy.postprocess.config import BasePostprocessorConfig

logger = logging.getLogger(__name__)


class LocalPipelineBackend:
    """Local pipeline backend that executes the full workflow locally.

    This backend uses the existing generate(), run() and postprocess() methods
    to execute the complete pipeline locally.
    """

    def execute(
        self,
        model_run,
        backend_config: Union[LocalConfig, DockerConfig, "SlurmConfig"] = None,
        processor: "BasePostprocessorConfig" = None,
        run_kwargs: Optional[Dict[str, Any]] = None,
        process_kwargs: Optional[Dict[str, Any]] = None,
        cleanup_on_failure: bool = False,
        validate_stages: bool = True,
        **kwargs,
    ) -> PipelineResult:
        """Execute the model pipeline locally.

        Args:
            model_run: The ModelRun instance to execute
            backend_config: Backend configuration object (LocalConfig, DockerConfig, etc.)
            processor: Processor configuration for the postprocess stage
            run_kwargs: Additional parameters for the run stage (deprecated, use backend_config)
            process_kwargs: Additional parameters for the postprocess stage
            cleanup_on_failure: Whether to cleanup outputs on pipeline failure
            validate_stages: Whether to validate each stage before proceeding
            **kwargs: Additional parameters (for backward compatibility)

        Returns:
            PipelineResult: Success or failure result with stage tracking, timing, and nested postprocess results

        Raises:
            ValueError: If model_run is invalid or parameters are invalid
            TypeError: If processor is not a BasePostprocessorConfig instance
        """
        from rompy.postprocess.config import BasePostprocessorConfig
        from rompy.backends.config import BaseBackendConfig

        # Validate input parameters
        if not model_run:
            raise ValueError("model_run cannot be None")

        if not hasattr(model_run, "run_id"):
            raise ValueError("model_run must have a run_id attribute")

        # Handle backward compatibility: accept run_backend string from kwargs
        if backend_config is None:
            run_backend = kwargs.get("run_backend")
            if run_backend:
                logger.warning(
                    "Passing run_backend as string is deprecated. "
                    "Use backend_config parameter instead."
                )
                run_kwargs = run_kwargs or {}
                backend_config = self._create_backend_config(run_backend, run_kwargs)
            else:
                raise ValueError(
                    "backend_config is required. Provide a BackendConfig instance."
                )

        if not isinstance(backend_config, BaseBackendConfig):
            raise TypeError(
                f"backend_config must be a BaseBackendConfig instance, "
                f"got {type(backend_config).__name__}"
            )

        if processor is None:
            raise ValueError("processor configuration is required")

        if not isinstance(processor, BasePostprocessorConfig):
            raise TypeError(
                f"processor must be a BasePostprocessorConfig instance, "
                f"got {type(processor).__name__}"
            )

        # Initialize parameters
        process_kwargs = process_kwargs or {}
        start_time = datetime.now(timezone.utc)
        stages_completed: List[PipelineStage] = []
        cleaned_up = False

        backend_type = backend_config.__class__.__name__.replace("Config", "").lower()
        logger.info(f"Starting pipeline execution for run_id: {model_run.run_id}")
        logger.info(
            f"Pipeline configuration: backend='{backend_type}', processor='{processor.type}'"
        )

        try:
            # Stage 1: Generate input files
            logger.info(f"Stage 1: Generating input files for {model_run.run_id}")

            try:
                staging_dir = model_run.generate()
                stages_completed.append(PipelineStage.GENERATE)
                logger.info(f"Input files generated successfully in: {staging_dir}")
            except Exception as e:
                logger.exception(f"Failed to generate input files: {e}")
                return PipelineFailure(
                    success=False,
                    run_id=model_run.run_id,
                    backend=backend_type,
                    processor=processor.type,
                    stages_completed=stages_completed,
                    failed_stage=PipelineStage.GENERATE,
                    message=f"Input file generation failed: {str(e)}",
                    error=str(e),
                    timing=TimingInfo(
                        start_time=start_time, end_time=datetime.now(timezone.utc)
                    ),
                    cleaned_up=cleaned_up,
                )

            # Validate generation stage
            if validate_stages:
                output_dir = Path(model_run.output_dir) / model_run.run_id
                if not output_dir.exists():
                    logger.error(f"Output directory was not created: {output_dir}")
                    return PipelineFailure(
                        success=False,
                        run_id=model_run.run_id,
                        backend=backend_type,
                        processor=processor.type,
                        stages_completed=stages_completed,
                        failed_stage=PipelineStage.GENERATE,
                        message=f"Output directory not found after generation: {output_dir}",
                        timing=TimingInfo(
                            start_time=start_time, end_time=datetime.now(timezone.utc)
                        ),
                        cleaned_up=cleaned_up,
                    )

            # Stage 2: Run the model
            logger.info(f"Stage 2: Running model using {backend_type} backend")

            try:
                # Pass the generated workspace directory to avoid duplicate generation
                run_success = model_run.run(
                    backend=backend_config, workspace_dir=staging_dir
                )

                if not run_success:
                    logger.error("Model run failed")
                    if cleanup_on_failure:
                        self._cleanup_outputs(model_run)
                        cleaned_up = True
                    return PipelineFailure(
                        success=False,
                        run_id=model_run.run_id,
                        backend=backend_type,
                        processor=processor.type,
                        stages_completed=stages_completed,
                        failed_stage=PipelineStage.RUN,
                        message="Model run failed",
                        timing=TimingInfo(
                            start_time=start_time, end_time=datetime.now(timezone.utc)
                        ),
                        cleaned_up=cleaned_up,
                    )

                stages_completed.append(PipelineStage.RUN)
                logger.info("Model run completed successfully")

            except Exception as e:
                logger.exception(f"Error during model run: {e}")
                if cleanup_on_failure:
                    self._cleanup_outputs(model_run)
                    cleaned_up = True
                return PipelineFailure(
                    success=False,
                    run_id=model_run.run_id,
                    backend=backend_type,
                    processor=processor.type,
                    stages_completed=stages_completed,
                    failed_stage=PipelineStage.RUN,
                    message=f"Model run error: {str(e)}",
                    error=str(e),
                    timing=TimingInfo(
                        start_time=start_time, end_time=datetime.now(timezone.utc)
                    ),
                    cleaned_up=cleaned_up,
                )

            # Stage 3: Postprocess outputs
            logger.info(f"Stage 3: Postprocessing with {processor.type}")

            try:
                postprocess_results = model_run.postprocess(
                    processor=processor, **process_kwargs
                )
                stages_completed.append(PipelineStage.POSTPROCESS)

                # Check if postprocessing was successful
                if isinstance(postprocess_results, PostprocessFailure):
                    logger.warning(
                        "Postprocessing failed but pipeline will mark as complete with failure"
                    )
                    # Return PipelineFailure with nested PostprocessFailure
                    return PipelineFailure(
                        success=False,
                        run_id=model_run.run_id,
                        backend=backend_type,
                        processor=processor.type,
                        stages_completed=stages_completed,
                        failed_stage=PipelineStage.POSTPROCESS,
                        message=f"Postprocessing failed: {postprocess_results.message}",
                        error=postprocess_results.error,
                        postprocess_results=postprocess_results,
                        timing=TimingInfo(
                            start_time=start_time, end_time=datetime.now(timezone.utc)
                        ),
                        cleaned_up=cleaned_up,
                    )

                logger.info("Postprocessing completed")

            except Exception as e:
                logger.exception(f"Error during postprocessing: {e}")
                return PipelineFailure(
                    success=False,
                    run_id=model_run.run_id,
                    backend=backend_type,
                    processor=processor.type,
                    stages_completed=stages_completed,
                    failed_stage=PipelineStage.POSTPROCESS,
                    message=f"Postprocessing error: {str(e)}",
                    error=str(e),
                    timing=TimingInfo(
                        start_time=start_time, end_time=datetime.now(timezone.utc)
                    ),
                    cleaned_up=cleaned_up,
                )

            # Pipeline completed successfully
            logger.info(
                f"Pipeline execution completed successfully for run_id: {model_run.run_id}"
            )
            return PipelineSuccess(
                success=True,
                run_id=model_run.run_id,
                backend=backend_type,
                processor=processor.type,
                stages_completed=stages_completed,
                postprocess_results=postprocess_results,
                message="Pipeline completed successfully",
                timing=TimingInfo(
                    start_time=start_time, end_time=datetime.now(timezone.utc)
                ),
                cleaned_up=cleaned_up,
            )

        except Exception as e:
            logger.exception(f"Unexpected error in pipeline execution: {e}")
            if cleanup_on_failure:
                self._cleanup_outputs(model_run)
                cleaned_up = True
            return PipelineFailure(
                success=False,
                run_id=model_run.run_id,
                backend=backend_type,
                processor=processor.type,
                stages_completed=stages_completed,
                failed_stage=stages_completed[-1]
                if stages_completed
                else PipelineStage.GENERATE,
                message=f"Pipeline error: {str(e)}",
                error=str(e),
                timing=TimingInfo(
                    start_time=start_time, end_time=datetime.now(timezone.utc)
                ),
                cleaned_up=cleaned_up,
            )

    def _cleanup_outputs(self, model_run) -> None:
        """Clean up output files on pipeline failure.

        Args:
            model_run: The ModelRun instance
        """
        try:
            output_dir = Path(model_run.output_dir) / model_run.run_id
            if output_dir.exists():
                logger.info(f"Cleaning up output directory: {output_dir}")
                import shutil

                shutil.rmtree(output_dir)
                logger.info("Cleanup completed")
        except Exception as e:
            logger.warning(f"Failed to cleanup output directory: {e}")

    def _create_backend_config(self, run_backend: str, run_kwargs: Dict[str, Any]):
        """Create appropriate backend configuration from string name and kwargs.

        Args:
            run_backend: Backend name ("local" or "docker")
            run_kwargs: Additional configuration parameters

        Returns:
            Backend configuration object

        Raises:
            ValueError: If backend name is not supported
        """
        if run_backend == "local":
            # Filter kwargs to only include valid LocalConfig fields
            valid_fields = set(LocalConfig.model_fields.keys())
            filtered_kwargs = {k: v for k, v in run_kwargs.items() if k in valid_fields}
            if filtered_kwargs != run_kwargs:
                invalid_fields = set(run_kwargs.keys()) - valid_fields
                logger.warning(f"Ignoring invalid LocalConfig fields: {invalid_fields}")
            return LocalConfig(**filtered_kwargs)
        elif run_backend == "docker":
            # Filter kwargs to only include valid DockerConfig fields
            valid_fields = set(DockerConfig.model_fields.keys())
            filtered_kwargs = {k: v for k, v in run_kwargs.items() if k in valid_fields}
            if filtered_kwargs != run_kwargs:
                invalid_fields = set(run_kwargs.keys()) - valid_fields
                logger.warning(
                    f"Ignoring invalid DockerConfig fields: {invalid_fields}"
                )
            return DockerConfig(**filtered_kwargs)
        else:
            raise ValueError(
                f"Unsupported backend: {run_backend}. Supported: local, docker"
            )
