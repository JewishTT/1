from orchestrator.app.services.file_meta import sniff_and_parse
from pypdf import PdfWriter
import io

def test_sniff_pdf_and_extract_meta():
    bio = io.BytesIO()
    w = PdfWriter(); w.add_blank_page(72,72); w.add_metadata({"/Title":"T"}); w.write(bio)
    out = sniff_and_parse("application/pdf", bio.getvalue())
    assert out["type"] == "pdf"
    assert out["meta"].get("Title") == "T"

