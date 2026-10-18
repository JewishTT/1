"""Access mode is a declared property of a collection surface (spec 030 FR-094).

The specification is unambiguous: no acquisition path may circumvent authentication, CAPTCHAs,
paywalls or other access controls, and no donor may hold privileges that bypass them. A rule
nobody can violate is a rule nobody can check, so the access mode lives on the surface itself and
``bypass_access_controls`` is refused at construction.

This is the negative capability test: it asserts what the platform cannot do, rather than
asserting what it does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "AccessMode",
    "BypassPrivilegeRefused",
    "AcquisitionSurface",
    "permitted_operations",
]


class BypassPrivilegeRefused(ValueError):
    """An acquisition surface declared the power to defeat an access control.

    Raised at construction. A donor that needs it cannot have it: the platform's position is
    that acquiring through permitted public or authorized interfaces is the whole job, and a
    module that can defeat a paywall will eventually be pointed at one.
    """


class AccessMode(StrEnum):
    """How a surface is allowed to reach its source."""

    PUBLIC = "public"
    """No control in the way. Ordinary public web."""

    REGISTERED = "registered"
    """The platform holds the operator's own account. Nothing about the source is circumvented."""

    AUTHORIZED = "authorized"
    """The source's owner granted access for a stated purpose under stated terms."""

    #: Declaring this is refused. It exists so the refusal has something to name.
    BYPASS = "bypass"


#: Access controls the platform will not defeat, whatever a surface declares it needs.
PROTECTED_CONTROLS = frozenset(
    {"authentication", "captcha", "paywall", "access_control", "rate_limit", "robots_exclusion"}
)


@dataclass(frozen=True, slots=True)
class AcquisitionSurface:
    """One way the platform can reach a source.

    ``bypass_access_controls`` is not a capability that can be granted. It is a declaration that
    is refused, which is why it is a constructor argument rather than a flag.
    """

    surface_id: str
    runtime_ref: str
    access_mode: AccessMode
    operations: tuple[str, ...]
    requires_credentials: bool = False
    declared_controls_defeated: tuple[str, ...] = ()
    notes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.surface_id).strip() or not str(self.runtime_ref).strip():
            raise ValueError("an acquisition surface must name itself and its runtime")
        if not self.operations:
            raise ValueError(
                f"surface {self.surface_id!r} declares no operations; an unused surface is not "
                "registered capability but an unexamined one"
            )

        # Checked before the generic bypass refusal, so the message names the control the
        # caller actually declared. A refusal that does not name the thing refused gets retried
        # with the thing renamed.
        defeated = {c.strip().lower() for c in self.declared_controls_defeated}
        protected = sorted(defeated & PROTECTED_CONTROLS)
        if protected:
            raise BypassPrivilegeRefused(
                f"surface {self.surface_id!r} (runtime {self.runtime_ref!r}) declared it "
                f"defeats {protected}. If the source is genuinely authorized, declare "
                "AccessMode.AUTHORIZED instead and say so in notes; a declared bypass is not "
                "a licence. This platform does not defeat authentication, CAPTCHAs, paywalls "
                "or other access controls (FR-094)"
            )

        if self.access_mode is AccessMode.BYPASS:
            raise BypassPrivilegeRefused(
                f"surface {self.surface_id!r} declared AccessMode.BYPASS, which is not a mode "
                "this platform operates in. Use PUBLIC, REGISTERED or AUTHORIZED (FR-094)"
            )

        if self.bypass_requested:
            raise BypassPrivilegeRefused(
                f"surface {self.surface_id!r} (runtime {self.runtime_ref!r}) declared the "
                f"ability to defeat access controls {sorted(defeated)}. Acquisition works "
                "through permitted public or authorized interfaces only (FR-094)"
            )
        if self.access_mode is AccessMode.PUBLIC and self.requires_credentials:
            raise ValueError(
                f"surface {self.surface_id!r} is PUBLIC yet carries credentials. A public surface "
                "with a secret is a private surface mislabelled, and it would bypass the "
                "authorization decision made for it"
            )

    @property
    def bypass_requested(self) -> bool:
        return self.access_mode is AccessMode.BYPASS or bool(self.declared_controls_defeated)

    @property
    def authorized(self) -> bool:
        return self.access_mode in (AccessMode.REGISTERED, AccessMode.AUTHORIZED)

    def may(self, operation: str) -> bool:
        """Whether this surface may perform ``operation``.

        A surface may not do what it did not declare. An undeclared operation is not a harmless
        default; it is an unexamined path to the source.
        """
        return operation in self.operations


def permitted_operations(
    surfaces: tuple[AcquisitionSurface, ...], *, operation: str
) -> tuple[str, ...]:
    """Which surfaces may perform ``operation``, for one audit line."""
    return tuple(sorted(s.surface_id for s in surfaces if s.may(operation)))