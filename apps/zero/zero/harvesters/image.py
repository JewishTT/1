"""Image harvesters (spec/010 §0.5): QR / EXIF / OCR with deterministic fallbacks.

Three pure-stdlib transforms with optional third-party acceleration:

- QR decoding uses ``pyzbar`` when importable; otherwise a deterministic
  fallback scans the raw bytes for ``mailto:`` / ``tel:`` / ``https://`` blobs.
- EXIF reads the JPEG APP1/TIFF structure directly with ``struct`` (Make,
  Model, Software, DateTime, GPS) — no Pillow required. PNG ``tEXt`` chunks
  (Author/Software/Description) are parsed too.
- OCR is never run inline: if the ``tesseract`` binary is present a
  ``CommandSpec`` worker is initialized; otherwise a note explains the
  fallback. Everything stays hermetic under tests.

   Source repos: donors/pyzbar (MIT) method, donors/Pillow+piexif (HPNS) EXIF
   pattern, donors/tesseract (Apache-2.0) as worker command only.
"""

from __future__ import annotations

import re
import shutil
import struct

from ..type_detector import InputType, SeedInput
from .contracts import CommandSpec, HarvestResult, ObservationCandidate
from .registry import HarvestContext

try:  # optional QR backend (MIT)
    from pyzbar.pyzbar import decode as _pyzbar_decode  # type: ignore

    _PYZBAR = True
except Exception:  # pragma: no cover - environment dependent
    _PYZBAR = False

_MAILTO_RE = re.compile(rb"mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", re.IGNORECASE)
_TEL_RE = re.compile(rb"tel:([0-9+ ()-]{7,20})", re.IGNORECASE)
_HTTP_RE = re.compile(rb"https?://[^\x00-\x20\x7f]{8,120}", re.IGNORECASE)

_EXIF_ASCII = 2
_EXIF_SHORT = 3
_EXIF_LONG = 4
_EXIF_RATIONAL = 5

_EXIF_TAGS = {
    0x010F: "make",
    0x0110: "model",
    0x0131: "software",
    0x0132: "datetime",
    0x013B: "artist",
    0x8298: "copyright",
    0x9003: "datetime_original",
}
_GPS_TAGS = {
    0x0001: "gps_lat_ref",
    0x0002: "gps_lat",
    0x0003: "gps_lon_ref",
    0x0004: "gps_lon",
}


def _qr_fallback(data: bytes) -> list[tuple[str, str]]:
    """Deterministic no-pyzbar fallback: embedded plain-text contact blobs."""
    found: list[tuple[str, str]] = []
    for match in _MAILTO_RE.findall(data):
        found.append((match.decode("ascii", "replace"), "email"))
    for match in _TEL_RE.findall(data):
        found.append((match.decode("ascii", "replace"), "phone"))
    for match in _HTTP_RE.findall(data):
        found.append((match.decode("ascii", "replace"), "url"))
    return found


def read_qr(data: bytes) -> list[tuple[str, str]]:
    """Decode QR blobs; falls back to the plain-text scan when pyzbar is absent."""
    if _PYZBAR:
        decoded: list[tuple[str, str]] = []
        for entry in _pyzbar_decode(data):
            raw = entry.data.decode("utf-8", errors="replace") if entry.data else ""
            if raw:
                decoded.append((raw, "qr"))
        if decoded:
            return decoded
    return _qr_fallback(data)


def read_exif_jpeg(data: bytes) -> dict[str, str]:
    """Extract selected EXIF tags from a JPEG (APP1/TIFF, stdlib struct)."""
    if not data.startswith(b"\xff\xd8\xff"):
        return {}
    index = 2
    while index < len(data):
        if data[index] != 0xFF:
            break
        marker = data[index + 1]
        if marker not in (0xE1, 0xE2, 0xE3):
            length = struct.unpack(">H", data[index + 2 : index + 4])[0]
            index += 2 + length
            continue
        seg_len = struct.unpack(">H", data[index + 2 : index + 4])[0]
        segment = data[index + 4 : index + 2 + seg_len]
        if marker == 0xE1 and segment.startswith(b"Exif\x00\x00"):
            return _parse_tiff(segment[6:], _EXIF_TAGS, gps_pointer=0x8825)
        if marker == 0xE2 and segment.startswith(b"http:"):
            # ICC profile APP2 — no EXIF, skip cleanly.
            index += 2 + seg_len
            continue
        index += 2 + seg_len
    return {}


