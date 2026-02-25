from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message, TelegramObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.converter import convert
from core.image_converter import format_size
from core.settings import settings

logger = logging.getLogger(__name__)


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: callable,
        event: TelegramObject,
        data: dict[str, any],
    ) -> any:
        if not settings.allowed_users:
            return await handler(event, data)

        user = data.get("event_from_user")
        if user and user.id in settings.allowed_users:
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer("У вас нет доступа к этому боту.")
        elif isinstance(event, CallbackQuery):
            await event.answer("Доступ запрещен.", show_alert=True)
        return


router = Router()
router.message.middleware(AccessMiddleware())
router.callback_query.middleware(AccessMiddleware())


class ConvertStates(StatesGroup):
    waiting_for_task = State()
    waiting_for_quality = State()
    waiting_for_dpi = State()
    waiting_for_pdf_mode = State()
    waiting_for_ico_sizes = State()


def build_task_keyboard(file_ext: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    if file_ext == ".pdf":
        kb.button(text="PDF → JPG", callback_data="task:pdf-to-jpeg")
    elif file_ext in {".jpg", ".jpeg", ".png"}:
        kb.button(text="JPG/PNG → PDF", callback_data="task:jpeg-to-pdf")
        kb.button(text="JPG/PNG → ICO", callback_data="task:jpeg-to-ico")
        kb.button(text="JPG/PNG → WebP", callback_data="task:jpeg-to-webp")
        kb.button(text="JPG/PNG → AVIF", callback_data="task:jpeg-to-avif")
    elif file_ext == ".zip":
        kb.button(text="PDF → JPG", callback_data="task:pdf-to-jpeg")
        kb.button(text="JPG/PNG → PDF", callback_data="task:jpeg-to-pdf")
        kb.button(text="JPG/PNG → ICO", callback_data="task:jpeg-to-ico")
        kb.button(text="JPG/PNG → WebP", callback_data="task:jpeg-to-webp")
        kb.button(text="JPG/PNG → AVIF", callback_data="task:jpeg-to-avif")
    kb.adjust(2)
    return kb


def build_quality_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    # Диапазоны качества: 50 / 75 / 85 / 95 / 100 (по умолчанию)
    kb.button(text="50 — меньше размер", callback_data="quality:50")
    kb.button(text="75 — баланс", callback_data="quality:75")
    kb.button(text="85 — хорошее", callback_data="quality:85")
    kb.button(text="95 — почти без потерь", callback_data="quality:95")
    default_text = "100 — по умолчанию" if settings.default_quality == 100 else "100"
    kb.button(text=default_text, callback_data="quality:100")
    kb.adjust(2)
    return kb


def build_dpi_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="72", callback_data="dpi:72")
    default_text = "150 — по умолчанию" if settings.default_dpi == 150 else "150"
    kb.button(text=default_text, callback_data="dpi:150")
    kb.button(text="300", callback_data="dpi:300")
    kb.adjust(2)
    return kb


def build_pdf_mode_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    combine_text = "Один PDF" + (" — по умолчанию" if settings.default_pdf_mode == "combine" else "")
    per_file_text = "Отдельный PDF на каждый файл" + (
        " — по умолчанию" if settings.default_pdf_mode == "per-file" else ""
    )
    kb.button(text=combine_text, callback_data="pdf-mode:combine")
    kb.button(text=per_file_text, callback_data="pdf-mode:per-file")
    kb.adjust(1)
    return kb


def build_ico_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="Стандартные размеры", callback_data="ico:default")
    kb.button(text="Указать вручную", callback_data="ico:custom")
    kb.adjust(1)
    return kb


def build_post_result_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="⚙️ Изменить параметры", callback_data="post:params")
    kb.button(text="🔁 Повторить", callback_data="post:repeat")
    kb.button(text="🆕 Новый файл", callback_data="post:reset")
    kb.adjust(1)
    return kb


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    text = (
        "Привет! Я — бот‑конвертер файлов.\n"
        "Пришлите **PDF**, **JPG/PNG** или **ZIP** — я предложу варианты и сделаю конвертацию.\n\n"
        "✨ Что умею:\n"
        "• PDF → JPG (качество, DPI)\n"
        "• JPG/PNG → PDF (один файл / отдельные)\n"
        "• JPG/PNG → ICO (размеры)\n"
        "• JPG/PNG → WebP (качество)\n"
        "• JPG/PNG → AVIF (качество)\n\n"
        "💡 Совет: если отправить изображение как «Фото», Telegram может сжать его.\n"
        "Чтобы сохранить качество — отправляйте как **Файл**."
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "Как пользоваться ботом:\n"
        "1) Отправьте файл (PDF/JPG/PNG/ZIP).\n"
        "2) Выберите действие кнопкой.\n"
        "3) Если нужно — выберите параметры (качество/DPI/режим/размеры).\n\n"
        "Качество (presets): 50 / 75 / 85 / 95 / 100 (по умолчанию).\n"
        "DPI (presets): 72 / 150 (по умолчанию) / 300."
    )
    await message.answer(text)


