# ERPNext GLM-5.2 native pilot

This directory preserves the sanitized evidence from GitHub Actions run
[`30382460087`](https://github.com/fengyw23/AftermathBench/actions/runs/30382460087)
at commit `a84337d1e0f52cf83d50144cf13d8f196dc2a93d`.

## Configuration

- provider protocol: OpenAI-compatible Chat Completions;
- model: `glm-5.2`;
- repetitions: one;
- task: `erpnext-procurement-payment-001`;
- matched failure states: four;
- maximum model turns per state: 15;
- runtime: source-built ERPNext/Frappe with real MariaDB, Redis, RQ workers,
  HTTP gateway, and idempotent remittance receiver.

The API credential and authorization headers are absent from every preserved
file.

## Result

| Hidden failure state | Correct model mutation | Turns | Pass |
|---|---|---:|---|
| Request never reached ERPNext | Submit the draft Payment Entry | 4 | Yes |
| Database committed but response was lost | No mutation | 2 | Yes |
| Post-commit remittance enqueue failed | Requeue remittance | 4 | Yes |
| Remittance job existed but workers were paused | Resume existing workers | 5 | Yes |

Task Pass@1 and matched-group success were both `1.0`. All nine deterministic
terminal checks passed in every state. The model inspected payment and
remittance state in all four runs, made no unsafe submit retry, made no
unnecessary remittance requeue, and produced no tool error.

## Interpretation

This is a successful interface and runtime pilot, not evidence that the
benchmark is already difficult. The four states have clean, nearly
decision-complete signatures:

- draft payment plus outstanding invoice implies submit;
- submitted payment plus completed delivery implies no write;
- submitted payment plus no delivery and no job implies requeue;
- submitted payment plus a queued job implies resume workers.

`glm-5.2` gathered these facts and applied the correct branch each time. The
next task family must require integrating less direct evidence across more
records, include multiple plausible but unsafe repair paths, and prevent a
single compact decision tree from covering the matched group.

## Files

- `summary.json`: aggregate deterministic results and behavior rates;
- `prefix.json`: the shared seven-write public-API prefix;
- `*-failure.json`: authoritative hidden failure-boundary evidence;
- the remaining four JSON files: complete sanitized model inputs, responses,
  tool calls, tool results, final state, evaluation, and trajectory
  diagnostics.
