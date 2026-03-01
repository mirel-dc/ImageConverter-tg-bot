from __future__ import annotations

from pathlib import Path
import sys
import zipfile

import fitz
import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import core.image_converter as ic


def create_jpeg(path: Path, size: tuple[int, int] = (64, 64), color: tuple[int, int, int] = (255, 0, 0)) -> None:
    img = Image.new("RGB", size, color)
    img.save(path, format="JPEG", quality=90)


def create_png(path: Path, size: tuple[int, int] = (64, 64), color: tuple[int, int, int, int] = (0, 0, 255, 255)) -> None:
    img = Image.new("RGBA", size, color)
    img.save(path, format="PNG")


def create_pdf(path: Path, pages: int = 2) -> None:
    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {index + 1}")
    doc.save(path)
    doc.close()


def test_pdf_to_jpeg(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    create_pdf(pdf_path, pages=2)

    output_dir = tmp_path / "out"
    created = ic.convert_pdf_to_jpegs(pdf_path, output_dir, quality=80, dpi=100)

    assert len(created) == 2
    assert all(path.exists() for path in created)


def test_jpeg_to_pdf_combine(tmp_path: Path) -> None:
    img1 = tmp_path / "a.jpg"
    img2 = tmp_path / "b.jpg"
    create_jpeg(img1, color=(255, 0, 0))
    create_jpeg(img2, color=(0, 255, 0))

    pdf_path = tmp_path / "combined.pdf"
    ic.convert_jpegs_to_pdf([img1, img2], pdf_path)

    with fitz.open(pdf_path) as doc:
        assert doc.page_count == 2


def test_png_to_pdf_combine(tmp_path: Path) -> None:
    img1 = tmp_path / "a.png"
    img2 = tmp_path / "b.png"
    create_png(img1, color=(0, 0, 255, 255))
    create_png(img2, color=(0, 255, 255, 255))

    pdf_path = tmp_path / "combined.png.pdf"
    ic.convert_jpegs_to_pdf([img1, img2], pdf_path)

    with fitz.open(pdf_path) as doc:
        assert doc.page_count == 2


def test_jpeg_to_ico(tmp_path: Path) -> None:
    img_path = tmp_path / "icon.jpg"
    create_jpeg(img_path)

    ico_path = tmp_path / "icon.ico"
    ic.convert_jpeg_to_ico(img_path, ico_path, sizes=[16, 32])

    with Image.open(ico_path) as ico:
        sizes = set(getattr(ico, "sizes", []) or ico.info.get("sizes", []))
        assert (16, 16) in sizes
        assert (32, 32) in sizes


def test_png_to_ico(tmp_path: Path) -> None:
    img_path = tmp_path / "icon.png"
    create_png(img_path)

    ico_path = tmp_path / "icon.png.ico"
    ic.convert_jpeg_to_ico(img_path, ico_path, sizes=[16, 32])

    with Image.open(ico_path) as ico:
        sizes = set(getattr(ico, "sizes", []) or ico.info.get("sizes", []))
        assert (16, 16) in sizes
        assert (32, 32) in sizes


def test_jpeg_to_webp(tmp_path: Path) -> None:
    img_path = tmp_path / "photo.jpg"
    create_jpeg(img_path)

    webp_path = tmp_path / "photo.webp"
    ic.convert_jpeg_to_webp(img_path, webp_path, quality=75)

    with Image.open(webp_path) as img:
        assert img.format == "WEBP"


def test_png_to_webp(tmp_path: Path) -> None:
    img_path = tmp_path / "photo.png"
    create_png(img_path)

    webp_path = tmp_path / "photo.png.webp"
    ic.convert_jpeg_to_webp(img_path, webp_path, quality=75)

    with Image.open(webp_path) as img:
        assert img.format == "WEBP"


def test_jpeg_to_avif(tmp_path: Path) -> None:
    img_path = tmp_path / "photo.jpg"
    create_jpeg(img_path)

    avif_path = tmp_path / "photo.avif"
    ic.convert_jpeg_to_avif(img_path, avif_path, quality=95)

    with Image.open(avif_path) as img:
        assert img.format == "AVIF"


def test_png_to_avif(tmp_path: Path) -> None:
    img_path = tmp_path / "photo.png"
    create_png(img_path)

    avif_path = tmp_path / "photo.png.avif"
    ic.convert_jpeg_to_avif(img_path, avif_path, quality=95)

    with Image.open(avif_path) as img:
        assert img.format == "AVIF"


def test_safe_extract_zip_ignores_macosx_and_appledouble(tmp_path: Path) -> None:
    zip_path = tmp_path / "input.zip"
    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("__MACOSX/._5.jpg", b"")
        zf.writestr("__MACOSX/5.jpg", b"not-an-image")
        zf.writestr("Новая папка/._6.jpg", b"")
        zf.writestr("Новая папка/6.jpg", b"ok")

    ic.safe_extract_zip(zip_path, extract_dir)

    assert not (extract_dir / "__MACOSX").exists()
    assert not (extract_dir / "Новая папка" / "._6.jpg").exists()
    assert (extract_dir / "Новая папка" / "6.jpg").exists()


def test_normalize_zip_member_name_fixes_mojibake_for_cyrillic() -> None:
    original = "Новая папка/5.jpg"
    mojibake = original.encode("utf-8").decode("cp437")
    assert ic.normalize_zip_member_name(mojibake) == original