@router.message(F.photo)
async def photo_handler(message: Message, state: FSMContext) -> None:
    # Берём крупнейшую версию фото
    if not message.photo:
        return
    photo = message.photo[-1]
    file_id = photo.file_id
    file_size = photo.file_size or 0
    # У фото нет имени файла — используем дефолт
    file_name = "photo.jpg"
    file_ext = ".jpg"

    await state.update_data(
        file_id=file_id,
        file_name=file_name,
        file_size=file_size,
        file_ext=file_ext,
    )

    kb = build_task_keyboard(file_ext)
    await message.answer("Что сделать с фото?", reply_markup=kb.as_markup())
    await state.set_state(ConvertStates.waiting_for_task)


@router.message(F.document)
async def document_handler(message: Message, state: FSMContext) -> None:
    document = message.document
    if document is None:
        return

    if document.file_size and document.file_size > settings.max_download_bytes:
        await message.answer(
            f"Файл слишком большой для скачивания: {format_size(document.file_size)}. "
            f"Максимум {format_size(settings.max_download_bytes)}."
        )
        return

    file_name = document.file_name or "file"
    file_ext = Path(file_name).suffix.lower()

    if file_ext not in {".pdf", ".jpg", ".jpeg", ".png", ".zip"}:
        await message.answer("Поддерживаются только PDF, JPG/PNG или ZIP-архивы.")
        return

    await state.update_data(
        file_id=document.file_id,
        file_name=file_name,
        file_size=document.file_size or 0,
        file_ext=file_ext,
    )

    kb = build_task_keyboard(file_ext)
    await message.answer("Что сделать с файлом?", reply_markup=kb.as_markup())
    await state.set_state(ConvertStates.waiting_for_task)


@router.callback_query(F.data.startswith("task:"))
async def task_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    task = callback.data.split(":", 1)[1]
    await state.update_data(task=task)

    if task == "pdf-to-jpeg":
        await state.set_state(ConvertStates.waiting_for_quality)
        await callback.message.answer("Выберите качество JPG:", reply_markup=build_quality_keyboard().as_markup())
        return

    if task == "jpeg-to-webp":
        await state.set_state(ConvertStates.waiting_for_quality)
        await callback.message.answer("Выберите качество WebP:", reply_markup=build_quality_keyboard().as_markup())
        return

    if task == "jpeg-to-avif":
        await state.set_state(ConvertStates.waiting_for_quality)
        await callback.message.answer("Выберите качество AVIF:", reply_markup=build_quality_keyboard().as_markup())
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
    await state.update_data(ico_sizes=settings.default_ico_sizes)
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


