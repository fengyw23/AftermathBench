# AftermathBench execution contract

## North star

Advance the repository toward the declared `top-conference-full` release.
The primary progress measures are the machine-derived counts of formally bound
slots, formally bound matched cases, and frozen hidden-test instances. Commit
count, test count, development-only cases, and additional documentation are not
substitutes for those outcomes.

Run `python -m aftermath_bench status` before making a stage decision. Treat
`data/benchmark_matrix.json` and `data/release_manifest.json` as authoritative.

## Fixed execution order

1. Close the in-flight Kubernetes K3, K4 and K5 chain, then freeze the shared
   formal-evidence protocol.
2. Bind one formal public-development slot in each of ERPNext, Forgejo and
   Kubernetes, then prove one end-to-end hidden-instance lifecycle.
3. Complete missing task families and public-development instances using the
   frozen shared pipeline.
4. Generate and freeze two hidden instances per family before provider access.
5. Run the preregistered cross-model evaluation only after data freeze.
6. Finish analysis, data card, reproducibility package and paper materials.

Do not start a later stage while an earlier shared gate is open, except for
independent work that directly produces another formal slot.

## Progress-first rules

- After the current Kubernetes chain, change the evidence schema, evaluator
  contract or runtime admission protocol only for a demonstrated correctness,
  fairness, reproducibility or security blocker affecting multiple future
  slots.
- Time-box an isolated failure to one focused diagnosis and at most two CI
  reruns. If it remains case-specific, quarantine that candidate with an
  explicit reason and advance another independent slot.
- Prefer parameterized family builders, shared workflow templates and sharded
  CI over one-off scripts. Generalize only after a second concrete use exists.
- Every implementation slice should either bind a formal slot, freeze a hidden
  instance, add a missing matrix family, or remove a shared blocker to one of
  those outputs.
- Record non-blocking cleanup, naming, formatting and documentation issues as
  technical debt; do not interrupt release construction for them.
- Do not add interface traps, hidden evidence, irrelevant records or shorter
  limits to manufacture difficulty. Difficulty must come from native state,
  dependencies, asynchronous effects and preservation requirements.
- Never promote model-seen development data to hidden test data. Development
  evidence remains diagnostic until independently rebuilt and formally bound.
- Do not add domains, taxonomies, metrics or task families outside the frozen
  matrix without explicit user approval.

## Reporting discipline

Status reports must separate:

- implemented development cases;
- hard-admitted cases;
- formally bound public cases;
- frozen hidden cases;
- valid model runs and infrastructure failures.

Report the active milestone, the next release-producing action and any blocker.
Avoid extended investigation of already understood historical failures unless
they block the active milestone.
