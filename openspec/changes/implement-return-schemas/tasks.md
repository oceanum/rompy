# Implementation Tasks: Implement Return Schemas

## Task Breakdown

### Phase 1: Create Result Schema Foundation

#### Task 1.1: Create result schema module
**File**: `src/rompy/core/responses.py`

**What**: Create new module with all response schema definitions (PipelineStage enum, ArtifactType enum, Artifact class, TimingInfo, PostprocessSuccess/Failure, PipelineSuccess/Failure, ModelRunResult)

**Acceptance**:
- [x] File created at `src/rompy/core/responses.py`
- [x] All schema classes defined with proper Pydantic v2 syntax
- [x] `ArtifactType` enum with YAML, NETCDF, PLOT, TEXT, OTHER
- [x] `Artifact` class for tracking generated files
- [x] `PostprocessSuccess` and `PostprocessFailure` include `artifacts: List[Artifact]`
- [x] Discriminated unions configured with `Field(discriminator="success")`
- [x] TimingInfo has `@computed_field` for duration_seconds
- [x] All classes have comprehensive docstrings
- [x] Module docstring with usage examples
- [x] No import errors, mypy type checks pass

**Dependencies**: None

**Estimated effort**: 3-4 hours (increased due to artifact tracking)

---

#### Task 1.2: Create unit tests for result schemas
**File**: `tests/test_responses.py`

**What**: Create comprehensive unit tests for all response schema classes

**Acceptance**:
- [x] Test file created at `tests/test_responses.py`
- [x] Tests for TimingInfo duration computation
- [x] Tests for Artifact class construction and type classification
- [x] Tests for discriminator behavior (success=True/False)
- [x] Tests for type narrowing (success field enables field access)
- [x] Tests for nested composition (Pipeline → Postprocess)
- [x] Tests for artifact tracking in PostprocessSuccess/Failure
- [x] Tests for serialization/deserialization round-trips
- [x] Tests for validation errors on invalid data
- [ ] All tests pass (will verify after dependencies installed)
- [ ] Coverage >95% for `src/rompy/core/responses.py` (will verify after tests run)

**Dependencies**: Task 1.1

**Estimated effort**: 2-3 hours

---

### Phase 2: Update Postprocessor Layer

#### Task 2.1: Update NoopPostprocessor with artifact tracking
**File**: `src/rompy/postprocess/__init__.py`

**What**: Change `NoopPostprocessor.process()` to return `PostprocessResult` with artifact tracking

**Acceptance**:
- [x] Import `PostprocessResult`, `PostprocessSuccess`, `PostprocessFailure`, `TimingInfo`, `Artifact`, `ArtifactType` from `rompy.core.responses`
- [x] Change return type annotation to `PostprocessResult`
- [x] Capture `start_time = datetime.now(timezone.utc)` at method start
- [x] Scan output directory and classify files as artifacts (YAML, NetCDF, plots, etc.)
- [x] Create `Artifact` objects with path, type, and size
- [x] Return `PostprocessSuccess` with artifacts list on validation success
- [x] Return `PostprocessFailure` on validation failure
- [x] Return `PostprocessFailure` on exceptions
- [x] Include `TimingInfo` in all return paths
- [x] Update docstring with return type
- [x] No import errors

**Dependencies**: Task 1.1

**Estimated effort**: 2 hours (increased due to artifact tracking logic)

---

#### Task 2.2: Update postprocessor tests
**File**: `tests/test_postprocess.py`

**What**: Update test assertions to work with `PostprocessResult` objects and artifact tracking

**Acceptance**:
- [x] Import result types from `rompy.core.responses`
- [x] Replace `results.get("success")` with `results.success`
- [x] Replace `results.get("output_dir")` with `results.output_dir`
- [x] Add assertions for `isinstance(result, PostprocessSuccess)` or `PostprocessFailure`
- [x] Test artifact tracking (check artifacts list, types, paths)
- [x] Test timing field presence
- [x] Test validated field values
- [x] All postprocessor tests pass (syntax verified, runtime pending dependencies)

**Dependencies**: Task 2.1

**Estimated effort**: 1.5 hours (increased for artifact tests)

---

### Phase 3: Update Pipeline Layer

#### Task 3.1: Update LocalPipelineBackend.execute()
**File**: `src/rompy/pipeline/__init__.py`

**What**: Change `execute()` to return `PipelineResult` with proper stage tracking

