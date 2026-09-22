# Issue #3 contract coverage

This map records contract authority only.  It intentionally does not claim
runtime implementation, plugin adaptation, or frozen fixture completion.

## Approved decisions

| Decision | Contract location | Owner |
|---|---|---|
| Reject legacy/ambiguous core-v1 and flat WW3-v1 sidecars with actionable kind/version errors; no migration reader now | `proposal.md`, `design.md`, `specs/result-serialization/spec.md` | #3 (approved), #4 (implementation) |
| Numeric seconds for duration/interval wire values; human formatting is presentation-only | `design.md`, `specs/timing-metadata/spec.md`, `specs/result-schemas/spec.md` | #3 (approved), #4 (implementation) |
| Typed local/remote artifact identities; observed artifacts separate from expected/missing evidence | `design.md`, `specs/result-schemas/spec.md` | #3 (approved), #4/#5 (implementation) |
| Typed generation direction; canonical persistence required; persistence failure observable while retaining primary error | `proposal.md`, `design.md`, `specs/result-schemas/spec.md`, `specs/result-serialization/spec.md` | #3 (approved), #4 (implementation) |

## Acceptance-criterion coverage

| Issue #3 criterion | Authoritative requirement/scenario | Follow-up ownership |
|---|---|---|
| `ModelRun.run()` and success/failure contracts explicit | `design.md` “Contract vocabulary”; `result-schemas` typed operation results | #4 validates; #5 integrates |
| One processor construction/input/output protocol | `design.md` “Processor protocol” | #5 |
| Same typed processor input for direct, pipeline, CLI, fresh process | `design.md` processor invariants | #5 |
| Artifact identity, remote URI, expected and missing evidence | `design.md` artifact contract; `result-schemas` artifact scenarios | #4/#5 |
| Core-v1/WW3-flat-v1 rejection | `design.md` sidecar envelope; `result-serialization` legacy scenario | #4 |
| Strict current version and envelope/payload coherence | `design.md`; `result-schemas` envelope requirements | #4 |
| UTC timing, end>=start, numeric seconds | `specs/timing-metadata/spec.md`; `result-schemas` timing requirement | #4 |
| Pipeline strict successful prefix and cleanup evidence | `design.md`; `result-schemas` pipeline scenarios | #5 |
| Observable persistence failure and primary-error preservation | `design.md`; serialization/result-schema persistence requirements | #4 |
| Syntactically valid success/failure/malformed JSON plus falsifiable round-trip/rejection requirements | `design.md` bounded contract fixtures; `specs/result-serialization/spec.md` scenarios | #4/#5 implement loaders/validators; #6 executes examples and freezes fixture hashes |

## Ownership boundaries

### Issue #3 (this change)

- Contract prose, falsifiable scenarios, bounded normative JSON examples.
- Explicit typed `run() -> ModelRunResult`; no alternate execution method or
  scalar-return compatibility contract.
- Contract decisions and residual implementation handoff to #4/#5/#6.

### Issue #4 — implementation follow-up (not complete here)

- Runtime discriminators and envelope/payload validators.
- UTC/order/duration validation and lossless round trips.
- Strict version/kind rejection and canonical sidecar persistence.
- Persistence failure injection and observable typed diagnostics.

### Issue #5 — integration follow-up (not complete here)

- Processor construction and validated `ModelRunResult` handoff across direct,
  pipeline, CLI, and fresh-process paths.
- Validated processor union output.
- Pipeline strict prefixes, nested evidence, actual paths, and cleanup truth.

### Issue #6 — fixture/validation follow-up (not complete here)

- Frozen executable success/failure/malformed/legacy fixtures and hashes after
  #4/#5 implement the contract.
- Fresh-process replay and adversarial contract validation after #4/#5.
- No fixture corpus is added by issue #3.

## Deliberate non-coverage

- No runtime source, implementation tests, dependencies, plugin, generated file,
  package metadata, or unrelated documentation changed.
- No migration reader is designed or implemented.
- No release/version bump is specified.
- Design claims do not imply that existing runtime behavior already satisfies
  every requirement; they define what #4/#5 must make true.
