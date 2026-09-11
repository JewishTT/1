"""Candidate correlation graph — adapted from OpenOSINT (MIT).

Source: donors/OpenOSINT/openosint/correlation.py.
Changes: renamed to COGNITIVE domain (CorrelationNode vs candidate, I-2 —
correlation NEVER merges into entities); ``source_tools`` -> ``observations``
(observation refs); docstrings + types tightened; no external dependencies.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CorrelationKind(Enum):
    """Recognized OSINT entity categories."""

    EMAIL = "email"
    USERNAME = "username"
    DOMAIN = "domain"
    IP = "ip"
    PHONE = "phone"
    HASH = "hash"
    URL = "url"
    PERSON = "person"
    ORG = "org"
    ASN = "asn"
    CANDIDATE = "candidate"


_PROTO_RE = re.compile(r"^https?://", re.IGNORECASE)


def _normalize_value(kind: CorrelationKind, value: str) -> str:
    """Return a canonical form used for deduplication."""
    if kind is CorrelationKind.URL:
        return _PROTO_RE.sub("", value.strip().lower()).rstrip("/")
    return value.strip().lower()


@dataclass
class CorrelationNode:
    """A single candidate-correlation node.

    Equality and hashing are defined by (kind, normalized) so two nodes with
    the same semantic identity compare equal regardless of original casing or
    whitespace. This is dedup WITHOUT merge: the node never collapses two
    candidates into an admitted entity (I-2).
    """

    kind: CorrelationKind
    value: str
    normalized: str
    confidence: float
    observations: set[str] = field(default_factory=set)

    def __hash__(self) -> int:
        return hash((self.kind, self.normalized))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CorrelationNode):
            return False
        return self.kind == other.kind and self.normalized == other.normalized


def make_node(
    kind: CorrelationKind,
    value: str,
    confidence: float,
    observation: str = "",
) -> CorrelationNode:
    """Convenience constructor that fills ``normalized`` automatically."""
    normalized = _normalize_value(kind, value)
    refs: set[str] = {observation} if observation else set()
    return CorrelationNode(
        kind=kind,
        value=value,
        normalized=normalized,
        confidence=confidence,
        observations=refs,
    )


@dataclass
class CorrelationLink:
    """A directed edge between two nodes with a semantic kind label."""

    source: CorrelationNode
    target: CorrelationNode
    kind: str
    observation: str
    confidence: float = 1.0


_MERMAID_OPEN: dict[CorrelationKind, str] = {
    CorrelationKind.EMAIL: "[",
    CorrelationKind.USERNAME: "([",
    CorrelationKind.DOMAIN: "(",
    CorrelationKind.IP: "[[",
    CorrelationKind.PHONE: "[/",
    CorrelationKind.HASH: "[",
    CorrelationKind.URL: "(",
    CorrelationKind.PERSON: "(((",
    CorrelationKind.ORG: "{",
    CorrelationKind.ASN: "[[",
}

_MERMAID_CLOSE: dict[CorrelationKind, str] = {
    CorrelationKind.EMAIL: "]",
    CorrelationKind.USERNAME: "])",
    CorrelationKind.DOMAIN: ")",
    CorrelationKind.IP: "]]",
    CorrelationKind.PHONE: "/]",
    CorrelationKind.HASH: "]",
    CorrelationKind.URL: ")",
    CorrelationKind.PERSON: ")))",
    CorrelationKind.ORG: "}",
    CorrelationKind.ASN: "]]",
}

_MERMAID_UNSAFE_RE = re.compile(r'["\[\]{}\(\)/\\<>|]')


def _safe_mermaid_label(value: str, max_len: int = 40) -> str:
    """Strip Mermaid-unsafe characters and truncate."""
    return _MERMAID_UNSAFE_RE.sub("", value)[:max_len]


class CorrelationGraph:
    """Deduplicated directed graph of candidate-correlation nodes and links."""

    def __init__(self) -> None:
        self._nodes: dict[tuple[CorrelationKind, str], CorrelationNode] = {}
        self._links: list[CorrelationLink] = []
        self._link_keys: set[tuple[Any, ...]] = set()

    def add_node(self, node: CorrelationNode) -> CorrelationNode:
        """Insert node, merging duplicate observations. Returns canonical."""
        key = (node.kind, node.normalized)
        if key in self._nodes:
            existing = self._nodes[key]
            existing.observations.update(node.observations)
            if node.confidence > existing.confidence:
                existing.confidence = node.confidence
            return existing
        canonical = CorrelationNode(
            kind=node.kind,
            value=node.value,
            normalized=node.normalized,
            confidence=node.confidence,
            observations=set(node.observations),
        )
        self._nodes[key] = canonical
        return canonical

    def add_link(self, link: CorrelationLink) -> None:
        """Insert link, silently discarding duplicates."""
        key = (
            link.source.kind,
            link.source.normalized,
            link.target.kind,
            link.target.normalized,
            link.kind,
        )
        if key in self._link_keys:
            return
        self._link_keys.add(key)
        self._links.append(link)

    def merge(self, other: CorrelationGraph) -> None:
        """Absorb all nodes and links from *other* in place."""
        for node in other._nodes.values():
            self.add_node(node)
        for link in other._links:
            self.add_link(link)

    def neighbors(self, node: CorrelationNode) -> list[CorrelationNode]:
        """Return nodes directly connected to *node* (either direction)."""
        key = (node.kind, node.normalized)
        seen: set[tuple[CorrelationKind, str]] = set()
        result: list[CorrelationNode] = []
        for link in self._links:
            src_key = (link.source.kind, link.source.normalized)
            tgt_key = (link.target.kind, link.target.normalized)
            if src_key == key and tgt_key not in seen:
                seen.add(tgt_key)
                result.append(link.target)
            elif tgt_key == key and src_key not in seen:
                seen.add(src_key)
                result.append(link.source)
        return result

    def _sorted_nodes(self) -> list[CorrelationNode]:
        return sorted(self._nodes.values(), key=lambda n: (n.kind.value, n.normalized))

    def _sorted_links(self) -> list[CorrelationLink]:
        return sorted(
            self._links,
            key=lambda r: (
                r.source.kind.value,
                r.source.normalized,
                r.target.kind.value,
                r.target.normalized,
                r.kind,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """D3 node-link format: {nodes: [...], links: [...]}."""
        nodes = self._sorted_nodes()
        index: dict[tuple[CorrelationKind, str], int] = {
            (n.kind, n.normalized): i for i, n in enumerate(nodes)
        }
        node_list = [
            {
                "id": i,
                "type": n.kind.value,
                "value": n.value,
                "confidence": n.confidence,
                "observations": sorted(n.observations),
            }
            for i, n in enumerate(nodes)
        ]
        links = []
        for link in self._sorted_links():
            src = index.get((link.source.kind, link.source.normalized))
            tgt = index.get((link.target.kind, link.target.normalized))
            if src is not None and tgt is not None:
                links.append(
                    {
                        "source": src,
                        "target": tgt,
                        "kind": link.kind,
                        "observation": link.observation,
                    }
                )
        return {"nodes": node_list, "links": links}

    def to_json(self) -> str:
        """Serialise to JSON string (D3 node-link)."""
        return json.dumps(self.to_dict(), indent=2)

    def to_graphml(self) -> str:
        """Produce a valid GraphML document (Gephi / yEd / Maltego)."""
        ns = "http://graphml.graphdrawing.org/graphml"
        xsi = "http://www.w3.org/2001/XMLSchema-instance"
        root = ET.Element(
            "graphml",
            attrib={
                "xmlns": ns,
                "xmlns:xsi": xsi,
                "xsi:schemaLocation": (
                    "http://graphml.graphdrawing.org/graphml "
                    "http://graphml.graphdrawing.org/graphml/1.0rc/graphml.xsd"
                ),
            },
        )

        def _key(key_id: str, for_: str, name: str, kind: str) -> None:
            ET.SubElement(
                root,
                "key",
                attrib={"id": key_id, "for": for_, "attr.name": name, "attr.type": kind},
            )

        _key("d_type", "node", "type", "string")
        _key("d_value", "node", "value", "string")
        _key("d_confidence", "node", "confidence", "double")
        _key("d_observations", "node", "observations", "string")
        _key("d_kind", "edge", "kind", "string")
        _key("d_observation", "edge", "observation", "string")

        graph_el = ET.SubElement(root, "graph", attrib={"id": "G", "edgedefault": "directed"})

        nodes = self._sorted_nodes()
        index: dict[tuple[CorrelationKind, str], int] = {
            (n.kind, n.normalized): i for i, n in enumerate(nodes)
        }

        def _data(parent: ET.Element, key_id: str, text: str) -> None:
            el = ET.SubElement(parent, "data", attrib={"key": key_id})
            el.text = text

        for i, n in enumerate(nodes):
            node_el = ET.SubElement(graph_el, "node", attrib={"id": f"n{i}"})
            _data(node_el, "d_type", n.kind.value)
            _data(node_el, "d_value", n.value)
            _data(node_el, "d_confidence", str(round(n.confidence, 4)))
            _data(node_el, "d_observations", ",".join(sorted(n.observations)))

        for edge_idx, link in enumerate(self._sorted_links()):
            src = index.get((link.source.kind, link.source.normalized))
            tgt = index.get((link.target.kind, link.target.normalized))
            if src is None or tgt is None:
                continue
            edge_el = ET.SubElement(
                graph_el,
                "edge",
                attrib={"id": f"e{edge_idx}", "source": f"n{src}", "target": f"n{tgt}"},
            )
            _data(edge_el, "d_kind", link.kind)
            _data(edge_el, "d_observation", link.observation)

        ET.indent(root, space="  ")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

    def to_mermaid(self) -> str:
        """Produce a Mermaid graph TD diagram with sanitized node IDs."""
        nodes = self._sorted_nodes()
        node_id: dict[tuple[CorrelationKind, str], str] = {
            (n.kind, n.normalized): f"n{i}" for i, n in enumerate(nodes)
        }

        lines = ["graph TD"]

        for i, n in enumerate(nodes):
            nid = f"n{i}"
            open_br = _MERMAID_OPEN.get(n.kind, "[")
            close_br = _MERMAID_CLOSE.get(n.kind, "]")
            label = _safe_mermaid_label(n.value)
            lines.append(f'    {nid}{open_br}"{label}"{close_br}')

        for link in self._sorted_links():
            src_id = node_id.get((link.source.kind, link.source.normalized))
            tgt_id = node_id.get((link.target.kind, link.target.normalized))
            if src_id is None or tgt_id is None:
                continue
            safe_kind = _MERMAID_UNSAFE_RE.sub("", link.kind)
            lines.append(f'    {src_id} -->|"{safe_kind}"| {tgt_id}')

        return "\n".join(lines)

    def summary(self) -> str:
        """One-paragraph human-readable summary for CLI/REPL display."""
        by_kind: dict[str, int] = {}
        for n in self._nodes.values():
            by_kind[n.kind.value] = by_kind.get(n.kind.value, 0) + 1
        counts = ", ".join(f"{v} {k}" for k, v in sorted(by_kind.items()) if v)
        total_n = len(self._nodes)
        total_l = len(self._links)
        return f"Graph: {total_n} nodes ({counts}), {total_l} links."