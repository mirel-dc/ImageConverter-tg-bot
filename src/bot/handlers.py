from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import CONVERT_TIMEOUT_SECONDS, MAX_DOWNLOAD_BYTES, MAX_UPLOAD_BYTES
from core.config import DEFAULT_DPI, DEFAULT_ICO_SIZES, DEFAULT_PDF_MODE, DEFAULT_QUALITY
from core.converter import convert
from core.image_converter import format_size

logger = logging.getLogger(__name__)

router = Router()


class ConvertStates(StatesGroup):
    waiting_for_task = State()
    waiting_for_quality = State()
    waiting_for_dpi = State()
    waiting_for_pdf_mode = State()
    waiting_for_ico_sizes = State()


def build_task_keyboard(file_ext: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    if file_ext == ".pdf":
        kb.button(text="PDF → JPEG", callback_data="task:pdf-to-jpeg")
    elif file_ext in {".jpg", ".jpeg", ".png"}:
        kb.button(text="JPEG/PNG → PDF", callback_data="task:jpeg-to-pdf")
        kb.button(text="JPEG/PNG → ICO", callback_data="task:jpeg-to-ico")
        kb.button(text="JPEG/PNG → WebP", callback_data="task:jpeg-to-webp")
    elif file_ext == ".zip":
        kb.button(text="PDF → JPEG", callback_data="task:pdf-to-jpeg")
        kb.button(text="JPEG → PDF", callback_data="task:jpeg-to-pdf")
        kb.button(text="JPEG → ICO", callback_data="task:jpeg-to-ico")
        kb.button(text="JPEG → WebP", callback_data="task:jpeg-to-webp")
    kb.adjust(2)
    return kb


def build_quality_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="50 — мин. размер", callback_data="quality:50")
    kb.button(text="75", callback_data="quality:75")
    kb.button(text="95", callback_data="quality:95")
    kb.button(text="100 — по умолчанию", callback_data="quality:100")
    kb.button(text="По умолчанию", callback_data=f"quality:{DEFAULT_QUALITY}")
    kb.adjust(2)
    return kb


def build_dpi_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="72", callback_data="dpi:72")
    kb.button(text="150 — по умолчанию", callback_data="dpi:150")
    kb.button(text="300", callback_data="dpi:300")
    kb.button(text="По умолчанию", callback_data=f"dpi:{DEFAULT_DPI}")
    kb.adjust(2)
    return kb


def build_pdf_mode_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="Один PDF (combine)", callback_data="pdf-mode:combine")
    kb.button(text="По файлу (per-file)", callback_data="pdf-mode:per-file")
    kb.button(text="По умолчанию", callback_data=f"pdf-mode:{DEFAULT_PDF_MODE}")
    kb.adjust(1)
    return kb


def build_ico_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="Стандартные размеры", callback_data="ico:default")
    kb.button(text="Указать вручную", callback_data="ico:custom")
    kb.adjust(1)
    return kb


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    text = (
        "Привет! Я конвертирую файлы. Отправь мне PDF, JPEG/PNG или ZIP-архив.\n\n"
        "Поддерживаемые конвертации:\n"
        "• PDF → JPEG (quality, dpi)\n"
        "• JPEG/PNG → PDF (combine/per-file)\n"
        "• JPEG/PNG → ICO (размеры)\n"
        "• JPEG/PNG → WebP (quality)"
    )
    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "Как пользоваться ботом:\n"
        "1) Отправьте файл как документ (PDF/JPEG/PNG/ZIP).\n"
        "2) Выберите нужную конвертацию кнопкой.\n"
        "3) При необходимости выберите параметры (quality/dpi/режим/размеры).\n\n"
        "Quality: 1–100, DPI: 72/150/300.\n"
        "Если отправляете фото как картинку, Telegram сжимает его — лучше отправить как файл."
    )
    await message.answer(text)


@router.message(F.photo)
async def photo_warning(message: Message) -> None:
    await message.answer(
        "Похоже, вы отправили фото как изображение. Telegram сжимает такие файлы. "
        "Пожалуйста, отправьте фото как документ (скрепка → файл)."
    )


@router.message(F.document)
async def document_handler(message: Message, state: FSMContext) -> None:
    document = message.document
    if document is None:
        return

    if document.file_size and document.file_size > MAX_DOWNLOAD_BYTES:
        await message.answer(
            f"Файл слишком большой для скачивания: {format_size(document.file_size)}. "
            f"Максимум {format_size(MAX_DOWNLOAD_BYTES)}."
        )
        return

    file_name = document.file_name or "file"
    file_ext = Path(file_name).suffix.lower()

    if file_ext not in {".pdf", ".jpg", ".jpeg", ".png", ".zip"}:
        await message.answer("Поддерживаются только PDF, JPEG/PNG или ZIP-архивы.")
        return

    await state.set_state(ConvertStates.waiting_for_task)
    await state.update_data(
        file_id=document.file_id,
        file_name=file_name,
        file_size=document.file_size or 0,
        file_ext=file_ext,
    )

    kb = build_task_keyboard(file_ext)
    await message.answer("Что сделать с файлом?", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("task:"))
