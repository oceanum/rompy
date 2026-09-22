# Issue #6 downstream handoff

## Compatible core baseline

Downstream integration should target core commit
`608dbc4241cc66f8973550a6bb1e568b87bdcb2c` (the merged #5 head on
`return_schema`). The contract is schema version **2** with these operation
kinds: `generate_result`, `run_result`, `postprocess_result`, and the validated
pipeline result kind `pipeline_result` used by the fixture envelope.

The public boundary is `ModelRun.run() -> ModelRunResult`; postprocessors are
constructed from validated configuration and receive the unchanged typed
`ModelRunResult`, returning `PostprocessSuccess | PostprocessFailure`.

## Frozen corpus and hashes

Fixtures live in `tests/fixtures/return_schema_v2/`; the executable checks are
in `tests/core/test_return_schema_fixtures.py`. `manifest.json` is the source
of truth for SHA-256 verification:

| Fixture | Kind/status | SHA-256 |
|---|---|---|
| `generate_success.json` | generate_result/success | `7d7b08398ab506bedae2dd50ae0cbcd0f2686fc6e255b9a1f7f6b0d66605c2f7` |
| `generate_failure.json` | generate_result/failed | `83b85aebe1b41dac3bebf589a9a06bd3c7d7217d5dcb6029a00ca43844c0c466` |
| `run_success.json` | run_result/success | `9e64d49a896a9fa521daa2cb5d0067517b3b65da5eb380d04c5d72e584d1ce9f` |
| `run_failure.json` | run_result/failed | `d1da8ea12df2c3a40ae00c2f41fc1f345a0d4b2292f12dbeb75c2652eb267643` |
| `postprocess_success.json` | postprocess_result/success | `0039a185e9a3284fa8d700f6ef9c9f984700681cf83e5473349226b014a32e01` |
| `postprocess_failure.json` | postprocess_result/failed | `348ca4b7a73544d54d7b914d74da2485d4a6305875d30aae085540af1f863256` |
| `pipeline_success.json` | pipeline_result/success | `a8b509cf680db2e6286bfb9000836ce7577cc9b88ca4ec553cae57af8ad70c55` |
| `pipeline_failure.json` | pipeline_result/failed | `afc33b6282000364aff23107cc8b3083a714e4d16ec93fba1e5f5c178f9e2541` |
| `adversarial/malformed.json` | malformed/reject | `6f5e7359678e8924994c6dbfb317d70fb6443042df93c6d531bef3aa73974ba9` |
| `adversarial/legacy_v1.json` | run_result v1/reject | `3c43fa6af22b2244292f3366a2c31fc4b2997e049bd98493b215187f1500abd6` |
| `adversarial/unsupported_v99.json` | run_result v99/reject | `b3975b59c2922984132d9a7e8febb142abb6ef7b36640e1c8db382cbd18d8265` |
| `adversarial/wrong_kind.json` | wrong_result/reject | `fb2d6f22f86148321d9a72b1abd38cc1866e6e7447714e4c37cfe033433635bc` |

All fixture timestamps, numeric intervals, paths, artifacts, expected/missing
evidence, normalized context, nested stage timing, and persistence diagnostics
are deterministic. Paths are fixture-relative; tests use only temporary paths
for writes and subprocess workspaces.

## Commands and results

```text
pytest -q tests/core/test_return_schema_fixtures.py
pytest -q tests/core/test_canonical_result_schema.py tests/test_issue5_handoffs.py
ruff check tests/core/test_return_schema_fixtures.py
python -m compileall -q tests/core/test_return_schema_fixtures.py
```

Observed results at this baseline: the fixture plus canonical schema suite passed **23 tests**;
the focused #5 suites passed **22 tests**; and the combined historical #4
regression command passed **62 tests**. The full practical repository suite
passed **495 tests**, with **18 explicit skips** and **50 warnings**; it
collected cleanly with no failures or errors. Warnings are the repository's
existing unknown `integration` mark and generic output-validation warnings.
The fixture suite verifies manifest hashes, model/JSON/sidecar round trips,
strict adversarial rejection, and a fresh subprocess with a recording
postprocessor.

## Compatibility and residual limitations

Legacy/unsupported, wrong-kind, malformed, and ambiguous sidecars are rejected
actionably; no migration reader is provided. Core only freezes and validates
this protocol. WW3/Ops downstream plugins still need their own typed adapters,
artifact mapping, and operational persistence checks; no plugin changes are
included in issue #6.
