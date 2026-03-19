## ADDED Requirements

### Requirement: Results can be serialized to dictionaries
The system SHALL support converting result objects to dictionaries via model_dump() for backward compatibility.

#### Scenario: Pipeline result to dict
- **WHEN** calling result.model_dump() on PipelineResult
- **THEN** returns dictionary with all fields including nested postprocess_results

#### Scenario: Dict structure matches legacy format
- **WHEN** dict serialization produces output
- **THEN** key names and structure match historical dictionary returns for gradual migration

#### Scenario: Type information preserved in dict
- **WHEN** serializing discriminated union to dict
- **THEN** 'success' field correctly reflects True/False for Success/Failure variants

### Requirement: Results can be serialized to JSON
The system SHALL support converting result objects to JSON strings via model_dump_json().

#### Scenario: JSON serialization of successful pipeline
- **WHEN** calling result.model_dump_json() on PipelineSuccess
- **THEN** returns valid JSON string with all fields properly formatted

#### Scenario: Datetime fields serialized to ISO8601
- **WHEN** JSON serialization includes TimingInfo
- **THEN** start_time and end_time are formatted as ISO8601 strings with timezone

#### Scenario: Optional fields omitted when None
- **WHEN** JSON serialization includes optional fields with None values
- **THEN** those fields can be excluded with exclude_none=True parameter

### Requirement: Results support pretty-printed JSON
The system SHALL support human-readable JSON output for debugging and logging.

#### Scenario: Pretty-printed JSON output
- **WHEN** calling model_dump_json(indent=2)
- **THEN** returns formatted JSON with 2-space indentation and newlines

#### Scenario: Readable error inspection
- **WHEN** logging failed pipeline result
- **THEN** pretty-printed JSON shows error message and context clearly

### Requirement: External systems can consume serialized results
The system SHALL produce serializable output that external tools can parse and process.

#### Scenario: REST API returns result JSON
- **WHEN** rompy is called via REST API
- **THEN** JSON serialized result can be returned as HTTP response body

#### Scenario: Result stored in database
- **WHEN** result needs persistence
- **THEN** JSON serialization enables storage in JSON columns or document stores

#### Scenario: Result passed to monitoring system
- **WHEN** result sent to monitoring/alerting
- **THEN** dict serialization provides structured data for metrics extraction

### Requirement: Deserialization reconstructs typed objects
The system SHALL support deserializing dictionaries back into typed result objects.

#### Scenario: Reconstruct result from dict
- **WHEN** calling PipelineResult.model_validate(dict_data)
- **THEN** returns properly typed PipelineSuccess or PipelineFailure based on discriminator

#### Scenario: Validation on deserialization
- **WHEN** dict data is invalid or missing required fields
- **THEN** Pydantic raises ValidationError with clear message

#### Scenario: Discriminator routing on load
- **WHEN** deserializing dict with success=True
- **THEN** Pydantic constructs PipelineSuccess and validates success-specific fields
