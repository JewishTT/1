"""OpenTelemetry tracing, Prometheus counters/histograms, structured logging (T015).

Bootstrap must run once at application startup. All consumers/producers/
projection jobs emit spans + metrics through this module.
"""

from __future__ import annotations

import logging
import sys
from functools import lru_cache

from config.settings import get_settings

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
except ImportError:  # pragma: no cover - optional at import time
    trace = None  # type: ignore[assignment]


try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server
except ImportError:  # pragma: no cover
    Counter = Gauge = Histogram = start_http_server = None  # type: ignore[assignment]

logger = logging.getLogger("cognitive")

# --- Prometheus counters (stable) ---

if Counter is not None:
    EVENTS_PRODUCED = Counter("cognitive_events_produced_total", "Events produced", ["event_type", "topic"])
    EVENTS_CONSUMED = Counter("cognitive_events_consumed_total", "Events consumed", ["event_type", "topic"])
    ACQUISITION_TASKS = Counter("cognitive_acquisition_tasks_total", "Acquisition tasks", ["worker_class", "state"])
    OBSERVATIONS = Counter("cognitive_observations_total", "Observations", ["status"])
    MENTIONS = Counter("cognitive_mentions_total", "Mentions extracted")
    CANDIDATES = Counter("cognitive_candidates_total", "Candidates created")
    ENTITIES = Counter("cognitive_entities_total", "Entities materialized", ["entity_type"])
    ADMISSION_DECISIONS = Counter("cognitive_admission_decisions_total", "Admission decisions", ["decision"])
    PROJECTIONS = Counter("cognitive_projections_total", "Projection writes", ["projection_type"])
    TDA_FEATURES = Counter("cognitive_tda_features_total", "TDA features persisted")
    FINDINGS = Counter("cognitive_findings_total", "Findings created")
    FEEDBACK_EVENTS = Counter("cognitive_feedback_events_total", "Feedback events emitted")
    DLQ_ROUTED = Counter("cognitive_dlq_routed_total", "Events routed to DLQ/quarantine", ["lane"])
    LATENCY = Histogram("cognitive_latency_seconds", "Operation latency", ["operation"])
    QUEUE_DEPTH = Gauge("cognitive_queue_depth", "Downstream queue depth", ["queue"])
    FRONTIER_SIZE = Gauge("cognitive_frontier_size", "Frontier item count", ["tenant"])
else:
    EVENTS_PRODUCED = EVENTS_CONSUMED = ACQUISITION_TASKS = OBSERVATIONS = None  # type: ignore[assignment]
    MENTIONS = CANDIDATES = ENTITIES = ADMISSION_DECISIONS = PROJECTIONS = None  # type: ignore[assignment]
    TDA_FEATURES = FINDINGS = FEEDBACK_EVENTS = DLQ_ROUTED = None  # type: ignore[assignment]
    LATENCY = QUEUE_DEPTH = FRONTIER_SIZE = None  # type: ignore[assignment]


@lru_cache(maxsize=1)
def setup_telemetry(service_name: str = "cognitive") -> None:
    """Bootstrap OTEL tracing + structured logging. Call once per process."""

    # Structured logging
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # OpenTelemetry
    if trace is not None:
        settings = get_settings()
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

    # Prometheus
    if start_http_server is not None:
        try:
            start_http_server(9090, addr="0.0.0.0")
        except OSError:
            pass  # Already running


def get_tracer(name: str = "cognitive"):
    if trace is not None:
        return trace.get_tracer(name)
    return None