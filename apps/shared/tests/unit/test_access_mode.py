"""The platform does not defeat access controls (spec 030 FR-094, T165).

A negative capability test. It asserts what the platform cannot acquire, rather than what it
can, because the assertion that matters here is about absence.
"""

from __future__ import annotations

import pytest

from domain.access_mode import (
    AccessMode,
    AcquisitionSurface,
    BypassPrivilegeRefused,
    permitted_operations,
)

pytestmark = pytest.mark.unit


def _surface(**kw) -> AcquisitionSurface:
    base = dict(
        surface_id="searxng",
        runtime_ref="searxng",
        access_mode=AccessMode.PUBLIC,
        operations=("search",),
    )
    base.update(kw)
    return AcquisitionSurface(**base)


class TestOrdinarySurfacesStillWork:
    def test_a_public_surface_registers(self):
        s = _surface()
        assert s.access_mode is AccessMode.PUBLIC
        assert s.authorized is False

    def test_an_authorized_surface_is_authorized(self):
        assert _surface(access_mode=AccessMode.AUTHORIZED).authorized is True

    def test_a_registered_surface_is_authorized(self):
        assert _surface(access_mode=AccessMode.REGISTERED).authorized is True

    def test_it_may_do_what_it_declared(self):
        assert _surface().may("search") is True

    def test_it_may_not_do_what_it_did_not_declare(self):
        """An undeclared operation is an unexamined path to the source."""
        assert _surface().may("submit_form") is False

    def test_the_audit_line_lists_only_permitted_surfaces(self):
        a = _surface(surface_id="a", operations=("search", "fetch"))
        b = _surface(surface_id="b", operations=("search",))
        assert permitted_operations((a, b), operation="fetch") == ("a",)
        assert permitted_operations((a, b), operation="search") == ("a", "b")


class TestBypassIsRefused:
    def test_access_mode_bypass_is_refused(self):
        with pytest.raises(BypassPrivilegeRefused) as e:
            _surface(access_mode=AccessMode.BYPASS)
        assert "BYPASS" in str(e.value)

    @pytest.mark.parametrize(
        "control", ["authentication", "captcha", "paywall", "access_control", "rate_limit"]
    )
    def test_every_protected_control_is_refused(self, control):
        with pytest.raises(BypassPrivilegeRefused) as e:
            _surface(declared_controls_defeated=(control,))
        assert control in str(e.value)

    def test_the_refusal_names_the_surface_and_runtime(self):
        with pytest.raises(BypassPrivilegeRefused) as e:
            _surface(surface_id="rogue-crawler", runtime_ref="crawler-x",
                     declared_controls_defeated=("paywall",))
        assert "rogue-crawler" in str(e.value)
        assert "crawler-x" in str(e.value)

    def test_it_points_at_the_authorized_route_instead(self):
        """A refusal that offers no way forward gets worked around."""
        with pytest.raises(BypassPrivilegeRefused) as e:
            _surface(declared_controls_defeated=("captcha",))
        assert "AUTHORIZED" in str(e.value)


class TestMislabelledSurfacesAreRefused:
    def test_a_public_surface_carrying_credentials_is_refused(self):
        """A private surface labelled public is how an authorization decision gets skipped."""
        with pytest.raises(ValueError) as e:
            _surface(access_mode=AccessMode.PUBLIC, requires_credentials=True)
        assert "credentials" in str(e.value)

    def test_an_authorized_surface_with_credentials_is_fine(self):
        s = _surface(access_mode=AccessMode.AUTHORIZED, requires_credentials=True)
        assert s.requires_credentials is True


class TestSurfacesMustDeclareThemselves:
    def test_an_unnamed_surface_is_refused(self):
        with pytest.raises(ValueError):
            _surface(surface_id="  ")

    def test_a_surface_with_no_operations_is_refused(self):
        with pytest.raises(ValueError) as e:
            _surface(operations=())
        assert "unexamined" in str(e.value)

    def test_a_fully_declared_surface_survives_every_check(self):
        """CD-7: the honest surface is accepted alongside the refusals."""
        s = AcquisitionSurface(
            surface_id="wayback-cdx",
            runtime_ref="http",
            access_mode=AccessMode.PUBLIC,
            operations=("query_cdx", "fetch_warc_range"),
            notes={"detection_power": "indexed-urls-only"},
        )
        assert s.may("fetch_warc_range") is True
        assert s.bypass_requested is False