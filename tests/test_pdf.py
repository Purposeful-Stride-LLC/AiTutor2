"""PDF sources: read with the optional pypdf extra, clear message without it."""

import builtins

import pytest

from aitutor.pipeline import ingest


def _tiny_pdf(text: str) -> bytes:
    """A minimal one-page PDF with a text layer (no external tools)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def test_pdf_text_is_extracted(tmp_path):
    pytest.importorskip("pypdf")
    f = tmp_path / "manual.pdf"
    f.write_bytes(_tiny_pdf("Omit needless words"))
    text = ingest.read_source_text(f)
    assert "Omit needless words" in text and "[page 1]" in text
    assert f in ingest.scan_folder(tmp_path).files


def test_pdf_without_pypdf_explains(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def no_pypdf(name, *a, **k):
        if name == "pypdf" or name.startswith("pypdf."):
            raise ImportError("no pypdf")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_pypdf)
    f = tmp_path / "manual.pdf"
    f.write_bytes(_tiny_pdf("x"))
    with pytest.raises(ValueError, match=r'aitutor\[pdf\]'):
        ingest.read_source_text(f)
    scan = ingest.scan_folder(tmp_path)
    assert not scan.files and "aitutor[pdf]" in scan.skipped[0][1]
