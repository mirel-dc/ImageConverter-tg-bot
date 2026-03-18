from __future__ import annotations

import sys
import zipfile
from pathlib import Path

# Добавляем путь к src, чтобы использовать существующие библиотеки
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Пытаемся импортировать зависимости, используемые в проекте
try:
    from PIL import Image
    import fitz
except ImportError:
    print("Ошибка: Необходимые библиотеки (Pillow, PyMuPDF) не установлены.")
    print("Пожалуйста, выполните: cd src && uv sync")
    sys.exit(1)

OUTPUT_DIR = PROJECT_ROOT / "test_data"
OUTPUT_DIR.mkdir(exist_ok=True)

def create_jpeg(path: Path, size: tuple[int, int] = (512, 512), color: tuple[int, int, int] = (255, 0, 0)) -> None:
    img = Image.new("RGB", size, color)
    img.save(path, format="JPEG", quality=95)
    print(f"Создан JPEG: {path.name}")

def create_png(path: Path, size: tuple[int, int] = (512, 512), color: tuple[int, int, int, int] = (0, 0, 255, 255)) -> None:
    img = Image.new("RGBA", size, color)
    img.save(path, format="PNG")
    print(f"Создан PNG: {path.name}")

def create_pdf(path: Path, pages: int = 2) -> None:
    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text((50, 50), f"Sample PDF Document - Page {index + 1}", fontsize=20)
        page.insert_text((50, 100), f"This is a test page generated for Image Converter Bot.", fontsize=12)
    doc.save(path)
    doc.close()
    print(f"Создан PDF: {path.name} ({pages} стр.)")

def main():
    # 1. Одиночные файлы
    create_jpeg(OUTPUT_DIR / "sample_red.jpg", color=(255, 0, 0))
    create_jpeg(OUTPUT_DIR / "sample_green.jpg", color=(0, 255, 0))
    create_png(OUTPUT_DIR / "sample_blue.png", color=(0, 0, 255, 255))
    create_pdf(OUTPUT_DIR / "sample_document.pdf", pages=3)

    # 2. ZIP с одним файлом
    zip_single = OUTPUT_DIR / "archive_single.zip"
    with zipfile.ZipFile(zip_single, "w") as zf:
        img_path = OUTPUT_DIR / "temp_img.jpg"
        create_jpeg(img_path, color=(255, 255, 0))
        zf.write(img_path, "yellow_image.jpg")
        img_path.unlink()
    print(f"Создан ZIP (1 файл): {zip_single.name}")

    # 3. ZIP с несколькими изображениями
    zip_images = OUTPUT_DIR / "archive_images.zip"
    with zipfile.ZipFile(zip_images, "w") as zf:
        for i, color in enumerate([(255, 0, 255), (0, 255, 255), (128, 128, 128)]):
            img_path = OUTPUT_DIR / f"temp_{i}.jpg"
            create_jpeg(img_path, color=color)
            zf.write(img_path, f"image_{i}.jpg")
            img_path.unlink()
    print(f"Создан ZIP (3 изображения): {zip_images.name}")

    # 4. ZIP с вложенными папками
    zip_nested = OUTPUT_DIR / "archive_nested.zip"
    with zipfile.ZipFile(zip_nested, "w") as zf:
        # Файл в корне
        img_path = OUTPUT_DIR / "temp_root.png"
        create_png(img_path, color=(0, 0, 0, 255))
        zf.write(img_path, "root_black.png")
        img_path.unlink()
        
        # Файл во вложенной папке
        img_path = OUTPUT_DIR / "temp_nested.jpg"
        create_jpeg(img_path, color=(255, 128, 0))
        zf.write(img_path, "photos/summer/orange.jpg")
        img_path.unlink()
    print(f"Создан ZIP (вложенные папки): {zip_nested.name}")

    # 5. ZIP со смешанным контентом (PDF + JPG)
    zip_mixed = OUTPUT_DIR / "archive_mixed.zip"
    with zipfile.ZipFile(zip_mixed, "w") as zf:
        pdf_path = OUTPUT_DIR / "temp_doc.pdf"
        create_pdf(pdf_path, pages=1)
        zf.write(pdf_path, "guide.pdf")
        pdf_path.unlink()
        
        img_path = OUTPUT_DIR / "temp_img.jpg"
        create_jpeg(img_path, color=(100, 100, 255))
        zf.write(img_path, "preview.jpg")
        img_path.unlink()
    print(f"Создан ZIP (смешанный): {zip_mixed.name}")

    print("\nВсе файлы успешно созданы в директории 'test_data/'")

if __name__ == "__main__":
    main()
