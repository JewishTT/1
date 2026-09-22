import os
from pathlib import Path
from orchestrator.app.services.exporter import export

def test_split_exports(tmp_path):
    outdir = tmp_path / "exp"
    sample = [
        {"url": "https://example.com/a", "title": "A", "domain": "example.com", "source": "opensearch"},
        {"url": "mailto:john@example.com", "title": "John", "domain": "", "source": "seed", "email": "john@example.com"},
        {"url": "https://cdn.site/img/a.jpg", "title": "Img A", "source": "image", "media_type": "image"},
        {"url": "https://example.com/file.pdf", "title": "PDF A", "source": "pdf", "media_type": "pdf"},
        {"url": "tel:+302101234567", "title": "Phone", "source": "seed", "phone": "+30 210 123 4567"},
    ]
    csv_p, json_p = export(sample, str(outdir), "run_20250101_000000_demo.ext", "demo", formats=("csv","json"), split_by_entity=True)
    assert Path(csv_p).exists() and Path(json_p).exists()
    # check split files created
    for suffix in ["_urls.csv", "_emails.csv", "_phones.csv", "_images.csv", "_pdfs.csv"]:
        p = outdir / ("run_20250101_000000_demo" + suffix)
        assert p.exists()

