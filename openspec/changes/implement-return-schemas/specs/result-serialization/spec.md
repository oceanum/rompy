## ADDED Requirements

### Requirement: Canonical results serialize without semantic loss
Typed result models SHALL support dictionary and JSON serialization while
preserving discriminator, envelope/payload coherence, typed artifact identity,
expected/missing evidence, UTC timestamps, and numeric seconds.

#### Scenario: Result to dictionary
- **WHEN** a concrete success or failure result is dumped
- **THEN** the dictionary contains the discriminator and all nested evidence with no URI/path rewriting.

#### Scenario: Result to JSON
- **WHEN** a result is serialized as JSON
- **THEN** timestamps are RFC 3339 UTC strings, durations/intervals are numeric seconds, and the JSON parses as an object.

#### Scenario: Human-readable formatting
- **WHEN** a CLI or UI displays a duration
- **THEN** it may format numeric seconds for people, but that presentation value is not written as the canonical wire value.

### Requirement: Canonical sidecars round-trip through explicit adapters
Sidecar readers SHALL deserialize only the concrete, versioned canonical envelope
for the requested kind.  Union aliases are typing annotations, not model classes;
callers SHALL use the concrete envelope loader or an explicit Pydantic
`TypeAdapter` for a result union rather than calling `model_validate` on an
`Annotated` union alias.

#### Scenario: Valid canonical round trip
- **WHEN** a canonical envelope is dumped, written, loaded, and validated
- **THEN** the same kind/version, typed result state, timing, artifact identities, and output evidence are reconstructed without deleting computed fields or rewriting paths/URIs.

#### Scenario: Normative example round trip
- **WHEN** the bounded success and failure JSON examples in `design.md` are passed through the future concrete envelope loaders
- **THEN** they validate and round-trip to semantically equivalent canonical JSON; executable validation is follow-up work for #4/#5 and frozen fixture/hash publication belongs to #6.

#### Scenario: Malformed result
- **WHEN** a required field is missing, a discriminator is contradictory, or a nested payload is the wrong family
- **THEN** deserialization fails with an actionable validation error.

#### Scenario: Normative malformed example rejection
- **WHEN** the bounded malformed JSON example in `design.md` is loaded
- **THEN** deserialization rejects it for envelope/payload `run_id` and `success` mismatch; executable validation remains owned by #4/#5 and frozen replay by #6.

#### Scenario: Legacy or ambiguous sidecar
- **WHEN** a core-v1 or flat WW3-v1 sidecar, missing version, boolean version, or unsupported version is loaded
- **THEN** loading fails with an actionable kind/version error directing the caller to regenerate a canonical sidecar; no migration reader runs.

### Requirement: External consumers receive one stable JSON shape
External API, monitoring, and storage integrations SHALL consume the same
canonical serialized shape used by local sidecar persistence.  They SHALL NOT
receive a legacy dictionary shape or a path-filtered artifact list.

#### Scenario: External result consumption
- **WHEN** a result is sent to an API, database, or monitoring system
- **THEN** its discriminator, typed artifact variants, expected/missing evidence, and numeric timing values remain machine-readable.

### Requirement: Persistence diagnostics survive serialization
A typed persistence failure SHALL serialize its sidecar kind/path, failure
message, and any primary operation error.  A successful operation SHALL NOT be
serialized as durably persisted when the required sidecar write failed.

#### Scenario: Failure evidence round trip
- **WHEN** a result contains persistence failure evidence
- **THEN** dictionary and JSON round trips retain both persistence and primary operation diagnostics.
