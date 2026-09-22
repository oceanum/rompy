# Contract and implementation task boundary

Issue #3 freezes the contract; it does not implement runtime behavior.  Items
below are intentionally uncompleted unless a follow-up issue owns them.

## Issue #3 — contract definition (this change)

- [x] Record owner decisions for legacy rejection, numeric-seconds wire values,
  typed artifact identity/evidence, typed generation, and observable persistence
  failure.
- [x] Define strict current sidecar version/kind handling and actionable legacy
  rejection.
- [x] Define envelope/payload coherence and falsifiable success/failure
  invariants.
- [x] Define UTC timing, `end_time >= start_time`, computed duration, and
  numeric duration/interval wire values.
- [x] Define local/remote artifact identity, traversal/URI rules, observed
  artifacts, and separate expected/missing evidence.
- [x] Approve `run() -> ModelRunResult`; remove obsolete alternate and
  scalar-return contract claims.
- [x] Define processor construction, unchanged `ModelRunResult` input, validated
  `PostprocessSuccess | PostprocessFailure` output, and parity boundaries.
- [x] Define strict pipeline successful-prefix, nested evidence, actual-path,
  and cleanup semantics.
- [x] Add syntactically valid bounded normative success, failure, and malformed
  JSON examples plus falsifiable round-trip/rejection requirements; executable
  validation and frozen hashes remain with #6 after #4/#5 implementation.
- [x] Restore concise required-field and persistence-diagnostic definitions for
  every approved result variant.
- [x] Reconcile design/spec/coverage material and identify #4/#5/#6 ownership.
- [x] Record exact JSON syntax-validation and OpenSpec validation commands.

## #4 — schema, serialization, and persistence implementation (follow-up)

- [x] Implement discriminated result variants and envelope/payload validators.
- [x] Enforce strict current version/kind checks and actionable legacy rejection.
- [x] Implement UTC/order validation, numeric-seconds serialization, and lossless
  model/JSON/sidecar round trips.
- [x] Implement canonical atomic sidecar persistence and the core typed
  persistence adapter, retaining primary operation errors. Producer call-site
  adoption remains owned by #5.
- [x] Add focused mutation and failure-injection tests for the approved contract.

## #5 — processor, pipeline, and CLI handoffs (follow-up)

- [ ] Construct processors through one validated configuration path.
- [ ] Pass the same validated `ModelRunResult` to processors from direct Python,
  pipeline, CLI, and fresh-process paths.
- [ ] Validate processor returns as `PostprocessSuccess | PostprocessFailure`.
- [ ] Enforce strict successful stage prefixes, nested failure evidence, actual
  generated paths, and truthful cleanup outcomes.
- [ ] Add equivalent-path and stage/cleanup tests.

## #6 — canonical fixtures and adversarial validation (follow-up)

- [ ] Create frozen executable success/failure/malformed/legacy fixtures and
  publish hashes.
- [ ] Validate fresh-process replay and all documented JSON examples after #4/#5
  implement the contract.
- [ ] Add adversarial artifact, URI, traversal, version, and contradiction cases.
- [ ] Publish frozen hashes for the executable fixture corpus.

## Explicit non-goals for this change

- Do not edit runtime source, implementation tests, plugins, dependencies,
  generated files, or unrelated docs.
- Do not add a migration reader or a new shared package.
- Do not add the frozen fixture corpus assigned to #6.
- Do not mark #5 or #6 implementation complete; #4 core schema, adapter, and persistence tasks above are complete, while producer call-site adoption remains #5.
