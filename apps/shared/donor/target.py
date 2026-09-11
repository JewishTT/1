"""Harvest-target value class: classify + canonical normalise (spec 004).

Attribution / license
=====================
Source: SpiderFoot (MIT, Copyright 2022 Steve Micallef) - ``spiderfoot/target.py``
  class ``SpiderFootTarget`` + ``TargetAlias``.
License: MIT (logic layer only).

Adaptation notes
================
- The donor depends on ``netaddr``; here all IP/subnet handling is rewritten to
  stdlib ``ipaddress`` (``getAddresses``/``matches`` subnetwork checks).
- Logger calls removed; class renamed to COGNITIVE ``Target``; type constants
  live on ``TargetType`` and classify()/normalize() are added so raw harvest
  input can be turned into a canonical target without external dicts.
- Keep the donor's "tight relation" semantics: names/aliases/subnet containment.
"""

from __future__ import annotations

import ipaddress
from typing import TypedDict

__all__ = [
    "Target",
    "TargetAlias",
    "TargetType",
    "classify",
    "normalize",
]


class TargetAlias(TypedDict):
    """One alias attached to a target: its data type + value."""

    type: str
    value: str


class TargetType:
    """Target data types accepted by the harvest layer."""

    DOMAIN = "DOMAIN"
    IP_ADDRESS = "IP_ADDRESS"
    IPV6_ADDRESS = "IPV6_ADDRESS"
    NETBLOCK = "NETBLOCK"
    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    USERNAME = "USERNAME"
    URL = "URL"
    UNKNOWN = "UNKNOWN"


def _strip_scheme(value: str) -> str:
    """Peel ``scheme://`` and a trailing path/query off a URL-like input."""
    s = value.strip()
    if "://" in s:
        s = s.split("://", 1)[1].split("/", 1)[0]
    else:
        s = s.split("://")[0].split("/", 1)[0]
    return s


def classify(value: str) -> str:
    """Infer the target type of a raw harvest value via lightweight rules."""
    raw = (value or "").strip()
    if not raw:
        return TargetType.UNKNOWN
    if "@" in raw:
        return TargetType.EMAIL_ADDRESS
    if "://" in raw:
        return TargetType.URL
    try:
        ipaddress.ip_address(raw)
        if ":" in raw:
            return TargetType.IPV6_ADDRESS
        return TargetType.IP_ADDRESS
    except ValueError:
        pass
    try:
        ipaddress.ip_network(raw, strict=False)
        return TargetType.NETBLOCK
    except ValueError:
        pass
    if "/" in raw:
        return TargetType.URL
    if raw.count(".") >= 1:
        return TargetType.DOMAIN
    return TargetType.USERNAME


def normalize(value: str, type_name: str) -> str:
    """Canonical form of a value for a given target type.

    - IP/IPv6 -> stdlib ``ipaddress`` canonical string
    - NETBLOCK -> collapsed network string (``ip_network(..., strict=False)``)
    - DOMAIN/URL -> lower-cased host, trailing dot stripped
    - EMAIL -> lower-cased
    - USERNAME -> unchanged
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    if type_name in (TargetType.IP_ADDRESS, TargetType.IPV6_ADDRESS):
        try:
            return str(ipaddress.ip_address(raw))
        except ValueError:
            return raw.lower()
    if type_name == TargetType.NETBLOCK:
        try:
            return str(ipaddress.ip_network(raw, strict=False))
        except ValueError:
            return raw.lower()
    if type_name == TargetType.URL:
        return _strip_scheme(raw).rstrip(".").lower()
    if type_name == TargetType.DOMAIN:
        return raw.rstrip(".").lower()
    if type_name == TargetType.EMAIL_ADDRESS:
        return raw.lower()
    return raw


class Target:
    """A harvest/resolution target with aliases (SpiderFoot port).

    Attributes
    ----------
    type_name : str
        One of the :class:`TargetType` constants.
    value : str
        The raw target value.
    aliases : list[TargetAlias]
        Equivalent types/values other sources contributed.
    """

    _valid_types = {
        TargetType.DOMAIN,
        TargetType.IP_ADDRESS,
        TargetType.IPV6_ADDRESS,
        TargetType.NETBLOCK,
        TargetType.EMAIL_ADDRESS,
        TargetType.USERNAME,
        TargetType.URL,
    }

    def __init__(self, value: str, type_name: str) -> None:
        if not isinstance(value, str):
            raise TypeError(f"value is {type(value)}; expected str()")
        value = value.strip()
        if not value:
            raise ValueError("value is blank")
        if type_name not in self._valid_types:
            expected = sorted(self._valid_types)
            raise ValueError(f"type_name is {type_name}; expected one of {expected}")
        self.value = value
        self.type_name = type_name
        self.aliases: list[TargetAlias] = []

    def set_alias(self, value: str, type_name: str) -> None:
        """Specify other hostnames, IPs, etc. that are aliases for this target."""
        if not value or not isinstance(value, str):
            return
        if not type_name or not isinstance(type_name, str):
            return
        alias: TargetAlias = {"type": type_name, "value": value.lower()}
        if alias in self.aliases:
            return
        self.aliases.append(alias)

    def _equivalents(self, type_name: str) -> list[str]:
        return [a["value"].lower() for a in self.aliases if a["type"] == type_name]

    def names(self) -> list[str]:
        """All domains/hostnames associated with the target."""
        out = list(self._equivalents(TargetType.DOMAIN))
        if self.type_name in (TargetType.DOMAIN, TargetType.EMAIL_ADDRESS):
            v = self.value.lower()
            if v not in out:
                out.append(v)
        return out

    def addresses(self) -> list[str]:
        """All IP subnet or IP address aliases associated with the target."""
        out = list(self._equivalents(TargetType.IP_ADDRESS))
        if self.type_name == TargetType.IP_ADDRESS:
            out.append(self.value)
        out.extend(self._equivalents(TargetType.IPV6_ADDRESS))
        if self.type_name == TargetType.IPV6_ADDRESS:
            out.append(self.value)
        return out

    def matches(
        self,
        value: str,
        include_parents: bool = False,
        include_children: bool = True,
    ) -> bool:
        """Whether ``value`` is "tightly" related to this target.

        IP values match when they are the target/alias or fall inside the
        target's subnetwork; names match when equal to the target/alias or a
        parent/child domain per ``include_parents``/``include_children``.
        """
        if not value:
            return False
        if self.type_name in (TargetType.USERNAME, TargetType.EMAIL_ADDRESS):
            return True
        try:
            ipaddress.ip_address(value)
        except ValueError:
            ip_found = False
        else:
            ip_found = True
        if ip_found:
            if value in self.addresses():
                return True
            if self.type_name in (
                TargetType.IP_ADDRESS,
                TargetType.IPV6_ADDRESS,
                TargetType.NETBLOCK,
            ):
                try:
                    return (
                        ipaddress.ip_address(value)
                        in ipaddress.ip_network(self.value, strict=False)
                    )
                except ValueError:
                    return False
            return False
        for name in self.names():
            if value == name:
                return True
            if include_parents and name.endswith("." + value):
                return True
            if include_children and value.endswith("." + name):
                return True
        return False

    def resolve(self) -> str:
        """Canonical value of this target (normalised)."""
        return normalize(self.value, self.type_name)