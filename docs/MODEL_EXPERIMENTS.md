# Model Experiment Protocol

## Official ITSM state source

Official model runs use the pinned EnterpriseOps-Gym asset:

```text
revision: de22905d21a080b83bf4a54258afe4250ee2dd55
archive SHA-256: d947543d4fba1aabc4aade73d3df955114187b7a94da7ac825c4c31169ddab47
seed: Domain Wise DBs and Task-DB Mappings/itsm/dbs/db_1765301900121_3mwjj54xy.sql
seed SHA-256: 99f193904ef9c1f06c3ecff48000697653f178d6300c70e86d34d5a17081e3a4
```

The loader infers the 24-table schema from the seed's INSERT headers and then
executes all 241 upstream rows. Task-specific records are created afterward by
the same six benchmark write tools recorded in the public prefix. Four matched
fault variants are then constructed from that shared state.

The archive is downloaded and verified automatically for official model runs.
It can also be fetched explicitly:

```powershell
$env:PYTHONPATH = "src"
python -m aftermath_bench fetch-enterpriseops
```

Set `AFTERMATH_CACHE_DIR` to control the reusable asset location.

## Model-visible input

The model receives only:

1. a normal ITSM recovery system instruction;
2. the user's still-valid request;
3. six successful prior tool activities;
4. the latest `escalate_major_incident` arguments and its `504 Gateway
   Timeout` result;
5. 16 ordinary investigation and mutation tools.

It does not receive the hidden commit-state label, SQL checks, expected repair
scope, reference trajectory, database fingerprint, or evaluator output.

The runner stops when the model returns no tool calls or after 15 model turns.
There is no `finish()` tool.

## Provider setup

API keys are read only from an environment variable and are never stored in the
trajectory.

OpenAI-compatible endpoints cover OpenAI-style APIs exposed by GPT, Qwen,
DeepSeek, and compatible gateways:

```powershell
$env:AFTERMATH_API_KEY = "<key>"
python -m aftermath_bench run-itsm-model `
  --provider openai-compatible `
  --base-url "https://provider.example/v1" `
  --model "<model-id>" `
  --variant partial_commit `
  --output "runs/partial_commit.json"
```

Anthropic:

```powershell
$env:AFTERMATH_API_KEY = "<key>"
python -m aftermath_bench run-itsm-model `
  --provider anthropic `
  --model "<claude-model-id>" `
  --variant async_pending `
  --output "runs/async_pending.json"
```

`--minimal-fixture` is available only for inexpensive interface debugging. It
must not be used in official benchmark results.

## Recorded evidence

Each JSON trajectory contains:

- exact system and user input;
- model text, tool calls, tool results, provider stop reasons, and token usage;
- raw provider responses with private-reasoning fields removed;
- the injected fault-proxy event and all environment tool events;
- seed provenance;
- final persistent-state fingerprint;
- component evaluation;
- fourteen task-scoped SQL verifier results.

The API key and authorization headers are not recorded.

## Primary pilot matrix

Run every model five times on each of the four matched variants:

```text
not_committed
commit_response_lost
partial_commit
async_pending
```

Report task pass rate and matched-group success. A model passes the matched
group only when it succeeds under every hidden commit state; this prevents a
fixed retry or fixed no-retry policy from appearing robust.

The complete 20-run pilot can be launched with:

```powershell
python -m aftermath_bench run-itsm-suite `
  --provider openai-compatible `
  --base-url "https://provider.example/v1" `
  --model "<model-id>" `
  --repetitions 5 `
  --output-directory "runs/itsm-pilot"
```

The suite preserves every trajectory and writes an aggregate `summary.json`
containing task pass rate, matched-group success, component pass rates, and
provider errors. Provider failures are kept separate from benchmark failures.

Before interpreting model reasoning failures, run the deterministic reference
and fixed baselines:

```powershell
python -m aftermath_bench demo-itsm --all `
  --enterpriseops-archive "<path-to-gym_dbs.zip>"
python -m aftermath_bench baselines
```