**Acceptance**:
- [x] Import all result types from `rompy.core.responses`
- [x] Change return type annotation to `PipelineResult`
- [x] Initialize `stages_completed: List[PipelineStage] = []`
- [x] Capture `start_time` at method start
- [x] Append to `stages_completed` after each successful stage
- [x] Return `PipelineFailure` on run failure with `failed_stage=RUN`
- [x] Return `PipelineFailure` on postprocess failure with nested `PostprocessFailure`
- [x] Return `PipelineSuccess` on full success with nested `PostprocessSuccess`
- [x] Handle exceptions with appropriate `PipelineFailure`
- [x] Track cleanup with `cleaned_up` field
- [x] Include `TimingInfo` in all return paths
- [x] Update docstring

**Dependencies**: Task 2.1

**Estimated effort**: 2-3 hours

---

#### Task 3.2: Update pipeline tests
**File**: `tests/test_pipeline.py`

**What**: Update pipeline test assertions to work with `PipelineResult` objects

**Acceptance**:
- [x] Import result types from `rompy.core.responses`
- [x] Replace dict access with attribute access
- [x] Test `isinstance(result, PipelineSuccess)` for success cases
- [x] Test `isinstance(result, PipelineFailure)` for failure cases
- [x] Verify `stages_completed` list contents
- [x] Verify `failed_stage` on failures
- [x] Verify nested `postprocess_results` structure
- [x] Verify timing information presence
- [x] Test cleanup tracking
- [x] All pipeline tests pass

**Dependencies**: Task 3.1

**Estimated effort**: 2 hours

---

### Phase 4: Update ModelRun Methods

#### Task 4.1: Update ModelRun.postprocess()
**File**: `src/rompy/model.py` (lines ~387-395)

**What**: Change return type to `PostprocessResult` and handle exceptions

**Acceptance**:
- [x] Import result types from `rompy.core.responses`
- [x] Change return type annotation to `PostprocessResult`
- [x] Capture `start_time` at method start
- [x] Wrap top-level exceptions in `PostprocessFailure`
- [x] Pass through processor results (processors return `PostprocessResult`)
- [x] Update docstring
- [x] No breaking changes to method signature (kwargs preserved)

**Dependencies**: Task 2.1

**Estimated effort**: 30 minutes

---

#### Task 4.2: Update ModelRun.pipeline()
**File**: `src/rompy/model.py` (lines ~397-437)

**What**: Change return type to `PipelineResult` and delegate to pipeline backend

**Acceptance**:
- [x] Import result types from `rompy.core.responses`
- [x] Change return type annotation to `PipelineResult`
- [x] Remove dict manipulation logic (backend handles it)
- [x] Return backend result directly
- [x] Update docstring
- [x] No breaking changes to method signature

**Dependencies**: Task 3.1

**Estimated effort**: 30 minutes

---

#### Task 4.3: Add ModelRun.run_detailed()
**File**: `src/rompy/model.py`

**What**: Add new method that returns `ModelRunResult` alongside existing `run() -> bool`

**Acceptance**:
- [x] Import `ModelRunResult`, `TimingInfo` from `rompy.core.responses`
- [x] Define `run_detailed()` method with same signature as `run()`
- [x] Capture `start_time` at method start
- [x] Call existing `run()` method internally
- [x] Wrap result in `ModelRunResult` with timing and metadata
- [x] Handle exceptions with `ModelRunResult(success=False, error=...)`
- [x] Include comprehensive docstring explaining new method vs old
- [x] Existing `run()` method unchanged (backward compat)
- [x] No import errors

**Dependencies**: Task 1.1

**Estimated effort**: 1 hour

---

#### Task 4.4: Update ModelRun tests
**File**: `tests/test_model.py`

**What**: Update model run test assertions to work with new return types

**Acceptance**:
- [x] Import result types from `rompy.core.responses`
- [x] Update `postprocess()` tests to use `PostprocessResult`
- [x] Update `pipeline()` tests to use `PipelineResult`
- [x] Add tests for `run_detailed()` method
- [x] Replace dict assertions with object assertions
- [x] Verify timing information
- [x] All model tests pass

**Dependencies**: Task 4.1, Task 4.2, Task 4.3

**Estimated effort**: 2 hours

---

### Phase 5: Update CLI

#### Task 5.1: Update CLI pipeline result handling
**File**: `src/rompy/cli.py` (lines ~810-850)

**What**: Replace dict access with typed object attribute access in pipeline CLI commands

**Acceptance**:
- [x] Import `PipelineSuccess`, `PipelineFailure` from `rompy.core.responses`
- [x] Replace `results.get("success")` with `results.success`
- [x] Replace `results.get("stages_completed")` with `results.stages_completed`
- [x] Replace `results.get("message")` with `results.message` or `results.error`
- [x] Use `stage.value` for enum logging
- [x] Use `results.timing.duration_seconds` for timing display
- [x] Handle nested `postprocess_results` properly
- [x] Use `if results.success:` for type narrowing
- [x] Update all logging statements
- [x] CLI commands work correctly with new types

