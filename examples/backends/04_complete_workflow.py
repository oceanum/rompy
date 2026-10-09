"""
Example 4: Complete Workflow with Custom Backend and Postprocessor

This example demonstrates how to:
1. Create a custom run backend
2. Create a custom postprocessor
3. Use them together in a complete workflow
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from rompy.backends import LocalConfig
from rompy.core.responses import (
    Artifact,
    ArtifactType,
    ModelRunSuccess,
    PostprocessFailure,
    PostprocessSuccess,
    TimingInfo,
)
from rompy.core.time import TimeRange
from rompy.model import ModelRun
from rompy.postprocess.config import BasePostprocessorConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 1. Define a custom postprocessor
class FileInfoPostprocessor:
    """Custom postprocessor returning the typed core result contract."""

    def __init__(self, config):
        self.config = config

    def process(self, run_result: ModelRunSuccess):
        """Collect output-file metadata from a successful model run."""
        start_time = datetime.now(timezone.utc)
        output_dir = Path(run_result.output_dir or "")
        if not output_dir.exists():
            return PostprocessFailure(
                run_id=run_result.run_id,
                output_dir=str(output_dir),
                error=f"Output directory not found: {output_dir}",
                artifacts=[],
                expected_outputs=list(run_result.expected_outputs),
                missing_outputs=list(run_result.missing_outputs),
                timing=TimingInfo(start_time=start_time, end_time=datetime.now(timezone.utc)),
            )

        artifacts = []
        for file_path in output_dir.rglob("*"):
            if file_path.is_file():
                artifacts.append(
                    Artifact(
                        path=file_path.relative_to(output_dir).as_posix(),
                        artifact_type=ArtifactType.OTHER,
                        size_bytes=file_path.stat().st_size,
                    )
                )

        return PostprocessSuccess(
            run_id=run_result.run_id,
            output_dir=str(output_dir),
            validated=True,
            artifacts=artifacts,
            expected_outputs=list(run_result.expected_outputs),
            missing_outputs=list(run_result.missing_outputs),
            file_count=len(artifacts),
            metadata={"file_count": len(artifacts)},
            timing=TimingInfo(start_time=start_time, end_time=datetime.now(timezone.utc)),
        )


class FileInfoPostprocessorConfig(BasePostprocessorConfig):
    type: str = "file_info"

    def get_postprocessor_class(self):
        return FileInfoPostprocessor


def main():
    """Run a complete workflow with custom backend and postprocessor."""
    # Create a model run
    model = ModelRun(
        run_id="complete_workflow",
        period=TimeRange(
            start=datetime(2023, 1, 1),
            end=datetime(2023, 1, 2),
            interval="1H",
        ),
        output_dir="./output",
        delete_existing=True,
    )

    # 1. Run with local backend using custom command
    logger.info("Running model with local backend...")
    local_config = LocalConfig(
        timeout=3600,  # 1 hour timeout
        command="echo 'Running custom command' && \
                echo 'This is a test file' > output.txt && \
                ls -la > file_list.txt",
    )
    success = model.run(backend=local_config)

    if not success.success:
        logger.error("Model run failed")
        return

    # 2. Process with custom postprocessor
    logger.info("Running custom postprocessor...")
    results = model.postprocess(
        processor=FileInfoPostprocessorConfig(), processor_input=success
    )

    if results.success:
        logger.info(f"Successfully processed {len(results.artifacts)} files")
        logger.info(f"Metadata: {results.metadata}")
    else:
        logger.error(f"Postprocessing failed: {results.error}")


if __name__ == "__main__":
    main()
