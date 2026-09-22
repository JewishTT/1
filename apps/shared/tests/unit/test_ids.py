"""Globally-unique IDs + multi-region partition (T119)."""

from __future__ import annotations

from ids import global_id, host_partition, normalize_region, partition_of, region_group, ulid


def test_ulid_shape() -> None:
    value = ulid()
    assert len(value) == 26
    assert value.isalnum()
    assert ulid() != ulid()


def test_global_id_prefixed_and_regional() -> None:
    obs = global_id("obs", "eu-west")
    assert obs.startswith("obs.eu-west.")
    frontier = global_id("frontier", "global")
    assert frontier.startswith("frontier.global.")
    assert obs != frontier


def test_global_id_unique_across_calls() -> None:
    ids = {global_id("obs", "us-east") for _ in range(100)}
    assert len(ids) == 100


def test_normalize_region() -> None:
    assert normalize_region("EU-WEST_1") == "eu-west-1"
    assert normalize_region("  apac ") == "apac"
    assert normalize_region("") == "global"


def test_partition_of_dotted_suffix() -> None:
    region_map = {".ru": "emea", ".jp": "apac"}
    assert partition_of("https://news.ru/x", region_map=region_map) == "emea"
    assert partition_of("https://foo.jp/", region_map=region_map) == "apac"
    assert partition_of("https://other.org/", region_map=region_map) == "global"


def test_partition_of_bare_suffix_subdomain() -> None:
    region_map = {"example.com": "amer"}
    assert partition_of("https://x.example.com/p", region_map=region_map) == "amer"
    assert partition_of("https://example.com/p", region_map=region_map) == "amer"


def test_host_partition_payload() -> None:
    info = host_partition("https://a.ru/x", region_map={".ru": "emea"})
    assert info == {"host": "a.ru", "region": "emea", "partition": "emea"}


def test_region_group_stability() -> None:
    a = region_group(["emea", "emea"], shards=2)
    b = region_group(["emea", "emea"], shards=2)
    assert a == b
    assert region_group([], shards=2) == "global"
    assert region_group(["emea"], shards=1) == "global"