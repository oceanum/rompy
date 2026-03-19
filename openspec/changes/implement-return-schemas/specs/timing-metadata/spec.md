## ADDED Requirements

### Requirement: Results include execution timing information
The system SHALL include start time, end time, and computed duration in all result objects.

#### Scenario: Pipeline result includes overall timing
- **WHEN** pipeline execution completes
- **THEN** result includes TimingInfo with start_time, end_time, and duration_seconds

#### Scenario: Nested postprocess timing preserved
- **WHEN** pipeline contains postprocess results
- **THEN** postprocess results include their own TimingInfo separate from pipeline timing

#### Scenario: Partial timing on failure
- **WHEN** pipeline fails at any stage
- **THEN** result includes TimingInfo representing time from start until failure

### Requirement: Timing uses UTC timestamps
The system SHALL use UTC timezone for all start_time and end_time values.

#### Scenario: Timestamp creation uses UTC
- **WHEN** capturing start or end time
- **THEN** system uses datetime.now(timezone.utc) to ensure consistent timezone

#### Scenario: Serialized timestamps include timezone
- **WHEN** result is serialized to JSON
- **THEN** timestamps include 'Z' suffix or explicit UTC timezone offset

### Requirement: Duration computed from timestamps
The system SHALL compute duration_seconds as a property derived from start_time and end_time.

#### Scenario: Duration calculation
- **WHEN** accessing duration_seconds
- **THEN** system computes (end_time - start_time).total_seconds() automatically

#### Scenario: Duration precision
- **WHEN** duration is computed
- **THEN** value is float with subsecond precision

### Requirement: Timing information aids debugging
The system SHALL include timing at multiple levels (operation, stage, nested) to support performance analysis.

#### Scenario: Identifying slow stages
- **WHEN** analyzing failed pipeline
- **THEN** timing shows how long each completed stage took before failure

#### Scenario: Comparing operation durations
- **WHEN** reviewing multiple pipeline runs
- **THEN** timing enables comparison of overall duration and stage-level performance
