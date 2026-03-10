# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0-alpha] - 2026-03-10

### 🚨 Breaking Changes

This is a **major version** release with breaking changes to the return types of key methods. See the [Migration Guide](docs/migration-v2.md) for detailed upgrade instructions.

#### Changed Return Types

- **`ModelRun.postprocess()`** now returns `PostprocessResult` (Pydantic model) instead of `Dict[str, Any]`
  - Success case: `PostprocessSuccess` with `success=True`, `artifacts`, `timing`
  - Failure case: `PostprocessFailure` with `success=False`, `error`, `timing`
  
- **`ModelRun.pipeline()`** now returns `PipelineResult` (Pydantic model) instead of `Dict[str, Any]`
  - Success case: `PipelineSuccess` with `success=True`, `stages_completed`, `timing`, `postprocess_results`
  - Failure case: `PipelineFailure` with `success=False`, `error`, `failed_stage`, `timing`

- **Postprocessor plugins** must now return `PostprocessResult` instead of `Dict[str, Any]`
  - All custom postprocessors need to be updated to return typed result objects
  - See migration guide for example implementations

#### Migration Required

**Before (v1.x):**
```python
results = model_run.pipeline()
if results.get("success", False):
    stages = results.get("stages_completed", [])
```

**After (v2.0):**
```python
results = model_run.pipeline()
if results.success:
    stages = results.stages_completed  # List[PipelineStage]
```

**See:** [Migration Guide](docs/migration-v2.md) for complete migration instructions.

### ✨ Added

- **New response schema module** (`rompy.core.responses`)
  - `PostprocessResult` = `PostprocessSuccess | PostprocessFailure`
  - `PipelineResult` = `PipelineSuccess | PipelineFailure`
  - `ModelRunResult` for structured run results
  - `PipelineStage` enum for type-safe stage tracking
  - `ArtifactType` enum for classifying output files
  - `Artifact` class for tracking generated files with metadata
  - `TimingInfo` class with computed duration field

- **New `ModelRun.run_detailed()` method**
  - Returns `ModelRunResult` with structured timing and metadata
  - Complements existing `run()` method (which still returns `bool`)
  - Use for detailed run information with type safety

- **Timing information** included in all result objects
  - `timing.start`, `timing.end`, `timing.duration_seconds`
  - Enables performance tracking and diagnostics

- **Artifact tracking** in postprocess results
  - Output files tracked with `path`, `type`, `size_bytes`
  - Automatic classification by file type (YAML, NetCDF, plot, text, other)
  - Enables downstream processing and file inventory

- **Type safety improvements**
  - Discriminated unions with `success` field as discriminator
  - Type narrowing in IDEs when checking `result.success`
  - Better autocomplete and compile-time validation

- **Comprehensive test coverage**
  - 60+ tests for response schemas
  - Updated tests for all affected components
  - Integration tests for new return types

- **Documentation**
  - [Migration Guide](docs/migration-v2.md) with before/after examples
  - Updated API documentation
  - Plugin development guide updates

### 🔄 Changed

- **CLI commands** updated to use typed result attributes
  - `rompy pipeline` now displays stage completion and timing
  - `rompy postprocess` shows artifact count and timing
  - Better error messages from structured failure results

- **NoopPostprocessor** returns `PostprocessResult`
  - Scans output directory for artifacts
  - Includes timing information

- **LocalPipelineBackend** returns `PipelineResult`
  - Tracks stages completed
  - Includes nested postprocess results
  - Captures timing for each stage

### 🐛 Fixed

- Improved error handling with structured error messages
- Better validation of postprocessor outputs

### 📦 Dependencies

- Requires **Pydantic v2.x** (no longer compatible with Pydantic v1.x)

### 🔗 Links

- **GitHub Issue:** [#15 - Implement strongly-typed response schemas](https://github.com/rom-py/rompy/issues/15)
- **Migration Guide:** [docs/migration-v2.md](docs/migration-v2.md)
- **API Reference:** See `rompy.core.responses` module docstrings

---

## [1.0.0] - (Previous Release)

_(Add previous version history here if available)_

---

## Legend

- 🚨 Breaking Changes
- ✨ Added (new features)
- 🔄 Changed (changes in existing functionality)
- 🗑️ Deprecated (soon-to-be removed features)
- ❌ Removed (now removed features)
- 🐛 Fixed (bug fixes)
- 🔒 Security (vulnerability fixes)
- 📦 Dependencies (dependency updates)
