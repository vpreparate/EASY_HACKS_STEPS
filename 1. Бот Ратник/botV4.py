import os
import platform
import subprocess
from pathlib import Path
import logging
import tempfile
import shutil
import asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_TOKEN = ''  # вставьте токен бота

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

user_paths = {}  # user_id -> текущий путь (str)
user_waiting_for_file = {}  # user_id -> bool, ждём ли файл
MAX_BUTTONS = 40  # ограничение кнопок в клавиатуре

def is_root_path(path_str):
    return path_str == 'ROOT'

def set_user_path(user_id, path_str):
    user_paths[user_id] = path_str

def get_user_path(user_id):
    if user_id not in user_paths:
        if platform.system() == 'Windows':
            user_paths[user_id] = 'ROOT'  # стартовый маркер для дисков
        else:
            user_paths[user_id] = str(Path.home())
    return user_paths[user_id]

async def build_keyboard(user_id):
    path_str = get_user_path(user_id)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)

    # Показываем диски Windows (если в корне)
    if platform.system() == 'Windows' and is_root_path(path_str):
        import string
        disks = [f"{d}:\\"
                 for d in string.ascii_uppercase
                 if Path(f"{d}:\\").exists()]
        for d in disks:
            kb.insert(types.KeyboardButton(f"📁 {d}"))
        return kb

    current_path = Path(path_str)
    kb.add(types.KeyboardButton("⬅️ Назад"))

    try:
        items = list(current_path.iterdir())
    except Exception:
        items = []

    folders = [i for i in items if i.is_dir()]
    files = [i for i in items if i.is_file()]

    total_items = len(folders) + len(files)

    # Обработка большого количества элементов
    if total_items > MAX_BUTTONS:
        if len(folders) > MAX_BUTTONS:
            # Очень много папок — показываем первые MAX_BUTTONS с кнопкой назад
            shown_folders = sorted(folders, key=lambda x: x.name)[:MAX_BUTTONS]
            for folder in shown_folders:
                kb.insert(types.KeyboardButton(f"📁 {folder.name}"))
            return kb
        else:
            # Много файлов — показываем только папки и кнопку для файлов
            for folder in sorted(folders, key=lambda x: x.name):
                kb.insert(types.KeyboardButton(f"📁 {folder.name}"))
            kb.add(types.KeyboardButton("📄 Показать файлы"))
            return kb
    else:
        # Всё помещается — показываем кнопки навигации и всё содержимое
        if current_path != current_path.anchor:
            kb.add(types.KeyboardButton("⬆️ Вверх"))
        for folder in sorted(folders, key=lambda x: x.name):
            kb.insert(types.KeyboardButton(f"📁 {folder.name}"))
        for file in sorted(files, key=lambda x: x.name):
            kb.insert(types.KeyboardButton(f"📄 {file.name}"))
        kb.add(types.KeyboardButton("⬆️ Загрузить папку"))
        kb.add(types.KeyboardButton("⬆️ Загрузить файл"))
        return kb

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    user_id = message.from_user.id
    if platform.system() == 'Windows':
        set_user_path(user_id, 'ROOT')
    else:
        set_user_path(user_id, str(Path.home()))
    user_waiting_for_file[user_id] = False
    kb = await build_keyboard(user_id)
    await message.answer("Выберите диск или папку:", reply_markup=kb)

@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def handle_document(message: types.Message):
    user_id = message.from_user.id
    if not user_waiting_for_file.get(user_id, False):
        await message.answer("Пожалуйста, нажмите '⬆️ Загрузить файл' перед отправкой файла.")
        return

    current_path_str = get_user_path(user_id)
    current_path = Path(current_path_str)
    document = message.document

    save_path = current_path / document.file_name

    try:
        file = await bot.get_file(document.file_id)
        await bot.download_file(file.file_path, destination=str(save_path))
        user_waiting_for_file[user_id] = False
        kb = await build_keyboard(user_id)
        await message.answer(f"Файл '{document.file_name}' успешно сохранён в папке:\n{current_path}", reply_markup=kb)
    except Exception as e:
        await message.answer(f"Ошибка сохранения файла: {e}")

@dp.message_handler(lambda message: message.text == "📄 Показать файлы")
async def show_files_only(message: types.Message):
    user_id = message.from_user.id
    current_path_str = get_user_path(user_id)
    current_path = Path(current_path_str)

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("⬅️ Назад"))

    try:
        items = list(current_path.iterdir())
    except Exception:
        items = []

    files = [i for i in items if i.is_file()]
    shown_files = sorted(files, key=lambda x: x.name)[:MAX_BUTTONS]

    for file in shown_files:
        kb.insert(types.KeyboardButton(f"📄 {file.name}"))

    if len(files) > MAX_BUTTONS:
        await message.answer("Слишком много файлов для отображения. Отображаются первые файлы.", reply_markup=kb)
    else:
        await message.answer("Файлы:", reply_markup=kb)

