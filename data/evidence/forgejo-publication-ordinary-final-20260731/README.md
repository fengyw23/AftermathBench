# Forgejo publication ordinary recovery

GitHub Actions run
[`30560679399`](https://github.com/fengyw23/AftermathBench/actions/runs/30560679399)
executed `glm-5.2` on all eight matched publication boundaries at commit
`0d4840df92a887c125f0a4288e90b564b9aabc85`.

This is the ordinary condition. Unlike the paired execution control, the
model was not supplied the state-dependent recovery rule. It received the
same scenario implementation, native public tools, 25-turn limit and provider
configuration, and each run rebuilt one authoritative failure boundary from a
fresh snapshot.

Results:

- Recovery Integrity: 7/8 (87.5%);
- matched-group success: 0/1;
- Preservation: 8/8;
- Goal Completion, Repair Completeness and Protocol Safety: 7/8 each;
- provider/runtime errors: 0;
- mutation-tool errors: 0.

The failed state was `release_committed_both_delivered`. Before its first
write, the model had read the publication manifest, target Release and assets,
both successful native webhook histories, and both existing receiver records.
It nevertheless replayed both already-successful deliveries after uploading
the assets. The replay created two new native delivery UUIDs, so the receiver
ledger contained four externally applied keys instead of two. The model then
mistook equal payload hashes for idempotency even though the visible receiver
records were keyed by delivery UUID.

This is a state/identity-composition and replay-scope failure, not missing
evidence, an unreachable target, or a tool error. The high 7/8 task pass also
shows that this development family alone is not difficult enough for a
top-tier benchmark estimate. The matched-group failure is useful as a
diagnostic, but independent hidden instances and additional native families
remain necessary.

`model-runs/repetition-01/` retains all complete model-visible inputs, calls,
results and terminal evaluations. `analysis.json` contains a deterministic
pre-write evidence and mutation-scope audit. No API credential is present.
