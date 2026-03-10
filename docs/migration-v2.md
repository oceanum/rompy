# Migration Guide: v1.x → v2.0

This guide helps you migrate from rompy v1.x to v2.0, which introduces **strongly-typed response schemas** as a breaking change.

## Summary of Breaking Changes

### What Changed

In v2.0, the following methods now return **typed Pydantic models** instead of dictionaries:

- `ModelRun.postprocess()` → returns `PostprocessResult` (was `Dict[str, Any]`)
- `ModelRun.pipeline()` → returns `PipelineResult` (was `Dict[str, Any]`)
- **NEW**: `ModelRun.run_detailed()` → returns `ModelRunResult` (new method)
- Postprocessor plugins → must return `PostprocessResult` (was `Dict[str, Any]`)

### Why This Change?

**Benefits:**
- ✅ **Type safety**: IDEs and type checkers can validate your code
- ✅ **Better autocomplete**: See available fields in your IDE
- ✅ **Discriminated unions**: Type narrowing based on `success` field
- ✅ **Structured timing data**: All results include timing information
- ✅ **Artifact tracking**: File outputs are tracked with metadata
- ✅ **Clearer API contracts**: Documented fields with validation

**Trade-offs:**
- ⚠️ **Breaking change**: Code using dict access (`.get()`, `["key"]`) will break
- ⚠️ **Plugin compatibility**: Custom postprocessors must be updated

---

## Migration Examples

### 1. Pipeline Result Handling

**Before (v1.x):**
```python
from rompy.model import ModelRun

model_run = ModelRun(**config)
results = model_run.pipeline()

# Dictionary access
if results.get("success", False):
    stages = results.get("stages_completed", [])
    print(f"Completed stages: {', '.join(stages)}")
else:
    error = results.get("message", "Unknown error")
    print(f"Failed: {error}")
```

**After (v2.0):**
```python
from rompy.model import ModelRun
from rompy.core.responses import PipelineResult

model_run = ModelRun(**config)
results: PipelineResult = model_run.pipeline()

# Object attribute access with type narrowing
if results.success:
    # Type checker knows this is PipelineSuccess
    stages = results.stages_completed  # List[PipelineStage]
    stage_names = [stage.value for stage in stages]
    print(f"Completed stages: {', '.join(stage_names)}")
    print(f"Duration: {results.timing.duration_seconds:.2f}s")
else:
    # Type checker knows this is PipelineFailure
    print(f"Failed: {results.error}")
```

**Key Changes:**
- Replace `.get("success")` → `.success`
- Replace `.get("stages_completed")` → `.stages_completed`
- Replace `.get("message")` → `.error` (on failure)
- Stages are now `PipelineStage` enums → use `.value` for string
- Timing data available via `results.timing`

---

### 2. Postprocess Result Handling

**Before (v1.x):**
```python
results = model_run.postprocess(processor=processor_cfg)

if results.get("success"):
    files = results.get("output_files", [])
    print(f"Generated {len(files)} files")
```

**After (v2.0):**
```python
from rompy.core.responses import PostprocessResult

results: PostprocessResult = model_run.postprocess(processor=processor_cfg)

if results.success:
    # Type checker knows this is PostprocessSuccess
    artifacts = results.artifacts  # List[Artifact]
    print(f"Generated {len(artifacts)} artifacts")
    
    # Access artifact metadata
    for artifact in artifacts:
        print(f"  - {artifact.path.name} ({artifact.type.value}, {artifact.size_bytes} bytes)")
```

**Key Changes:**
- Replace `.get("output_files")` → `.artifacts`
- Artifacts now have structured metadata (type, size, path)
- Use `artifact.type` enum instead of file extension checking

---

### 3. Using the New `run_detailed()` Method

**v2.0 introduces a new method** that returns detailed run information:

```python
from rompy.core.responses import ModelRunResult

# Use run_detailed() instead of run() for typed results
result: ModelRunResult = model_run.run_detailed()

if result.success:
    print(f"✅ Run completed successfully")
    print(f"Duration: {result.timing.duration_seconds:.2f}s")
    print(f"Config: {result.config_summary['id']}")
else:
    print(f"❌ Run failed: {result.error}")

# Old run() method still works for backward compatibility
success: bool = model_run.run()  # Returns bool
```

---

### 4. Custom Postprocessor Plugins

If you've written custom postprocessor plugins, you must update them to return `PostprocessResult`.

**Before (v1.x):**
```python
from rompy.postprocess.base import BasePostprocessor

class MyPostprocessor(BasePostprocessor):
    def process(self, output_dir, validate_outputs):
        try:
            # Do processing...
            return {
                "success": True,
                "output_files": ["file1.nc", "file2.nc"],
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
            }
```

