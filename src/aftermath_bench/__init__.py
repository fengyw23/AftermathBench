"""AftermathBench public package."""

from .admission import AdmissionReport, validate_task
from .evaluator import EvaluationResult, evaluate

__all__ = [
    "AdmissionReport",
    "EvaluationResult",
    "evaluate",
    "validate_task",
]

__version__ = "0.1.0"

