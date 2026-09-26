# Postprocessor protocol

ROMPy exposes a typed contract for postprocessing without requiring a
composition runtime. Import `PostprocessContext`, `PostprocessStep`, and
`PostprocessProcessor` from `rompy.postprocess`.

```python
from rompy.postprocess import PostprocessContext, PostprocessStep
from rompy.core.responses import PostprocessResult

class CheckStep:
    name = "check"

    def process(self, context: PostprocessContext) -> PostprocessResult:
        # Return a concrete PostprocessSuccess or PostprocessFailure.
        ...
```

A context contains one concrete `ModelRunSuccess` or `ModelRunFailure`,
observed artifact evidence, separate expected/missing evidence, a failure
policy, and namespaced operational state. `context.handoff(result)` is the
future ordered-step handoff: it validates the concrete result and carries its
observed artifacts to the next context. Ordered composition and execution are
not implemented by this contract issue.

## Ownership rules

- The core runner owns ordered execution, failure policy, final result
  construction, validation, and the sole canonical
  `postprocess_result.json` sidecar.
- Steps own transformations and integrations only. They must not write a
  competing result sidecar. Artifacts returned by a step are evidence for the
  core handoff, not persistence instructions.
- Operational state is non-canonical, namespaced by processor, recursively
  JSON-safe, and immutable. The core snapshots caller input; processors read a
  namespace and call `context.with_state(name, values)` to receive a new
  context with that namespace replaced. It is for bounded runtime state, not
  result or artifact authority.
- `FAIL_FAST` and `CONTINUE` describe the policy a future ordered runner will
  apply to a failed step; this issue does not implement that runner.

## Configuration discovery

Validated processor configurations are discovered only from the
`rompy.postprocess.config` entry-point group. The sibling
`rompy.postprocess` group is for runtime implementations and is not a config
registry. Discovery is sorted and rejects duplicate names with a deterministic
ambiguity error rather than choosing metadata enumeration order. Existing
`NoopPostprocessorConfig` and single-processor `ModelRun.postprocess(...)`
calls remain supported.