**After (v2.0):**
```python
from datetime import datetime, timezone
from pathlib import Path
from rompy.postprocess.base import BasePostprocessor
from rompy.core.responses import (
    PostprocessResult,
    PostprocessSuccess,
    PostprocessFailure,
    TimingInfo,
    Artifact,
    ArtifactType,
)

class MyPostprocessor(BasePostprocessor):
    def process(self, output_dir, validate_outputs) -> PostprocessResult:
        start_time = datetime.now(timezone.utc)
        
        try:
            # Do processing...
            output_files = [Path("file1.nc"), Path("file2.nc")]
            
            # Create artifact objects
            artifacts = [
                Artifact(
                    path=f,
                    type=ArtifactType.NETCDF,
                    size_bytes=f.stat().st_size if f.exists() else 0,
                )
                for f in output_files
            ]
            
            return PostprocessSuccess(
                success=True,
                artifacts=artifacts,
                timing=TimingInfo(start=start_time, end=datetime.now(timezone.utc)),
            )
        except Exception as e:
            return PostprocessFailure(
                success=False,
                error=str(e),
                timing=TimingInfo(start=start_time, end=datetime.now(timezone.utc)),
            )
```

**Key Changes:**
- Import response types from `rompy.core.responses`
- Return `PostprocessResult` (union type)
- Capture `start_time` at method start
- Create `Artifact` objects for output files
- Return `PostprocessSuccess` or `PostprocessFailure`
- Include `TimingInfo` in both success and failure cases

---

## Backward Compatibility Options

### Option 1: Convert to Dict (Quick Fix)

If you need a quick migration path, you can convert result objects back to dictionaries:

```python
# v2.0 typed result
result = model_run.pipeline()

# Convert to dict for legacy code
result_dict = result.model_dump()

# Now use old dict access patterns
if result_dict.get("success"):
    print("Success!")
```

**Note:** This defeats the purpose of type safety but can be useful during gradual migration.

### Option 2: Use Both Methods

The old `run()` method still exists and returns `bool`:

```python
# Old way (still works)
success = model_run.run()  # Returns bool

# New way (typed result)
result = model_run.run_detailed()  # Returns ModelRunResult
```

---

## Type Narrowing and IDE Support

v2.0 uses **discriminated unions** with the `success` field as discriminator. This enables powerful type narrowing:

```python
from rompy.core.responses import PipelineResult

result: PipelineResult = model_run.pipeline()

# Before checking success, result is Union[PipelineSuccess, PipelineFailure]
# IDE doesn't know which fields are available

if result.success:
    # Now result is narrowed to PipelineSuccess
    # IDE autocomplete shows: stages_completed, timing, postprocess_results, metadata
    print(result.stages_completed)  # ✅ Valid
    # print(result.error)  # ❌ Type checker error: PipelineSuccess has no 'error'
else:
    # Now result is narrowed to PipelineFailure
    # IDE autocomplete shows: error, failed_stage, timing, metadata
    print(result.error)  # ✅ Valid
    # print(result.stages_completed)  # ❌ Type checker error: PipelineFailure has no 'stages_completed'
```

---

## Common Migration Issues

### Issue 1: Enum Values in Logging

**Problem:**
```python
stages = results.stages_completed  # List[PipelineStage]
print(f"Stages: {', '.join(stages)}")  # TypeError: expected str, got PipelineStage
```

**Solution:**
```python
stage_names = [stage.value for stage in results.stages_completed]
print(f"Stages: {', '.join(stage_names)}")
```

### Issue 2: Missing `message` Field

**Problem:**
```python
if not results.success:
    print(results.message)  # AttributeError: PipelineFailure has no 'message'
```

**Solution:**
```python
if not results.success:
    print(results.error)  # Changed from 'message' to 'error'
```

### Issue 3: Dict Access on Object

**Problem:**
```python
if results.get("success"):  # AttributeError: PipelineResult has no 'get'
    ...
```

**Solution:**
```python
if results.success:  # Direct attribute access
    ...
```

---

## Testing Your Migration

After migrating, ensure:

1. **Type checking passes:**
   ```bash
   mypy src/your_module
   ```

2. **Tests pass:**
   ```bash
   pytest tests/
   ```

3. **IDE shows no errors** when accessing result fields

4. **No runtime AttributeError or KeyError** exceptions

---

## Version Requirements

- **rompy v2.0+** requires Pydantic v2.x
- If you're on Pydantic v1, first migrate to Pydantic v2 before upgrading rompy

---

## Need Help?

- **GitHub Issues**: https://github.com/rom-py/rompy/issues
- **Documentation**: https://rompy.readthedocs.io/
- **API Reference**: See `rompy.core.responses` module docstrings

---

## Summary Checklist

- [ ] Replace dict access (`.get()`, `["key"]`) with attribute access (`.field`)
- [ ] Update success checks from `.get("success")` to `.success`
- [ ] Replace `.get("message")` with `.error` for failures
- [ ] Convert `PipelineStage` enums to strings with `.value` for display
- [ ] Update custom postprocessor plugins to return `PostprocessResult`
- [ ] Add type annotations to functions returning results
- [ ] Use `run_detailed()` if you need structured run results
- [ ] Run type checker and tests to verify migration
- [ ] Update any code that relies on dict serialization format

---

**Related Documentation:**
- [API Reference](api.md) - Updated API documentation
- [Plugin Development](plugins.md) - Writing custom postprocessors
- [CHANGELOG](../CHANGELOG.md) - Full v2.0 changelog