@router.callback_query(F.data == "post:reset")
async def post_reset(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer("Сбросил контекст. Отправьте новый файл (PDF/JPG/PNG/ZIP).")


@router.callback_query(F.data == "post:repeat")
async def post_repeat(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await perform_conversion(callback.message, state)


@router.callback_query(F.data == "post:params")
async def post_params(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    task = data.get("task")
    if not task:
        await callback.message.answer("Сначала выберите задачу конвертации.")
        return

    if task == "pdf-to-jpeg":
        await state.set_state(ConvertStates.waiting_for_quality)
        await callback.message.answer("Выберите качество JPG:", reply_markup=build_quality_keyboard().as_markup())
        return

    if task in {"jpeg-to-webp", "jpeg-to-avif"}:
        await state.set_state(ConvertStates.waiting_for_quality)
        fmt = "WebP" if task == "jpeg-to-webp" else "AVIF"
        await callback.message.answer(f"Выберите качество {fmt}:", reply_markup=build_quality_keyboard().as_markup())
        return

    if task == "jpeg-to-pdf":
        await state.set_state(ConvertStates.waiting_for_pdf_mode)
        await callback.message.answer(
            "Выберите режим JPEG/PNG → PDF:", reply_markup=build_pdf_mode_keyboard().as_markup()
        )
        return

    if task == "jpeg-to-ico":
        await state.set_state(ConvertStates.waiting_for_ico_sizes)
        await callback.message.answer("Выберите размеры ICO:", reply_markup=build_ico_keyboard().as_markup())
        return

    await callback.message.answer("Неизвестная задача конвертации.")


async def perform_conversion(message: Message, state: FSMContext) -> None:
    data = await state.get_data()

    file_id = data.get("file_id")
    file_name = data.get("file_name")
    if not file_id or not file_name:
        await message.answer("Не удалось получить данные файла. Попробуйте ещё раз.")
        return

    options = {
        "quality": data.get("quality", settings.default_quality),
        "dpi": data.get("dpi", settings.default_dpi),
        "pdf_mode": data.get("pdf_mode", settings.default_pdf_mode),
        "ico_sizes": data.get("ico_sizes", settings.default_ico_sizes),
    }

    task = data.get("task")
    if not task:
        await message.answer("Не выбрана задача конвертации.")
        return

    def pretty_task(task_id: str) -> str:
        return {
            "pdf-to-jpeg": "PDF → JPG",
            "jpeg-to-pdf": "JPG/PNG → PDF",
            "jpeg-to-ico": "JPG/PNG → ICO",
            "jpeg-to-webp": "JPG/PNG → WebP",
            "jpeg-to-avif": "JPG/PNG → AVIF",
        }.get(task_id, task_id)

    def output_format(task_id: str, file_name_value: str) -> str:
        if task_id == "pdf-to-jpeg":
            return "JPG (архив ZIP)"
        if task_id == "jpeg-to-pdf":
            return "PDF"
        if task_id == "jpeg-to-ico":
            return "ICO"
        if task_id == "jpeg-to-webp":
            return "WebP"
        if task_id == "jpeg-to-avif":
            return "AVIF"
        # Для ZIP входа результат часто тоже ZIP
        if Path(file_name_value).suffix.lower() == ".zip":
            return "ZIP"
        return "файл"

    bot: Bot = message.bot
    await bot.send_chat_action(message.chat.id, "upload_document")

    # Сообщение прогресса + периодические апдейты
    progress_msg: Message | None = None
    progress_running = True

    async def progress_updater() -> None:
        nonlocal progress_msg, progress_running
        try:
            dots = 0
            while progress_running:
                fmt = output_format(task, file_name)
                text = (
                    f"⌛ Конвертирую ({pretty_task(task)})\n"
                    f"Формат результата: **{fmt}**\n\n"
                    "Пожалуйста, подождите — после конвертации начнётся загрузка файла" + "." * dots
                )
                if progress_msg is None:
                    progress_msg = await message.answer(text, parse_mode="Markdown")
                else:
                    try:
                        await message.bot.edit_message_text(
                            chat_id=message.chat.id,
                            message_id=progress_msg.message_id,
                            text=text,
                            parse_mode="Markdown",
                        )
                    except Exception:
                        # Игнорируем ошибки правок
                        pass
                dots = (dots + 1) % 4
                await asyncio.sleep(settings.progress_update_seconds)
        except Exception:
            logger.exception("Ошибка обновления прогресса")

    updater_task = asyncio.create_task(progress_updater())

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            input_path = temp_root / file_name
            file = await bot.get_file(file_id)
            await bot.download(file, destination=input_path)

            result_path = await asyncio.wait_for(
                convert(input_path, task, options),
                timeout=settings.convert_timeout_seconds,
            )

            # Останавливаем прогресс
            progress_running = False
            try:
                await updater_task
            except Exception:
                pass
            if progress_msg is not None:
                try:
                    await message.bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=progress_msg.message_id,
                        text="✅ Готово! Начинаю загрузку результата…",
                    )
                except Exception:
                    pass

            if result_path.stat().st_size > settings.max_upload_bytes:
                await message.answer(
                    f"Результат слишком большой для отправки: {format_size(result_path.stat().st_size)}. "
                    f"Максимум {format_size(settings.max_upload_bytes)}."
                )
                return

            before_size = input_path.stat().st_size
            after_size = result_path.stat().st_size
            fmt = output_format(task, file_name)
            caption = (
                "✅ Готово!\n"
                f"Результат: {fmt}\n"
                f"Размер: {format_size(before_size)} → {format_size(after_size)}"
            )

            await message.answer_document(FSInputFile(result_path), caption=caption)
            await message.answer(
                "Хотите повторить конвертацию или поменять параметры?",
                reply_markup=build_post_result_keyboard().as_markup(),
            )
    except asyncio.TimeoutError:
        progress_running = False
        try:
            await updater_task
        except Exception:
            pass
        tip = (
            "Превышен таймаут конвертации. Попробуйте снизить DPI или качество, "
            "а также уменьшить размер входного файла."
        )
        if progress_msg is not None:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=progress_msg.message_id,
                    text=f"⏲️ {tip}",
                )
            except Exception:
                await message.answer(tip)
        else:
            await message.answer(tip)
    except RuntimeError as exc:
        progress_running = False
        try:
            await updater_task
        except Exception:
            pass
        if progress_msg is not None:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=progress_msg.message_id,
                    text=f"❌ {exc}",
                )
            except Exception:
                await message.answer(str(exc))
        else:
            await message.answer(str(exc))
    except Exception as exc:  # noqa: BLE001
        progress_running = False
        try:
            await updater_task
        except Exception:
            pass
        logger.exception("Ошибка конвертации")
        if progress_msg is not None:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=progress_msg.message_id,
                    text=f"❌ Неожиданная ошибка: {exc}",
                )
            except Exception:
                await message.answer(f"Неожиданная ошибка: {exc}")
        else:
            await message.answer(f"Неожиданная ошибка: {exc}")