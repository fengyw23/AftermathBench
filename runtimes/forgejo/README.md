# Native Forgejo runtime

This runtime builds Forgejo from the exact audited source revision in
`runtime.lock.json`. The upstream Dockerfile is verified byte-for-byte and a
derived build file pins all three base images by digest before the image is
built.

The initial recovery seam is a Pull Request merge whose HTTP result is
ambiguous. Two independent, persistent observers prevent the task from
collapsing to “retry or do not retry”:

- Forgejo stores the Pull Request, branch, linked issue, release, webhook task,
  and delivery result;
- an external webhook sink stores every delivery attempt under Forgejo's
  `X-Forgejo-Delivery` identifier.

The two fault gateways can independently suppress a request or drop a response:

1. the API gateway makes the merge request appear to fail before or after the
   native merge commits;
2. the webhook gateway distinguishes a delivery that never reached the
   receiver from one whose response was lost after the external effect.

This supports four matched states with the same visible merge error but
different correct recovery scopes: perform the merge, preserve the merge,
wait for native delivery, or redeliver only when the receiver has no event.
The external sink is an observer and fault target, not a replacement for
Forgejo's merge, issue, release, or webhook logic.

Execution admission remains false until the source-built image, deterministic
snapshot/reset, all matched boundaries, reference recovery, fixed baselines,
and terminal evaluator have been replayed in CI.
