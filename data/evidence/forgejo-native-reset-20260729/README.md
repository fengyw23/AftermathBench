# Forgejo source build and deterministic reset

GitHub Actions run
[`30428615076`](https://github.com/fengyw23/AftermathBench/actions/runs/30428615076)
verified the audited files from Forgejo revision
`fbafae6c6288f3448aa6932576841f5daf5a9c76`, pinned all three base images,
and built image:

`sha256:1caed0f77ab011a5c86b5d9aebd8a8f0d2b12284712bb282ec878f2fb7ca9dfd`

Because the source revision is not a release tag, the build uses the valid
semantic prerelease `17.0.0-aftermath.fbafae6c`. This preserves Forgejo's
native migration checks; it does not bypass or patch database migration logic.

The validation then:

1. created an administrator through the Forgejo CLI;
2. created a repository and baseline issue through the native REST API;
3. stopped Forgejo and captured the complete `/data` volume;
4. created a second issue;
5. restored the captured volume; and
6. proved that only the baseline issue remained.

This admits deterministic original-system reset. Merge, webhook delivery,
reference recovery, evaluator, and hard-task admission remain pending.
