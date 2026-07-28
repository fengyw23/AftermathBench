from __future__ import annotations

import argparse

from aftermath_bench.integrations.erpnext_faults import (
    ERP_NEXT_FAULT_VARIANTS,
    ERPNextFaultController,
    default_worker_control,
)
from aftermath_bench.schema import repository_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Control source-supported ERPNext fault boundaries."
    )
    parser.add_argument(
        "action",
        choices=("arm", "disarm-transport", "restore"),
    )
    parser.add_argument("--variant", choices=ERP_NEXT_FAULT_VARIANTS)
    parser.add_argument(
        "--container-cli",
        choices=("docker", "podman"),
        default="docker",
    )
    args = parser.parse_args()
    controller = ERPNextFaultController(
        worker_control=default_worker_control(
            repository_root(),
            container_cli=args.container_cli,
        )
    )
    if args.action == "restore":
        controller.restore()
        return 0
    if not args.variant:
        parser.error("--variant is required for arm and disarm-transport")
    if args.action == "arm":
        controller.arm(args.variant)
    else:
        controller.disarm_transport_after_failure(args.variant)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

