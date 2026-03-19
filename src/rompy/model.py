"""
Model run implementation for ROMPY.

This module provides the ModelRun class which is the main entry point for
running models with ROMPY.
"""

import hashlib
import os
import platform
import shutil
import zipfile as zf
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Union

from pydantic import Field

from rompy.backends import BackendConfig
from rompy.backends.config import BaseBackendConfig
from rompy.core.config import BaseConfig
from rompy.core.responses import (
    GenerateResult,
    GenerateResultSidecar,
    ModelRunResult,
    NormalizedContext,
    PipelineResult,
    PostprocessFailure,
    PostprocessResult,
    PostprocessResultSidecar,
    TimingInfo,
)
from rompy.core.time import TimeRange
from rompy.core.types import RompyBaseModel
from rompy.logging import get_logger
from rompy.utils import load_entry_points

# Initialize the logger
logger = get_logger(__name__)


# Accepted config types are defined in the entry points of the rompy.config group
CONFIG_TYPES = load_entry_points("rompy.config")


def _load_backends():
    """Load backends from entry points with fallback handling."""
    run_backends = {}
    postprocessors = {}
    pipeline_backends = {}

    # Load run backends
    try:
        for backend in load_entry_points("rompy.run"):
            name = backend.__name__.lower().replace("runbackend", "")
            run_backends[name] = backend
    except Exception as e:
        logger.warning(f"Failed to load run backends: {e}")

    # Load postprocessors
    try:
        for proc in load_entry_points("rompy.postprocess"):
            name = proc.__name__.lower().replace("postprocessor", "")
            postprocessors[name] = proc
    except Exception as e:
        logger.warning(f"Failed to load postprocessors: {e}")

    # Load pipeline backends
    try:
        for backend in load_entry_points("rompy.pipeline"):
            name = backend.__name__.lower().replace("pipelinebackend", "")
            pipeline_backends[name] = backend
    except Exception as e:
        logger.warning(f"Failed to load pipeline backends: {e}")

    return run_backends, postprocessors, pipeline_backends


# Load backends from entry points
RUN_BACKENDS, POSTPROCESSORS, PIPELINE_BACKENDS = _load_backends()


