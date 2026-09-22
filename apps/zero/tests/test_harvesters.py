"""Unit tests for deterministic harvest modules (spec/010 §0.2–§0.6).

All network access is routed through ``DictTransport`` fakes — nothing here
ever opens a socket.
"""

from __future__ import annotations

import dataclasses

import pytest

from zero.harvesters.contracts import CommandSpec
from zero.harvesters.domain import (
    EmailPermutationHarvester,
    SubdomainBruteHarvester,
    email_permutations,
    role_addresses,
)
from zero.harvesters.git import CommitEmailHarvester, git_log_email
from zero.harvesters.image import QrExifHarvester, read_exif_jpeg, read_gps, read_qr
from zero.harvesters.phone import PhoneDorkHarvester, WhatsAppPresenceHarvester
from zero.harvesters.registry import HarvesterContext, HarvesterRegistry
from zero.harvesters.transport import DictTransport
from zero.harvesters.url import EmbeddedContactsHarvester, SocialLinkHarvester
from zero.harvesters.username import (
    MaigretWorkerAdapter,
    SherlockWorkerAdapter,
    SocialProfilePatternHarvester,
)
from zero.type_detector import InputType, TypeDetector

# ---------------------------------------------------------------------------
# email-permutation engine
# ---------------------------------------------------------------------------


class TestEmailPermutation:
    def test_generates_unique_deterministic_candidates(self) -> None:
        emails = email_permutations("John", "Smith", "example.com")
        assert emails, "engine must return candidates"
        assert len({e for e, _ in emails}) == len(emails)
        assert email_permutations("John", "Smith", "example.com") == emails
        assert all(e.endswith("@example.com") for e, _ in emails)
        assert all(e == e.lower() for e, _ in emails)

    def test_requires_all_three_components(self) -> None:
        assert email_permutations("", "Smith", "example.com") == []
        assert email_permutations("John", "", "example.com") == []
        assert email_permutations("John", "Smith", "") == []

    def test_role_addresses_are_plural(self) -> None:
        addresses = role_addresses("acme.com")
        assert len(addresses) >= 25
        assert ("admin@acme.com", "role-address") in addresses
        assert ("info@acme.com", "role-address") in addresses


# ---------------------------------------------------------------------------
# domain harvesters
# ---------------------------------------------------------------------------


class TestEmailPermutationHarvester:
    def test_domain_seed_emits_role_addresses(self) -> None:
        detector = TypeDetector()
        seed = detector.detect("acme.com")
        ctx = HarvesterContext(seed=seed)
        result = EmailPermutationHarvester().run(seed, ctx)
        assert len(result.candidates) >= 25
        assert all(c.kind == "email" for c in result.candidates)

    def test_name_seed_emits_personal_permutations(self) -> None:
        base = TypeDetector().detect("John Smith")
        seed = dataclasses.replace(base, metadata={"domain": "example.com"})
        result = EmailPermutationHarvester().run(seed, HarvesterContext(seed=seed))
        emails = [c.value for c in result.candidates]
        assert len(emails) >= 10
        assert "john.smith@example.com" in emails


class TestSubdomainBruteHarvester:
    def test_verified_subs_rank_higher(self) -> None:
        seed = TypeDetector().detect("example.com")
        transport = DictTransport(existing={"http://www.example.com"})
        ctx = HarvesterContext(seed=seed, transport=transport)
        result = SubdomainBruteHarvester().run(seed, ctx)
        by_value = {c.value: c for c in result.candidates}
        assert by_value["www.example.com"].confidence == pytest.approx(0.85)
        assert by_value["api.example.com"].confidence == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# url harvesters
# ---------------------------------------------------------------------------


class TestEmbeddedContactsHarvester:
    HTML = """
    <html><head><title>Team</title></head><body>
      <p>Reach us at alice.smith@corp.co or alice.smith@corp.co</p>
      <p>Call +12025550199.</p>
      <a href="https://github.com/octocat">github</a>
      <a href="https://blog.example.org/post">blog</a>
    </body></html>
    """

    def test_extracts_emails_phones_domains(self) -> None:
        seed = TypeDetector().detect("https://corp.co/team")
        transport = DictTransport(bodies={"https://corp.co/team": self.HTML})
        ctx = HarvesterContext(seed=seed, transport=transport)
        result = EmbeddedContactsHarvester().run(seed, ctx)
        kinds = [c.kind for c in result.candidates]
        assert "email" in kinds and "phone" in kinds and "domain" in kinds
        emails = [c.value for c in result.candidates if c.kind == "email"]
        assert emails.count("alice.smith@corp.co") == 1  # deduplicated
        phones = [c.value for c in result.candidates if c.kind == "phone"]
        assert "12025550199" in phones
        assert "blog.example.org" in [c.value for c in result.candidates if c.kind == "domain"]

    def test_offline_transport_returns_note(self) -> None:
        seed = TypeDetector().detect("https://example.com/x")
        ctx = HarvesterContext(seed=seed)
        result = EmbeddedContactsHarvester().run(seed, ctx)
        assert result.candidates == ()
        assert any("empty" in note for note in result.notes)