def read_exif_png(data: bytes) -> dict[str, str]:
    """Extract AUTHOR / SOFTWARE / DESCRIPTION from PNG tEXt chunks."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return {}
    result: dict[str, str] = {}
    index = 8
    while index + 8 <= len(data):
        (length,) = struct.unpack(">I", data[index : index + 4])
        chunk_type = data[index + 4 : index + 8]
        chunk = data[index + 8 : index + 8 + length]
        if chunk_type == b"tEXt":
            key, _, value = chunk.partition(b"\x00")
            key_name = key.decode("latin-1").lower()
            if key_name in ("author", "software", "description", "comment", "title"):
                result[key_name] = value.decode("latin-1", errors="replace")
        if chunk_type == b"IEND":
            break
        index += 12 + length
    return result


def read_gps(data: bytes) -> str | None:
    """Return ``"lat,lon"`` decimal string when a GPS IFD is present (or None)."""
    if not data.startswith(b"\xff\xd8\xff"):
        return None
    tiff = _find_tiff_blob(data)
    if tiff is None:
        return None
    values = _parse_tiff(tiff, _GPS_TAGS, gps_pointer=0x8825)
    if not {"gps_lat", "gps_lon", "gps_lat_ref", "gps_lon_ref"}.issubset(values):
        return None
    try:
        lat = _rational(values["gps_lat"])
        lon = _rational(values["gps_lon"])
    except (TypeError, ValueError):
        return None
    if values["gps_lat_ref"] in ("S", "s"):
        lat = -lat
    if values["gps_lon_ref"] in ("W", "w"):
        lon = -lon
    return f"{lat:.6f},{lon:.6f}"


# -- private TIFF helpers ----------------------------------------------------


def _find_tiff_blob(data: bytes) -> bytes | None:
    index = 2
    while index < len(data):
        if data[index] != 0xFF:
            return None
        marker = data[index + 1]
        if marker == 0xE1:
            seg_len = struct.unpack(">H", data[index + 2 : index + 4])[0]
            segment = data[index + 4 : index + 2 + seg_len]
            if segment.startswith(b"Exif\x00\x00"):
                return segment[6:]
        length = struct.unpack(">H", data[index + 2 : index + 4])[0]
        index += 2 + length
    return None


def _parse_tiff(blob: bytes, tags: dict[int, str], *, gps_pointer: int | None) -> dict[str, str]:
    if len(blob) < 8:
        return {}
    byte_order = blob[:2]
    if byte_order == b"II":
        endian = "<"
    elif byte_order == b"MM":
        endian = ">"
    else:
        return {}
    if struct.unpack(f"{endian}H", blob[2:4])[0] != 42:
        return {}
    (ifd0_offset,) = struct.unpack(f"{endian}I", blob[4:8])
    result: dict[str, str] = {}
    _scan_ifd(blob, endian, ifd0_offset, tags, result, gps_pointer)
    return result


def _scan_ifd(
    blob: bytes,
    endian: str,
    ifd_offset: int,
    tags: dict[int, str],
    out: dict[str, str],
    gps_pointer: int | None,
) -> None:
    if ifd_offset + 2 > len(blob):
        return
    (count,) = struct.unpack(f"{endian}H", blob[ifd_offset : ifd_offset + 2])
    offset = ifd_offset + 2
    gps_ifd: int | None = None
    for _ in range(count):
        if offset + 12 > len(blob):
            return
        entry = blob[offset : offset + 12]
        (tag,) = struct.unpack(f"{endian}H", entry[0:2])
        (entry_type,) = struct.unpack(f"{endian}H", entry[2:4])
        (value_count,) = struct.unpack(f"{endian}I", entry[4:8])
        name = tags.get(tag)
        if name:
            try:
                out[name] = _read_field(blob, endian, entry_type, value_count, entry[8:12])
            except (struct.error, ValueError):
                pass
        if gps_pointer is not None and tag == gps_pointer:
            (gps_ifd,) = struct.unpack(f"{endian}I", entry[8:12])
        offset += 12
    if gps_ifd is not None:
        _scan_ifd(blob, endian, gps_ifd, tags, out, gps_pointer=None)


def _read_field(blob: bytes, endian: str, entry_type: int, count: int, value_field: bytes) -> str:
    size = {1: 1, _EXIF_ASCII: 1, _EXIF_SHORT: 2, _EXIF_LONG: 4, _EXIF_RATIONAL: 8}[entry_type]
    if size * count > 4:  # value stored at offset
        (ptr,) = struct.unpack(f"{endian}I", value_field)
        value_bytes = blob[ptr : ptr + size * count]
    else:
        value_bytes = value_field[: size * count]
    if entry_type == _EXIF_ASCII:
        return value_bytes.split(b"\x00")[0].decode("latin-1", errors="replace").strip()
    if entry_type == _EXIF_LONG:
        values = struct.unpack(f"{endian}I", value_bytes[:4])[0]
        return str(values)
    if entry_type == _EXIF_SHORT:
        values = struct.unpack(f"{endian}H", value_bytes[:2])[0]
        return str(values)
    if entry_type == _EXIF_RATIONAL:
        raw_fracs = struct.unpack(f"{endian}" + "I" * (count * 2), value_bytes)
        fracs = [
            num / den if den else 0.0
            for num, den in zip(raw_fracs[0::2], raw_fracs[1::2], strict=True)
        ]
        if count == 1:
            return f"{fracs[0]:.8f}"
        return ",".join(f"{f:.8f}" for f in fracs)
    raise ValueError(f"unsupported exif type {entry_type}")


def _rational(value: str) -> float:
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 3:
        raise ValueError("expected 3 rational coordinates")
    return float(parts[0]) + float(parts[1]) / 60.0 + float(parts[2]) / 3600.0


class QrExifHarvester:
    """Image bytes → QR contacts + EXIF metadata (fallbacks when binaries absent)."""

    name = "qr_exif"
    required_types = frozenset({InputType.IMAGE})
    method = "QR decode (pyzbar) + EXIF (struct) + OCR worker init"
    license = "MIT"
    attribution = (
        "donors/pyzbar (MIT), donors/Pillow+piexif (HPNS) EXIF pattern, "
        "tesseract (Apache-2.0) worker"
    )

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        raw = seed.raw_value.encode("latin-1", errors="replace")
        candidates: list[ObservationCandidate] = []
        for payload, kind in read_qr(raw):
            candidates.append(
                ObservationCandidate(
                    value=payload,
                    kind=kind,
                    confidence=0.9,
                    source_module=self.name,
                    method=self.method,
                    raw_fields={"image_type": seed.metadata.get("file_hint", "raw")},
                    evidence="QR-decoded payload" if _PYZBAR else "QR fallback scan",
                )
            )
        exif = read_exif_jpeg(raw)
        if not exif:
            exif = read_exif_png(raw)
        for key, value in sorted(exif.items()):
            candidates.append(
                ObservationCandidate(
                    value=value,
                    kind="exif_" + key,
                    confidence=0.85,
                    source_module=self.name,
                    method=self.method,
                    raw_fields={"exif_tag": key},
                    evidence="EXIF metadata field",
                )
            )
        gps = read_gps(raw)
        if gps:
            candidates.append(
                ObservationCandidate(
                    value=gps,
                    kind="exif_gps",
                    confidence=0.95,
                    source_module=self.name,
                    method=self.method,
                    raw_fields={"gps_format": "decimal"},
                    evidence="EXIF GPS IFD coordinates",
                )
            )
        commands: list[CommandSpec] = []
        notes: list[str] = []
        if shutil.which("tesseract"):
            commands.append(
                CommandSpec(
                    tool="tesseract",
                    args=(seed.raw_value, "stdout"),
                    method="OCR worker (tesseract)",
                    timeout_s=120.0,
                )
            )
        else:
            notes.append("tesseract binary not found — OCR worker not initialized")
        return HarvestResult(
            module=self.name,
            candidates=tuple(candidates),
            commands=tuple(commands),
            notes=tuple(notes),
        )


MODULES = (QrExifHarvester(),)