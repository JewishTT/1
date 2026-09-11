"""Unit tests for donor/target.py (SpiderFoot port, spec 004)."""

import pytest

from donor.target import Target, TargetType, classify, normalize


def test_classify_ipv4() -> None:
    assert classify("93.184.216.34") == TargetType.IP_ADDRESS


def test_classify_ipv6() -> None:
    assert classify("2606:2800:220:1:248:1893:25c8:1946") == TargetType.IPV6_ADDRESS


def test_classify_domain() -> None:
    assert classify("example.com") == TargetType.DOMAIN


def test_classify_email() -> None:
    assert classify("admin@example.com") == TargetType.EMAIL_ADDRESS


def test_classify_url() -> None:
    assert classify("https://example.com/page") == TargetType.URL


def test_classify_unknown_defaults_to_username() -> None:
    assert classify("some_handle") == TargetType.USERNAME
    assert classify("") == TargetType.UNKNOWN


def test_normalize_ip_canonical() -> None:
    assert normalize("93.184.216.34", TargetType.IP_ADDRESS) == "93.184.216.34"
    assert normalize("2001:0DB8:0:0:0:0:0:1", TargetType.IPV6_ADDRESS) == "2001:db8::1"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("93.184.216.34/24", "93.184.216.0/24"),
        ("10.0.0.5/8", "10.0.0.0/8"),
    ],
)
def test_normalize_netblock(raw: str, expected: str) -> None:
    assert normalize(raw, TargetType.NETBLOCK) == expected


def test_normalize_domain_trims_trailing_dot_and_case() -> None:
    assert normalize("Example.COM.", TargetType.DOMAIN) == "example.com"


def test_normalize_email_lowercases() -> None:
    assert normalize("Admin@Example.COM", TargetType.EMAIL_ADDRESS) == "admin@example.com"


def test_normalize_url_keeps_host_only() -> None:
    url = "https://WWW.Example.com:443/path?q=1"
    assert normalize(url, TargetType.URL) == "www.example.com:443"


def test_target_requires_valid_type() -> None:
    with pytest.raises(ValueError):
        Target("example.com", "BOGUS")


def test_target_aliases_and_names() -> None:
    t = Target("example.com", TargetType.DOMAIN)
    t.set_alias("www.example.com", TargetType.DOMAIN)
    assert set(t.names()) == {"example.com", "www.example.com"}


def test_target_matches_child_domain() -> None:
    t = Target("example.com", TargetType.DOMAIN)
    assert t.matches("sub.example.com")
    assert not t.matches("otherexample.com")


def test_target_matches_parent_domain_only_when_allowed() -> None:
    t = Target("sub.example.com", TargetType.DOMAIN)
    assert not t.matches("example.com")
    assert t.matches("example.com", include_parents=True)


def test_target_matches_ip_in_subnet() -> None:
    t = Target("10.0.0.0/8", TargetType.NETBLOCK)
    assert t.matches("10.1.2.3")
    assert not t.matches("11.0.0.1")


def test_target_value_rejected_when_blank() -> None:
    with pytest.raises(ValueError):
        Target("   ", TargetType.DOMAIN)


def test_target_resolve_returns_canonical() -> None:
    assert Target("ExaMPLE.Com.", TargetType.DOMAIN).resolve() == "example.com"