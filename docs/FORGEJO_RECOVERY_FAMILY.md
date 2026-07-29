# Forgejo Pull Request recovery family

## Research purpose

The first Forgejo family tests recovery after a merge operation reports a
connection failure. It is deliberately not a binary “retry or do not retry”
task. The merge can affect five independently inspectable records:

1. the Git branch head;
2. the Pull Request state and merged commit;
3. a linked issue closed by the native post-receive path;
4. Forgejo's persistent webhook task and delivery result;
5. the external receiver's exactly-once event ledger.

The remaining user goal also requires a release from the actual merged commit,
while unrelated work and branch policy must stay unchanged.

## Matched hidden states

All variants start from the same native snapshot, receive the same instruction,
and expose the same connection error from the merge call.

| Hidden state | Evidence that distinguishes it | Necessary recovery |
|---|---|---|
| Merge request did not reach Forgejo | PR open, branch unchanged, no webhook task or receiver event | merge, verify downstream effects, release |
| Merge committed and delivery succeeded | PR/branch/issue updated, successful hook task, one receiver event | preserve merge and delivery; release only |
| Receiver accepted but its response was lost | hook task reports failure, receiver already has the delivery UUID | do not replay; release only |
| Webhook request did not reach receiver | hook task reports failure, receiver has no matching UUID | replay that delivery once; verify; release |

The third and fourth variants are the central counterfactual pair. Looking only
at Forgejo produces the same tempting conclusion (“delivery failed”), while
the external audit changes the correct action. Looking only at the external
receiver is also insufficient because the model must first identify the
specific Forgejo delivery and its relationship to the merged PR.

## Why this is an original-system task

- The branch, commit, Pull Request, linked issue, release, webhook and hook
  task are created and mutated by source-built Forgejo.
- Merge semantics and linked-issue closure are not reproduced in benchmark
  code.
- The API fault gateway only suppresses a request or drops a response.
- The webhook gateway only suppresses a request or drops a response.
- The external sink records an actual outgoing Forgejo webhook under the
  native `X-Forgejo-Delivery` identifier.

The family remains `unvalidated` until all four boundaries, a reference
recovery, fixed baselines and terminal preservation checks pass after
deterministic snapshot restoration.
