"""Recover and deliver SpecOps&CI operator decisions from the PostgreSQL outbox."""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from db.session import make_session_factory
from db.specops_ci_signal_outbox import SpecOpsDecisionSignalOutboxRelay

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _session_factory():
    return make_session_factory()


async def relay_specops_ci_decision_signals(*, limit: int = 20) -> dict[str, int]:
    """Dispatch committed admin decisions to Temporal; duplicate delivery is safe."""
    relay = SpecOpsDecisionSignalOutboxRelay(_session_factory())
    rows = await relay.claim_ready(limit=limit)
    counts = {"claimed": len(rows), "dispatched": 0, "failed": 0}
    if not rows:
        return counts

    try:
        from workflow.client import connect_temporal

        temporal = await connect_temporal()
    except Exception as exc:  # noqa: BLE001 - leave durable rows retryable
        for row in rows:
            await relay.mark_failed(row["outbox_id"], f"Temporal unavailable: {type(exc).__name__}")
            counts["failed"] += 1
        return counts

    for row in rows:
        try:
            if row["signal_name"] != "provide_operator_decision":
                raise ValueError("unsupported SpecOps&CI outbox signal")
            handle = temporal.get_workflow_handle(row["operation_id"])
            await handle.signal(row["signal_name"], row["payload"])
            await relay.mark_dispatched(row["outbox_id"])
            counts["dispatched"] += 1
        except Exception as exc:  # noqa: BLE001 - retry from the durable outbox
            await relay.mark_failed(row["outbox_id"], f"{type(exc).__name__}: {exc}")
            counts["failed"] += 1
            log.warning(
                "SpecOps&CI decision signal %s deferred: %s",
                row["decision_id"],
                type(exc).__name__,
            )
    return counts


async def run_specops_ci_signal_relay_forever(*, interval_seconds: float = 5.0) -> None:
    while True:
        try:
            await relay_specops_ci_decision_signals()
        except Exception:  # noqa: BLE001 - process remains alive; rows remain durable
            log.exception("SpecOps&CI decision outbox relay cycle failed")
        await asyncio.sleep(max(1.0, interval_seconds))


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_specops_ci_signal_relay_forever())


if __name__ == "__main__":
    main()


__all__ = [
    "relay_specops_ci_decision_signals",
    "run_specops_ci_signal_relay_forever",
]
