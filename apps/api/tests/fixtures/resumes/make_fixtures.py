"""Regenerate the PDF/DOCX resume fixtures from the .txt sources next to this file.

    cd apps/api && python tests/fixtures/resumes/make_fixtures.py

Every person, employer and contact detail in these fixtures is invented. The PDF writer
is hand-rolled (Helvetica, one text object per page) so it needs no extra dependency.
"""

from pathlib import Path

HERE = Path(__file__).parent
LINES_PER_PAGE = 60


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(lines: list[str], path: Path) -> None:
    pages = [lines[i:i + LINES_PER_PAGE] for i in range(0, max(len(lines), 1), LINES_PER_PAGE)]
    objects: list[bytes] = []
    page_ids = [4 + 2 * i for i in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for i, page in enumerate(pages):
        body = "BT /F1 9 Tf 12 TL 40 800 Td\n" + "".join(f"({_escape(l)}) Tj T*\n" for l in page) + "ET"
        stream = body.encode("cp1252")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_ids[i] + 1} 0 R >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path.write_bytes(bytes(out))


def write_docx(lines: list[str], path: Path) -> None:
    import docx

    document = docx.Document()
    for line in lines:
        document.add_paragraph(line)
    document.core_properties.author = "fixture"
    document.save(path)


if __name__ == "__main__":
    for name in ("sample_resume", "injection_resume"):
        lines = (HERE / f"{name}.txt").read_text(encoding="utf-8").splitlines()
        write_pdf(lines, HERE / f"{name}.pdf")
    write_docx((HERE / "sample_resume.txt").read_text(encoding="utf-8").splitlines(), HERE / "sample_resume.docx")
