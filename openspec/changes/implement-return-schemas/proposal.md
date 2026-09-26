# Proposal: Canonical typed return schemas

## Why

Rompy's generation, execution, pipeline, and postprocessing boundaries need one
reviewable result contract.  The contract must survive direct Python calls,
pipeline execution, CLI handoff, and a fresh process without silently changing
meaning or dropping evidence.

## Scope of this change

This OpenSpec change freezes the public, versioned contract for:

- typed success/failure results for generation, execution, pipeline, and
  postprocessing;
- coherent sidecar envelopes and strict version/kind handling;
- UTC timing and numeric-seconds interval/duration wire values;
- typed local/remote artifact identity and distinct expected/missing evidence;
- the processor construction and handoff protocol; and
- observable canonical-sidecar persistence failures.

This is design and contract work.  It does not change runtime source, plugins,
tests, dependencies, generated files, or release/package metadata.  The
implementation follow-ups are #4 (schema, persistence, and invariant
implementation), #5 (processor/pipeline/CLI handoffs), and #6 (canonical
fixtures and adversarial validation).

## Authoritative decisions

1. Legacy or ambiguous core-v1 and flat WW3-v1 sidecars are rejected with an
   actionable kind/version error.  No migration reader is introduced now.
2. Duration and interval wire values are numeric seconds.  Human-readable
   formatting is presentation only.
3. Artifact identity is typed: local artifacts are normalized
   staging-relative paths, remote artifacts are an explicit URI variant,
   `artifacts` contains observed outputs, and expected/missing outputs are
   separate structured evidence.
4. Generation moves toward typed results.  Canonical sidecar persistence is
   required; persistence failure is an observable typed failure and retains any
   primary operation error.

## Non-goals

- Implementing #4, #5, or #6.
- A migration reader for legacy sidecars.
- A new shared package or plugin implementation.
- The frozen executable fixture corpus assigned to #6.
- Changing the current runtime source or adding a parallel scalar-return mode
  (the canonical execution API is explicitly typed below).
