"""Donor-derived modules: code extracted, adapted and integrated.

Attribution / licenses
=====================
Track 003 (spec 003)
- ``correlation_graph``  <- OpenOSINT ``openosint/correlation.py`` (MIT).
- ``statement``          <- FollowTheMoney ``statement/statement.py`` (MIT).
- ``evidence``           <- NetForensicAI ``netforensicai/core/evidence.py`` (MIT).

Track 004 (spec 004)
- ``temporal``           <- investigator ``graph/temporal_consistency.py`` +
                            ``graph/dedup.py`` date primitives (MIT).
- ``target``             <- SpiderFoot ``spiderfoot/target.py`` (MIT, logic
                            layer; netaddr rewritten to stdlib ipaddress).

Each module is a faithful port rewritten to COGNITIVE domain conventions
(candidate-correlation, observation provenance, tenant-scoping). Donor
dependencies (rigour, sqlalchemy, netaddr, numpy/semhash/wordllama,
Django/Celery, ML libs) are removed. No code was taken from GPL/CC-BY-NC
donors (reNgine, PANO); kipi was unreadable. Allowed donors fully covered:
OpenOSINT, FollowTheMoney, NetForensicAI, investigator, SpiderFoot (logic),
kafSIEM + vitni (TS, in apps/webapp/src/lib/donor).
"""

from .correlation_graph import (
    CorrelationGraph,
    CorrelationKind,
    CorrelationLink,
    CorrelationNode,
    make_node,
)
from .evidence import (
    EvidenceError,
    EvidenceItem,
    EvidenceVault,
    infer_evidence_type,
    sha256_of_file,
)
from .statement import Statement
from .target import Target, TargetAlias, TargetType, classify, normalize
from .temporal import (
    DATE_CONFLICT_DAYS,
    as_date_list,
    date_spread_conflict,
    dates_compatible,
    ordering_conflicts,
    parse_iso_date,
    scan,
    to_iso_date,
)

__all__ = [
    "DATE_CONFLICT_DAYS",
    "CorrelationGraph",
    "CorrelationKind",
    "CorrelationLink",
    "CorrelationNode",
    "EvidenceError",
    "EvidenceItem",
    "EvidenceVault",
    "Statement",
    "Target",
    "TargetAlias",
    "TargetType",
    "as_date_list",
    "classify",
    "date_spread_conflict",
    "dates_compatible",
    "infer_evidence_type",
    "make_node",
    "normalize",
    "ordering_conflicts",
    "parse_iso_date",
    "scan",
    "sha256_of_file",
    "to_iso_date",
]