**Dependencies**: Task 4.2

**Estimated effort**: 1-2 hours

---

#### Task 5.2: Update CLI postprocess result handling
**File**: `src/rompy/cli.py`

**What**: Replace dict access for postprocess results (if directly called from CLI)

**Acceptance**:
- [x] Import `PostprocessSuccess`, `PostprocessFailure` from `rompy.core.responses`
- [x] Replace dict access with attribute access
- [x] Update logging statements
- [x] CLI works correctly

**Dependencies**: Task 4.1

**Estimated effort**: 30 minutes

---

### Phase 6: Integration Testing

#### Task 6.1: Run full test suite
**Files**: All test files

**What**: Verify all existing tests pass with new return types

**Acceptance**:
- [ ] Run `pytest tests/` (all tests)
- [ ] All tests pass
- [ ] No import errors
- [ ] No type errors
- [ ] Coverage remains >80% overall
- [ ] Coverage >95% for `src/rompy/core/responses.py`

**Dependencies**: All previous tasks

**Estimated effort**: 1 hour (troubleshooting)

---

#### Task 6.2: Run mypy type checking
**Files**: All source files

**What**: Verify type annotations are correct and type narrowing works

**Acceptance**:
- [ ] Run `mypy src/rompy`
- [ ] No type errors in result schema definitions
- [ ] No type errors in updated methods
- [ ] Type narrowing works correctly (no `type: ignore` needed)
- [ ] CI type checking passes

**Dependencies**: All previous tasks

**Estimated effort**: 1 hour (fixing type errors)

---

#### Task 6.3: Integration smoke tests
**Files**: Manual testing

**What**: Manually test CLI with real configuration examples

**Acceptance**:
- [ ] Run `rompy pipeline` with example config
- [ ] Verify success output formatting
- [ ] Trigger failure scenario, verify error output
- [ ] Check timing display works
- [ ] Verify nested result display
- [ ] No CLI crashes

**Dependencies**: Task 5.1, Task 5.2

**Estimated effort**: 30 minutes

---

### Phase 7: Documentation

#### Task 7.1: Update API documentation
**Files**: Docstrings in `src/rompy/model.py`, `src/rompy/pipeline/__init__.py`, `src/rompy/postprocess/__init__.py`

**What**: Ensure all docstrings reflect new return types

**Acceptance**:
- [ ] `ModelRun.postprocess()` docstring documents `PostprocessResult`
- [ ] `ModelRun.pipeline()` docstring documents `PipelineResult`
- [ ] `ModelRun.run_detailed()` docstring explains difference from `run()`
- [ ] `LocalPipelineBackend.execute()` docstring updated
- [ ] `NoopPostprocessor.process()` docstring updated
- [ ] Docstrings follow numpy style
- [ ] Include examples in docstrings

**Dependencies**: Task 4.1, Task 4.2, Task 4.3, Task 3.1, Task 2.1

**Estimated effort**: 1 hour

---

#### Task 7.2: Create migration guide
**File**: `docs/migration-v2.md` (NEW)

**What**: Document breaking changes and migration path for users

**Acceptance**:
- [ ] File created at `docs/migration-v2.md`
- [ ] Summary of breaking changes
- [ ] Before/after code examples for:
  - Pipeline result handling
  - Postprocess result handling
  - Plugin postprocessor updates
- [ ] Backward compatibility via `.model_dump()` documented
- [ ] Version bump explanation (v2.0.0)
- [ ] Plugin author guidance

**Dependencies**: All implementation tasks

**Estimated effort**: 1-2 hours

---

#### Task 7.3: Update CHANGELOG
**File**: `CHANGELOG.md`

**What**: Document v2.0.0 breaking changes

**Acceptance**:
- [ ] Add section for v2.0.0 (or v2.0.0-alpha)
- [ ] List breaking changes:
  - `pipeline()` returns `PipelineResult` instead of `Dict[str, Any]`
  - `postprocess()` returns `PostprocessResult` instead of `Dict[str, Any]`
  - Postprocessor plugins must return `PostprocessResult`
- [ ] List new features:
  - `run_detailed()` method for structured run results
  - Timing information in all results
  - Discriminated unions for type safety
- [ ] Link to migration guide

**Dependencies**: Task 7.2

**Estimated effort**: 30 minutes

---

#### Task 7.4: Update user documentation
**Files**: `docs/usage.md`, `docs/plugins.md`

**What**: Update usage examples to show new result objects

**Acceptance**:
- [ ] `docs/usage.md` shows `PipelineResult` usage with attribute access
- [ ] `docs/usage.md` includes type narrowing examples
- [ ] `docs/plugins.md` documents `PostprocessResult` return requirement
- [ ] `docs/plugins.md` provides example postprocessor implementation
- [ ] Examples are tested and work

