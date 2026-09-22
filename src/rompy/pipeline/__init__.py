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
    StageTiming,
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
        backend_config: Optional[
            Union[LocalConfig, DockerConfig, "SlurmConfig"]
        ] = None,
        processor: Optional["BasePostprocessorConfig"] = None,
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
            PipelineResult: Success or failure result with stage tracking, timing, and nested postprocess results.

            The result is a discriminated union:
            - PipelineSuccess: Contains stages_completed, nested postprocess_results, timing
            - PipelineFailure: Contains failed_stage, error, optional postprocess_results

        Raises:
            ValueError: If model_run is invalid or parameters are invalid
            TypeError: If processor is not a BasePostprocessorConfig instance

        Examples:
            ::

                from rompy.backends import LocalConfig
                from rompy.postprocess.config import NoopPostprocessorConfig

                backend = LocalPipelineBackend()
                result = backend.execute(
                    model_run=my_model,
                    backend_config=LocalConfig(timeout=3600),
                    processor=NoopPostprocessorConfig()
                )

                # Type-safe result handling with discriminated union
                if result.success:
                    # Type narrowing: result is PipelineSuccess
                    print(f"Stages: {[s.value for s in result.stages_completed]}")
                    print(f"Duration: {result.timing.duration_seconds}s")

                    # Access nested postprocess results
                    if result.postprocess_results and result.postprocess_results.success:
                        print(f"Artifacts: {len(result.postprocess_results.artifacts)}")
                else:
                    # Type narrowing: result is PipelineFailure
                    print(f"Failed at: {result.failed_stage.value}")
                    print(f"Error: {result.error}")

                # Serialize to dict for logging
                result_dict = result.model_dump()
        """
        from rompy.postprocess.config import BasePostprocessorConfig
        from rompy.backends.config import BaseBackendConfig

        # Validate input parameters
        if not model_run:
            raise ValueError("model_run cannot be None")

        if not hasattr(model_run, "run_id"):
            raise ValueError("model_run must have a run_id attribute")

        if backend_config is None:
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
        stage_timings: List[StageTiming] = []
        cleaned_up = False
        staging_dir = None

        backend_type = backend_config.__class__.__name__.replace("Config", "").lower()
        processor_type = getattr(
            processor,
            "type",
            processor.__class__.__name__.replace("Config", "").lower(),
        )
        logger.info(f"Starting pipeline execution for run_id: {model_run.run_id}")
        logger.info(
            f"Pipeline configuration: backend='{backend_type}', processor='{processor_type}'"
        )

        try:
            # Stage 1: Generate input files
            logger.info(f"Stage 1: Generating input files for {model_run.run_id}")

            try:
                generate_result = model_run.generate()
                if not generate_result.success:
                    stage_timings.append(StageTiming(stage=PipelineStage.GENERATE, timing=generate_result.timing))
                    raise RuntimeError(generate_result.error)
                staging_dir = Path(generate_result.staging_dir)
                stage_timings.append(StageTiming(stage=PipelineStage.GENERATE, timing=generate_result.timing))
                stages_completed.append(PipelineStage.GENERATE)
                logger.info(f"Input files generated successfully in: {staging_dir}")
            except Exception as e:
                logger.exception(f"Failed to generate input files: {e}")
                return PipelineFailure(
                    success=False,
                    run_id=model_run.run_id,
                    backend=backend_type,
                    processor=processor_type,
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
                output_dir = Path(staging_dir)
                if not output_dir.exists():
                    logger.error(f"Output directory was not created: {output_dir}")
                    return PipelineFailure(
                        success=False,
                        run_id=model_run.run_id,
                        backend=backend_type,
                        processor=processor_type,
                        stages_completed=stages_completed,
                        failed_stage=PipelineStage.GENERATE,
                        error=f"Output directory not found: {output_dir}",
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
                run_result = model_run.run(
                    backend=backend_config, workspace_dir=staging_dir
                )

                if not run_result.success:
                    stage_timings.append(StageTiming(stage=PipelineStage.RUN, timing=run_result.timing))
                    logger.error("Model run failed")
                    if cleanup_on_failure:
                        cleaned_up = self._cleanup_outputs(staging_dir)
                    return PipelineFailure(
                        success=False,
                        run_id=model_run.run_id,
                        backend=backend_type,
                        processor=processor_type,
                        stages_completed=stages_completed,
                        failed_stage=PipelineStage.RUN,
                        staging_dir=str(staging_dir),
                        output_dir=run_result.output_dir,
                        error=run_result.error,
                        message=run_result.message or "Model run failed",
                        metadata={"stage_result": run_result.model_dump(mode="json")},
                        stage_timings=stage_timings,
                        timing=TimingInfo(
                            start_time=start_time, end_time=datetime.now(timezone.utc)
                        ),
                        cleaned_up=cleaned_up,
                    )

                stage_timings.append(StageTiming(stage=PipelineStage.RUN, timing=run_result.timing))
                stages_completed.append(PipelineStage.RUN)
                logger.info("Model run completed successfully")

            except Exception as e:
                logger.exception(f"Error during model run: {e}")
                if cleanup_on_failure:
                    cleaned_up = self._cleanup_outputs(staging_dir)
                return PipelineFailure(
                    success=False,
                    run_id=model_run.run_id,
                    backend=backend_type,
                    processor=processor_type,
                    stages_completed=stages_completed,
                    failed_stage=PipelineStage.RUN,
                    staging_dir=str(staging_dir),
                    message=f"Model run error: {str(e)}",
                    error=str(e),
                    timing=TimingInfo(
                        start_time=start_time, end_time=datetime.now(timezone.utc)
                    ),
                    cleaned_up=cleaned_up,
                )

            # Stage 3: Postprocess outputs
            logger.info(f"Stage 3: Postprocessing with {processor_type}")

            try:
                postprocess_results = model_run.postprocess(
                    processor=processor, processor_input=run_result, **process_kwargs
                )

                # Check if postprocessing was successful
                if isinstance(postprocess_results, PostprocessFailure):
                    if cleanup_on_failure:
                        cleaned_up = self._cleanup_outputs(staging_dir)
                    logger.warning(
                        "Postprocessing failed but pipeline will mark as complete with failure"
                    )
                    # Return PipelineFailure with nested PostprocessFailure
                    return PipelineFailure(
                        success=False,
                        run_id=model_run.run_id,
                        backend=backend_type,
                        processor=processor_type,
                        stages_completed=stages_completed,
                        failed_stage=PipelineStage.POSTPROCESS,
                        staging_dir=str(staging_dir),
                        output_dir=postprocess_results.output_dir,
                        message=f"Postprocessing failed: {postprocess_results.message}",
                        error=postprocess_results.error,
                        postprocess_results=postprocess_results,
                        metadata={"stage_result": postprocess_results.model_dump(mode="json")},
                        stage_timings=stage_timings,
                        timing=TimingInfo(
                            start_time=start_time, end_time=datetime.now(timezone.utc)
                        ),
                        cleaned_up=cleaned_up,
                    )

                stage_timings.append(StageTiming(stage=PipelineStage.POSTPROCESS, timing=postprocess_results.timing))
                stages_completed.append(PipelineStage.POSTPROCESS)
                logger.info("Postprocessing completed")

            except Exception as e:
                logger.exception(f"Error during postprocessing: {e}")
                return PipelineFailure(
                    success=False,
                    run_id=model_run.run_id,
                    backend=backend_type,
                    processor=processor_type,
                    stages_completed=stages_completed,
                    failed_stage=PipelineStage.POSTPROCESS,
                    staging_dir=str(staging_dir),
                    message=f"Postprocessing error: {str(e)}",
                    error=str(e),
                    stage_timings=stage_timings,
                    timing=TimingInfo(
                        start_time=start_time, end_time=datetime.now(timezone.utc)
                    ),
                    cleaned_up=cleaned_up,
                )

            # Pipeline completed successfully
            logger.info(
                f"Pipeline execution completed successfully for run_id: {model_run.run_id}"
            )

            # Compute output_dir for successful pipeline
            output_dir_path = Path(run_result.output_dir)

            return PipelineSuccess(
                success=True,
                run_id=model_run.run_id,
                backend=backend_type,
                processor=processor_type,
                stages_completed=stages_completed,
                staging_dir=str(staging_dir),
                output_dir=str(output_dir_path),
                postprocess_results=postprocess_results,
                stage_timings=stage_timings,
                message="Pipeline completed successfully",
                timing=TimingInfo(
                    start_time=start_time, end_time=datetime.now(timezone.utc)
                ),
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
                processor=processor_type,
                stages_completed=stages_completed,
                failed_stage=(
                    stages_completed[-1] if stages_completed else PipelineStage.GENERATE
                ),
                message=f"Pipeline error: {str(e)}",
                error=str(e),
                timing=TimingInfo(
                    start_time=start_time, end_time=datetime.now(timezone.utc)
                ),
                cleaned_up=cleaned_up,
            )

    def _cleanup_outputs(self, output_dir) -> bool:
        """Clean the actual generated path and report the confirmed outcome."""
        if output_dir is None:
            return False
        try:
            output_dir = Path(output_dir)
            if not output_dir.exists():
                return True
            logger.info(f"Cleaning up output directory: {output_dir}")
            import shutil
            shutil.rmtree(output_dir)
            return not output_dir.exists()
        except Exception as e:
            logger.warning(f"Failed to cleanup output directory: {e}")
            return False
