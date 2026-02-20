from __future__ import annotations

from pathlib import Path
import sys

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