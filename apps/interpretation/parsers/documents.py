"""Document parser adapter: PDF / DOCX / XLSX / image EXIF (spec 007, T023/T025).

Deterministic, offline, dependency-light: pypdf + python-docx + openpyxl + Pillow.
Text emerges as page/row-granular segments with byte offsets; producer-side
metadata and image GPS surface as ``source=structure`` /**coords** mentions
(to DRY-rule resolution: no visual/ML). EXIF GPS is resolved to the nearest
GeoNames city from the mini dataset via a haversine scan (brand-new datasets —
453 nm acceptance Φ: explicit distance gate stays deterministic and honest,
precision ≤ 0.01 km).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from dictionaries import cities  # type: ignore[import-not-found]
from extractors.language import detect_language
from extractors.types import ExtractionResult, NormalizedName, TypedMention
from parsers.registry import Finding, Segment

_MAX_HAVERSINE_KM = 100.0


@dataclass
class DocumentsAdapter:
    name: str = "documents"
    """Parses PDF/DOCX/XLSX/JPEG/PNG files (binary-first; text went to html_full)."""

    content_types: tuple[str, ...] = (
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/jpeg",
        "image/png",
    )

    def can_parse(self, artifact) -> bool:
        head = _to_bytes(artifact)[:16]
        return bool(
            head[:5] == b"%PDF-"
            or head[:4] == b"PK\x03\x04"
            or head[:2] == b"\xff\xd8"
            or head[:4] == b"\x89PNG"
        )

    def parse(self, artifact) -> list[Finding]:
        result = self.extract(artifact)
        return [Finding(kind=s.kind, value=s.text, offset=s.offset, meta=s.meta) for s in result.segments]

    def extract(self, artifact) -> ExtractionResult:
        raw = _to_bytes(artifact)
        head = raw[:16]
        if head[:5] == b"%PDF-":
            return self._pdf(raw)
        if raw[:4] == b"PK\x03\x04":
            return self._zip_ooxml(raw)
        if head[:2] == b"\xff\xd8" or head[:4] == b"\x89PNG":
            return self._image(raw)
        raise ValueError(f"unsupported document signature: {head[:8]!r}")

    # -- PDF ---------------------------------------------------------------
    def _pdf(self, raw: bytes) -> ExtractionResult:
        from io import BytesIO

        from pypdf import PdfReader  # type: ignore[import-not-found]

        reader = PdfReader(BytesIO(raw))
        segments = []
        meta = _pdf_meta(reader)
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            segments.append(
                {
                    "text": text,
                    "kind": "text",
                    "meta": {"parser": "pypdf", "page": i},
                }
            )
        for field in ("author", "title", "producer", "creator", "subject"):
            value = str(meta.get(field) or "").strip()
            if value:
                segments.append(
                    {
                        "text": value,
                        "kind": "doc_meta",
                        "meta": {"meta_field": field, "parser": "pypdf"},
                    }
                )
        return self._assemble(raw, "application/pdf", segments)

    def _zip_ooxml(self, raw: bytes) -> ExtractionResult:
        from io import BytesIO
        from zipfile import ZipFile

        try:
            names = ZipFile(BytesIO(raw)).namelist()
        except Exception:  # noqa: BLE001 - corrupt zip → unreadable as ooxml
            return self._assemble(
                raw, "application/zip", [{"text": "", "kind": "text", "meta": {}}]
            )
        if "word/document.xml" in names:
            return self._docx(raw)
        if "xl/workbook.xml" in names:
            return self._xlsx(raw)
        return self._assemble(raw, "application/zip", [{"text": "", "kind": "text", "meta": {}}])

    def _docx(self, raw: bytes) -> ExtractionResult:
        from io import BytesIO

        import docx  # type: ignore[import-not-found]

        document = docx.Document(BytesIO(raw))
        segments = [
            {"text": p.text, "kind": "text", "meta": {"parser": "python-docx"}}
            for p in document.paragraphs
            if p.text and p.text.strip()
        ]
        props = document.core_properties
        for field, value in (("author", props.author), ("title", props.title), ("subject", props.subject)):
            if value:
                segments.append(
                    {"text": str(value), "kind": "doc_meta", "meta": {"meta_field": field, "parser": "python-docx"}}
                )
        return self._assemble(
            raw, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", segments
        )

    def _xlsx(self, raw: bytes) -> ExtractionResult:
        from io import BytesIO

        from openpyxl import load_workbook  # type: ignore[import-not-found]

        wb = load_workbook(BytesIO(raw), read_only=True, data_only=True)
        segments = []
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            for i, row in enumerate(rows):
                cells = " ".join(str(c) for c in row if c is not None)
                if cells.strip():
                    segments.append({"text": cells.strip(), "kind": "text", "meta": {"parser": "openpyxl", "sheet": ws.title, "row": i}})
        for field, value in (("title", wb.properties.title), ("creator", wb.properties.creator), ("description", wb.properties.description)):
            if value:
                segments.append({"text": str(value), "kind": "doc_meta", "meta": {"meta_field": field, "parser": "openpyxl"}})
        wb.close()
        return self._assemble(raw, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", segments)

    # -- images ------------------------------------------------------------
    def _image(self, raw: bytes) -> ExtractionResult:
        from io import BytesIO

        from PIL import ExifTags, Image  # type: ignore[import-not-found]

        image = Image.open(BytesIO(raw))
        segments = []
        try:
            exif = image._getexif() or {}
        except Exception:  # noqa: BLE001 - malformed EXIF tolerated
            exif = {}
        tag_names = dict(ExifTags.TAGS)
        for key, value in exif.items():
            label = tag_names.get(int(key), str(key))
            if label in {"Make", "Model", "DateTime", "ImageDescription", "Software"} and value:
                segments.append(
                    {"text": str(value), "kind": "doc_meta", "meta": {"meta_field": label, "parser": "Pillow"}}
                )
        coords = _gps_from_exif(exif)
        raw_text = {}
        if coords is None:
            photo = _parse_photo_exif(raw)
            coords = photo.get("gps")
            raw_text = photo.get("text", {})
        if not raw_text:
            raw_text = {}
        for label, value in raw_text.items():
            if value:
                segments.append(
                    {"text": value, "kind": "doc_meta", "meta": {"meta_field": label, "parser": "exif-raw"}}
                )
        place: TypedMention | None = None
        if coords:
            city = _nearest_city(coords[0], coords[1], cities.CITIES)
            value = f"{city['name_ru']} ({city['country']})" if city else f"{coords[0]:.5f},{coords[1]:.5f}"
            place = TypedMention(
                kind="place",
                value=value,
                offset=0,
                end_offset=len(value.encode("utf-8")),
                extractor="documents",
                source="coords",
                confidence=1.0,
                evidence={
                    "coords": {"lat": round(coords[0], 6), "lon": round(coords[1], 6)},
                    "exact_coords": {"lat": coords[0], "lon": coords[1]},
                    "dictionary": _dictionary_stamp(),
                },
                normalized=NormalizedName(canonical=_canonical_place(value), transforms=["geonames-dab"]),
            )
        return ExtractionResult(
            artifact_sha=hashlib.sha256(raw).hexdigest(),
            content_type="image/jpeg" if raw[:2] == b"\xff\xd8" else "image/png",
            segments=[_segment(s) for s in segments],
            mentions=[place] if place else [],
        )

    # -- assembly ----------------------------------------------------------
    def _assemble(self, raw: bytes, content_type: str, dict_segments: list[dict]) -> ExtractionResult:
        segments = [_segment(s) for s in dict_segments]
        lang = detect_language(" ".join(s.text for s in segments)) if segments else None
        for seg in segments:
            if seg.lang_hint is None:
                seg.lang_hint = lang
        return ExtractionResult(
            artifact_sha=hashlib.sha256(raw).hexdigest(),
            content_type=content_type,
            segments=segments,
            mentions=[],
        )


def _segment(d: dict) -> Segment:
    return Segment(text=d["text"], offset=0, kind=d["kind"], meta=d["meta"])


def _pdf_meta(reader) -> dict:
    data = getattr(reader, "metadata", None)
    if data is None:
        return {}
    out = {}
    for key in ("Author", "Title", "Producer", "Creator", "Subject"):
        for raw_key, value in dict(data).items():
            if str(raw_key).lstrip("/").casefold() == key.casefold():
                out[key.casefold()] = str(value)
                break
    return out


def _gps_from_exif(exif: dict) -> tuple[float, float] | None:
    gps = None
    for key, value in exif.items():
        label = str(getattr(key, "name", key)).lower()
        if key == 34853 or label in ("gpsinfo", "gps", "gps_ifd"):
            gps = value
            break
    if not isinstance(gps, dict):
        return None
    lat = _exif_gps_component(gps, 2, "GPSLatitude")
    lon = _exif_gps_component(gps, 4, "GPSLongitude")
    if lat is None or lon is None:
        return None
    ref_n = gps.get(1, gps.get("GPSLatitudeRef", "N"))
    ref_e = gps.get(3, gps.get("GPSLongitudeRef", "E"))
    return (
        abs(lat) * (-1 if str(ref_n).upper() == "S" else 1),
        abs(lon) * (-1 if str(ref_e).upper() == "W" else 1),
    )


def _exif_gps_component(gps: dict, int_key: int, name_key: str) -> float | None:
    value = gps.get(int_key, gps.get(name_key))
    if value is None:
        return None
    parts: list[float] = []
    for item in value if isinstance(value, (list, tuple)) else [value]:
        try:
            if hasattr(item, "numerator") and hasattr(item, "denominator"):
                parts.append(item.numerator / item.denominator)
            else:
                parts.append(float(item))
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    if not parts:
        return None
    return parts[0] + parts[1] / 60.0 + (parts[2] / 3600.0 if len(parts) > 2 else 0.0)


def _photo_gps_raw(data: bytes) -> tuple[float, float] | None:
    return _parse_photo_exif(data).get("gps")


def _parse_photo_exif(data: bytes) -> dict:
    """Deterministic EXIF read from raw buttons (Pillow-independent).

    Parses the APP1 ``Exif`` TIFF stream: IFD0 make/model + GPSInfo pointer →
    GPS IFD (lat/lon rationals + N/E/S/W refs). Used as a fallback because
    Pillow's nested-IFD reader is not reliable for hand-built EXIF fixtures.
    """
    import struct

    start = data.find(b"Exif\x00\x00")
    if start < 0:
        return {"gps": None, "text": {}}
    tiff = data[start + 6 :]
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return {"gps": None, "text": {}}
    little = tiff[:2] == b"II"

    def u16(off: int) -> int:
        return struct.unpack_from("<H" if little else ">H", tiff, off)[0]

    def u32(off: int) -> int:
        return struct.unpack_from("<I" if little else ">I", tiff, off)[0]

    def ascii_at(off: int, ent: int, cnt: int) -> str:
        if cnt <= 4:
            return tiff[ent + 8 : ent + 8 + cnt].split(b"\x00", 1)[0].decode("utf-8", errors="ignore")
        return tiff[off : off + cnt].split(b"\x00", 1)[0].decode("utf-8", errors="ignore")

    if u16(2) != 42:
        return {"gps": None, "text": {}}
    try:
        ifd0 = u32(4)
        count = u16(ifd0)
        text: dict[str, str] = {}
        gps_off = None
        for e in range(count):
            ent = ifd0 + 2 + e * 12
            if ent + 12 > len(tiff):
                break
            tag, typ, cnt = u16(ent), u16(ent + 2), u32(ent + 4)
            val = u32(ent + 8)
            if tag == 0x010F and typ == 2:
                text["Make"] = ascii_at(val, ent, cnt)
            elif tag == 0x0110 and typ == 2:
                text["Model"] = ascii_at(val, ent, cnt)
            elif tag == 0x0132 and typ == 2:
                text["DateTime"] = ascii_at(val, ent, cnt)
            elif tag == 0x8825 and typ == 4:
                gps_off = val
        if gps_off is None or gps_off + 2 > len(tiff):
            return {"gps": None, "text": text}
        gc = u16(gps_off)
        ref_n = ref_e = None
        lat = lon = None
        for e in range(gc):
            ent = gps_off + 2 + e * 12
            if ent + 12 > len(tiff):
                break
            tag, typ, cnt = u16(ent), u16(ent + 2), u32(ent + 4)
            val = u32(ent + 8)
            if tag == 1 and typ == 2:
                ref_n = tiff[ent + 8 : ent + 10]
                ref_n = ref_n[:1].decode("utf-8", errors="ignore")
            elif tag == 3 and typ == 2:
                ref_e = tiff[ent + 8 : ent + 10]
                ref_e = ref_e[:1].decode("utf-8", errors="ignore")
            elif tag == 2 and typ == 5:
                lat = _rationals_dms(tiff, val, cnt)
            elif tag == 4 and typ == 5:
                lon = _rationals_dms(tiff, val, cnt)
        gps = None
        if lat is not None and lon is not None:
            gps = (
                abs(lat) * (-1 if ref_n and ref_n.upper() == "S" else 1),
                abs(lon) * (-1 if ref_e and ref_e.upper() == "W" else 1),
            )
        return {"gps": gps, "text": {k: v for k, v in text.items() if v}}
    except (struct.error, IndexError, ValueError):
        return {"gps": None, "text": {}}


def _rationals_dms(tiff: bytes, off: int, cnt: int) -> float | None:
    import struct

    if off + cnt * 8 > len(tiff):
        return None
    parts: list[float] = []
    for k in range(min(cnt, 3)):
        n, d = struct.unpack_from("<II", tiff, off + k * 8)
        parts.append(n / d if d else 0.0)
    if not parts:
        return None
    value = parts[0] + parts[1] / 60.0 + (parts[2] / 3600.0 if len(parts) > 2 else 0.0)
    return value


def _nearest_city(lat: float, lon: float, cities_table: list[dict]) -> dict | None:
    best = None
    best_km = None
    for entry in cities_table:
        clat = float(entry["lat"])
        clon = float(entry["lon"])
        km = _haversine_km(lat, lon, clat, clon)
        if best_km is None or km < best_km:
            best, best_km = entry, km
    if best_km is not None and best_km <= _MAX_HAVERSINE_KM:
        return best
    return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    R = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * R * asin(sqrt(a))


def _canonical_place(value: str) -> str:
    return " ".join(value.split()).casefold()


def _dictionary_stamp() -> str:
    from dictionaries.build_mini import VERSIONS  # type: ignore[import-not-found]

    return f"geonames@{VERSIONS['geonames']}"


def _to_bytes(artifact) -> bytes:
    if isinstance(artifact, (bytes, bytearray)):
        return bytes(artifact)
    if isinstance(artifact, str):
        return artifact.encode("utf-8")
    return b""