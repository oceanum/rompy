# Return-schema contract migration

This guide describes the approved typed return contract for issue #3. Runtime
implementation is follow-up work in #4 and #5; it is not a claim that every
current release path already enforces these rules.

## Approved execution API

`ModelRun.run()` returns a typed `ModelRunResult` success/failure union:

```python
from rompy.core.responses import ModelRunResult

result: ModelRunResult = model_run.run(
    backend=backend_config,
    workspace_dir=workspace_dir,
)

if result.success:
    print(result.output_dir, result.timing.duration_seconds)
else:
    print(result.error)
```

There is no parallel detailed-run method and no scalar/boolean execution
contract. `ModelRunResult`, `GenerateResult`, `PostprocessResult`, and
`PipelineResult` use explicit success discriminators.

## Pipeline and postprocess results

```python
pipeline_result = model_run.pipeline(
    backend_config=backend_config,
    processor=processor_config,
)

if pipeline_result.success:
    output = pipeline_result.postprocess_results.output_dir
    stages = [stage.value for stage in pipeline_result.stages_completed]
else:
    print(pipeline_result.failed_stage.value, pipeline_result.error)
    # failed_stage is excluded from stages_completed

postprocess_result = model_run.postprocess(processor=processor_config)
if postprocess_result.success:
    for artifact in postprocess_result.artifacts:
        print(artifact)
else:
    print(postprocess_result.error)
```

The pipeline stages are `GENERATE -> RUN -> POSTPROCESS`. Failure results retain
known paths, timing, typed evidence, nested postprocess failure (when relevant),
and truthful cleanup status.

## Processor boundary

Processors are constructed through the validated postprocessor configuration.
Every execution path—direct Python, pipeline, CLI, and fresh process—passes the
same unchanged validated `ModelRunResult` to:

```python
processor = validated_config.build_processor()
result = processor.process(model_result, **validated_process_options)
# PostprocessSuccess | PostprocessFailure
```

Processor output is validated at the boundary. Dictionaries, `None`, and
malformed result unions are not accepted.

## Serialization and union adapters

A result union is a typing alias, not a model class. Use a concrete sidecar
loader or an explicit Pydantic adapter when deserializing raw data:

```python
from pydantic import TypeAdapter
from rompy.core.responses import PipelineResult

result = TypeAdapter(PipelineResult).validate_python(raw_result)
json_text = result.model_dump_json()
```

Canonical sidecars use strict current kind/version envelopes. Legacy or
ambiguous core-v1 and flat WW3-v1 documents are rejected with actionable
kind/version errors; no migration reader is provided now.

## Timing, artifacts, and output evidence

- Timestamps are timezone-aware UTC and `end_time >= start_time`.
- Duration and interval wire values are numeric seconds; human-readable display
  formatting is presentation-only.
- Local artifact identities are normalized staging-relative paths.
- Remote artifacts use an explicit URI identity and are never treated as local
  paths.
- `artifacts` contains observed outputs only. `expected_outputs` and
  `missing_outputs` are separate structured validation evidence.
- Persistence failure is an observable typed failure with sidecar kind/path,
  write error, and any primary operation error retained.

## Follow-up ownership

- **#4:** schema coherence, strict versioning, adapters, UTC/numeric-seconds
  round trips, and canonical sidecar persistence.
- **#5:** processor construction/handoff parity, pipeline semantics, CLI parity,
  and fresh-process behavior.
- **#6:** executable success/failure/malformed/legacy fixture validation, fresh
  process replay, adversarial coverage, and frozen hashes after #4/#5.