class TestSocialLinkHarvester:
    def test_extracts_social_profiles(self) -> None:
        seed = TypeDetector().detect("https://example.com/about")
        html = (
            '<a href="https://github.com/octocat">g</a>'
            '<a href="https://twitter.com/octocat">t</a>'
            '<a href="https://example.net/x">no</a>'
        )
        transport = DictTransport(bodies={"https://example.com/about": html})
        ctx = HarvesterContext(seed=seed, transport=transport)
        result = SocialLinkHarvester().run(seed, ctx)
        values = {c.value for c in result.candidates}
        assert "https://github.com/octocat" in values
        assert len(result.candidates) == 2


# ---------------------------------------------------------------------------
# git harvester
# ---------------------------------------------------------------------------


class TestCommitEmailHarvester:
    LOG = """commit 0123
Author: John Smith <john.smith@corp.co>
AuthorDate: Mon Jan 1 12:00:00 2026
Committer: jsmith <jsmith@corp.co>
Signed-off-by: Gina <gina@corp.co>
    message

commit 0456
Author: John Smith <john.smith@corp.co>
"""

    def test_parses_commit_identities(self) -> None:
        found = git_log_email(self.LOG)
        names = [row[0] for row in found]
        assert "John Smith" in names
        emails = {row[1] for row in found}
        assert "jsmith@corp.co" in emails

    def test_harvester_dedups(self) -> None:
        seed = TypeDetector().detect("jsmith")
        seed_with_log = dataclasses.replace(seed, metadata={"git_log": self.LOG})
        ctx = HarvesterContext(seed=seed_with_log, transport=DictTransport())
        result = CommitEmailHarvester().run(seed_with_log, ctx)
        emails = [c.value for c in result.candidates]
        assert len(emails) == len(set(emails))
        assert "john.smith@corp.co" in emails


# ---------------------------------------------------------------------------
# image harvester
# ---------------------------------------------------------------------------


def _rational(value: float) -> bytes:
    import struct

    parts = [(int(value), 1), (0, 1), (0, 1)]
    return b"".join(struct.pack("<II", num, den) for num, den in parts)


def _build_jpeg_with_exif(
    *, make: str, model: str, gps: tuple[float, float] | None = None
) -> bytes:
    """Build a minimal JPEG with an EXIF APP1 segment (LE TIFF, GPS optional)."""
    import struct

    def ascii_field(tag: int, text: str) -> dict:
        payload = text.encode("latin-1") + b"\x00"
        return {"tag": tag, "type": 2, "count": len(payload), "payload": payload}

    entries = [ascii_field(0x010F, make), ascii_field(0x0110, model)]
    ifd0_count = len(entries) + (1 if gps else 0)

    offsets_end = 8 + 2 + 12 * ifd0_count + 4
    ascii_area = offsets_end

    gps_ifd_offset = ascii_area + sum(len(e["payload"]) for e in entries)
    gps_data_offset = gps_ifd_offset + 2 + 12 * 4 + 4

    tiff = bytearray()
    tiff += b"II" + struct.pack("<H", 42) + struct.pack("<I", 8)
    tiff += struct.pack("<H", ifd0_count)
    for index, entry in enumerate(entries):
        value_offset = ascii_area + sum(len(e["payload"]) for e in entries[:index])
        wide = len(entry["payload"]) > 4
        value_field = struct.pack("<I", value_offset) if wide else entry["payload"]
        tiff += struct.pack("<HHI", entry["tag"], entry["type"], entry["count"])
        tiff += value_field.ljust(4, b"\x00")
    if gps is not None:
        tiff += struct.pack("<HHI", 0x8825, 4, 1) + struct.pack("<I", gps_ifd_offset)
    tiff += struct.pack("<I", 0)
    for entry in entries:
        tiff += entry["payload"]

    if gps is not None:
        lat_blob = _rational(gps[0])
        lon_blob = _rational(gps[1])
        tiff += struct.pack("<H", 4)
        tiff += struct.pack("<HH I", 1, 2, 2) + b"N\x00\x00\x00"
        tiff += struct.pack("<HHII", 2, 5, 3, gps_data_offset)
        tiff += struct.pack("<HH I", 3, 2, 2) + b"E\x00\x00\x00"
        tiff += struct.pack("<HHII", 4, 5, 3, gps_data_offset + 24)
        tiff += struct.pack("<I", 0)
        tiff += lat_blob
        tiff += lon_blob

    app1_payload = b"Exif\x00\x00" + bytes(tiff)
    app1_segment = struct.pack(">H", 2 + len(app1_payload))
    return b"\xff\xd8\xff\xe1" + app1_segment + app1_payload + b"\xff\xd9"