async def task_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    task = callback.data.split(":", 1)[1]
    await state.update_data(task=task)

    if task == "pdf-to-jpeg":
        await state.set_state(ConvertStates.waiting_for_quality)
        await callback.message.answer("Выберите качество JPEG:", reply_markup=build_quality_keyboard().as_markup())
        return

    if task == "jpeg-to-webp":
        await state.set_state(ConvertStates.waiting_for_quality)
        await callback.message.answer("Выберите качество WebP:", reply_markup=build_quality_keyboard().as_markup())
        return

    if task == "jpeg-to-ico":
        await state.set_state(ConvertStates.waiting_for_ico_sizes)
        await callback.message.answer("Выберите размеры ICO:", reply_markup=build_ico_keyboard().as_markup())
        return

    if task == "jpeg-to-pdf":
        await state.set_state(ConvertStates.waiting_for_pdf_mode)
        await callback.message.answer("Выберите режим JPEG/PNG → PDF:", reply_markup=build_pdf_mode_keyboard().as_markup())
        return

    await callback.message.answer("Неизвестная задача конвертации.")


@router.callback_query(ConvertStates.waiting_for_quality, F.data.startswith("quality:"))
async def quality_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    quality = int(callback.data.split(":", 1)[1])
    await state.update_data(quality=quality)

    data = await state.get_data()
    task = data.get("task")
    if task == "pdf-to-jpeg":
        await state.set_state(ConvertStates.waiting_for_dpi)
        await callback.message.answer("Выберите DPI:", reply_markup=build_dpi_keyboard().as_markup())
        return

    await perform_conversion(callback.message, state)


@router.callback_query(ConvertStates.waiting_for_dpi, F.data.startswith("dpi:"))
async def dpi_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    dpi = int(callback.data.split(":", 1)[1])
    await state.update_data(dpi=dpi)
    await perform_conversion(callback.message, state)


@router.callback_query(ConvertStates.waiting_for_pdf_mode, F.data.startswith("pdf-mode:"))
async def pdf_mode_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    pdf_mode = callback.data.split(":", 1)[1]
    await state.update_data(pdf_mode=pdf_mode)
    await perform_conversion(callback.message, state)


@router.callback_query(ConvertStates.waiting_for_ico_sizes, F.data == "ico:default")
async def ico_default(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(ico_sizes=DEFAULT_ICO_SIZES)
    await perform_conversion(callback.message, state)


@router.callback_query(ConvertStates.waiting_for_ico_sizes, F.data == "ico:custom")
async def ico_custom(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer("Отправьте размеры через запятую, например: 16,32,48")


@router.message(ConvertStates.waiting_for_ico_sizes)
async def ico_custom_sizes(message: Message, state: FSMContext) -> None:
    raw = message.text or ""
    try:
        sizes = [int(size.strip()) for size in raw.split(",") if size.strip()]
    except ValueError:
        await message.answer("Не удалось распознать размеры. Пример: 16,32,48")
        return

    if not sizes:
        await message.answer("Список размеров пуст. Пример: 16,32,48")
        return

    await state.update_data(ico_sizes=sizes)
    await perform_conversion(message, state)


async def perform_conversion(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()

    file_id = data.get("file_id")
    file_name = data.get("file_name")
    if not file_id or not file_name:
        await message.answer("Не удалось получить данные файла. Попробуйте ещё раз.")
        return

    options = {
        "quality": data.get("quality", DEFAULT_QUALITY),
        "dpi": data.get("dpi", DEFAULT_DPI),
        "pdf_mode": data.get("pdf_mode", DEFAULT_PDF_MODE),
        "ico_sizes": data.get("ico_sizes", DEFAULT_ICO_SIZES),
    }

    task = data.get("task")
    if not task:
        await message.answer("Не выбрана задача конвертации.")
        return

    bot: Bot = message.bot
    await bot.send_chat_action(message.chat.id, "upload_document")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            input_path = temp_root / file_name
            file = await bot.get_file(file_id)
            await bot.download(file, destination=input_path)

            result_path = await asyncio.wait_for(
                convert(input_path, task, options),
                timeout=CONVERT_TIMEOUT_SECONDS,
            )

            if result_path.stat().st_size > MAX_UPLOAD_BYTES:
                await message.answer(
                    f"Результат слишком большой для отправки: {format_size(result_path.stat().st_size)}. "
                    f"Максимум {format_size(MAX_UPLOAD_BYTES)}."
                )
                return

            before_size = input_path.stat().st_size
            after_size = result_path.stat().st_size
            caption = f"Готово! {format_size(before_size)} → {format_size(after_size)}"

            await message.answer_document(FSInputFile(result_path), caption=caption)
    except asyncio.TimeoutError:
        await message.answer("Превышен таймаут конвертации. Попробуйте файл поменьше.")
    except RuntimeError as exc:
        await message.answer(str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка конвертации")
        await message.answer(f"Неожиданная ошибка: {exc}")