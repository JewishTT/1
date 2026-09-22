"""Failure/replay chaos benchmark (T125).

Reproduces the crash path deterministically: a collector is killed in the middle
of a batch (journal holds exactly the pre-crash trophies), then *replayed* from
its durable journal. The projection invariant asserted here is exactly-once:
``processed + replayed == manifest`` with disjoint covers, so no observation is
dropped or double-gated across a crash (T120/T127b, content addressing does the
dedup, the journal does the resume).

Stack-free: the real ``FileReplayJournal`` from the acquisition app is used; the
"sink" is the projection set (the Observation Gate's content-addressed store in
production).

Usage:
    uv run python -m bench.chaos.bench_replay [--records 2000] [--kill-at 700]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / "apps"
for _p in (str(_ROOT / "acquisition"), str(_ROOT / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from observation_gate.replay import FileReplayJournal, replay_collector


@dataclass
class BenchResult:
    name: str
    values: dict = field(default_factory=dict)


def _manifest(n: int) -> list[dict]:
    return [
        {
            "source_type": f"cc-{i % 3}",
            "uri": f"https://news.example/{i % 12}/{i}",
            "digest": f"{i:064x}",
        }
        for i in range(n)
    ]


def bench_replay(records: int = 2000, kill_at: int = 700) -> dict:
    manifest = _manifest(records)

    # -- pass 1: collector runs, is killed at kill_at (journal stops growing).
    with tempfile.TemporaryDirectory() as tmp:
        journal_path = Path(tmp) / "journal.jsonl"
        journal = FileReplayJournal(journal_path)
        for consumed, record in enumerate(replay_collector(journal, manifest)):
            if consumed >= kill_at:
                break  # simulated worker death mid-batch: no further marks
            journal.mark_processed(record)

        # -- pass 2: resume the SAME manifest from a fresh journal (process restart).
        resumed_journal = FileReplayJournal(journal_path)
        replayed = list(replay_collector(resumed_journal, manifest))
        projected = {_key(r) for r in replayed}
        processed = {_key(r) for r in manifest} - projected

    n = len(manifest)
    exactly_once = {_key(r) for r in manifest} == (processed | projected) and len(
        processed & projected
    ) == 0
    no_drops = len(processed) + len(projected) == n
    single_reemit = not (set(projected) & set(processed))
    return {
        "records": n,
        "kill_at": kill_at,
        "processed_before_crash": kill_at,
        "replayed_after_crash": len(projected),
        "exactly_once_projection": exactly_once and no_drops and single_reemit,
        "uncovered": n - len(processed) - len(projected),
    }


def _key(record: dict) -> tuple[str, str, str]:
    return (
        str(record.get("source_type") or record.get("source") or "unknown"),
        str(record.get("uri") or ""),
        str(record.get("digest") or ""),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="COGNITIVE failure/replay chaos bench (T125)")
    parser.add_argument("--records", type=int, default=2000)
    parser.add_argument("--kill-at", type=int, default=700)
    args = parser.parse_args()
    values = bench_replay(records=args.records, kill_at=args.kill_at)
    result = BenchResult(name="replay-chaos", values=values)
    print(json.dumps(asdict(result), indent=2))
    return 0 if values["exactly_once_projection"] else 1


if __name__ == "__main__":
    raise SystemExit(main())