class TestQrExifHarvester:
    def test_fallback_qr_scan_finds_embedded_contacts(self) -> None:
        blob = b"\xff\xd8\xff\xe0" + b"fake-image-bytes mailto:alice@corp.co tel:+12025550199"
        found = read_qr(blob)
        kinds = {kind for _, kind in found}
        assert {"email", "phone", "url"}.intersection(kinds)

    def test_exif_tags_extracted_from_struct_tiff(self) -> None:
        jpeg = _build_jpeg_with_exif(make="ACME", model="X100", gps=None)
        exif = read_exif_jpeg(jpeg)
        assert exif["make"] == "ACME"
        assert exif["model"] == "X100"

    def test_gps_extracted(self) -> None:
        jpeg = _build_jpeg_with_exif(make="ACME", model="X100", gps=(51.0, 7.0))
        gps = read_gps(jpeg)
        assert gps is not None
        lat, lon = (float(p) for p in gps.split(","))
        assert lat == pytest.approx(51.0, abs=0.001)

    def test_not_an_image_no_exif(self) -> None:
        assert read_exif_jpeg(b"not-jpeg-at-all") == {}

    def test_harvester_on_plain_bytes(self) -> None:
        seed = TypeDetector().detect(b"\xff\xd8\xff\xe0buffer")
        result = QrExifHarvester().run(seed, HarvesterContext(seed=seed))
        # offline/image: either candidates or tesseract note — but always a result
        assert result.module == "qr_exif"


# ---------------------------------------------------------------------------
# username harvesters
# ---------------------------------------------------------------------------


class TestUsernameHarvesters:
    def test_social_pattern_profiles(self) -> None:
        seed = TypeDetector().detect("octocat")
        transport = DictTransport(existing={"https://github.com/octocat"})
        ctx = HarvesterContext(seed=seed, transport=transport)
        result = SocialProfilePatternHarvester().run(seed, ctx)
        assert len(result.candidates) == 9
        by_value = {c.value: c for c in result.candidates}
        assert by_value["https://github.com/octocat"].confidence == pytest.approx(0.85)
        assert by_value["https://x.com/octocat"].confidence == pytest.approx(0.35)

    def test_sherlock_worker_command(self) -> None:
        seed = TypeDetector().detect("octocat")
        result = SherlockWorkerAdapter().run(seed, HarvesterContext(seed=seed))
        assert len(result.commands) == 1
        command: CommandSpec = result.commands[0]
        assert command.tool == "sherlock"
        assert "octocat" in command.args

    def test_maigret_worker_command(self) -> None:
        seed = TypeDetector().detect("bob")
        result = MaigretWorkerAdapter().run(seed, HarvesterContext(seed=seed))
        assert result.commands[0].tool == "maigret"


# ---------------------------------------------------------------------------
# phone harvesters
# ---------------------------------------------------------------------------


class TestPhoneHarvesters:
    def test_whatsapp_presence_confirmed(self) -> None:
        seed = TypeDetector().detect("+12025550199")
        transport = DictTransport(existing={"https://wa.me/12025550199"})
        ctx = HarvesterContext(seed=seed, transport=transport)
        result = WhatsAppPresenceHarvester().run(seed, ctx)
        assert len(result.candidates) == 1
        assert result.candidates[0].value == "whatsapp:12025550199"
        assert result.candidates[0].confidence == pytest.approx(0.9)

    def test_whatsapp_presence_not_confirmed(self) -> None:
        seed = TypeDetector().detect("+12025550199")
        result = WhatsAppPresenceHarvester().run(seed, HarvesterContext(seed=seed))
        assert result.candidates == ()

    def test_phone_dorks_variants(self) -> None:
        seed = TypeDetector().detect("+12025550199")
        result = PhoneDorkHarvester().run(seed, HarvesterContext(seed=seed))
        assert result.candidates
        values = {c.value for c in result.candidates}
        assert '"+12025550199"' in values


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


class TestHarvesterRegistry:
    def test_register_and_sort_dispatch(self) -> None:
        registry = HarvesterRegistry()
        assert registry.register_all() >= 8
        assert registry.names() == sorted(registry.names())
        domain_modules = registry.modules_for(InputType.DOMAIN)
        assert domain_modules == sorted(domain_modules, key=lambda m: m.name)

    def test_duplicate_registration_rejected(self) -> None:
        registry = HarvesterRegistry()
        module = EmailPermutationHarvester()
        registry.register(module)
        with pytest.raises(ValueError):
            registry.register(module)

    def test_fault_contained(self) -> None:
        registry = HarvesterRegistry()
        seed = TypeDetector().detect("example.com")

        class Boom:
            name = "boom"
            required_types = frozenset({InputType.DOMAIN})
            method = "boom"
            license = "MIT"
            attribution = "test"

            def run(self, _seed, _ctx):
                raise RuntimeError("boom")

        registry.register(Boom())
        results = registry.run(seed, HarvesterContext(seed=seed))
        assert any("module fault" in note for result in results for note in result.notes)
        assert any(result.module == "boom" for result in results)