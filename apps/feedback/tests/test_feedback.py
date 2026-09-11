"""Unit tests for feedback engine + stopping policy (T044-T045)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import FeedbackEngine, FeedbackSignal
from stopping import StoppingPolicy, StopState


class TestFeedback:
    def test_signals_generate_actions(self):
        engine = FeedbackEngine()
        rec = engine.ingest(FeedbackSignal(kind="entity", source_id="s1"))
        assert any(a.action == "discover" for a in rec.actions)
        rec2 = engine.ingest(FeedbackSignal(kind="relation", source_id="s2"))
        assert any(a.action == "recrawl" for a in rec2.actions)

    def test_topological_raises_budget(self):
        engine = FeedbackEngine()
        rec = engine.ingest(FeedbackSignal(kind="topological", source_id="s3", weight=0.9))
        budget = next(a for a in rec.actions if a.action == "budget")
        assert budget.priority > 0.2

    def test_emits_feedback_generated(self):
        events: list[tuple] = []
        engine = FeedbackEngine(emitter=lambda et, payload: events.append((et, payload)))
        engine.ingest(FeedbackSignal(kind="discovery", source_id="s4"))
        assert events[0][0] == "feedback.generated"
        assert events[0][1]["actions"]


class TestStopping:
    def test_running_when_gains_high(self):
        policy = StoppingPolicy()
        for g in [0.9, 0.85, 0.8, 0.9, 0.86, 0.82, 0.88, 0.84]:
            policy.record_gain("src-a", g)
        assert policy.state_for("src-a") == StopState.RUN

    def test_sustained_decay_sleeps_not_stops(self):
        policy = StoppingPolicy(sleep_below=0.3, stop_below=0.1)
        for g in [0.29, 0.28, 0.27, 0.26, 0.25, 0.24, 0.23, 0.22]:
            policy.record_gain("src-b", g)
        assert policy.state_for("src-b") == StopState.SLEEP

    def test_floor_decay_stops(self):
        policy = StoppingPolicy(sleep_below=0.3, stop_below=0.1)
        for g in [0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02]:
            policy.record_gain("src-b", g)
        assert policy.state_for("src-b") == StopState.STOP
        assert policy.marginal_gain("src-b") < 0.1

    def test_frontier_explosion_guard_sleeps(self):
        policy = StoppingPolicy(guard_frontier=100)
        policy.record_gain("src-c", 0.9)
        policy.set_frontier_size("src-c", 5000)
        assert policy.state_for("src-c") == StopState.SLEEP

    def test_unknown_source_runs(self):
        assert StoppingPolicy().state_for("nope") == StopState.RUN