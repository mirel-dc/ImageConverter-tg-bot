from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

SUPPORTED_JPEG = {".jpg", ".jpeg", ".png"}


def require_pillow():
    try:
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Библиотека Pillow не установлена. Установите: pip install Pillow") from exc


def require_pymupdf():
    try:
        import fitz  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Библиотека PyMuPDF не установлена. Установите: pip install pymupdf") from exc


def require_img2pdf():
    try:
        import img2pdf  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Библиотека img2pdf не установлена. Установите: pip install img2pdf") from exc


def format_size(size_bytes: int) -> str:
    """Форматирует размер в человекочитаемый вид."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def normalize_zip_member_name(name: str) -> str:
    """Пытается исправить частый кейс с битой кириллицей в ZIP.

    Иногда ZIP содержит имена в UTF-8, но флаг UTF-8 не выставлен,
    и при чтении они декодируются как cp437, что даёт "моджибейк" вида "╨...".
    В таком случае пробуем обратное преобразование: cp437 -> bytes -> utf-8.
    """

    # Быстрый хинт: такие символы очень характерны для UTF-8, прочитанного как cp437.
    if "╨" not in name and "╤" not in name:
        return name

    try:
        return name.encode("cp437").decode("utf-8")
    except Exception:
        return name


def is_ignored_zip_member(member_path: Path) -> bool:
    # macOS metadata
    if "__MACOSX" in member_path.parts:
        return True
    # AppleDouble resource forks
    if member_path.name.startswith("._"):
        return True
    return False


def safe_extract_zip(zip_path: Path, extract_dir: Path) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            normalized_name = normalize_zip_member_name(member.filename)
            member_path = Path(normalized_name)

            if is_ignored_zip_member(member_path):
                continue

            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError(f"Небезопасный путь в ZIP: {member.filename}")

            # Директории могут приходить отдельными записями
            if member.is_dir() or normalized_name.endswith("/"):
                (extract_dir / member_path).mkdir(parents=True, exist_ok=True)
                continue

            dest_path = extract_dir / member_path
            # Доп. защита от обхода путей (на случай странных разделителей/драйвов)
            try:
                resolved_dest = dest_path.resolve()
                resolved_root = extract_dir.resolve()
                if resolved_root not in resolved_dest.parents and resolved_dest != resolved_root:
                    raise RuntimeError(f"Небезопасный путь в ZIP: {member.filename}")
            except FileNotFoundError:
                # resolve() может падать, если часть пути не существует; создадим родителя ниже
                pass

            ensure_parent(dest_path)
            with zf.open(member, "r") as src, dest_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def convert_pdf_to_jpegs(src_path: Path, output_dir: Path, quality: int, dpi: int) -> list[Path]:
    require_pymupdf()
    import fitz

    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    with fitz.open(src_path) as doc:
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        for index, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            data = pix.tobytes("jpeg", jpg_quality=quality)
            dest = output_dir / f"page_{index:03d}.jpg"
            dest.write_bytes(data)
            created.append(dest)
    return created


def convert_jpeg_to_webp(src_path: Path, dest_path: Path, quality: int) -> None:
    require_pillow()
    from PIL import Image

    with Image.open(src_path) as img:
        img.save(dest_path, format="WEBP", quality=quality, method=6)


def convert_jpeg_to_avif(src_path: Path, dest_path: Path, quality: int) -> None:
    require_pillow()
    try:
        import pillow_avif  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Плагин pillow-avif-plugin не установлен.") from exc
    from PIL import Image

    with Image.open(src_path) as img:
        img.save(dest_path, format="AVIF", quality=quality)


def convert_jpeg_to_ico(src_path: Path, dest_path: Path, sizes: list[int]) -> None:
    require_pillow()
    from PIL import Image

    with Image.open(src_path) as img:
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        ico_sizes = [(size, size) for size in sizes]
        img.save(dest_path, format="ICO", sizes=ico_sizes)


def convert_jpegs_to_pdf(src_files: list[Path], dest_path: Path) -> None:
    require_img2pdf()
    import img2pdf

    if not src_files:
        raise RuntimeError("Не найдено JPEG/PNG файлов для сборки PDF")
    src_files_sorted = sorted(src_files, key=lambda p: p.name.lower())
    with dest_path.open("wb") as out_file:
        out_file.write(img2pdf.convert([str(path) for path in src_files_sorted]))


def collect_jpeg_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_JPEG]


def collect_pdf_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"]


def build_output_dir(input_path: Path, suffix: str) -> Path:
    return input_path.parent / f"{input_path.name}_{suffix}"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def zip_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(source_dir))


def process_pdf_to_jpeg(input_path: Path, quality: int, dpi: int) -> Path:
    if input_path.suffix.lower() == ".pdf":
        output_dir = input_path.parent / f"{input_path.stem}_jpeg_{dpi}dpi"
        created = convert_pdf_to_jpegs(input_path, output_dir, quality, dpi)
        if len(created) > 1:
            zip_path = input_path.parent / f"{input_path.stem}_jpeg_{dpi}dpi.zip"
            zip_directory(output_dir, zip_path)
            return zip_path
        return created[0]

    output_dir = build_output_dir(input_path, f"pdf_to_jpeg_{dpi}dpi")
    pdf_files = collect_pdf_files(input_path)
    if not pdf_files:
        raise RuntimeError("PDF файлы не найдены")
    for pdf in pdf_files:
        relative = pdf.relative_to(input_path)
        target_dir = output_dir / relative.with_suffix("")
        convert_pdf_to_jpegs(pdf, target_dir, quality, dpi)
    return output_dir


def process_jpeg_to_webp(input_path: Path, quality: int) -> Path:
    if input_path.suffix.lower() in SUPPORTED_JPEG:
        dest = input_path.with_suffix(".webp")
        convert_jpeg_to_webp(input_path, dest, quality)
        return dest

    output_dir = build_output_dir(input_path, f"webp_{quality}")
    jpg_files = collect_jpeg_files(input_path)
    if not jpg_files:
        raise RuntimeError("JPEG/PNG файлы не найдены")
    for src in jpg_files:
        relative = src.relative_to(input_path)
        dest = output_dir / relative.with_suffix(".webp")
        ensure_parent(dest)
        convert_jpeg_to_webp(src, dest, quality)
    return output_dir


def process_jpeg_to_avif(input_path: Path, quality: int) -> Path:
    if input_path.suffix.lower() in SUPPORTED_JPEG:
        dest = input_path.with_suffix(".avif")
        convert_jpeg_to_avif(input_path, dest, quality)
        return dest

    output_dir = build_output_dir(input_path, f"avif_{quality}")
    jpg_files = collect_jpeg_files(input_path)
    if not jpg_files:
        raise RuntimeError("JPEG/PNG файлы не найдены")
    for src in jpg_files:
        relative = src.relative_to(input_path)
        dest = output_dir / relative.with_suffix(".avif")
        ensure_parent(dest)
        convert_jpeg_to_avif(src, dest, quality)
    return output_dir


def process_jpeg_to_ico(input_path: Path, sizes: list[int]) -> Path:
    if input_path.suffix.lower() in SUPPORTED_JPEG:
        dest = input_path.with_suffix(".ico")
        convert_jpeg_to_ico(input_path, dest, sizes)
        return dest

    output_dir = build_output_dir(input_path, "ico")
    jpg_files = collect_jpeg_files(input_path)
    if not jpg_files:
        raise RuntimeError("JPEG/PNG файлы не найдены")
    for src in jpg_files:
        relative = src.relative_to(input_path)
        dest = output_dir / relative.with_suffix(".ico")
        ensure_parent(dest)
        convert_jpeg_to_ico(src, dest, sizes)
    return output_dir


def process_jpeg_to_pdf(input_path: Path, pdf_mode: str) -> Path:
    if input_path.suffix.lower() in SUPPORTED_JPEG:
        dest = input_path.with_suffix(".pdf")
        convert_jpegs_to_pdf([input_path], dest)
        return dest

    jpg_files = collect_jpeg_files(input_path)
    if not jpg_files:
        raise RuntimeError("JPEG/PNG файлы не найдены")

    if pdf_mode == "combine":
        dest = input_path.parent / f"{input_path.name}.pdf"
        convert_jpegs_to_pdf(jpg_files, dest)
        return dest

    output_dir = build_output_dir(input_path, "pdf")
    for src in jpg_files:
        relative = src.relative_to(input_path)
        dest = output_dir / relative.with_suffix(".pdf")
        ensure_parent(dest)
        convert_jpegs_to_pdf([src], dest)
    return output_dir


def handle_zip_input(input_path: Path, task: str, quality: int, dpi: int, pdf_mode: str, ico_sizes: list[int]) -> Path:
    with tempfile.TemporaryDirectory() as tmp_dir:
        temp_root = Path(tmp_dir)
        extracted_dir = temp_root / "input"
        output_dir = temp_root / "output"
        extracted_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_extract_zip(input_path, extracted_dir)

        if task == "pdf-to-jpeg":
            pdf_files = collect_pdf_files(extracted_dir)
            if not pdf_files:
                raise RuntimeError("PDF файлы не найдены в ZIP")
            for pdf in pdf_files:
                relative = pdf.relative_to(extracted_dir)
                target_dir = output_dir / relative.with_suffix("")
                convert_pdf_to_jpegs(pdf, target_dir, quality, dpi)
        elif task == "jpeg-to-pdf":
            jpg_files = collect_jpeg_files(extracted_dir)
            if not jpg_files:
                raise RuntimeError("JPEG/PNG файлы не найдены в ZIP")
            if pdf_mode == "combine":
                dest = output_dir / "combined.pdf"
                convert_jpegs_to_pdf(jpg_files, dest)
            else:
                for src in jpg_files:
                    relative = src.relative_to(extracted_dir)
                    dest = output_dir / relative.with_suffix(".pdf")
                    ensure_parent(dest)
                    convert_jpegs_to_pdf([src], dest)
        elif task == "jpeg-to-ico":
            jpg_files = collect_jpeg_files(extracted_dir)
            if not jpg_files:
                raise RuntimeError("JPEG/PNG файлы не найдены в ZIP")
            for src in jpg_files:
                relative = src.relative_to(extracted_dir)
                dest = output_dir / relative.with_suffix(".ico")
                ensure_parent(dest)
                convert_jpeg_to_ico(src, dest, ico_sizes)
        elif task == "jpeg-to-webp":
            jpg_files = collect_jpeg_files(extracted_dir)
            if not jpg_files:
                raise RuntimeError("JPEG/PNG файлы не найдены в ZIP")
            for src in jpg_files:
                relative = src.relative_to(extracted_dir)
                dest = output_dir / relative.with_suffix(".webp")
                ensure_parent(dest)
                convert_jpeg_to_webp(src, dest, quality)
        elif task == "jpeg-to-avif":
            jpg_files = collect_jpeg_files(extracted_dir)
            if not jpg_files:
                raise RuntimeError("JPEG/PNG файлы не найдены в ZIP")
            for src in jpg_files:
                relative = src.relative_to(extracted_dir)
                dest = output_dir / relative.with_suffix(".avif")
                ensure_parent(dest)
                convert_jpeg_to_avif(src, dest, quality)
        else:
            raise RuntimeError(f"Неизвестная задача: {task}")

        zip_path = input_path.parent / f"{input_path.stem}_{task}.zip"
        zip_directory(output_dir, zip_path)
        return zip_path


def main():
    parser = argparse.ArgumentParser(description="Конвертации PDF/JPEG без Telegram")
    parser.add_argument("input_path", type=Path, help="Путь к файлу, папке или ZIP")
    parser.add_argument(
        "--task",
        required=True,
        choices=["pdf-to-jpeg", "jpeg-to-pdf", "jpeg-to-ico", "jpeg-to-webp"],
        help="Тип конвертации",
    )
    parser.add_argument("--quality", type=int, default=85, help="Качество 1-100 (по умолчанию 85)")
    parser.add_argument("--dpi", type=int, default=150, help="DPI для PDF→JPEG (по умолчанию 150)")
    parser.add_argument(
        "--pdf-mode",
        choices=["combine", "per-file"],
        default="combine",
        help="Режим JPEG→PDF: один PDF (combine) или по файлу (per-file)",
    )
    parser.add_argument(
        "--ico-sizes",
        default="16,32,48,64,128,256",
        help="Размеры ICO через запятую (по умолчанию: 16,32,48,64,128,256)",
    )

    args = parser.parse_args()

    if not args.input_path.exists():
        print(f"Ошибка: путь '{args.input_path}' не существует")
        sys.exit(1)

    ico_sizes = [int(size) for size in args.ico_sizes.split(",") if size.strip()]
    if not ico_sizes:
        print("Ошибка: список размеров ICO пуст")
        sys.exit(1)

    input_path = args.input_path
    try:
        if input_path.suffix.lower() == ".zip":
            result = handle_zip_input(input_path, args.task, args.quality, args.dpi, args.pdf_mode, ico_sizes)
        else:
            if args.task == "pdf-to-jpeg":
                result = process_pdf_to_jpeg(input_path, args.quality, args.dpi)
            elif args.task == "jpeg-to-pdf":
                result = process_jpeg_to_pdf(input_path, args.pdf_mode)
            elif args.task == "jpeg-to-ico":
                result = process_jpeg_to_ico(input_path, ico_sizes)
            elif args.task == "jpeg-to-webp":
                result = process_jpeg_to_webp(input_path, args.quality)
            else:
                raise RuntimeError(f"Неизвестная задача: {args.task}")
    except RuntimeError as exc:
        print(f"Ошибка: {exc}")
        sys.exit(1)

    if result.is_dir():
        print(f"Готово: {result}")
    else:
        print(f"Готово: {result} ({format_size(result.stat().st_size)})")


if __name__ == "__main__":
    main()