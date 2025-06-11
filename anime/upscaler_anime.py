import os
import subprocess
import sys

def print_step(msg):
    print(f"\n[✔] {msg}")

def print_error(msg):
    print(f"\n❌ {msg}")
    sys.exit(1)

# Підготовка директорій
print_step("Підготовка директорій...")
os.makedirs("frames", exist_ok=True)
os.makedirs("upscaled", exist_ok=True)

# Витяг кадрів з відео
print_step("Витяг кадрів з відео...")
result = subprocess.run([
    "ffmpeg", "-y", "-i", "myvideo.mp4", "frames/frame_%05d.png"
], capture_output=True, text=True)
if result.returncode != 0:
    print_error(f"Помилка під час витягування кадрів:\n{result.stderr}")

# Перевірка Real-ESRGAN
print_step("Перевірка середовища Real-ESRGAN...")

venv_python = os.path.join("Real-ESRGAN", ".venv", "Scripts", "python.exe") if os.name == "nt" else os.path.join("Real-ESRGAN", ".venv", "bin", "python")
realesrgan_script = os.path.join("Real-ESRGAN", "inference_realesrgan.py")

model_file_name = "realesr-animevideov3.pth"
model_path = os.path.join("Real-ESRGAN", "weights", model_file_name)

if not os.path.exists(venv_python):
    print_error("Не знайдено Real-ESRGAN venv! Очікується Real-ESRGAN/.venv/bin/python")

if not os.path.exists(realesrgan_script):
    print_error("Не знайдено файл inference_realesrgan.py у папці Real-ESRGAN.")

if not os.path.exists(model_path):
    print_error(f"Модель {model_file_name} не знайдена в Real-ESRGAN/weights/. Скопіюй її туди.")

# Перевірка CUDA
print_step("Перевірка доступності CUDA в середовищі Real-ESRGAN...")

check_cuda = subprocess.run([
    venv_python, "-c", "import torch; print(torch.cuda.is_available())"
], capture_output=True, text=True)

print(f"CUDA доступна: {check_cuda.stdout.strip()}")
if "True" not in check_cuda.stdout:
    print("⚠️  Увага: CUDA недоступна. Real-ESRGAN буде використовувати CPU (повільно).")

# Запуск апскейлу з новою моделлю
print_step("Запуск апскейлу через Real-ESRGAN...")

result = subprocess.run([
    venv_python,
    realesrgan_script,
    "-i", "frames",
    "-o", "upscaled",
    "-n", model_file_name.replace(".pth", "")
], capture_output=True, text=True)

if result.returncode != 0:
    print_error(f"Помилка під час апскейлу кадрів:\n{result.stderr}")

# Збирання відео назад
print_step("Збирання апскейлених кадрів у відео...")

first_frame = os.path.join("upscaled", "frame_00001_out.png")
if not os.path.exists(first_frame):
    print_error("Не знайдено жодного апскейленого кадру. Real-ESRGAN не створив файлів?")

result = subprocess.run([
    "ffmpeg", "-y", "-framerate", "23.98", "-i", "upscaled/frame_%05d_out.png",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "upscaled_output.mp4"
], capture_output=True, text=True)

if result.returncode != 0:
    print_error(f"Помилка при створенні фінального відео:\n{result.stderr}")

print_step("Готово! Відео збережено як: upscaled_output.mp4")
