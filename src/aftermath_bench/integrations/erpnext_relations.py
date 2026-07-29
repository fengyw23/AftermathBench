from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ERPNextRelationRule:
    """One native ERPNext link that can be reproduced from public documents."""

    relation_type: str
    source_doctype: str
    target_doctype: str
    target_path: tuple[str, ...]
    target_type_path: tuple[str, ...] | None = None
    target_type_value: str | None = None


RELATION_RULES = (
    ERPNextRelationRule(
        "fulfilled_by",
        "Purchase Order",
        "Purchase Receipt",
        ("items", "*", "purchase_order"),
    ),
    ERPNextRelationRule(
        "billed_by",
        "Purchase Order",
        "Purchase Invoice",
        ("items", "*", "purchase_order"),
    ),
    ERPNextRelationRule(
        "billed_by",
        "Purchase Receipt",
        "Purchase Invoice",
        ("items", "*", "purchase_receipt"),
    ),
    ERPNextRelationRule(
        "paid_by",
        "Purchase Invoice",
        "Payment Entry",
        ("references", "*", "reference_name"),
        ("references", "*", "reference_doctype"),
        "Purchase Invoice",
    ),
    ERPNextRelationRule(
        "inspected_by",
        "Purchase Receipt",
        "Quality Inspection",
        ("reference_name",),
        ("reference_type",),
        "Purchase Receipt",
    ),
    ERPNextRelationRule(
        "returned_by",
        "Purchase Receipt",
        "Purchase Receipt",
        ("return_against",),
    ),
    ERPNextRelationRule(
        "credited_by",
        "Purchase Invoice",
        "Purchase Invoice",
        ("return_against",),
    ),
)


def _path_matches(
    document: dict[str, Any],
    path: tuple[str, ...],
    expected: str,
) -> list[str]:
    matches: list[str] = []

    def visit(value: Any, index: int, rendered: str) -> None:
        if index == len(path):
            if str(value) == expected:
                matches.append(rendered)
            return
        segment = path[index]
        if segment == "*":
            if not isinstance(value, list):
                return
            for item_index, item in enumerate(value):
                visit(item, index + 1, f"{rendered}[{item_index}]")
            return
        if not isinstance(value, dict) or segment not in value:
            return
        next_rendered = f"{rendered}.{segment}" if rendered else segment
        visit(value[segment], index + 1, next_rendered)

    visit(document, 0, "")
    return matches


def _rule_matches(
    rule: ERPNextRelationRule,
    document: dict[str, Any],
    source_name: str,
) -> list[str]:
    paths = _path_matches(document, rule.target_path, source_name)
    if not paths or rule.target_type_path is None:
        return paths
    type_paths = _path_matches(
        document,
        rule.target_type_path,
        str(rule.target_type_value),
    )
    if not type_paths:
        return []
    if "*" not in rule.target_path:
        return paths
    matched_rows = {path.rsplit(".", 1)[0] for path in paths}
    typed_rows = {path.rsplit(".", 1)[0] for path in type_paths}
    return [
        path
        for path in paths
        if path.rsplit(".", 1)[0] in matched_rows & typed_rows
    ]


def applicable_relation_rules(
    *,
    source_doctype: str,
    target_doctype: str,
    relation_type: str | None = None,
) -> tuple[ERPNextRelationRule, ...]:
    return tuple(
        rule
        for rule in RELATION_RULES
        if rule.source_doctype == source_doctype
        and rule.target_doctype == target_doctype
        and (relation_type is None or rule.relation_type == relation_type)
    )


def find_related_documents(
    *,
    source_doctype: str,
    source_name: str,
    target_doctype: str,
    documents: Iterable[dict[str, Any]],
    relation_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return one-hop native records plus the exact fields proving each edge."""
    rules = applicable_relation_rules(
        source_doctype=source_doctype,
        target_doctype=target_doctype,
        relation_type=relation_type,
    )
    if not rules:
        raise ValueError(
            "unsupported one-hop relation: "
            f"{source_doctype} -> {target_doctype}"
        )
    related: list[dict[str, Any]] = []
    for document in documents:
        evidence = []
        for rule in rules:
            paths = _rule_matches(rule, document, source_name)
            if paths:
                evidence.append(
                    {
                        "relation_type": rule.relation_type,
                        "matched_paths": paths,
                        "matched_value": source_name,
                    }
                )
        if evidence:
            related.append(
                {
                    "document": document,
                    "evidence": evidence,
                }
            )
    return related