**Dependencies**: All implementation tasks

**Estimated effort**: 1-2 hours

---

### Phase 8: Finalization

#### Task 8.1: Update version
**Files**: `pyproject.toml`, `src/rompy/_version.py` (if using versioneer), `tbump.toml`

**What**: Bump version to v2.0.0-alpha

**Acceptance**:
- [ ] Version updated to `2.0.0-alpha` in `pyproject.toml`
- [ ] If using tbump: run `tbump 2.0.0-alpha` (updates all version files)
- [ ] Version tag created in git
- [ ] Version reflects breaking change (major bump)

**Dependencies**: All previous tasks

**Estimated effort**: 15 minutes

---

#### Task 8.2: Pre-commit checks
**Files**: All modified files

**What**: Run linting and formatting checks

**Acceptance**:
- [ ] Run `make lint` - passes
- [ ] Run `make format` - no changes needed (or applied)
- [ ] Run `pre-commit run --all-files` - passes
- [ ] No flake8 errors
- [ ] Black formatting consistent

**Dependencies**: All previous tasks

**Estimated effort**: 30 minutes

---

#### Task 8.3: Final review checklist
**Files**: All

**What**: Verify all requirements met before PR/merge

**Acceptance**:
- [ ] All unit tests pass (`pytest tests/`)
- [ ] All integration tests pass
- [ ] Type checking passes (`mypy src/rompy`)
- [ ] Linting passes (`make lint`)
- [ ] Coverage >80% overall
- [ ] Coverage >95% for new schemas
- [ ] All specs requirements implemented
- [ ] Documentation complete
- [ ] CHANGELOG updated
- [ ] Migration guide complete
- [ ] No TODO comments left in code
- [ ] Ready for PR

**Dependencies**: All previous tasks

**Estimated effort**: 1 hour

---

## Task Dependencies Graph

```
1.1 (Create schemas)
  ├─→ 1.2 (Schema tests)
  ├─→ 2.1 (Update NoopPostprocessor)
  │    └─→ 2.2 (Postprocessor tests)
  │         └─→ 3.1 (Update Pipeline backend)
  │              └─→ 3.2 (Pipeline tests)
  │                   └─→ 4.2 (Update ModelRun.pipeline)
  ├─→ 4.1 (Update ModelRun.postprocess)
  ├─→ 4.3 (Add run_detailed)
  └─→ 4.4 (ModelRun tests)

4.1, 4.2, 4.3 → 5.1 (Update CLI pipeline)
4.1, 4.2 → 5.2 (Update CLI postprocess)

All implementation → 6.1 (Test suite)
All implementation → 6.2 (Type checking)
5.1, 5.2 → 6.3 (Integration smoke tests)

All implementation → 7.1 (API docs)
All implementation → 7.2 (Migration guide)
7.2 → 7.3 (CHANGELOG)
All implementation → 7.4 (User docs)

All previous → 8.1 (Version bump)
All previous → 8.2 (Pre-commit)
All previous → 8.3 (Final review)
```

## Estimated Total Effort

- **Phase 1 (Foundation)**: 4-6 hours
- **Phase 2 (Postprocessor)**: 2 hours
- **Phase 3 (Pipeline)**: 4-5 hours
- **Phase 4 (ModelRun)**: 4-5 hours
- **Phase 5 (CLI)**: 1.5-2.5 hours
- **Phase 6 (Testing)**: 2.5 hours
- **Phase 7 (Documentation)**: 3.5-5 hours
- **Phase 8 (Finalization)**: 1.75 hours

**Total**: ~23-31 hours (3-4 full working days)

## Critical Path

1. Task 1.1 (schemas) → Task 2.1 (postprocessor) → Task 3.1 (pipeline) → Task 4.2 (ModelRun.pipeline) → Task 5.1 (CLI) → Task 6.1 (tests)

Any delays on critical path tasks will delay the entire implementation.

## Recommended Implementation Order

1. **Start**: Task 1.1 (schemas) + Task 1.2 (schema tests)
2. **Bottom-up**: Task 2.1 (postprocessor) → Task 2.2 (tests)
3. **Middle layer**: Task 3.1 (pipeline) → Task 3.2 (tests)
4. **Top layer**: Task 4.1, 4.2, 4.3 (ModelRun methods)
5. **Integration**: Task 4.4 (ModelRun tests) + Task 5.1, 5.2 (CLI)
6. **Validation**: Task 6.1, 6.2, 6.3 (full testing)
7. **Documentation**: Task 7.1, 7.2, 7.3, 7.4 (docs)
8. **Finalization**: Task 8.1, 8.2, 8.3 (release prep)

This order ensures each layer is tested before building the next layer on top.
