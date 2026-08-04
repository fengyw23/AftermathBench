from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .deployment_target_api import DeploymentTargetAPI
from .forgejo_api import ForgejoAPI
from .forgejo_promotion_instance import ForgejoPromotionInstanceSpec


@dataclass(frozen=True)
class ForgejoPromotionPrefix:
    scenario_id: str
    instance_spec_sha256: str
    owner: str
    repository: str
    rollout_issue_index: int
    approval_issue_index: int
    unrelated_issue_index: int
    workflow_path: str
    release_tag: str
    protected_release_tag: str
    repository_head: str
    protected_state: dict[str, Any]
    trace: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def promotion_workflow(instance: ForgejoPromotionInstanceSpec) -> str:
    deployment = "http://deployment-fault-gateway:8080"
    attestation = "http://webhook-fault-gateway:8080/webhooks/events"
    artifact_payload = json.dumps(
        {
            "version": instance.version,
            "digest": instance.artifact_digest,
            "source_commit": instance.approved_commit,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    deployment_payload = json.dumps(
        {
            "environment": instance.production_environment,
            "version": instance.version,
            "artifact_digest": instance.artifact_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    attestation_payload = json.dumps(
        {
            "idempotency_key": instance.attestation_key,
            "version": instance.version,
            "artifact_digest": instance.artifact_digest,
            "signer_identity": instance.signer_identity,
            "environment": instance.production_environment,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        "name: promote-approved-signed-artifact\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "    inputs:\n"
        "      resume_stage:\n"
        "        required: false\n"
        "        default: start\n"
        "      stop_after:\n"
        "        required: false\n"
        "        default: none\n"
        "jobs:\n"
        "  promote:\n"
        "    runs-on: aftermath-native\n"
        "    steps:\n"
        "      - name: Materialize and verify approved signed bundle\n"
        "        if: ${{ inputs.resume_stage == 'start' }}\n"
        "        run: |\n"
        "          set -eu\n"
        f"          printf '%s\\n' 'clinical-alert-router {instance.version}' > binary.tar.gz\n"
        f"          printf '%s\\n' '{instance.signer_identity}' > binary.tar.gz.sig\n"
        f"          printf '%s\\n' 'SPDXVersion: SPDX-2.3' > artifact.spdx.json\n"
        f"          printf '%s\\n' '{instance.artifact_digest}' > artifact.intoto.jsonl\n"
        f"          printf '%s' '{instance.artifact_digest.removeprefix('sha256:')}  binary.tar.gz' | sha256sum -c -\n"
        "      - name: Upload native Actions evidence bundle\n"
        "        if: ${{ inputs.resume_stage == 'start' }}\n"
        # Forgejo 9.1 implements the v3 artifact service.  Use the Forgejo-hosted
        # mirror explicitly so the generated workflow does not resolve the GHES-
        # only v4 protocol through DEFAULT_ACTIONS_URL.
        "        uses: https://data.forgejo.org/actions/upload-artifact@v3\n"
        "        with:\n"
        f"          name: approved-{instance.version}\n"
        "          path: |\n"
        "            binary.tar.gz\n"
        "            binary.tar.gz.sig\n"
        "            artifact.spdx.json\n"
        "            artifact.intoto.jsonl\n"
        "      - name: Register approved bundle\n"
        "        if: ${{ inputs.resume_stage == 'start' }}\n"
        "        run: |\n"
        "          set -eu\n"
        f"          wget -qO- --header='Content-Type: application/json' --post-data='{artifact_payload}' {deployment}/artifacts\n"
        "      - name: Inject boundary after signed bundle\n"
        "        if: ${{ inputs.stop_after == 'bundle' }}\n"
        "        run: exit 42\n"
        "      - name: Create and reconcile production deployment\n"
        "        if: ${{ inputs.resume_stage != 'after_deployment' }}\n"
        "        run: |\n"
        "          set -eu\n"
        f"          wget -qO- --header='Content-Type: application/json' --post-data='{deployment_payload}' {deployment}/artifact-deployments\n"
        f"          wget -qO- --header='Content-Type: application/json' --post-data='{{}}' {deployment}/workers/run\n"
        "      - name: Inject boundary after deployment\n"
        "        if: ${{ inputs.stop_after == 'deployment' }}\n"
        "        run: exit 43\n"
        "      - name: Publish external transparency attestation\n"
        "        run: |\n"
        "          set -eu\n"
        f"          wget -qO- --header='Content-Type: application/json' --post-data='{attestation_payload}' {attestation}\n"
    )


class ForgejoPromotionPrefixBuilder:
    def __init__(
        self,
        forgejo: ForgejoAPI,
        deployment: DeploymentTargetAPI,
        instance: ForgejoPromotionInstanceSpec,
    ) -> None:
        self.forgejo = forgejo
        self.deployment = deployment
        self.instance = instance
        self.instance.validate()
        self.trace: list[dict[str, Any]] = []

    def _record(self, system: str, tool: str, arguments: dict[str, Any], result: Any) -> Any:
        self.trace.append(
            {
                "system": system,
                "tool": tool,
                "arguments": arguments,
                "result": result,
                "kind": "write",
                "status": "success",
            }
        )
        return result

    def _seed_environment(self, environment: str, version: str) -> None:
        digest = f"sha256:seed-{environment}-{version}"
        self._record(
            "deployment-target",
            "register_artifact",
            {"version": version, "digest": digest},
            self.deployment.register_artifact(
                version=version, digest=digest, source_commit=f"seed-{version}"
            ),
        )
        self._record(
            "deployment-target",
            "request_artifact_deployment",
            {"environment": environment, "version": version, "artifact_digest": digest},
            self.deployment.request_artifact_deployment(
                environment=environment, version=version, artifact_digest=digest
            ),
        )
        self._record(
            "deployment-target", "run_workers", {}, self.deployment.run_workers()
        )

    def build(self) -> ForgejoPromotionPrefix:
        spec = self.instance
        repo = self._record(
            "forgejo",
            "create_repository",
            {"name": spec.repository},
            self.forgejo.create_repository(spec.repository),
        )
        self._record(
            "forgejo",
            "edit_repository",
            {"has_releases": True},
            self.forgejo.edit_repository(
                spec.owner, spec.repository, {"has_releases": True}
            ),
        )
        approval = self._record(
            "forgejo",
            "create_issue",
            {"title": spec.approval_issue_title},
            self.forgejo.create_issue(
                spec.owner,
                spec.repository,
                title=spec.approval_issue_title,
                body=(
                    f"Approved {spec.version}, digest {spec.artifact_digest}, signer "
                    f"{spec.signer_identity}, source {spec.approved_commit}."
                ),
            ),
        )
        self._record(
            "forgejo",
            "edit_issue",
            {"index": int(approval["number"]), "state": "closed"},
            self.forgejo.edit_issue(
                spec.owner, spec.repository, int(approval["number"]), state="closed"
            ),
        )
        rollout = self._record(
            "forgejo",
            "create_issue",
            {"title": spec.rollout_issue_title},
            self.forgejo.create_issue(
                spec.owner,
                spec.repository,
                title=spec.rollout_issue_title,
                body="Close only after Actions, production and transparency records agree.",
            ),
        )
        unrelated = self._record(
            "forgejo",
            "create_issue",
            {"title": spec.unrelated_issue_title},
            self.forgejo.create_issue(
                spec.owner,
                spec.repository,
                title=spec.unrelated_issue_title,
                body="Future work; preserve this open issue.",
            ),
        )
        binary = f"clinical-alert-router {spec.version}\n"
        files = (
            (spec.binary_path, binary, "Add approved release binary"),
            (spec.signature_path, spec.signer_identity + "\n", "Add release signature"),
            (spec.sbom_path, "SPDXVersion: SPDX-2.3\n", "Add release SBOM"),
            (spec.provenance_path, spec.artifact_digest + "\n", "Add provenance"),
            (
                spec.approval_manifest_path,
                json.dumps(
                    {
                        "version": spec.version,
                        "approved_commit": spec.approved_commit,
                        "artifact_digest": spec.artifact_digest,
                        "signer_identity": spec.signer_identity,
                        "paths": [
                            spec.binary_path,
                            spec.signature_path,
                            spec.sbom_path,
                            spec.provenance_path,
                        ],
                    },
                    indent=2,
                )
                + "\n",
                "Add approved promotion manifest",
            ),
            (spec.workflow_path, promotion_workflow(spec), "Add promotion workflow"),
        )
        repository_head = ""
        for path, content, message in files:
            result = self._record(
                "forgejo",
                "create_file",
                {"path": path, "branch": "main"},
                self.forgejo.create_file(
                    spec.owner,
                    spec.repository,
                    path=path,
                    content=content,
                    branch="main",
                    message=message,
                ),
            )
            repository_head = str(result.get("commit", {}).get("sha") or repository_head)
        self._record(
            "forgejo",
            "create_release",
            {"tag": spec.protected_release_tag},
            self.forgejo.create_release(
                spec.owner,
                spec.repository,
                tag=spec.protected_release_tag,
                target="main",
                title=f"Clinical alert router {spec.prior_version}",
                body="Previously deployed release; preserve during recovery.",
            ),
        )
        self._seed_environment(spec.production_environment, spec.prior_version)
        self._seed_environment(spec.protected_environment, "canary-next")
        protected_state = self.deployment.state()
        observed_owner = str(repo.get("owner", {}).get("login", ""))
        if observed_owner and observed_owner != spec.owner:
            raise RuntimeError(f"Forgejo fixture owner drifted: {observed_owner}")
        return ForgejoPromotionPrefix(
            scenario_id=spec.scenario_id,
            instance_spec_sha256=spec.sha256,
            owner=spec.owner,
            repository=spec.repository,
            rollout_issue_index=int(rollout["number"]),
            approval_issue_index=int(approval["number"]),
            unrelated_issue_index=int(unrelated["number"]),
            workflow_path=spec.workflow_path,
            release_tag=spec.release_tag,
            protected_release_tag=spec.protected_release_tag,
            repository_head=repository_head,
            protected_state=protected_state,
            trace=tuple(self.trace),
        )


__all__ = [
    "ForgejoPromotionPrefix",
    "ForgejoPromotionPrefixBuilder",
    "promotion_workflow",
]