@dp.message_handler()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    current_path_str = get_user_path(user_id)

    if user_waiting_for_file.get(user_id, False):
        if message.content_type != 'document':
            await message.answer("Пожалуйста, отправьте файл.")
        return

    # Обработка выбора диска Windows
    if platform.system() == 'Windows' and is_root_path(current_path_str):
        if text and text.startswith("📁 ") and text[2:].endswith(":\\"):
            disk_path = text[2:]
            path_obj = Path(disk_path)
            if path_obj.exists():
                set_user_path(user_id, disk_path)
                kb = await build_keyboard(user_id)
                await message.answer(f"Вы выбрали диск {disk_path}", reply_markup=kb)
            else:
                await message.answer("Диск не доступен.")
        else:
            await message.answer("Пожалуйста, выберите дисковый раздел из списка.")
        return

    current_path = Path(current_path_str)

    # Навигация назад
    if text == "⬅️ Назад":
        set_user_path(user_id, 'ROOT' if platform.system() == 'Windows' else str(Path.home()))
        kb = await build_keyboard(user_id)
        await message.answer("Выберите диск или папку:", reply_markup=kb)
        return

    # Навигация вверх
    if text == "⬆️ Вверх":
        if platform.system() == 'Windows':
            if current_path == Path(current_path.anchor):
                set_user_path(user_id, 'ROOT')
                kb = await build_keyboard(user_id)
                await message.answer("Вернулись к выбору дисков.", reply_markup=kb)
                return
        else:
            home = Path.home()
            if current_path == home:
                await message.answer("Вы и так в домашней папке.")
                return
        set_user_path(user_id, str(current_path.parent))
        kb = await build_keyboard(user_id)
        await message.answer(f"Перешли в папку: {current_path.parent}", reply_markup=kb)
        return

    # Вход в папку
    if text and text.startswith("📁 "):
        folder_name = text[2:].strip()
        target_path = current_path / folder_name
        if target_path.exists() and target_path.is_dir():
            set_user_path(user_id, str(target_path))
            kb = await build_keyboard(user_id)
            await message.answer(f"Папка: {target_path}", reply_markup=kb)
        else:
            await message.answer("Папка не найдена.")
        return

    # Выбор файла для запуска/скачивания
    if text and text.startswith("📄 "):
        file_name = text[2:].strip()
        file_path = current_path / file_name
        if file_path.exists() and file_path.is_file():
            stat = file_path.stat()
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton("▶️ Запустить", callback_data=f"run|{file_path}"),
                InlineKeyboardButton("⬇️ Скачать", callback_data=f"download|{file_path}")
            )
            await message.answer(
                f"Файл: {file_path.name}\nРазмер: {stat.st_size} байт\nВыберите действие:",
                reply_markup=kb
            )
        else:
            await message.answer("Файл не найден.")
        return

    # Загрузка папки - архивировать и отправить
    if text == "⬆️ Загрузить папку":
        folder_path = current_path

        await message.answer("Архивирую папку, подождите, это может занять некоторое время...")

        async def archive_and_send():
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    archive_name = os.path.join(tmpdir, "archive")
                    shutil.make_archive(archive_name, 'zip', root_dir=folder_path)
                    zip_path = archive_name + '.zip'
                    await bot.send_document(message.chat.id, open(zip_path, 'rb'))
            except Exception as e:
                await message.answer(f"Ошибка архивации или отправки: {e}")

        asyncio.create_task(archive_and_send())
        return

    # Подготовка к загрузке файла
    if text == "⬆️ Загрузить файл":
        user_waiting_for_file[user_id] = True
        await message.answer("Пожалуйста, отправьте файл для загрузки.")
        return

    await message.answer("Неизвестная команда или ничего не выбрано.")

@dp.callback_query_handler(lambda c: c.data and (c.data.startswith("run|") or c.data.startswith("download|")))
async def handle_callback(call: types.CallbackQuery):
    action, path_str = call.data.split('|', 1)
    path = Path(path_str)
    user_id = call.from_user.id
    current_path_str = get_user_path(user_id)
    current_path = Path(current_path_str)

    try:
        path.relative_to(current_path)
    except Exception:
        await call.answer("Доступ запрещён.", show_alert=True)
        return

    if not path.exists() or not path.is_file():
        await call.answer("Файл не найден.", show_alert=True)
        return

    if action == "run":
        try:
            if platform.system() == 'Windows':
                os.startfile(str(path))
            else:
                subprocess.Popen([str(path)])
            await call.answer("Файл запущен.")
        except Exception as e:
            await call.answer(f"Ошибка запуска: {e}", show_alert=True)

    elif action == "download":
        try:
            await bot.send_document(call.from_user.id, open(path, 'rb'))
            await call.answer("Файл отправлен.")
        except Exception as e:
            await call.answer(f"Ошибка отправки: {e}", show_alert=True)

if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp)
    
