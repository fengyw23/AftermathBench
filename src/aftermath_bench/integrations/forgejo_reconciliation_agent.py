from __future__ import annotations

from typing import Any

from .forgejo_promotion_agent import ForgejoPromotionEnvironment
from .forgejo_reconciliation_recovery import (
    collect_reconciliation_state,
    evaluate_reconciliation_terminal,
)


class ForgejoReconciliationEnvironment(ForgejoPromotionEnvironment):
    """Promotion tools with reconciliation-specific deterministic scoring."""

    def snapshot(self) -> dict[str, Any]:
        state = collect_reconciliation_state(
            forgejo=self.forgejo,
            deployment=self.deployment,
            instance=self.instance,
            prefix=self.prefix,
            external_url=self.external_url,
        )
        evaluation = evaluate_reconciliation_terminal(
            state, instance=self.instance, prefix=self.prefix
        )
        return {"evaluation": evaluation, "authoritative_state": state}


__all__ = ["ForgejoReconciliationEnvironment"]
