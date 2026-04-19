from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from core.settings import settings
from core.image_converter import (
    handle_zip_input,
    process_jpeg_compress,
    process_jpeg_to_avif,
    process_jpeg_to_ico,
    process_jpeg_to_pdf,
    process_jpeg_to_webp,
    process_pdf_to_jpeg,
    zip_directory,
)


async def convert(file_path: Path, task: str, options: dict) -> Path:
    return await asyncio.to_thread(_convert_sync, file_path, task, options)


def _convert_sync(file_path: Path, task: str, options: dict) -> Path:
    input_path = Path(file_path)
    quality = int(options.get("quality", settings.default_quality))
    dpi = int(options.get("dpi", settings.default_dpi))
    pdf_mode = options.get("pdf_mode", settings.default_pdf_mode)
    ico_sizes = options.get("ico_sizes", settings.default_ico_sizes)

    if isinstance(ico_sizes, str):
        ico_sizes = [int(size) for size in ico_sizes.split(",") if size.strip()]

    if not ico_sizes:
        raise RuntimeError("Список размеров ICO пуст")

    if not input_path.exists():
        raise RuntimeError("Файл не найден")

    with tempfile.TemporaryDirectory() as tmp_dir:
        temp_root = Path(tmp_dir)
        temp_input = temp_root / input_path.name
        if input_path.is_dir():
            shutil.copytree(input_path, temp_input)
        else:
            shutil.copy2(input_path, temp_input)

        try:
            if temp_input.suffix.lower() == ".zip":
                result = handle_zip_input(temp_input, task, quality, dpi, pdf_mode, ico_sizes)
            else:
                if task == "pdf-to-jpeg":
                    result = process_pdf_to_jpeg(temp_input, quality, dpi)
                elif task == "jpeg-to-pdf":
                    result = process_jpeg_to_pdf(temp_input, pdf_mode)
                elif task == "jpeg-to-ico":
                    result = process_jpeg_to_ico(temp_input, ico_sizes)
                elif task == "jpeg-to-webp":
                    result = process_jpeg_to_webp(temp_input, quality)
                elif task == "jpeg-to-avif":
                    result = process_jpeg_to_avif(temp_input, quality)
                elif task == "jpeg-compress":
                    result = process_jpeg_compress(temp_input, quality)
                else:
                    raise RuntimeError("Неизвестная задача конвертации")
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Ошибка конвертации: {exc}") from exc

        if result.is_dir():
            output_path = input_path.parent / f"{input_path.stem}_{task}.zip"
            zip_directory(result, output_path)
            return output_path

        output_path = input_path.parent / result.name
        shutil.copy2(result, output_path)
        return output_path