class ModelRun(RompyBaseModel):
    """A model run.

    It is intented to be model agnostic.
    It deals primarily with how the model is to be run, i.e. the period of the run
    and where the output is going. The actual configuration of the run is
    provided by the config object.

    Further explanation is given in the rompy.core.Baseconfig docstring.
    """

    # Initialize formatting variables in __init__

    model_type: Literal["modelrun"] = Field("modelrun", description="The model type.")
    run_id: str = Field("run_id", description="The run id")
    period: TimeRange = Field(
        TimeRange(
            start=datetime(2020, 2, 21, 4),
            end=datetime(2020, 2, 24, 4),
            interval="15M",
        ),
        description="The time period to run the model",
    )
    output_dir: Path = Field("./simulations", description="The output directory")
    config: Union[CONFIG_TYPES] = Field(
        default_factory=BaseConfig,
        description="The configuration object",
        discriminator="model_type",
    )
    delete_existing: bool = Field(False, description="Delete existing output directory")
    run_id_subdir: bool = Field(
        True, description="Use run_id subdirectory in the output directory"
    )
    _datefmt: str = "%Y%m%d.%H%M%S"
    _staging_dir: Path = None

    @property
    def staging_dir(self):
        """The directory where the model is staged for execution

        returns
        -------
        staging_dir : str
        """

        if self._staging_dir is None:
            self._staging_dir = self._create_staging_dir()
        return self._staging_dir

    def _create_staging_dir(self):
        if self.run_id_subdir:
            odir = Path(self.output_dir) / self.run_id
        else:
            odir = Path(self.output_dir)
        if self.delete_existing and odir.exists():
            shutil.rmtree(odir)
        odir.mkdir(parents=True, exist_ok=True)
        return odir

    @property
    def _generation_medatadata(self):
        return dict(
            _generated_at=str(datetime.now(timezone.utc)),
            _generated_by=os.environ.get("USER"),
            _generated_on=platform.node(),
        )

    def _compute_config_hash(self, staging_dir: Path) -> str:
        """Compute SHA256 hash of all files in staging_dir.

        Files are sorted by path to ensure deterministic hash.
        Returns empty string if no files exist or on any IO error.
        """
        try:
            from rompy.core.result_persistence import GENERATE_RESULT_FILENAME

            files = sorted(staging_dir.iterdir(), key=lambda f: str(f))
            files = [
                f for f in files if f.is_file() and f.name != GENERATE_RESULT_FILENAME
            ]

            if not files:
                return ""

            hasher = hashlib.sha256()
            for file_path in files:
                hasher.update(file_path.read_bytes())

            return hasher.hexdigest()
        except Exception:
            return ""

    def generate(self) -> str:
        """Generate the model input files

        returns
        -------
        staging_dir : str

        """
        # Import formatting utilities
        from rompy.formatting import format_table_row, log_box

        # Format model settings in a structured way
        config_type = type(self.config).__name__
        duration = self.period.end - self.period.start
        formatted_duration = self.period.format_duration(duration)

        # Create table rows for the model run info
        rows = [
            format_table_row("Run ID", str(self.run_id)),
            format_table_row("Model Type", config_type),
            format_table_row("Start Time", self.period.start.isoformat()),
            format_table_row("End Time", self.period.end.isoformat()),
            format_table_row("Duration", formatted_duration),
            format_table_row("Time Interval", str(self.period.interval)),
            format_table_row("Output Directory", str(self.output_dir)),
        ]

        # Add description if available
        if hasattr(self.config, "description") and self.config.description:
            rows.append(format_table_row("Description", self.config.description))

        # Create a formatted table with proper alignment
        formatted_rows = []
        key_lengths = []

        # First pass: collect all valid rows and calculate max key length
        for row in rows:
            try:
                # Split the row by the box-drawing vertical line character
                parts = [p.strip() for p in row.split("┃") if p.strip()]
                if len(parts) >= 2:  # We expect at least key and value parts
                    key = parts[0].strip()
                    value = parts[1].strip() if len(parts) > 1 else ""
                    key_lengths.append(len(key))
                    formatted_rows.append((key, value))
            except Exception as e:
                logger.warning(f"Error processing row '{row}': {e}")

        if not formatted_rows:
            logger.warning("No valid rows found for model run configuration table")
            return self._staging_dir

        max_key_len = max(key_lengths) if key_lengths else 0

        # Format the rows with proper alignment
        aligned_rows = []
        for key, value in formatted_rows:
            aligned_row = f"{key:>{max_key_len}} : {value}"
            aligned_rows.append(aligned_row)

        # Log the box with the model run info
        log_box(title="MODEL RUN CONFIGURATION", logger=logger, add_empty_line=False)

        # Log each row of the content with proper indentation
        for row in aligned_rows:
            logger.info(f"  {row}")

        # Log the bottom of the box
        log_box(
            title=None,
            logger=logger,
            add_empty_line=True,  # Just the bottom border
        )

        # Display detailed configuration info using the new formatting framework
        from rompy.formatting import log_box

        # Create a box with the configuration type as title
        log_box(f"MODEL CONFIGURATION ({config_type})")

        # Use the model's string representation which now uses the new formatting
        try:
            # The __str__ method of RompyBaseModel already handles the formatting
            config_str = str(self.config)
            for line in config_str.split("\n"):
                logger.info(line)
        except Exception as e:
            # If anything goes wrong with config formatting, log the error and minimal info
            logger.info(f"Using {type(self.config).__name__} configuration")
            logger.debug(f"Configuration string formatting error: {str(e)}")

        logger.info("")
        log_box(
            title="STARTING MODEL GENERATION",
            logger=logger,
            add_empty_line=False,
        )
        logger.info(f"Preparing input files in {self.output_dir}")

        try:
            # Collect context data
            cc_full = {}
            cc_full["runtime"] = self.model_dump()
            cc_full["runtime"]["staging_dir"] = self.staging_dir
            cc_full["runtime"].update(self._generation_medatadata)
            cc_full["runtime"].update({"_datefmt": self._datefmt})

            # Process configuration
            logger.info("Processing model configuration...")
            if callable(self.config):
                # Run the __call__() method of the config object if it is callable passing
                # the runtime instance, and fill in the context with what is returned
                logger.info("Running configuration callable...")
                cc_full["config"] = self.config(self)
            else:
                # Otherwise just fill in the context with the config instance itself
                logger.info("Using static configuration...")
                cc_full["config"] = self.config

            # Render templates
            logger.info(f"Rendering model configurations to {self.staging_dir}...")
            self.config.render(cc_full, self.output_dir)

            logger.info("")
            # Use the log_box utility function
            from rompy.formatting import log_box

            log_box(
                title="MODEL GENERATION COMPLETE",
                logger=logger,
                add_empty_line=False,
            )
            logger.info(f"Model files generated at: {self.staging_dir}")

            # Write generate result sidecar
            try:
                from rompy.core.result_persistence import write_generate_result

                # Collect generated files from staging directory
                generated_files = [
                    str(f.relative_to(self.staging_dir))
                    for f in self.staging_dir.iterdir()
                    if f.is_file()
                ]

                model_type = (
                    self.config.model_type
                    if hasattr(self.config, "model_type")
                    else type(self.config).__name__.lower()
                )

                normalized_ctx = NormalizedContext(
                    model_type=model_type,
                    period_start=self.period.start,
                    period_end=self.period.end,
                    output_dir=str(self.output_dir),
                    staging_dir=str(self.staging_dir),
                    config_hash=self._compute_config_hash(self.staging_dir),
                    extensions=self._get_normalized_extensions(),
                )

                # Build GenerateResult payload
                generate_result = GenerateResult(
                    generated_at=datetime.now(timezone.utc),
                    staging_dir=str(self.staging_dir),
                    config_file=None,  # Could be extracted from config if available
                    success=True,
                    generated_files=generated_files,
                )

                # Build GenerateResultSidecar envelope
                sidecar = GenerateResultSidecar(
                    created_at=datetime.now(timezone.utc),
                    run_id=self.run_id,
                    staging_dir=str(self.staging_dir),
                    status="success",
                    success=True,
                    payload=generate_result,
                    normalized_context=normalized_ctx,
                )

                # Write atomically to staging_dir/generate_result.json
                sidecar_path = write_generate_result(self.staging_dir, sidecar)
                logger.debug(f"Wrote generate result sidecar to {sidecar_path}")
            except Exception as e:
                # Don't fail the entire generation if sidecar writing fails
                logger.warning(f"Failed to write generate result sidecar: {e}")

            return self.staging_dir

        except Exception as e:
            # Write failure sidecar if staging_dir is known
            try:
                if self.staging_dir is not None:
                    from rompy.core.result_persistence import write_generate_result

                    model_type = (
                        self.config.model_type
                        if hasattr(self.config, "model_type")
                        else type(self.config).__name__.lower()
                    )

                    normalized_ctx = NormalizedContext(
                        model_type=model_type,
                        period_start=self.period.start,
                        period_end=self.period.end,
                        output_dir=str(self.output_dir),
                        staging_dir=str(self.staging_dir),
                        config_hash="",
                        extensions=self._get_normalized_extensions(),
                    )

                    failure_sidecar = GenerateResultSidecar(
                        created_at=datetime.now(timezone.utc),
                        run_id=self.run_id,
                        staging_dir=str(self.staging_dir),
                        status="failed",
                        success=False,
                        error=str(e),
                        payload=GenerateResult(
                            generated_at=datetime.now(timezone.utc),
                            staging_dir=str(self.staging_dir),
                            config_file=None,
                            success=False,
                            generated_files=[],
                            error=str(e),
                        ),
                        normalized_context=normalized_ctx,
                    )
                    write_generate_result(self.staging_dir, failure_sidecar)
            except Exception:
                # Sidecar write failure must not mask original error
                pass
            raise

    def zip(self) -> str:
        """Zip the input files for the model run

        This function zips the input files for the model run and returns the
        name of the zip file. It also cleans up the staging directory leaving
        only the settings.json file that can be used to reproduce the run.

        returns
        -------
        zip_fn : str
        """
        # Use the log_box utility function
        from rompy.formatting import log_box

        log_box(
            title="ARCHIVING MODEL FILES",
            logger=logger,
        )

        # Always remove previous zips
        zip_fn = Path(str(self.staging_dir) + ".zip")
        if zip_fn.exists():
            logger.info(f"Removing existing archive at {zip_fn}")
            zip_fn.unlink()

        # Count files to be archived
        file_count = sum([len(fn) for _, _, fn in os.walk(self.staging_dir)])
        logger.info(f"Archiving {file_count} files from {self.staging_dir}")

        # Create zip archive
        with zf.ZipFile(zip_fn, mode="w", compression=zf.ZIP_DEFLATED) as z:
            for dp, dn, fn in os.walk(self.staging_dir):
                for filename in fn:
                    source_path = os.path.join(dp, filename)
                    rel_path = os.path.relpath(source_path, self.staging_dir)
                    z.write(source_path, rel_path)

        # Clean up staging directory
        logger.info(f"Cleaning up staging directory {self.staging_dir}")
        shutil.rmtree(self.staging_dir)

        from rompy.formatting import log_box

        log_box(
            f"✓ Archive created successfully: {zip_fn}",
            logger=logger,
            add_empty_line=False,
        )
        return zip_fn

    def __call__(self):
        return self.generate()

    def _get_normalized_extensions(self) -> Dict[str, Any]:
        get_extensions = getattr(self.config, "get_normalized_extensions", None)
        if callable(get_extensions):
            try:
                extensions = get_extensions()
                if isinstance(extensions, dict):
                    return extensions
            except Exception:
                pass
        return {}

    def _compute_run_normalized_context(
        self, workspace_dir: Optional[str]
    ) -> NormalizedContext:
        """Compute normalized context for run sidecars.

        Tries to copy normalized_context from generate_result.json if present,
        otherwise computes fallback from model fields.

        Args:
            workspace_dir: Workspace directory path (may be None)

        Returns:
            NormalizedContext for inclusion in RunResultSidecar
        """
        normalized_ctx = None

        # Try to copy from generate_result.json if workspace exists
        if workspace_dir:
            try:
                from rompy.core.result_persistence import load_generate_result

                gen_result = load_generate_result(Path(workspace_dir))
                if gen_result.normalized_context is not None:
                    normalized_ctx = gen_result.normalized_context
            except (FileNotFoundError, Exception):
                pass

        # Fallback: compute from model fields if not found or no workspace
        if normalized_ctx is None:
            model_type = (
                self.config.model_type
                if hasattr(self.config, "model_type")
                else type(self.config).__name__.lower()
            )
            normalized_ctx = NormalizedContext(
                model_type=model_type,
                period_start=self.period.start,
                period_end=self.period.end,
                output_dir=str(self.output_dir) if self.output_dir else "",
                staging_dir=str(workspace_dir) if workspace_dir else "",
                config_hash=(
                    self._compute_config_hash(Path(workspace_dir))
                    if workspace_dir
                    else ""
                ),
                extensions=self._get_normalized_extensions(),
            )

        return normalized_ctx

    def run(
        self, backend: BackendConfig, workspace_dir: Optional[str] = None
    ) -> ModelRunResult:
        """
        Run the model using the specified backend configuration.

        This method uses Pydantic configuration objects that provide type safety
        and validation for all backend parameters. It returns a structured
        ``ModelRunResult`` with timing information, metadata, and detailed error
        messages.

        Args:
            backend: Pydantic configuration object (LocalConfig, DockerConfig, etc.)
            workspace_dir: Path to generated workspace directory (optional)

        Returns:
            ModelRunResult: Structured result object with success status, timing,
                backend information, and error details (if applicable).

        Examples:
            ::

                from rompy.backends import LocalConfig, DockerConfig

                # Local execution
                result = model.run(LocalConfig(timeout=3600, command="python run.py"))
                if result.success:
                    print(f"Completed in {result.timing.duration_seconds}s")

                # Docker execution
                result = model.run(DockerConfig(image="swan:latest", cpu=4, memory="2g"))
                if not result.success:
                    print(f"Failed: {result.error}")
        """
        start_time = datetime.now(timezone.utc)

        try:
            # Validate backend type
            if not isinstance(backend, BaseBackendConfig):
                result = ModelRunResult(
                    success=False,
                    run_id=self.run_id,
                    backend_used=type(backend).__name__,
                    output_dir=str(self.output_dir) if self.output_dir else None,
                    workspace_dir=workspace_dir,
                    error=f"Backend must be a subclass of BaseBackendConfig, got {type(backend).__name__}",
                    message="Invalid backend configuration",
                    timing=TimingInfo(
                        start_time=start_time,
                        end_time=datetime.now(timezone.utc),
                    ),
                )

                # Write run_result.json sidecar
                if workspace_dir:
                    from rompy.core.result_persistence import write_run_result
                    from rompy.core.responses import RunResultSidecar

                    normalized_ctx = self._compute_run_normalized_context(workspace_dir)

                    sidecar = RunResultSidecar(
                        created_at=datetime.now(timezone.utc),
                        run_id=result.run_id,
                        staging_dir=str(workspace_dir),
                        status="failed",
                        success=False,
                        error=result.error,
                        normalized_context=normalized_ctx,
                        payload=result,
                    )
                    try:
                        write_run_result(Path(workspace_dir), sidecar)
                    except Exception:
                        # Sidecar write failure must NOT mask run result
                        pass

                return result

            logger.debug(f"Using backend config: {type(backend).__name__}")

            # Dispatch directly to the backend
            backend_class = backend.get_backend_class()
            backend_instance = backend_class()
            success = backend_instance.run(
                self, config=backend, workspace_dir=workspace_dir
            )

            # Determine output/workspace directories
            output_dir_path = None
            if self.output_dir:
                output_dir_path = Path(self.output_dir)
                if self.run_id_subdir:
                    output_dir_path = output_dir_path / self.run_id
            output_dir_str = str(output_dir_path) if output_dir_path else None
            workspace_dir_str = str(workspace_dir) if workspace_dir else None
            backend_class_name = type(backend).__name__.replace("Config", "")
            artifacts = []
            if success and output_dir_str:
                artifacts = self.config.validate_outputs(output_dir_str)
                normalized_artifacts = []
                output_dir_base = Path(output_dir_str)
                for artifact in artifacts:
                    artifact_path = Path(artifact.path)
                    if artifact_path.is_absolute():
                        try:
                            normalized_path = artifact_path.relative_to(output_dir_base)
                        except ValueError:
                            normalized_path = artifact_path
                    else:
                        try:
                            normalized_path = artifact_path.relative_to(output_dir_base)
                        except ValueError:
                            normalized_path = artifact_path
                    normalized_artifacts.append(
                        artifact.model_copy(update={"path": str(normalized_path)})
                    )
                artifacts = normalized_artifacts

            result = ModelRunResult(
                success=success,
                run_id=self.run_id,
                backend_used=backend_class_name,
                output_dir=output_dir_str,
                workspace_dir=workspace_dir_str,
                artifacts=artifacts,
                message=(
                    "Model execution completed successfully"
                    if success
                    else "Model execution failed"
                ),
                timing=TimingInfo(
                    start_time=start_time,
                    end_time=datetime.now(timezone.utc),
                ),
                metadata={
                    "backend_config": backend.model_dump(exclude_none=True),
                },
            )

            # Write run_result.json sidecar
            if workspace_dir:
                from rompy.core.result_persistence import write_run_result
                from rompy.core.responses import RunResultSidecar

                normalized_ctx = self._compute_run_normalized_context(workspace_dir)

                sidecar = RunResultSidecar(
                    created_at=datetime.now(timezone.utc),
                    run_id=result.run_id,
                    staging_dir=str(workspace_dir),
                    status="success" if result.success else "failed",
                    success=result.success,
                    error=result.error,
                    normalized_context=normalized_ctx,
                    payload=result,
                )
                try:
                    write_run_result(Path(workspace_dir), sidecar)
                except Exception:
                    # Sidecar write failure must NOT mask run result
                    pass

            return result

        except Exception as e:
            # Wrap any exceptions in ModelRunResult
            workspace_dir_str = str(workspace_dir) if workspace_dir else None

            result = ModelRunResult(
                success=False,
                run_id=self.run_id,
                backend_used=(
                    type(backend).__name__.replace("Config", "")
                    if isinstance(backend, BaseBackendConfig)
                    else "unknown"
                ),
                output_dir=str(self.output_dir) if self.output_dir else None,
                workspace_dir=workspace_dir_str,
                error=str(e),
                message=f"Model execution failed with exception: {str(e)}",
                timing=TimingInfo(
                    start_time=start_time,
                    end_time=datetime.now(timezone.utc),
                ),
            )

            # Write run_result.json sidecar
            if workspace_dir:
                from rompy.core.result_persistence import write_run_result
                from rompy.core.responses import RunResultSidecar

                normalized_ctx = self._compute_run_normalized_context(workspace_dir)

                sidecar = RunResultSidecar(
                    created_at=datetime.now(timezone.utc),
                    run_id=result.run_id,
                    staging_dir=str(workspace_dir),
                    status="failed",
                    success=False,
                    error=result.error,
                    normalized_context=normalized_ctx,
                    payload=result,
                )
                try:
                    write_run_result(Path(workspace_dir), sidecar)
                except Exception:
                    # Sidecar write failure must NOT mask run result
                    pass

            return result

    def postprocess(
        self,
        processor,
        processor_input=None,
        **kwargs,
    ) -> PostprocessResult:
        """
        Postprocess the model outputs using the specified processor configuration.

        This method uses the provided configuration to instantiate and execute
        the appropriate postprocessor. The processor type is determined by the
        configuration object.

        Args:
            processor: Configuration object for the postprocessor to use
            **kwargs: Additional processor-specific parameters (override config values)

        Returns:
            PostprocessResult: Typed result object with success status, timing,
                and artifacts (for success) or error details (for failure).

                The result is a discriminated union:
                - PostprocessSuccess: Contains artifacts list, output_dir, timing
                - PostprocessFailure: Contains error message, timing

        Raises:
            TypeError: If processor is not a BasePostprocessorConfig instance

        Examples:
            ::

                from rompy.postprocess.config import NoopPostprocessorConfig

                # Run postprocessing
                result = model.postprocess(NoopPostprocessorConfig())

                # Type-safe result handling with discriminated union
                if result.success:
                    # Type narrowing: result is PostprocessSuccess
                    print(f"Generated {len(result.artifacts)} artifacts")
                    for artifact in result.artifacts:
                        print(f"  {artifact.type.value}: {artifact.path}")
                    print(f"Completed in {result.timing.duration_seconds}s")
                else:
                    # Type narrowing: result is PostprocessFailure
                    print(f"Failed: {result.error}")
                    print(f"Message: {result.message}")

                # Serialize to dict for logging or storage
                result_dict = result.model_dump()
        """
        from rompy.postprocess.config import BasePostprocessorConfig

        start_time = datetime.now(timezone.utc)

        try:
            if not isinstance(processor, BasePostprocessorConfig):
                raise TypeError(
                    f"processor must be a BasePostprocessorConfig instance, "
                    f"got {type(processor).__name__}"
                )

            # Get processor class from config
            processor_class = processor.get_postprocessor_class()
            processor_instance = processor_class()

            # Extract processor-specific fields (exclude common base fields)
            base_fields = {"timeout", "env_vars", "working_dir", "type"}
            processor_fields = {
                k: v for k, v in processor.model_dump().items() if k not in base_fields
            }

            # Merge with any user-provided kwargs (kwargs take precedence)
            processor_fields.update(kwargs)

            process_target = processor_input if processor_input is not None else self
            result = processor_instance.process(process_target, **processor_fields)

            # Write postprocess result sidecar
            from rompy.core.result_persistence import write_postprocess_result

            sidecar = PostprocessResultSidecar(
                created_at=datetime.now(timezone.utc),
                run_id=self.run_id,
                staging_dir=str(self.staging_dir),
                status="success" if result.success else "failed",
                success=result.success,
                error=result.error if hasattr(result, "error") else None,
                payload=result,
            )
            try:
                write_postprocess_result(Path(self.staging_dir), sidecar)
            except Exception:
                # Sidecar write failure must NOT mask postprocess result
                pass

            return result

        except Exception as e:
            # Wrap any top-level exceptions in PostprocessFailure
            result = PostprocessFailure(
                run_id=self.run_id,
                message=f"Postprocessing failed: {str(e)}",
                error=str(e),
                timing=TimingInfo(
                    start_time=start_time,
                    end_time=datetime.now(timezone.utc),
                ),
            )

            # Write postprocess result sidecar (failure case)
            from rompy.core.result_persistence import write_postprocess_result

            sidecar = PostprocessResultSidecar(
                created_at=datetime.now(timezone.utc),
                run_id=self.run_id,
                staging_dir=str(self.staging_dir),
                status="failed",
                success=False,
                error=str(e),
                payload=result,
            )
            try:
                write_postprocess_result(Path(self.staging_dir), sidecar)
            except Exception:
                # Sidecar write failure must NOT mask postprocess result
                pass

            return result

    def pipeline(self, pipeline_backend: str = "local", **kwargs) -> PipelineResult:
        """
        Run the complete model pipeline (generate, run, postprocess) using the specified pipeline backend.

        This method executes the entire model workflow from input generation through running
        the model to postprocessing outputs. It uses entry points to load and execute the
        appropriate pipeline backend from the rompy.pipeline entry point group.

        Built-in pipeline backends:
        - "local": Execute the complete pipeline locally using the existing ModelRun methods

        Args:
            pipeline_backend: Name of the pipeline backend to use (default: "local")
            **kwargs: Additional backend-specific parameters. Common parameters include:
                - backend_config: BackendConfig instance for the run stage (for local pipeline)
                - processor: ProcessorConfig instance for postprocessing (for local pipeline)
                - run_kwargs: Additional parameters for the run stage
                - process_kwargs: Additional parameters for postprocessing

        Returns:
            PipelineResult: Typed result object with success status, timing, stage tracking,
                and nested postprocess results.

                The result is a discriminated union:
                - PipelineSuccess: Contains stages_completed, nested postprocess_results, timing
                - PipelineFailure: Contains failed_stage, error, optional postprocess_results

        Raises:
            ValueError: If the specified pipeline backend is not available

        Examples:
            ::

                from rompy.backends import LocalConfig
                from rompy.postprocess.config import NoopPostprocessorConfig

                # Run complete pipeline
                result = model.pipeline(
                    pipeline_backend="local",
                    backend_config=LocalConfig(timeout=3600),
                    processor=NoopPostprocessorConfig()
                )

                # Type-safe result handling with discriminated union
                if result.success:
                    # Type narrowing: result is PipelineSuccess
                    print(f"Stages completed: {[s.value for s in result.stages_completed]}")
                    print(f"Total time: {result.timing.duration_seconds}s")

                    # Access nested postprocess results
                    pp_result = result.postprocess_results
                    if pp_result and pp_result.success:
                        print(f"Artifacts: {len(pp_result.artifacts)}")
                        for artifact in pp_result.artifacts:
                            print(f"  {artifact.type.value}: {artifact.path}")
                else:
                    # Type narrowing: result is PipelineFailure
                    print(f"Failed at stage: {result.failed_stage.value}")
                    print(f"Error: {result.error}")

                    # Check if postprocessing was attempted
                    if result.postprocess_results:
                        print("Postprocess also failed")

                # Serialize to dict for logging
                result_dict = result.model_dump()
        """
        # Get the requested pipeline backend class from entry points
        if pipeline_backend not in PIPELINE_BACKENDS:
            available = list(PIPELINE_BACKENDS.keys())
            raise ValueError(
                f"Unknown pipeline backend: {pipeline_backend}. "
                f"Available backends: {', '.join(available)}"
            )

        # Create an instance and execute the pipeline
        # Backend returns PipelineResult directly
        backend_class = PIPELINE_BACKENDS[pipeline_backend]
        backend_instance = backend_class()
        return backend_instance.execute(self, **kwargs)
