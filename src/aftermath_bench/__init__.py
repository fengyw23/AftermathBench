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

__all__ = [
    "AdmissionReport",
    "CommitOutcome",
    "EvaluationResult",
    "FaultPlan",
    "RecordedEnvironment",
    "ToolEnvironment",
    "TransitionFaultProxy",
    "canonical_fingerprint",
    "evaluate",
    "validate_task",
]

__version__ = "0.1.0"
