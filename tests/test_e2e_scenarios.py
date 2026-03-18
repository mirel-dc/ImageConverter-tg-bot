from __future__ import annotations

import sys
import zipfile
from pathlib import Path

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


def create_pdf(path: Path, pages: int = 1) -> None:
    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {index + 1}")
    doc.save(path)
    doc.close()


def test_zip_with_single_jpeg_to_webp(tmp_path: Path) -> None:
    zip_path = tmp_path / "input.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        img_path = tmp_path / "test.jpg"
        create_jpeg(img_path)
        zf.write(img_path, "test.jpg")

    result_path = ic.handle_zip_input(
        zip_path, task="jpeg-to-webp", quality=80, dpi=150, pdf_mode="combine", ico_sizes=[16, 32]
    )

    assert result_path.is_dir()
    webp_files = list(result_path.glob("test.webp"))
    assert len(webp_files) == 1
    with Image.open(webp_files[0]) as img:
        assert img.format == "WEBP"


def test_zip_with_multiple_images_to_pdf_combine(tmp_path: Path) -> None:
    zip_path = tmp_path / "images.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for i in range(3):
            img_path = tmp_path / f"img_{i}.jpg"
            create_jpeg(img_path)
            zf.write(img_path, f"img_{i}.jpg")
        
        png_path = tmp_path / "img_3.png"
        create_png(png_path)
        zf.write(png_path, "img_3.png")

    result_path = ic.handle_zip_input(
        zip_path, task="jpeg-to-pdf", quality=80, dpi=150, pdf_mode="combine", ico_sizes=[16, 32]
    )

    # При pdf_mode="combine" и ZIP входе, handle_zip_input обычно возвращает директорию с одним PDF или ZIP
    # Посмотрим реализацию handle_zip_input в src/core/image_converter.py:287
    
    assert result_path.is_dir()
    pdf_files = list(result_path.glob("*.pdf"))
    assert len(pdf_files) == 1
    with fitz.open(pdf_files[0]) as doc:
        assert doc.page_count == 4


def test_zip_with_multiple_images_to_pdf_per_file(tmp_path: Path) -> None:
    zip_path = tmp_path / "images_per_file.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for i in range(2):
            img_path = tmp_path / f"img_{i}.jpg"
            create_jpeg(img_path)
            zf.write(img_path, f"img_{i}.jpg")

    result_path = ic.handle_zip_input(
        zip_path, task="jpeg-to-pdf", quality=80, dpi=150, pdf_mode="per-file", ico_sizes=[16, 32]
    )

    assert result_path.is_dir()
    pdf_files = list(result_path.glob("*.pdf"))
    assert len(pdf_files) == 2


def test_zip_with_multiple_pdfs_to_jpeg(tmp_path: Path) -> None:
    zip_path = tmp_path / "pdfs.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for i in range(2):
            pdf_path = tmp_path / f"doc_{i}.pdf"
            create_pdf(pdf_path, pages=2)
            zf.write(pdf_path, f"doc_{i}.pdf")

    result_path = ic.handle_zip_input(
        zip_path, task="pdf-to-jpeg", quality=80, dpi=72, pdf_mode="combine", ico_sizes=[16, 32]
    )

    assert result_path.is_dir()
    # Каждая PDF на 2 страницы даст 2 джипега в своей папке или общей структуре
    # handle_zip_input для pdf-to-jpeg создает подпапки для каждого PDF
    doc0_dir = result_path / "doc_0"
    doc1_dir = result_path / "doc_1"
    assert doc0_dir.is_dir()
    assert doc1_dir.is_dir()
    assert len(list(doc0_dir.glob("*.jpg"))) == 2
    assert len(list(doc1_dir.glob("*.jpg"))) == 2


def test_zip_with_nested_folders(tmp_path: Path) -> None:
    zip_path = tmp_path / "nested.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        img_path = tmp_path / "root.jpg"
        create_jpeg(img_path)
        zf.write(img_path, "root.jpg")
        
        nested_img = tmp_path / "nested.jpg"
        create_jpeg(nested_img)
        zf.write(nested_img, "folder/subfolder/nested.jpg")

    result_path = ic.handle_zip_input(
        zip_path, task="jpeg-to-webp", quality=80, dpi=150, pdf_mode="combine", ico_sizes=[16, 32]
    )

    assert result_path.is_dir()
    assert (result_path / "root.webp").exists()
    assert (result_path / "folder" / "subfolder" / "nested.webp").exists()


def test_zip_with_mixed_content_ignores_unsupported(tmp_path: Path) -> None:
    zip_path = tmp_path / "mixed.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        img_path = tmp_path / "test.jpg"
        create_jpeg(img_path)
        zf.write(img_path, "test.jpg")
        
        txt_path = tmp_path / "info.txt"
        txt_path.write_text("hello")
        zf.write(txt_path, "info.txt")

    result_path = ic.handle_zip_input(
        zip_path, task="jpeg-to-webp", quality=80, dpi=150, pdf_mode="combine", ico_sizes=[16, 32]
    )

    assert result_path.is_dir()
    assert (result_path / "test.webp").exists()
    assert not (result_path / "info.txt").exists()
    # Проверяем что папка результата не содержит лишнего
    all_files = [p.name for p in result_path.rglob("*") if p.is_file()]
    assert all_files == ["test.webp"]
