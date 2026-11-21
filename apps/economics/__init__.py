"""Economic Intelligence Silo: evidence-backed economic domain analysis."""
from .domain import (
    EconomicSubject,
    FinancialFlow,
    FinancialFlowAggregate,
    aggregate_flows,
    subjects_from_snapshot,
)

__all__ = [
    "EconomicSubject",
    "FinancialFlow",
    "FinancialFlowAggregate",
    "aggregate_flows",
    "subjects_from_snapshot",
]
