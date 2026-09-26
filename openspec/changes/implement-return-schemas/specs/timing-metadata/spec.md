## ADDED Requirements

### Requirement: Results include complete execution timing
Completed operations and pipeline failures SHALL include operation timing with
`start_time`, `end_time`, and computed `duration_seconds`. Pipeline results SHALL
also retain nested postprocess timing and stage timing evidence where a stage
started or completed.

#### Scenario: Successful operation timing
- **WHEN** generation, execution, postprocessing, or a pipeline succeeds
- **THEN** its timing starts no later than the operation and ends no earlier than completion, with nonnegative computed seconds.

#### Scenario: Failure timing
- **WHEN** any stage fails
- **THEN** timing ends at or after failure observation and remains available on the typed failure result.

### Requirement: Timestamps are UTC and ordered
All canonical timestamps SHALL be timezone-aware UTC values.  `end_time` SHALL be
greater than or equal to `start_time`; naïve, non-UTC, and reversed intervals
SHALL fail validation.

#### Scenario: UTC serialization
- **WHEN** a timestamp is serialized
- **THEN** it includes `Z` or an explicit `+00:00` offset.

#### Scenario: Invalid timestamp
- **WHEN** a timestamp lacks timezone information, uses a non-UTC offset, or precedes its start
- **THEN** validation fails with the field and invariant identified.

### Requirement: Duration and intervals use numeric seconds
`duration_seconds`, `period_interval`, and stage-duration wire fields SHALL be
numeric seconds (including fractional seconds).  They SHALL be derived or
validated against timestamps where applicable. Human-readable strings such as
`"1:00:00"` or `"3600s"` SHALL NOT be canonical wire values.

#### Scenario: Precision-preserving duration
- **WHEN** timestamps differ by 2.25 seconds
- **THEN** computed and serialized `duration_seconds` is numeric `2.25`.

#### Scenario: Numeric modelling interval
- **WHEN** a normalized execution context has a one-hour sampling interval
- **THEN** its wire value is numeric `3600`, not a duration string.

### Requirement: Timing round trips without surgery
Model, JSON, and sidecar writer/loader round trips SHALL preserve timestamps and
numeric duration semantics without callers deleting computed fields or changing
wire types.

#### Scenario: Writer/loader round trip
- **WHEN** a timed canonical result is written and loaded in a fresh process
- **THEN** timing remains UTC-aware, ordered, and numerically equal within the model's precision.
