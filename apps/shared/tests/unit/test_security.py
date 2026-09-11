"""Tests for security hardening policy (T072, FR-029)."""

import pytest

from security import (
    DnsRebindingGuard,
    EgressPolicy,
    ResourceLimits,
    SecurityBlocked,
    is_public_ip,
    parse_host,
    sanitize_archive_path,
    ssrf_guard,
)


class TestSsrfGuard:
    def test_blocks_private_ip(self):
        with pytest.raises(SecurityBlocked):
            ssrf_guard("http://internal.example/x", "10.0.0.5")

    def test_blocks_metadata_ip(self):
        with pytest.raises(SecurityBlocked):
            ssrf_guard("http://169.254.169.254/latest/meta-data", "169.254.169.254")

    def test_blocks_loopback(self):
        with pytest.raises(SecurityBlocked):
            ssrf_guard("http://127.0.0.1/api", "127.0.0.1")

    def test_blocks_non_egress_port(self):
        with pytest.raises(SecurityBlocked):
            ssrf_guard("http://example.com:22/x", "93.184.216.34")

    def test_blocks_disallowed_scheme(self):
        egress = EgressPolicy(schemes={"https"})
        with pytest.raises(SecurityBlocked):
            ssrf_guard("http://example.com/x", "93.184.216.34", egress=egress)

    def test_allows_public_https(self):
        ssrf_guard("https://example.com:443/x", "93.184.216.34")  # no raise

    def test_blocks_unresolvable_host(self):
        with pytest.raises(SecurityBlocked):
            ssrf_guard("http://example.com/x", "not-an-ip")

    def test_allowlist_routes(self):
        egress = EgressPolicy(allow_cidrs=["93.184.216.0/24"])
        ssrf_guard("https://example.com/x", "93.184.216.34", egress=egress)
        with pytest.raises(SecurityBlocked):
            ssrf_guard("https://example.com/x", "203.0.113.9", egress=egress)


class TestDnsRebindingGuard:
    def test_detects_rebinding(self):
        g = DnsRebindingGuard()
        g.pin("example.com", "93.184.216.34")
        g.check("example.com", "93.184.216.34")  # stable resolve: ok
        with pytest.raises(SecurityBlocked):
            g.check("example.com", "127.0.0.1")  # second answer differs

    def test_case_insensitive_host(self):
        g = DnsRebindingGuard()
        g.pin("Example.COM", "93.184.216.34")
        g.check("example.com", "93.184.216.34")


class TestIsPublicIp:
    def test_accepts_public(self):
        assert is_public_ip("93.184.216.34")
        assert is_public_ip("2606:2800:220:1::248")

    def test_rejects_private_and_special(self):
        assert not is_public_ip("192.168.1.1")
        assert not is_public_ip("10.0.0.1")
        assert not is_public_ip("169.254.1.1")
        assert not is_public_ip("::1")
        assert not is_public_ip("fd00::1")
        assert not is_public_ip("bogus")


class TestParseHost:
    def test_plain_host(self):
        assert parse_host("example.com") == ("example.com", "80")

    def test_host_port(self):
        assert parse_host("example.com:443") == ("example.com", "443")

    def test_v6(self):
        assert parse_host("[::1]:8080") == ("::1", "8080")

    def test_malformed(self):
        assert parse_host(":notaport") is None


class TestResourceLimits:
    def test_byte_and_cpu_limits(self):
        L = ResourceLimits(max_response_bytes=1024, max_timeout_ms=500, max_archive_depth=3)
        with pytest.raises(SecurityBlocked):
            L.check_bytes(2048)
        with pytest.raises(SecurityBlocked):
            L.check_timeout(600)
        with pytest.raises(SecurityBlocked):
            L.check_archive_depth(4)
        L.check_bytes(1024)  # exact boundary allowed

    def test_archive_traversal_blocked(self):
        L = ResourceLimits()
        assert sanitize_archive_path("dir/file.txt", L) == "dir/file.txt"
        with pytest.raises(SecurityBlocked):
            sanitize_archive_path("../etc/passwd", L)
        with pytest.raises(SecurityBlocked):
            sanitize_archive_path("..\\..\\win.ini", L)
        with pytest.raises(SecurityBlocked):
            sanitize_archive_path("", L)

    def test_to_dict_matches_policy(self):
        d = EgressPolicy().to_dict()
        assert 443 in d["ports"]
        assert "https" in d["schemes"]