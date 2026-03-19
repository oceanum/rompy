## Why

Rompy currently returns untyped dictionaries from key operations (`pipeline()`, `postprocess()`, `run()`), creating inconsistency with its otherwise Pydantic-based architecture. This leads to stringly-typed code, lack of IDE support, and runtime errors from unexpected dictionary structures. Moving to strongly-typed Pydantic response schemas will improve type safety, developer experience, and API consistency.

## What Changes

- **BREAKING**: Replace `Dict[str, Any]` returns with Pydantic response models for `postprocess()` and `pipeline()` methods
- Add new `ModelRun.run_detailed()` method that returns structured `ModelRunResult` (non-breaking)
- Create discriminated unions for success/failure states (`PipelineResult`, `PostprocessResult`)
- Add rich metadata including timing information, file counts, and backend-specific details
- Update CLI to consume typed result objects instead of dictionary `.get()` calls
- Update all postprocessor plugins to return structured results
- Provide `.model_dump()` for backward compatibility with dict-based consumers

## Capabilities

### New Capabilities
- `result-schemas`: Pydantic models for pipeline, postprocess, and run operation results with discriminated unions for success/failure states
- `timing-metadata`: Execution timing capture with start/end times and computed duration
- `result-serialization`: JSON/dict serialization of result objects for external consumers

### Modified Capabilities
<!-- No existing capabilities are being modified at the requirements level -->

## Impact

**Code Impact**:
- `src/rompy/model.py`: Change return types for `postprocess()` and `pipeline()`, add `run_detailed()`
- `src/rompy/pipeline/__init__.py`: Return `PipelineResult` instead of dict
- `src/rompy/postprocess/__init__.py`: Return `PostprocessResult` instead of dict  
- `src/rompy/cli.py`: Update result handling to use object properties instead of `.get()`
- `tests/**/*.py`: Update assertions from dict access to object properties (~32 test files)

**API Impact**:
- **BREAKING**: External code calling `pipeline()` or `postprocess()` must adapt to Pydantic models
- **BREAKING**: Postprocessor plugins must return `PostprocessResult` instead of dict
- Mitigation: `.model_dump()` provides dict for gradual migration

**Dependencies**:
- Requires Pydantic v2 (already in use via `RompyBaseModel`)
- No new external dependencies

**Version**: This is a major version change (v2.0.0)
