import os
import sys
import math
import subprocess
import re
import time
import json
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QFileDialog,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QTextEdit,
    QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt, QThread, Signal

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


class UpscaleThread(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int, int)  
    done_signal = Signal(bool)

    def __init__(self, video_path, output_name, category, model_name, scale):
        super().__init__()
        self.video_path = video_path
        self.output_name = output_name
        self.category = category
        self.model_name = model_name
        self.scale = scale
        self.stop_requested = False

    def log(self, msg):
        self.log_signal.emit(msg)

    def request_stop(self):
        self.stop_requested = True

    def run(self):
        try:
            self.log("[✔] Підготовка директорій...")
            os.makedirs("frames", exist_ok=True)
            os.makedirs("upscaled", exist_ok=True)
            os.makedirs("res", exist_ok=True)

            
            for folder in ["frames", "upscaled"]:
                for f in os.listdir(folder):
                    if self.stop_requested:
                        self.log("[!] Операція перервана користувачем")
                        self.done_signal.emit(False)
                        return
                    fp = os.path.join(folder, f)
                    if os.path.isfile(fp):
                        os.remove(fp)

            if not os.path.isfile(self.video_path):
                self.log(f"❌ Відео не знайдено: {self.video_path}")
                self.done_signal.emit(False)
                return

            
            def get_video_info(path):
                cmd = ['ffprobe', '-v', 'error',
                       '-select_streams', 'v:0',
                       '-show_entries', 'stream=nb_frames,r_frame_rate,duration,width,height',
                       '-of', 'json',
                       path]
                res = subprocess.run(cmd, capture_output=True, text=True)

                
                width = 0
                height = 0
                fps = 30.0
                total_frames = 0
                duration = 0.0

                try:
                    data = json.loads(res.stdout)
                    streams = data.get('streams', [])
                    if streams:
                        stream = streams[0]
                        width = int(stream.get('width', 0))
                        height = int(stream.get('height', 0))

                        
                        fps_str = stream.get('r_frame_rate', '0/0')
                        if fps_str and '/' in fps_str:
                            num, den = fps_str.split('/')
                            try:
                                num_f = float(num)
                                den_f = float(den)
                                if den_f == 0:
                                    fps = 30.0
                                else:
                                    fps = num_f / den_f
                            except:
                                fps = 30.0
                        else:
                            try:
                                fps = float(fps_str) if fps_str else 30.0
                            except:
                                fps = 30.0

                        duration = float(stream.get('duration', 0.0))
                        total_frames = int(stream.get('nb_frames', 0))

                    
                        if total_frames == 0 and duration > 0 and fps > 0:
                            total_frames = int(duration * fps)
                except Exception as e:
                    self.log(f"[!] Помилка аналізу даних ffprobe: {str(e)}")
                return fps, total_frames, duration, width, height

            fps, total_frames, duration, width, height = get_video_info(self.video_path)
            self.log(
                f"[i] FPS: {fps:.2f}, Кадрів: {total_frames}, Розмір: {width}x{height}, Тривалість: {duration:.2f} сек")

            model_file_name = model_categories[self.category][self.model_name][self.scale]
            model_path = os.path.join("Real-ESRGAN", "weights", model_file_name)
            if not os.path.exists(model_path):
                self.log(f"❌ Модель не знайдена: {model_path}")
                self.done_signal.emit(False)
                return

            
            self.log("[✔] Перевірка наявності аудіо...")
            audio_path = "temp_audio.aac"
            has_audio = False

        
            check_audio_cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                self.video_path
            ]
            result = subprocess.run(check_audio_cmd, capture_output=True, text=True)
            has_audio = "audio" in result.stdout

            if has_audio:
                self.log("[i] Виявлено аудіо доріжку, витягую...")
                ffmpeg_audio_cmd = [
                    "ffmpeg", "-y", "-i", self.video_path,
                    "-vn", "-acodec", "copy",
                    audio_path
                ]
                result_audio = subprocess.run(ffmpeg_audio_cmd, capture_output=True, text=True)
                if result_audio.returncode == 0:
                    self.log("[✔] Аудіо витягнуто")
                else:
                    self.log("⚠️ Не вдалося витягти аудіо, продовження без звуку")
                    has_audio = False
            else:
                self.log("[i] Аудіо доріжка не знайдена")

            
            self.log("[✔] Витяг кадрів з відео...")
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", self.video_path,
                "-vsync", "vfr",
                "frames/frame_%05d.png"
            ]
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.log(f"❌ Помилка витягування кадрів:\n{result.stderr}")
                self.done_signal.emit(False)
                return

            
            frame_count = len([f for f in os.listdir("frames") if f.endswith('.png')])
            if frame_count == 0:
                self.log("❌ Не вдалося витягти кадри з відео")
                self.done_signal.emit(False)
                return
            self.log(f"[i] Витягнуто кадрів: {frame_count}")

            
            venv_python = os.path.join("Real-ESRGAN", ".venv", "Scripts", "python.exe")
            if os.name != "nt":
                venv_python = os.path.join("Real-ESRGAN", ".venv", "bin", "python")

            realesrgan_script = os.path.join("Real-ESRGAN", "inference_realesrgan.py")

            if not os.path.exists(venv_python) or not os.path.exists(realesrgan_script):
                self.log("❌ Не знайдено середовище .venv або скрипт inference_realesrgan.py")
                self.done_signal.emit(False)
                return

            
            self.log("[i] Перевірка залежностей Real-ESRGAN...")
            check_deps_cmd = [
                venv_python,
                "-c",
                "import importlib.util; "
                "assert importlib.util.find_spec('cv2') is not None, 'Missing opencv-python'; "
                "assert importlib.util.find_spec('torch') is not None, 'Missing torch'"
            ]

            result = subprocess.run(check_deps_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.log("[i] Встановлення недостатніх залежностей...")
                install_cmd = [venv_python, "-m", "pip", "install", "opencv-python", "torch", "torchvision"]
                result_install = subprocess.run(install_cmd, capture_output=True, text=True)
                if result_install.returncode != 0:
                    self.log(f"❌ Помилка встановлення:\n{result_install.stderr}")
                    self.done_signal.emit(False)
                    return
                self.log("[✔] Залежності успішно встановлено")

            base_scale = min(int(s.replace('x', '')) for s in model_categories[self.category][self.model_name].keys())
            target_scale_int = int(self.scale.replace("x", ""))

            
            def run_upscale(model_file, in_folder, out_folder):
                self.log(f"[✔] Апскейл кадрів: {model_file}...")
                frames = [f for f in os.listdir(in_folder) if f.endswith('.png')]
                total = len(frames)
                if total == 0:
                    self.log("❌ Не знайдено кадрів для апскейлу.")
                    return False

                
                cmd = [
                    venv_python,
                    realesrgan_script,
                    "-i", in_folder,
                    "-o", out_folder,
                    "-n", model_file.replace(".pth", ""),
                    "--tile", "0"  
                ]

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )

                
                processed = 0
                progress_pattern = re.compile(r'Processing.*?(\d+)/(\d+)')
                start_time = time.time()

                while True:
                    if self.stop_requested:
                        process.terminate()
                        self.log("[!] Апскейл перервано")
                        return False

                    line = process.stdout.readline()
                    if not line:
                        break

                    line = line.strip()
                    self.log(line)

                
                    match = progress_pattern.search(line)
                    if match:
                        current = int(match.group(1))
                        total_frames = int(match.group(2))
                        self.progress_signal.emit(current, total_frames)
                        processed = current
                    else:
                
                        elapsed = time.time() - start_time
                        if elapsed > 0 and processed > 0:
                            fps = processed / elapsed
                            remaining = (total - processed) / fps if fps > 0 else 0
                            mins, secs = divmod(int(remaining), 60)
                            self.log(
                                f"[i] Прогрес: {processed}/{total} (~{fps:.1f} кадр/сек) Залишилось: {mins}хв {secs}с")

                process.wait()
                if process.returncode != 0:
                    self.log(f"❌ Помилка апскейлу (код {process.returncode})")
                    return False

                return True

            
            if target_scale_int == base_scale:
                if not run_upscale(model_file_name, "frames", "upscaled"):
                    self.done_signal.emit(False)
                    return
            else:
                times = round(math.log(target_scale_int, base_scale))
                if base_scale ** times != target_scale_int:
                    self.log(f"❌ Неможливо досягти x{target_scale_int} з базовою x{base_scale}")
                    self.done_signal.emit(False)
                    return

                for i in range(times):
                    in_folder = "frames" if i == 0 else "upscaled"
                    if not run_upscale(model_file_name, in_folder, "upscaled"):
                        self.done_signal.emit(False)
                        return

            
            self.log("[✔] Збирання відео...")
            output_path = f"res/{self.output_name}.mp4"

            
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", "upscaled/frame_%05d_out.png",
                "-c:v", "libx264",
                "-preset", "slow",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
            ]

        
            if has_audio and os.path.exists(audio_path):
                ffmpeg_cmd.extend(["-i", audio_path, "-c:a", "copy"])
                ffmpeg_cmd.append("-map")
                ffmpeg_cmd.append("0:v")
                ffmpeg_cmd.append("-map")
                ffmpeg_cmd.append("1:a")
                ffmpeg_cmd.append("-shortest")  
            else:
                ffmpeg_cmd.append("-an")  

            ffmpeg_cmd.append(output_path)

            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.log(f"❌ Помилка при створенні відео:\n{result.stderr}")
                self.done_signal.emit(False)
                return

            
            if has_audio and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    self.log("[i] Тимчасовий аудіо файл видалено")
                except Exception as e:
                    self.log(f"⚠️ Не вдалося видалити тимчасовий аудіо файл: {str(e)}")

        
            self.log("[i] Очистка тимчасових файлів...")
            for folder in ["frames", "upscaled"]:
                for f in os.listdir(folder):
                    if self.stop_requested:
                        break
                    fp = os.path.join(folder, f)
                    if os.path.isfile(fp):
                        try:
                            os.remove(fp)
                        except:
                            pass

            self.log(f"[✔] Готово! Відео збережено як: {output_path}")
            if has_audio:
                self.log("[i] Відео містить оригінальний звук")
            else:
                self.log("[i] Відео без звуку (оригінал не містив аудіо)")

            self.done_signal.emit(True)

        except Exception as e:
            import traceback
            self.log(f"❌ Критична помилка:\n{str(e)}\n{traceback.format_exc()}")
            self.done_signal.emit(False)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Real-ESRGAN Video Upscaler")
        self.setMinimumSize(900, 600)
        self.setStyleSheet(self.get_stylesheet())
        self.model_buttons = []
        self.setup_ui()
        self.upscale_thread = None
        self.model_buttons = []

    def get_stylesheet(self):
        return """
            QWidget {
                background-color: #0a0a0a;
                color: #00cc00;
                font-family: "Courier New", monospace;
                font-size: 13px;
            }
            QPushButton {
                background-color: #222222;
                border: 1px solid #00cc00;
                color: #00cc00;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #333333;
            }
            QPushButton:pressed {
                background-color: #004400;
            }
            QPushButton:checked {
                background-color: #006600;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #111111;
                color: #555555;
                border-color: #555555;
            }
            QLineEdit {
                background-color: #111111;
                border: 1px solid #00cc00;
                color: #00cc00;
                padding: 5px;
                font-family: "Courier New", monospace;
            }
            QTextEdit {
                background-color: #000000;
                color: #00cc00;
                border: 1px solid #00cc00;
                font-family: "Courier New", monospace;
                font-size: 12px;
            }
            QGroupBox {
                border: 1px solid #00cc00;
                border-radius: 5px;
                margin-top: 1ex;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
                background-color: #0a0a0a;
            }
            QLabel {
                padding: 2px;
            }
        """

    def setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(10)
        self.layout.setContentsMargins(15, 15, 15, 15)

        
        video_layout = QHBoxLayout()
        video_layout.setSpacing(10)
        self.video_label = QLabel("Вхідне відео: (не вибрано)")
        self.btn_browse_video = QPushButton("Обрати відео")
        self.btn_browse_video.setMinimumHeight(30)
        self.btn_browse_video.clicked.connect(self.browse_video)
        video_layout.addWidget(self.video_label, 70)
        video_layout.addWidget(self.btn_browse_video, 30)
        self.layout.addLayout(video_layout)

        
        self.model_groupbox = QGroupBox("Оберіть модель та масштаб")
        grid = QGridLayout()
        grid.setSpacing(8)
        self.model_radio_map = {}

        
        row, col = 0, 0
        for category, models in model_categories.items():
            cat_label = QLabel(f"<b>{category}</b>")
            cat_label.setStyleSheet("color: #00ff00;")
            grid.addWidget(cat_label, row, col, 1, 2)
            row += 1

            for model_name, scales in models.items():
                for scale_key in scales.keys():
                    btn = QPushButton(f"{model_name} - {scale_key}")
                    btn.setCheckable(True)
                    btn.setMinimumHeight(35)
                    btn.setStyleSheet("text-align: left; padding-left: 10px;")
                    btn.clicked.connect(self.model_selected)
                    self.model_radio_map[btn] = (category, model_name, scale_key)
                    self.model_buttons.append(btn)
                    grid.addWidget(btn, row, col)

                    col += 1
                    if col > 1:
                        col = 0
                        row += 1

            row += 1
            col = 0

        self.model_groupbox.setLayout(grid)
        self.layout.addWidget(self.model_groupbox)

        
        output_layout = QHBoxLayout()
        output_layout.setSpacing(10)
        output_label = QLabel("Ім'я вихідного файлу:")
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Введіть назву або залиште за замовчуванням")
        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_edit)
        self.layout.addLayout(output_layout)

        
        self.log = QTextEdit()
        self.log.setMinimumHeight(200)
        self.layout.addWidget(self.log)

        
        button_layout = QHBoxLayout()
        self.btn_start = QPushButton("Старт")
        self.btn_start.setMinimumHeight(40)
        self.btn_start.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.btn_start.clicked.connect(self.start_upscale)

        self.btn_stop = QPushButton("Стоп")
        self.btn_stop.setMinimumHeight(40)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_upscale)

        button_layout.addWidget(self.btn_start)
        button_layout.addWidget(self.btn_stop)
        self.layout.addLayout(button_layout)

    def browse_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Оберіть відео",
            "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.flv *.webm)"
        )
        if file_path:
            self.video_path = file_path
            self.video_label.setText(f"Вхідне відео: {os.path.basename(file_path)}")
            self.log.append(f"[✔] Вибрано відео: {file_path}")

    def model_selected(self):
        sender = self.sender()
        for btn in self.model_buttons:
            if btn != sender:
                btn.setChecked(False)
        sender.setChecked(True)

        self.selected_category, self.selected_model, self.selected_scale = self.model_radio_map[sender]
        self.log.append(f"[✔] Обрана модель: {self.selected_model}, масштаб: {self.selected_scale}")

        
        if hasattr(self, 'video_path') and self.video_path:
            base_name = os.path.splitext(os.path.basename(self.video_path))[0]
            self.output_edit.setText(f"{base_name}_{self.selected_model}_{self.selected_scale}")
        else:
            self.output_edit.setText(f"output_{self.selected_model}_{self.selected_scale}")

        
        if hasattr(self, 'video_path') and self.video_path:
            try:
                cmd = [
                    "ffprobe", "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height",
                    "-of", "json",
                    self.video_path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                data = json.loads(result.stdout)
                streams = data.get('streams', [])
                if streams:
                    stream = streams[0]
                    width = stream.get('width', 0)
                    height = stream.get('height', 0)
                    self.log.append(f"[i] Поточний розмір: {width}x{height}")

                    scale_int = int(self.selected_scale.replace("x", ""))
                    new_w = int(width) * scale_int
                    new_h = int(height) * scale_int
                    self.log.append(f"[i] Після апскейлу: {new_w}x{new_h}")
            except Exception as e:
                self.log.append(f"[!] Помилка аналізу: {str(e)}")

    def start_upscale(self):
        if not hasattr(self, 'video_path') or not self.video_path:
            QMessageBox.warning(self, "Помилка", "Відео не вибрано!")
            return
        if not hasattr(self, 'selected_model') or not hasattr(self, 'selected_scale'):
            QMessageBox.warning(self, "Помилка", "Оберіть модель та масштаб!")
            return

        
        output_name = self.output_edit.text().strip()
        if not output_name:
            base_name = os.path.splitext(os.path.basename(self.video_path))[0]
            output_name = f"{base_name}_{self.selected_model}_{self.selected_scale}"
            self.output_edit.setText(output_name)

        
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_browse_video.setEnabled(False)
        self.log.append("[i] Початок апскейлу...")

        self.upscale_thread = UpscaleThread(
            self.video_path,
            output_name,
            self.selected_category,
            self.selected_model,
            self.selected_scale
        )
        self.upscale_thread.log_signal.connect(self.log.append)
        self.upscale_thread.progress_signal.connect(self.show_progress)
        self.upscale_thread.done_signal.connect(self.upscale_done)
        self.upscale_thread.start()

    def stop_upscale(self):
        if self.upscale_thread and self.upscale_thread.isRunning():
            self.upscale_thread.request_stop()
            self.btn_stop.setEnabled(False)
            self.log.append("[!] Запит на зупинку...")

    def show_progress(self, current_frame, total_frames):
        if total_frames == 0:
            return
        percent = (current_frame / total_frames) * 100
        self.log.append(f"[i] Обробка: {current_frame}/{total_frames} ({percent:.1f}%)")

    def upscale_done(self, success):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_browse_video.setEnabled(True)

        if success:
            self.log.append("[✔] Апскейл успішно завершено!")
        else:
            self.log.append("[❌] Апскейл завершено з помилкою")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
