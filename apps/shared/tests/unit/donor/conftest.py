import pytest

from donor.correlation_graph import CorrelationGraph


@pytest.fixture
def correlation_graph() -> CorrelationGraph:
    return CorrelationGraph()