"""AftermathBench public package."""

from .admission import AdmissionReport, validate_task
from .core import (
    CommitOutcome,
    FaultPlan,
    RecordedEnvironment,
    ToolEnvironment,
    TransitionFaultProxy,
    canonical_fingerprint,
)
from .evaluator import EvaluationResult, evaluate
from .runtime_gate import RuntimeAdmissionReport, validate_runtime_manifest

__all__ = [
    "AdmissionReport",
    "CommitOutcome",
    "EvaluationResult",
    "FaultPlan",
    "RecordedEnvironment",
    "RuntimeAdmissionReport",
    "ToolEnvironment",
    "TransitionFaultProxy",
    "canonical_fingerprint",
    "evaluate",
    "validate_task",
    "validate_runtime_manifest",
]

__version__ = "0.3.0"
