import os
import subprocess
import sys
import math

# |-----------base-----------|
def print_step(msg):
    print(f"\n[✔] {msg}")

def print_error(msg):
    print(f"\n❌ {msg}")
    sys.exit(1)

print_step("Підготовка директорій...")
os.makedirs("frames", exist_ok=True)
os.makedirs("upscaled", exist_ok=True)
os.makedirs("res", exist_ok=True)
[os.remove(f"frames/{f}") for f in os.listdir("frames") if os.path.isfile(f"frames/{f}")]
[os.remove(f"upscaled/{f}") for f in os.listdir("upscaled") if os.path.isfile(f"upscaled/{f}")]

# |-----------models-----------|
model_categories = {
    "🟢 Універсальні": {
        "RealESRGAN_x2plus": {
            "2x": "RealESRGAN_x2plus.pth",
            "8x": "RealESRGAN_x2plus.pth",
            "16x": "RealESRGAN_x2plus.pth",
        },
        "RealESRGAN_x4plus": {
            "4x": "RealESRGAN_x4plus.pth",
            "8x": "RealESRGAN_x4plus.pth",
            "16x": "RealESRGAN_x4plus.pth",
        },
    },
    "🟣 Аніме / 2D": {
        "RealESRGAN_x4plus_anime_6B": {
            "4x": "RealESRGAN_x4plus_anime_6B.pth",
            "8x": "RealESRGAN_x4plus_anime_6B.pth",
            "16x": "RealESRGAN_x4plus_anime_6B.pth",
        },
        "realesr-animevideov3": {
            "4x": "realesr-animevideov3.pth",
            "8x": "realesr-animevideov3.pth",
            "16x": "realesr-animevideov3.pth",
        },
    },
}

# |-----------menu-----------|
print("\nОберіть модель та масштаб:")
univ_options = []
anime_options = []
for model_name, scales in model_categories["🟢 Універсальні"].items():
    for scale_key in scales.keys():
        univ_options.append((model_name, scale_key))
for model_name, scales in model_categories["🟣 Аніме / 2D"].items():
    for scale_key in scales.keys():
        anime_options.append((model_name, scale_key))
max_len = max(len(univ_options), len(anime_options))
option_map = {}
index = 1
col_width = 40
print("Універсальні".center(col_width) + "Аніме / 2D".center(col_width))
print("-" * col_width + "-" * col_width)
for i in range(max_len):
    left_str = ''
    right_str = ''
    if i < len(univ_options):
        model_name, scale_key = univ_options[i]
        left_str = f"{index}. {model_name} - {scale_key}"
        option_map[index] = ("🟢 Універсальні", model_name, scale_key)
        index += 1
    left_str = left_str.ljust(col_width)
    if i < len(anime_options):
        model_name, scale_key = anime_options[i]
        right_str = f"{index}. {model_name} - {scale_key}"
        option_map[index] = ("🟣 Аніме / 2D", model_name, scale_key)
        index += 1
    print(left_str + right_str)

try:
    choice = int(input("\nВведи номер опції (модель + масштаб): "))
    category, model_name, target_scale = option_map[choice]
except (ValueError, KeyError):
    print_error("Неправильний вибір моделі або масштабу.")

model_file_name = model_categories[category][model_name][target_scale]
available_scales = list(model_categories[category][model_name].keys())
base_scale = min(int(s.replace('x','')) for s in available_scales)
target_scale_int = int(target_scale.replace("x", ""))

model_path = os.path.join("Real-ESRGAN", "weights", model_file_name)
if not os.path.exists(model_path):
    print_error(f"Модель {model_file_name} не знайдена в Real-ESRGAN/weights/")

# |-----------frame-----------|
print_step("Витяг кадрів з відео...")
result = subprocess.run([
    "ffmpeg", "-y", "-i", "test/test2.mp4", "frames/frame_%05d.png"
], capture_output=True, text=True)
if result.returncode != 0:
    print_error(f"Помилка витягування кадрів:\n{result.stderr}")

def get_fps(video_path):
    cmd = [
        'ffprobe', '-v', '0',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=r_frame_rate',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    fps_str = result.stdout.strip()
    if '/' in fps_str:
        num, denom = map(int, fps_str.split('/'))
        return num / denom
    else:
        return float(fps_str)

fps = get_fps("test/test2.mp4")

# |-----------venv-----------|
print_step("Перевірка середовища Real-ESRGAN...")
venv_python = os.path.join("Real-ESRGAN", ".venv", "Scripts", "python.exe") if os.name == "nt" else os.path.join("Real-ESRGAN", ".venv", "bin", "python")
realesrgan_script = os.path.join("Real-ESRGAN", "inference_realesrgan.py")
if not os.path.exists(venv_python):
    print_error("Не знайдено середовище .venv")
if not os.path.exists(realesrgan_script):
    print_error("Не знайдено файл inference_realesrgan.py")

# |-----------cuda-----------|
print_step("Перевірка CUDA...")
check_cuda = subprocess.run([
    venv_python, "-c", "import torch; print(torch.cuda.is_available())"
], capture_output=True, text=True)
print(f"CUDA доступна: {check_cuda.stdout.strip()}")

# |-----------start-----------|
def run_upscale(model_file, in_folder, out_folder):
    print_step(f"Апскейл з {model_file}...")
    result = subprocess.run([
        venv_python,
        realesrgan_script,
        "-i", in_folder,
        "-o", out_folder,
        "-n", model_file.replace(".pth", "")
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print_error(f"Помилка апскейлу:\n{result.stderr}")

if target_scale_int == base_scale:
    run_upscale(model_file_name, "frames", "upscaled")
else:
    times = round(math.log(target_scale_int, base_scale))
    if base_scale ** times != target_scale_int:
        print_error(f"Неможливо досягти x{target_scale_int} з базовою x{base_scale}")
    input_folder = "frames"
    output_folder = "upscaled"
    for i in range(times):
        in_folder = input_folder if i == 0 else output_folder
        run_upscale(model_file_name, in_folder, output_folder)

# |-----------final-----------|
print_step("Збирання відео...")
first_frame = os.path.join("upscaled", "frame_00001_out.png")
if not os.path.exists(first_frame):
    print_error("Не знайдено жодного кадру після апскейлу.")
result = subprocess.run([
    "ffmpeg", "-y", "-framerate", str(fps), "-i", "upscaled/frame_%05d_out.png",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "res/upscaled_output.mp4"
], capture_output=True, text=True)
if result.returncode != 0:
    print_error(f"Помилка при створенні фінального відео:\n{result.stderr}")

# |-----------clean-----------|
[os.remove(f"frames/{f}") for f in os.listdir("frames") if os.path.isfile(f"frames/{f}")]
[os.remove(f"upscaled/{f}") for f in os.listdir("upscaled") if os.path.isfile(f"upscaled/{f}")]
print_step("Готово! Відео збережено як: res/upscaled_output.mp4")
