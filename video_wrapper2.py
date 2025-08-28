#!/usr/bin/env python3

# -*- coding: utf-8 -*-

"""
影片編輯器 (FFmpeg 直呼版) - 在主片前後插入靜態圖片
優先路線A：主片免重編碼（TS 轉封 + concat -c copy）
回退路線B：全段硬體重編碼（VideoToolbox）
"""

import sys
import os
import json
import subprocess
import tempfile
import uuid
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QFileDialog, QVBoxLayout, QHBoxLayout,
    QGroupBox, QDoubleSpinBox, QTextEdit, QProgressBar, QMessageBox, QCheckBox, QScrollArea, QFrame, QSplitter,
    QListView, QStyledItemDelegate, QMenu, QStyle
)
from PyQt6.QtGui import QPixmap, QFont, QImage, QPainter, QColor, QPen, QBrush, QFontMetrics
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QAbstractListModel, QModelIndex, QSize


class FFmpegEnv:
    def __init__(self):
        embedded_ffmpeg_candidates = self._embedded_candidates('ffmpeg')
        embedded_ffprobe_candidates = self._embedded_candidates('ffprobe')
        self.ffmpeg_path = self._find_binary('FFMPEG_BIN', embedded_ffmpeg_candidates + ['ffmpeg', '/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg'])
        self.ffprobe_path = self._find_binary('FFPROBE_BIN', embedded_ffprobe_candidates + ['ffprobe', '/opt/homebrew/bin/ffprobe', '/usr/local/bin/ffprobe'])
        self.hardware_encoders = self._detect_hardware_encoders()

    def _find_binary(self, env_key, candidates):
        env_val = os.environ.get(env_key)
        if env_val and os.path.exists(env_val):
            return env_val
        for c in candidates:
            try:
                res = subprocess.run([c, '-version'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                if res.returncode == 0:
                    return c
            except Exception:
                continue
        return candidates[0]

    def _app_base_dir(self):
        # PyInstaller 打包後：有 sys._MEIPASS；.app 中通常在 Contents/MacOS
        try:
            if hasattr(sys, '_MEIPASS') and sys._MEIPASS:
                return sys._MEIPASS
        except Exception:
            pass
        # frozen one-dir 下，sys.executable 指向可執行檔
        try:
            if getattr(sys, 'frozen', False):
                return os.path.dirname(os.path.abspath(sys.executable))
        except Exception:
            pass
        # 開發模式：以此檔所在目錄為基準
        try:
            return os.path.dirname(os.path.abspath(__file__))
        except Exception:
            return os.getcwd()

    def _embedded_candidates(self, bin_name):
        base = self._app_base_dir()
        candidates = []
        # 優先：assets/bin/mac/arm64
        candidates.append(os.path.join(base, 'assets', 'bin', 'mac', 'arm64', bin_name))
        # 次要：assets/bin
        candidates.append(os.path.join(base, 'assets', 'bin', bin_name))
        # 有些佈局可能把資源放到 Resources 或 _internal；一併嘗試。
        # .app 內從 MacOS/ 退回到 Contents/
        app_contents = os.path.abspath(os.path.join(base, '..'))
        resources_dir = os.path.join(app_contents, 'Resources')
        internal_dir = os.path.join(app_contents, '_internal')
        candidates.append(os.path.join(resources_dir, 'assets', 'bin', 'mac', 'arm64', bin_name))
        candidates.append(os.path.join(resources_dir, 'assets', 'bin', bin_name))
        candidates.append(os.path.join(internal_dir, 'assets', 'bin', 'mac', 'arm64', bin_name))
        candidates.append(os.path.join(internal_dir, 'assets', 'bin', bin_name))
        # 僅返回存在或可執行的路徑優先，其餘也保留以便 _find_binary 嘗試
        # 這裡不過濾，交由 _find_binary 一次測試 -version 判斷
        return candidates

    def _detect_hardware_encoders(self):
        enc = []
        try:
            p = subprocess.run([self.ffmpeg_path, '-hide_banner', '-encoders'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            out = p.stdout or ''
            if 'h264_videotoolbox' in out:
                enc.append('h264_videotoolbox')
            if 'hevc_videotoolbox' in out:
                enc.append('hevc_videotoolbox')
        except Exception:
            pass
        return enc


class ProbeResult:
    def __init__(self):
        self.video_codec = None
        self.profile = None
        self.level = None
        self.width = None
        self.height = None
        self.pix_fmt = None
        self.fps = None
        self.colorspace = None
        self.color_primaries = None
        self.color_trc = None
        self.sar = None
        self.dar = None
        self.has_audio = False
        self.audio_codec = None
        self.audio_sample_rate = 48000
        self.audio_channels = 2
        self.duration = 0.0


def _parse_fraction(frac):
    try:
        if isinstance(frac, (int, float)):
            return float(frac)
        if isinstance(frac, str) and '/' in frac:
            a, b = frac.split('/')
            a = float(a)
            b = float(b)
            return a / b if b != 0 else 0.0
        return float(frac)
    except Exception:
        return 0.0


def probe_main_video(probe_bin, video_path):
    r = ProbeResult()
    try:
        cmd = [probe_bin, '-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', video_path]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if p.returncode != 0:
            return r
        data = json.loads(p.stdout)
        streams = data.get('streams', [])
        for s in streams:
            if s.get('codec_type') == 'video' and r.video_codec is None:
                r.video_codec = s.get('codec_name')
                r.profile = s.get('profile')
                r.level = s.get('level')
                r.width = s.get('width')
                r.height = s.get('height')
                r.pix_fmt = s.get('pix_fmt')
                r.fps = _parse_fraction(s.get('avg_frame_rate') or s.get('r_frame_rate') or '0/1')
                r.colorspace = s.get('colorspace')
                r.color_primaries = s.get('color_primaries')
                r.color_trc = s.get('color_transfer') or s.get('color_trc')
                r.sar = s.get('sample_aspect_ratio')
                r.dar = s.get('display_aspect_ratio')
            if s.get('codec_type') == 'audio' and not r.has_audio:
                r.has_audio = True
                r.audio_codec = s.get('codec_name')
                try:
                    r.audio_sample_rate = int(s.get('sample_rate') or 48000)
                except Exception:
                    r.audio_sample_rate = 48000
                r.audio_channels = int(s.get('channels') or 2)
        fmt = data.get('format', {})
        try:
            r.duration = float(fmt.get('duration') or 0.0)
        except Exception:
            r.duration = 0.0
    except Exception:
        pass
    return r


class FFmpegWrapperProcessor(QThread):
    progress = pyqtSignal(str, int)
    status = pyqtSignal(str, str)
    job_finished = pyqtSignal(str, str)
    error = pyqtSignal(str, str)

    def __init__(self, job_id, video_file, start_image, end_image, start_duration, end_duration, output_file, prefer_copy_concat=True, use_hardware=True, env: FFmpegEnv | None = None):
        super().__init__()
        self.job_id = job_id
        self.video_file = video_file
        self.start_image = start_image
        self.end_image = end_image
        self.start_duration = start_duration
        self.end_duration = end_duration
        self.output_file = output_file
        self.prefer_copy_concat = prefer_copy_concat
        self.use_hardware = use_hardware
        self.env = env or FFmpegEnv()
        self.is_cancelled = False
        self._running_proc = None
        self._tmp_dir = None

    def cancel(self):
        self.is_cancelled = True
        try:
            if self._running_proc and self._running_proc.poll() is None:
                self._running_proc.kill()
        except Exception:
            pass

    def _run_cmd(self, cmd):
        try:
            self._running_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            while True:
                if self.is_cancelled:
                    try:
                        self._running_proc.kill()
                    except Exception:
                        pass
                    return False
                line = self._running_proc.stdout.readline() if self._running_proc.stdout else ''
                if not line and self._running_proc.poll() is not None:
                    break
            return self._running_proc.returncode == 0
        except Exception:
            return False
        finally:
            self._running_proc = None

    def _encode_image_ts(self, image_path, duration_sec, fps, has_audio, audio_sr, audio_ch):
        out_path = os.path.join(self._tmp_dir, f"seg_{uuid.uuid4().hex}.ts")
        gop = max(2, int(round(fps * 2))) if fps and fps > 0 else 60
        vf = f"scale=1920:1080:flags=lanczos,format=yuv420p"

        cmd = [
            self.env.ffmpeg_path, '-hide_banner', '-y',
            '-loop', '1', '-framerate', str(int(round(fps))) if fps and fps > 0 else '30', '-t', f"{duration_sec:.3f}", '-i', image_path,
        ]

        if has_audio:
            cmd += ['-f', 'lavfi', '-t', f"{duration_sec:.3f}", '-i', f"anullsrc=r={audio_sr}:cl={'stereo' if audio_ch != 1 else 'mono'}"]

        cmd += [
            '-r', str(int(round(fps))) if fps and fps > 0 else '30',
            '-vf', vf,
            '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
            '-c:v', 'libx264', '-profile:v', 'high', '-level:v', '4.1', '-g', str(gop), '-sc_threshold', '0',
        ]

        if has_audio:
            cmd += ['-c:a', 'aac', '-b:a', '192k', '-ar', str(audio_sr), '-ac', '2']

        cmd += [
            '-f', 'mpegts', out_path
        ]

        return out_path if self._run_cmd(cmd) else None

    def _mux_main_to_ts(self):
        out_path = os.path.join(self._tmp_dir, f"main_{uuid.uuid4().hex}.ts")
        cmd = [
            self.env.ffmpeg_path, '-hide_banner', '-y',
            '-i', self.video_file,
            '-c', 'copy', '-bsf:v', 'h264_mp4toannexb',
            '-f', 'mpegts', out_path
        ]
        return out_path if self._run_cmd(cmd) else None

    def _concat_ts_to_mp4(self, ts_list, output_path):
        list_txt = os.path.join(self._tmp_dir, 'list.txt')
        with open(list_txt, 'w', encoding='utf-8') as f:
            for p in ts_list:
                f.write(f"file '{p}'\n")
        cmd = [
            self.env.ffmpeg_path, '-hide_banner', '-y',
            '-f', 'concat', '-safe', '0', '-i', list_txt,
            '-c', 'copy', '-bsf:a', 'aac_adtstoasc', '-movflags', '+faststart',
            output_path
        ]
        return self._run_cmd(cmd)

    def _transcode_fallback(self, main_info: ProbeResult, output_path):
        fps = int(round(main_info.fps)) if main_info.fps and main_info.fps > 0 else 30
        gop = max(2, int(round(fps * 2)))

        inputs = ['-i', self.video_file]
        if self.start_image:
            inputs += ['-loop', '1', '-t', f"{self.start_duration:.3f}", '-i', self.start_image]
        if self.end_image:
            inputs += ['-loop', '1', '-t', f"{self.end_duration:.3f}", '-i', self.end_image]

        filters = []
        idx = 1
        if self.start_image:
            filters.append(f"[{idx}:v]scale=1920:1080:flags=lanczos,format=yuv420p[s]")
            idx += 1
        filters.append(f"[0:v]scale=1920:1080:flags=bicubic,format=yuv420p[mv]")
        if self.end_image:
            filters.append(f"[{idx}:v]scale=1920:1080:flags=lanczos,format=yuv420p[e]")

        concat_inputs = []
        if self.start_image:
            concat_inputs.append('[s]')
        concat_inputs.append('[mv]')
        if self.end_image:
            concat_inputs.append('[e]')
        concat_str = ''.join(concat_inputs) + f"concat=n={len(concat_inputs)}:v=1:a=0[v]"
        filter_complex = ','.join(filters) + ';' + concat_str if filters else concat_str

        cmd = [self.env.ffmpeg_path, '-hide_banner', '-y'] + inputs + [
            '-filter_complex', filter_complex,
            '-map', '[v]', '-map', '0:a?',
            '-r', str(fps),
            '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
        ]

        if self.use_hardware and ('h264_videotoolbox' in self.env.hardware_encoders):
            cmd += ['-c:v', 'h264_videotoolbox', '-profile:v', 'high', '-level:v', '4.1', '-g', str(gop), '-sc_threshold', '0', '-b:v', '8M', '-maxrate', '10M', '-bufsize', '20M']
        else:
            cmd += ['-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-profile:v', 'high', '-level:v', '4.1', '-g', str(gop), '-sc_threshold', '0']

        if main_info.has_audio:
            cmd += ['-c:a', 'aac', '-b:a', '192k', '-ar', str(main_info.audio_sample_rate or 48000), '-ac', '2']

        cmd += ['-movflags', '+faststart', output_path]
        return self._run_cmd(cmd)

    def run(self):
        self._tmp_dir = tempfile.mkdtemp(prefix=f"vw2_{self.job_id}_")
        intro_ts = None
        outro_ts = None
        main_ts = None

        try:
            if self.is_cancelled:
                return

            self.status.emit(self.job_id, "探測主片參數...")
            self.progress.emit(self.job_id, 5)
            info = probe_main_video(self.env.ffprobe_path, self.video_file)
            fps = int(round(info.fps)) if info.fps and info.fps > 0 else 30

            if self.prefer_copy_concat:
                self.status.emit(self.job_id, "建立主片 TS...")
                self.progress.emit(self.job_id, 15)
                main_ts = self._mux_main_to_ts()
                if not main_ts:
                    raise RuntimeError('主片轉 TS 失敗')

                if self.start_image:
                    if self.is_cancelled: return
                    self.status.emit(self.job_id, "編碼開頭圖片段...")
                    self.progress.emit(self.job_id, 35)
                    intro_ts = self._encode_image_ts(self.start_image, self.start_duration, fps, info.has_audio, info.audio_sample_rate, info.audio_channels)
                    if not intro_ts:
                        raise RuntimeError('開頭段編碼失敗')

                if self.end_image:
                    if self.is_cancelled: return
                    self.status.emit(self.job_id, "編碼結尾圖片段...")
                    self.progress.emit(self.job_id, 55)
                    outro_ts = self._encode_image_ts(self.end_image, self.end_duration, fps, info.has_audio, info.audio_sample_rate, info.audio_channels)
                    if not outro_ts:
                        raise RuntimeError('結尾段編碼失敗')

                seq = []
                if intro_ts: seq.append(intro_ts)
                if main_ts: seq.append(main_ts)
                if outro_ts: seq.append(outro_ts)
                if not seq:
                    raise RuntimeError('沒有可合併的段落')

                self.status.emit(self.job_id, "合併段落為輸出...")
                self.progress.emit(self.job_id, 80)
                if not self._concat_ts_to_mp4(seq, self.output_file):
                    if self.is_cancelled: return
                    self.status.emit(self.job_id, "0-copy 合併失敗，回退重編碼...")
                    ok = self._transcode_fallback(info, self.output_file)
                    if not ok:
                        raise RuntimeError('回退重編碼失敗')
            else:
                self.status.emit(self.job_id, "進行重編碼輸出...")
                self.progress.emit(self.job_id, 20)
                ok = self._transcode_fallback(info, self.output_file)
                if not ok:
                    raise RuntimeError('重編碼輸出失敗')

            if self.is_cancelled:
                return
            self.progress.emit(self.job_id, 100)
            self.status.emit(self.job_id, "處理完成！")
            self.job_finished.emit(self.job_id, self.output_file)
        except Exception as e:
            if not self.is_cancelled:
                self.error.emit(self.job_id, str(e))
        finally:
            try:
                if self._tmp_dir and os.path.exists(self._tmp_dir):
                    for name in os.listdir(self._tmp_dir):
                        try:
                            os.remove(os.path.join(self._tmp_dir, name))
                        except Exception:
                            pass
                    try:
                        os.rmdir(self._tmp_dir)
                    except Exception:
                        pass
            except Exception:
                pass


class JobWidget(QFrame):
    cancel_requested = pyqtSignal(str)

    def __init__(self, job_id, job_name):
        super().__init__()
        self.job_id = job_id
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("QFrame { background: #2a2a2a; border: 1px solid #444; border-radius: 4px; margin: 2px; padding: 5px; }")

        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        self.name_label = QLabel(job_name)
        self.name_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.time_label = QLabel(datetime.now().strftime("%H:%M:%S"))
        self.time_label.setStyleSheet("color: #888; font-size: 10px;")
        header_layout.addWidget(self.name_label)
        header_layout.addStretch()
        header_layout.addWidget(self.time_label)
        layout.addLayout(header_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.status_label = QLabel("準備中...")
        self.status_label.setStyleSheet("color: #ccc; font-size: 10px;")
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)

        button_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setStyleSheet("QPushButton { background: #d32f2f; padding: 4px 8px; font-size: 10px; }")
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.job_id))
        self.open_btn = QPushButton("開啟位置")
        self.open_btn.setStyleSheet("QPushButton { background: #388e3c; padding: 4px 8px; font-size: 10px; }")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.open_file_location)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.open_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.output_file = None

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_status(self, status):
        self.status_label.setText(status)

    def set_finished(self, output_file):
        self.output_file = output_file
        self.cancel_btn.setEnabled(False)
        self.open_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        self.status_label.setText("✅ 完成")
        self.status_label.setStyleSheet("color: #4caf50; font-size: 10px;")

    def set_error(self, error_msg):
        self.cancel_btn.setEnabled(False)
        self.status_label.setText(f"❌ 錯誤: {error_msg}")
        self.status_label.setStyleSheet("color: #f44336; font-size: 10px;")

    def set_cancelled(self):
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("🚫 已取消")
        self.status_label.setStyleSheet("color: #ff9800; font-size: 10px;")

    def open_file_location(self):
        if self.output_file and os.path.exists(self.output_file):
            subprocess.run(["open", "-R", self.output_file])


class JobItem:
    def __init__(self, job_id: str, name: str):
        self.job_id = job_id
        self.name = name
        self.status_text = "佇列中"
        self.progress = 0
        self.state = "queued"  # queued|running|done|error|cancel
        self.output_file = None
        self.started_at = datetime.now()


class JobListModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.items: list[JobItem] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.items)

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return None
        item = self.items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return item.name
        if role == Qt.ItemDataRole.UserRole:
            return item
        return None

    # convenience
    def add_item(self, item: JobItem):
        self.beginInsertRows(QModelIndex(), len(self.items), len(self.items))
        self.items.append(item)
        self.endInsertRows()

    def find_row_by_id(self, job_id: str) -> int:
        for i, it in enumerate(self.items):
            if it.job_id == job_id:
                return i
        return -1

    def update_progress(self, job_id: str, progress: int, status: str | None = None):
        row = self.find_row_by_id(job_id)
        if row < 0:
            return
        item = self.items[row]
        item.progress = progress
        if status is not None:
            item.status_text = status
        if progress >= 100:
            item.state = "done"
        top_left = self.index(row, 0)
        self.dataChanged.emit(top_left, top_left)

    def set_state(self, job_id: str, state: str, status: str | None = None, output_file: str | None = None):
        row = self.find_row_by_id(job_id)
        if row < 0:
            return
        item = self.items[row]
        item.state = state
        if status is not None:
            item.status_text = status
        if output_file:
            item.output_file = output_file
        top_left = self.index(row, 0)
        self.dataChanged.emit(top_left, top_left)

    def remove_row(self, row: int):
        if row < 0 or row >= len(self.items):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        del self.items[row]
        self.endRemoveRows()


class JobItemDelegate(QStyledItemDelegate):
    ROW_HEIGHT = 56
    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ROW_HEIGHT)

    def paint(self, painter: QPainter, option, index):
        item: JobItem = index.data(Qt.ItemDataRole.UserRole)
        if not item:
            return super().paint(painter, option, index)

        rect = option.rect
        painter.save()

        # 背景
        bg = QColor(42, 42, 42)
        if option.state & QStyle.StateFlag.State_MouseOver:
            bg = QColor(48, 48, 48)
        painter.fillRect(rect, bg)

        # 左側狀態點
        dot_map = {
            "queued": QColor(120,120,120),
            "running": QColor(33,150,243),
            "done": QColor(76,175,80),
            "error": QColor(244,67,54),
            "cancel": QColor(255,152,0),
        }
        dot_color = dot_map.get(item.state, QColor(120,120,120))
        dot_r = 6
        cx = rect.left() + 12
        cy = rect.top() + rect.height()//2
        painter.setBrush(QBrush(dot_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(cx - dot_r, cy - dot_r, dot_r*2, dot_r*2)

        # 文字區域
        left = cx + 10 + dot_r
        right_padding = 8
        text_rect = rect.adjusted(left, 6, -right_padding, -18)
        sub_rect = rect.adjusted(left, 24, -right_padding, -6)

        painter.setPen(QPen(QColor(240,240,240)))
        fm = QFontMetrics(painter.font())
        name_text = fm.elidedText(item.name, Qt.TextElideMode.ElideMiddle, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, name_text)

        painter.setPen(QPen(QColor(170,170,170)))
        painter.setFont(QFont(painter.font().family(), 10))
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignVCenter,
                         f"{item.status_text}  •  {item.progress}%")

        # 進度條（底部極細）
        bar_h = 3
        bar_rect = rect.adjusted(left, rect.height()-bar_h-4, -right_padding, -4)
        track = QColor(60,60,60)
        painter.fillRect(bar_rect, track)
        if item.progress > 0:
            if item.state == "done":
                chunk = QColor(76,175,80)
            elif item.state == "error":
                chunk = QColor(244,67,54)
            elif item.state == "cancel":
                chunk = QColor(255,152,0)
            else:
                chunk = QColor(0,120,212)
            w = max(0, int(bar_rect.width() * max(0, min(item.progress, 100)) / 100))
            painter.fillRect(bar_rect.adjusted(0,0, -(bar_rect.width()-w), 0), chunk)

        painter.restore()

class DropZone(QFrame):
    filesDropped = pyqtSignal(list)

    def __init__(self, text: str = "拖曳影片或圖片到此處"):
        super().__init__()
        self.setAcceptDrops(True)
        self.label = QLabel(text, self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: #aaa; font-size: 16px; font-weight: 500;")
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        self._normal_style()
        self.setFixedHeight(180)

    def _normal_style(self):
        self.setStyleSheet(
            "QFrame { border: 2px dashed #666; border-radius: 8px; background: #1b1b1b; }"
        )

    def _highlight_style(self):
        self.setStyleSheet(
            "QFrame { border: 2px solid #2196f3; border-radius: 8px; background: #16232e; }"
        )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self._highlight_style()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._normal_style()
        event.accept()

    def dropEvent(self, event):
        try:
            self._normal_style()
            urls = event.mimeData().urls()
            paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
            if paths:
                self.filesDropped.emit(paths)
            event.acceptProposedAction()
        except Exception:
            event.ignore()


class VideoEditorFFApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("影片編輯器 - FFmpeg 直呼版（序列處理）")
        self.resize(1200, 800)
        self.setStyleSheet(self.get_dark_theme())
        self.setAcceptDrops(True)

        self.env = FFmpegEnv()

        self.video_file = None
        self.start_image_file = None
        self.end_image_file = None

        self.prefer_copy_concat = True
        self.use_hardware = True
        self.auto_output_to_source = True

        self.active_processors = {}
        self.job_widgets = {}
        self.job_queue = []
        self.MAX_CONCURRENT_JOBS = 1

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.splitter)

        self.create_left_panel()
        self.create_right_panel()

        # 設置分割器比例（左側更寬）
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([900, 300])

        self.update_active_count()
        self.update_queue_count()

    def get_dark_theme(self):
        return """
            QWidget { background: #232323; color: #f0f0f0; font-size: 15px; }
            /* 緊湊樣式 */
            QLabel { color: #f0f0f0; font-size: 15px; font-weight: 500; }
            /* 功能區分組樣式 */
            QWidget#FunctionGroup { background: #2a2a2a; border: 1px solid #3a3a3a; border-radius: 8px; margin: 4px; padding: 8px; }
            QLabel#SectionTitle { color: #4fc3f7; font-size: 14px; font-weight: 600; margin-bottom: 4px; }
            /* 按鈕：緊湊但清晰 */
            QPushButton { background: #007acc; color: #fff; border: 1px solid #444; border-radius: 5px; padding: 8px 10px; font-size: 14px; }
            QPushButton:disabled { background: #444; color: #888; }
            QPushButton:hover { background: #0099ff; }
            /* 主要操作按鈕 - 綠色系 - 強制優先級 */
            QPushButton#PrimaryCTA { 
                background-color: #4caf50 !important; 
                color: #ffffff !important;
                font-size: 16px !important; 
                font-weight: 700 !important; 
                height: 40px !important; 
                border: 2px solid #66bb6a !important; 
                border-radius: 6px !important;
                padding: 8px 16px !important;
            }
            QPushButton#PrimaryCTA:hover { 
                background-color: #66bb6a !important; 
                border: 2px solid #81c784 !important; 
            }
            QPushButton#PrimaryCTA:disabled { 
                background-color: #424242 !important; 
                color: #757575 !important; 
                border: 2px dashed #616161 !important; 
            }
            /* 次要操作按鈕 - 灰色系 - 強制優先級 */
            QPushButton#SecondaryBtn { 
                background-color: #757575 !important; 
                color: #ffffff !important;
                border: 1px solid #9e9e9e !important; 
                border-radius: 5px !important;
                font-size: 14px !important;
                padding: 8px 12px !important;
            }
            QPushButton#SecondaryBtn:hover { 
                background-color: #9e9e9e !important; 
                border: 1px solid #bdbdbd !important; 
            }
            /* 進度條 */
            QProgressBar { background: #2c2c2c; border: 1px solid #444; border-radius: 5px; text-align: center; color: #fff; min-height: 10px; }
            QProgressBar::chunk { background: #0078d4; }
            /* 文本區緊湊 */
            QTextEdit { background: #232323; color: #d0d0d0; border: 1px solid #444; border-radius: 5px; font-size: 13px; padding: 4px; }
            /* 數字輸入緊湊 */
            QDoubleSpinBox { background: #232323; color: #fff; border: 1px solid #444; border-radius: 5px; padding: 4px; font-size: 14px; }
            /* 複選框 */
            QCheckBox { color: #f0f0f0; font-size: 14px; padding: 4px 2px; }
            QCheckBox::indicator { width: 20px; height: 20px; }
            QCheckBox::indicator:unchecked { background: #444; border: 1px solid #666; border-radius: 3px; }
            QCheckBox::indicator:checked { background: #007acc; border: 1px solid #007acc; border-radius: 3px; }
            /* 捲動區 */
            QScrollArea { background: #1e1e1e; border: 1px solid #444; }
            QSplitter::handle { background: #444; }
        """

    def create_left_panel(self):
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(8)  # 緊湊間距

        # 標題區（縮小）
        title = QLabel("影片編輯器 - FFmpeg 直呼")
        title.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        left_layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)

        # 拖放區（擴大為主要操作區）
        self.drop_zone = DropZone("📁 拖曳影片或圖片到此處 📁\n支援 MP4, MOV, PNG, JPG 等格式")
        self.drop_zone.filesDropped.connect(self.handle_dropped_files)
        left_layout.addWidget(self.drop_zone)

        # 分欄佈局：左檔案右選項
        main_layout = QHBoxLayout()
        main_layout.setSpacing(12)
        
        # 左欄：檔案選擇
        files_widget = self.create_files_column()
        main_layout.addWidget(files_widget, 1)
        
        # 右欄：選項
        options_widget = self.create_options_column()
        main_layout.addWidget(options_widget, 1)
        
        left_layout.addLayout(main_layout)

        # 底部：主按鈕區
        self.create_control_buttons(left_layout)

        # 預覽區（可選，底部）
        self.chk_show_preview = QCheckBox("顯示預覽")
        self.chk_show_preview.setChecked(False)
        self.chk_show_preview.stateChanged.connect(lambda _: self.toggle_preview_group())
        left_layout.addWidget(self.chk_show_preview)
        
        self.preview_group = self.create_preview_group()
        self.preview_group.setVisible(False)
        left_layout.addWidget(self.preview_group)

        # 讓左側可捲動，避免內容超出視窗高度
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setWidget(left_widget)

        self.splitter.addWidget(left_scroll)

    def create_right_panel(self):
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        header_layout = QHBoxLayout()
        title = QLabel("處理工作列表")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.active_count_label = QLabel("進行中: 0")
        self.active_count_label.setStyleSheet("color: #4caf50; font-size: 12px;")
        self.pending_count_label = QLabel("佇列中: 0")
        self.pending_count_label.setStyleSheet("color: #ff9800; font-size: 12px;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.active_count_label)
        header_layout.addWidget(self.pending_count_label)
        right_layout.addLayout(header_layout)

        # 使用 QListView + Model/Delegate
        self.jobs_view = QListView()
        self.jobs_view.setUniformItemSizes(True)
        self.jobs_view.setMouseTracking(True)
        self.jobs_view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.jobs_model = JobListModel()
        self.jobs_delegate = JobItemDelegate(self.jobs_view)
        self.jobs_view.setModel(self.jobs_model)
        self.jobs_view.setItemDelegate(self.jobs_delegate)
        self.jobs_view.doubleClicked.connect(self.on_jobs_double_clicked)
        self.jobs_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.jobs_view.customContextMenuRequested.connect(self.on_jobs_context_menu)
        right_layout.addWidget(self.jobs_view)

        clear_all_btn = QPushButton("清除所有完成的工作")
        clear_all_btn.clicked.connect(self.clear_finished_jobs)
        right_layout.addWidget(clear_all_btn)

        self.splitter.addWidget(right_widget)

    def create_files_column(self):
        """左欄：檔案選擇"""
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setSpacing(8)

        # 影片選擇區塊
        video_group = QWidget()
        video_group.setObjectName("FunctionGroup")
        video_layout = QVBoxLayout(video_group)
        video_layout.setSpacing(4)
        
        video_title = QLabel("📹 影片檔案")
        video_title.setObjectName("SectionTitle")
        video_layout.addWidget(video_title)
        
        self.video_btn = QPushButton("選擇影片")
        self.video_btn.clicked.connect(self.select_video_file)
        self.video_label = QLabel("請選擇主要影片檔案")
        self.video_label.setStyleSheet("color: #888; font-size: 13px; font-style: italic;")
        video_layout.addWidget(self.video_btn)
        video_layout.addWidget(self.video_label)
        vbox.addWidget(video_group)

        # 圖片選擇區塊
        image_group = QWidget()
        image_group.setObjectName("FunctionGroup")
        image_layout = QVBoxLayout(image_group)
        image_layout.setSpacing(4)
        
        image_title = QLabel("🖼️ 圖片設定")
        image_title.setObjectName("SectionTitle")
        image_layout.addWidget(image_title)
        
        # 開頭圖片（水平佈局）
        start_layout = QHBoxLayout()
        start_layout.addWidget(QLabel("開頭:"))
        self.start_duration = QDoubleSpinBox()
        self.start_duration.setRange(0.1, 30.0)
        self.start_duration.setValue(3.0)
        self.start_duration.setSuffix("秒")
        self.start_duration.setFixedWidth(70)
        start_layout.addWidget(self.start_duration)
        start_layout.addStretch()
        image_layout.addLayout(start_layout)
        
        self.start_btn = QPushButton("選擇開頭圖片")
        self.start_btn.clicked.connect(self.select_start_image)
        self.start_label = QLabel("尚未選擇開頭圖片")
        self.start_label.setStyleSheet("color: #888; font-size: 13px; font-style: italic;")
        image_layout.addWidget(self.start_btn)
        image_layout.addWidget(self.start_label)

        # 同圖選項
        self.same_image_checkbox = QCheckBox("✨ 開頭與結尾使用相同圖片")
        self.same_image_checkbox.stateChanged.connect(self.on_same_image_changed)
        image_layout.addWidget(self.same_image_checkbox)

        # 結尾圖片（水平佈局）
        end_layout = QHBoxLayout()
        end_layout.addWidget(QLabel("結尾:"))
        self.end_duration = QDoubleSpinBox()
        self.end_duration.setRange(0.1, 30.0)
        self.end_duration.setValue(3.0)
        self.end_duration.setSuffix("秒")
        self.end_duration.setFixedWidth(70)
        end_layout.addWidget(self.end_duration)
        end_layout.addStretch()
        image_layout.addLayout(end_layout)
        
        self.end_btn = QPushButton("選擇結尾圖片")
        self.end_btn.clicked.connect(self.select_end_image)
        self.end_label = QLabel("尚未選擇結尾圖片")
        self.end_label.setStyleSheet("color: #888; font-size: 13px; font-style: italic;")
        image_layout.addWidget(self.end_btn)
        image_layout.addWidget(self.end_label)
        
        vbox.addWidget(image_group)
        vbox.addStretch()
        return widget

    def create_options_column(self):
        """右欄：選項"""
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setSpacing(8)

        # 處理選項區塊
        options_group = QWidget()
        options_group.setObjectName("FunctionGroup")
        options_layout = QVBoxLayout(options_group)
        options_layout.setSpacing(4)
        
        options_title = QLabel("⚙️ 處理選項")
        options_title.setObjectName("SectionTitle")
        options_layout.addWidget(options_title)
        
        self.chk_prefer_copy = QCheckBox("🚀 免重編碼優先")
        self.chk_prefer_copy.setChecked(True)
        self.chk_prefer_copy.stateChanged.connect(lambda _: self.on_options_changed())
        options_layout.addWidget(self.chk_prefer_copy)

        self.chk_use_hw = QCheckBox("⚡ 硬體加速編碼")
        self.chk_use_hw.setChecked(True)
        self.chk_use_hw.stateChanged.connect(lambda _: self.on_options_changed())
        options_layout.addWidget(self.chk_use_hw)

        self.auto_output_checkbox = QCheckBox("📁 自動輸出到來源資料夾")
        self.auto_output_checkbox.setChecked(True)
        self.auto_output_checkbox.stateChanged.connect(lambda _: setattr(self, 'auto_output_to_source', self.auto_output_checkbox.isChecked()))
        options_layout.addWidget(self.auto_output_checkbox)
        
        vbox.addWidget(options_group)

        # 狀態與資訊區塊
        info_group = QWidget()
        info_group.setObjectName("FunctionGroup")
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(4)
        
        info_title = QLabel("📊 檔案狀態")
        info_title.setObjectName("SectionTitle")
        info_layout.addWidget(info_title)
        
        # 選擇進度
        self.progress_label = QLabel("📋 請選擇檔案以開始")
        self.progress_label.setStyleSheet("color: #ff9800; font-size: 13px;")
        info_layout.addWidget(self.progress_label)
        
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setText("檔案資訊將顯示在此處...")
        self.info_text.setMaximumHeight(60)
        info_layout.addWidget(self.info_text)
        
        vbox.addWidget(info_group)
        vbox.addStretch()
        return widget

    def create_preview_group(self):
        group = QGroupBox()
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel("預覽"))
        self.preview_label = QLabel("請選擇檔案進行預覽")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFixedSize(350, 200)
        self.preview_label.setStyleSheet("background: #111; border: 1px solid #444;")
        vbox.addWidget(self.preview_label)

        btn_layout = QHBoxLayout()
        btn_preview_start = QPushButton("預覽開頭")
        btn_preview_start.clicked.connect(self.preview_start)
        btn_preview_video = QPushButton("預覽影片")
        btn_preview_video.clicked.connect(self.preview_video)
        btn_preview_end = QPushButton("預覽結尾")
        btn_preview_end.clicked.connect(self.preview_end)
        btn_layout.addWidget(btn_preview_start)
        btn_layout.addWidget(btn_preview_video)
        btn_layout.addWidget(btn_preview_end)
        vbox.addLayout(btn_layout)

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setText("檔案資訊將顯示在此處...")
        self.info_text.setMaximumHeight(120)
        vbox.addWidget(self.info_text)
        group.setLayout(vbox)
        return group

    def create_control_buttons(self, layout):
        """主按鈕區"""
        # 按鈕容器
        btn_container = QWidget()
        btn_container.setStyleSheet("""
            QWidget { 
                background: #2a2a2a; 
                border: 1px solid #3a3a3a; 
                border-radius: 8px; 
                padding: 8px; 
            }
        """)
        hbox = QHBoxLayout(btn_container)
        hbox.setSpacing(12)
        
        # 主 CTA 按鈕（更寬）
        self.process_btn = QPushButton("➕ 加入處理佇列")
        self.process_btn.setObjectName("PrimaryCTA")
        self.process_btn.setEnabled(False)
        self.process_btn.setToolTip("請先選擇影片和圖片檔案")
        self.process_btn.clicked.connect(self.add_to_queue)
        # 直接設定樣式
        self.apply_primary_button_style(self.process_btn)
        hbox.addWidget(self.process_btn, 3)
        
        # 次要按鈕
        self.clear_btn = QPushButton("🗑️ 清除")
        self.clear_btn.setObjectName("SecondaryBtn")
        self.clear_btn.setToolTip("清除所有已選擇的檔案")
        self.clear_btn.clicked.connect(self.clear_selection)
        # 直接設定樣式
        self.apply_secondary_button_style(self.clear_btn)
        hbox.addWidget(self.clear_btn, 1)
        
        layout.addWidget(btn_container)

    def apply_primary_button_style(self, button):
        """直接套用主要按鈕樣式"""
        button.setStyleSheet("""
            QPushButton {
                background-color: #4caf50;
                color: #ffffff;
                font-size: 16px;
                font-weight: 700;
                height: 40px;
                border: 2px solid #66bb6a;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #66bb6a;
                border: 2px solid #81c784;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #757575;
                border: 2px dashed #616161;
            }
        """)

    def apply_secondary_button_style(self, button):
        """直接套用次要按鈕樣式"""
        button.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: #ffffff;
                border: 1px solid #9e9e9e;
                border-radius: 5px;
                font-size: 14px;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background-color: #9e9e9e;
                border: 1px solid #bdbdbd;
            }
        """)

    def on_options_changed(self):
        self.prefer_copy_concat = self.chk_prefer_copy.isChecked()
        self.use_hardware = self.chk_use_hw.isChecked()

    def select_video_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "選擇影片檔案", "", "影片檔案 (*.mp4 *.mov *.mkv *.avi)")
        if file:
            self.video_file = file
            self.video_label.setText(os.path.basename(file))
            self.update_info_display()
            self.check_all_files_selected()

    def select_start_image(self):
        file, _ = QFileDialog.getOpenFileName(self, "選擇開頭圖片", "", "圖片檔案 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if file:
            self.start_image_file = file
            self.start_label.setText(os.path.basename(file))
            # 若勾選同圖，帶入結尾
            if hasattr(self, 'same_image_checkbox') and self.same_image_checkbox.isChecked():
                self.end_image_file = file
                self.end_label.setText(f"與開頭相同: {os.path.basename(file)}")
            self.update_info_display()
            self.check_all_files_selected()

    def select_end_image(self):
        file, _ = QFileDialog.getOpenFileName(self, "選擇結尾圖片", "", "圖片檔案 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if file:
            self.end_image_file = file
            self.end_label.setText(os.path.basename(file))
            self.update_info_display()
            self.check_all_files_selected()

    def check_all_files_selected(self):
        has_video = bool(self.video_file)
        has_start = bool(self.start_image_file)
        # 若同圖勾選，且已有開頭圖，視為也有結尾圖
        has_end = bool(self.end_image_file) or (hasattr(self, 'same_image_checkbox') and self.same_image_checkbox.isChecked() and has_start)
        
        if has_video and (has_start or has_end):
            self.process_btn.setEnabled(True)
            self.process_btn.setText("➕ 加入處理佇列")
            self.process_btn.setToolTip("準備好！點擊開始處理")
        else:
            self.process_btn.setEnabled(False)
            if not has_video:
                self.process_btn.setText("⚠️ 請先選擇影片")
                self.process_btn.setToolTip("需要選擇主要影片檔案")
            elif not has_start and not has_end:
                self.process_btn.setText("⚠️ 請選擇圖片")
                self.process_btn.setToolTip("需要至少選擇開頭或結尾圖片")
        
        # 更新進度指示
        self.update_progress_indicator(has_video, has_start, has_end)

    def update_info_display(self):
        info = ""
        if self.video_file:
            try:
                pr = probe_main_video(self.env.ffprobe_path, self.video_file)
                info += f"📹 {os.path.basename(self.video_file)}\n{pr.width}x{pr.height} @ {pr.fps:.1f}fps\n{pr.video_codec} / {'有音' if pr.has_audio else '無音'}\n\n"
            except Exception:
                info += f"📹 {os.path.basename(self.video_file)}\n無法讀取資訊\n\n"
        if self.start_image_file:
            info += f"🖼️ 開頭: {os.path.basename(self.start_image_file)} ({self.start_duration.value()}秒)\n"
        if self.end_image_file:
            info += f"🖼️ 結尾: {os.path.basename(self.end_image_file)} ({self.end_duration.value()}秒)\n"
        elif hasattr(self, 'same_image_checkbox') and self.same_image_checkbox.isChecked() and self.start_image_file:
            info += f"🖼️ 結尾: 與開頭相同 ({self.end_duration.value()}秒)\n"
        
        if not info.strip():
            info = "檔案資訊將顯示在此處..."
        self.info_text.setText(info)
    
    def update_progress_indicator(self, has_video, has_start, has_end):
        """更新選擇進度指示器"""
        if not hasattr(self, 'progress_label'):
            return
        
        if has_video and (has_start or has_end):
            self.progress_label.setText("✅ 檔案選擇完成，可以開始處理")
            self.progress_label.setStyleSheet("color: #4caf50; font-size: 13px; font-weight: 500;")
        elif has_video:
            self.progress_label.setText("🟡 影片已選，請選擇圖片")
            self.progress_label.setStyleSheet("color: #ff9800; font-size: 13px;")
        elif has_start or has_end:
            self.progress_label.setText("🟡 圖片已選，請選擇影片")
            self.progress_label.setStyleSheet("color: #ff9800; font-size: 13px;")
        else:
            self.progress_label.setText("📋 請選擇檔案以開始")
            self.progress_label.setStyleSheet("color: #ff9800; font-size: 13px;")

    def preview_start(self):
        if not self.start_image_file:
            QMessageBox.warning(self, "警告", "請先選擇開頭圖片")
            return
        img = QPixmap(self.start_image_file)
        self.preview_label.setPixmap(img.scaled(350, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def preview_video(self):
        if not self.video_file:
            QMessageBox.warning(self, "警告", "請先選擇影片檔案")
            return
        try:
            # 以 ffmpeg 擷取首幀縮圖到暫存，簡化處理
            tmp = os.path.join(tempfile.gettempdir(), f"vw2_{uuid.uuid4().hex}.jpg")
            subprocess.run([self.env.ffmpeg_path, '-y', '-ss', '0', '-i', self.video_file, '-frames:v', '1', tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(tmp):
                img = QPixmap(tmp)
                self.preview_label.setPixmap(img.scaled(350, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                try:
                    os.remove(tmp)
                except Exception:
                    pass
        except Exception:
            self.preview_label.setText("無法預覽影片")

    def preview_end(self):
        if not self.end_image_file:
            QMessageBox.warning(self, "警告", "請先選擇結尾圖片")
            return
        img = QPixmap(self.end_image_file)
        self.preview_label.setPixmap(img.scaled(350, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def add_to_queue(self):
        if not self.video_file:
            QMessageBox.critical(self, "錯誤", "請選擇影片檔案")
            return
        if not self.start_image_file and not self.end_image_file:
            QMessageBox.critical(self, "錯誤", "請至少選擇開頭或結尾圖片")
            return

        default_name = f"processed_{os.path.splitext(os.path.basename(self.video_file))[0]}.mp4"
        output_file = None
        if getattr(self, 'auto_output_to_source', True):
            output_file = os.path.join(os.path.dirname(self.video_file), default_name)
        else:
            of, _ = QFileDialog.getSaveFileName(self, "儲存處理後的影片", default_name, "MP4 檔案 (*.mp4);;所有檔案 (*.*)")
            output_file = of
            if not output_file:
                return

        job_id = str(uuid.uuid4())
        job_name = os.path.basename(self.video_file)
        # 新列表模型加入項目
        job_item = JobItem(job_id, job_name)
        self.jobs_model.add_item(job_item)

        # 若勾選同圖，確保結尾路徑帶入
        if hasattr(self, 'same_image_checkbox') and self.same_image_checkbox.isChecked():
            self.end_image_file = self.start_image_file

        processor_args = {
            'job_id': job_id,
            'video_file': self.video_file,
            'start_image': self.start_image_file,
            'end_image': self.end_image_file,
            'start_duration': self.start_duration.value(),
            'end_duration': self.end_duration.value(),
            'output_file': output_file,
            'prefer_copy_concat': self.prefer_copy_concat,
            'use_hardware': self.use_hardware,
            'env': self.env,
        }

        self.job_queue.append(processor_args)
        self.jobs_model.set_state(job_id, "queued", "已加入佇列…")
        self.update_queue_count()
        self.process_next_in_queue()
        # 非阻塞提示：狀態列訊息
        try:
            self.statusBar().showMessage(f"已加入佇列：{job_name} → {os.path.basename(output_file)}", 3000)
        except Exception:
            pass

    def process_next_in_queue(self):
        if not self.job_queue or len(self.active_processors) >= self.MAX_CONCURRENT_JOBS:
            return

        processor_args = self.job_queue.pop(0)
        job_id = processor_args['job_id']
        # 若模型中找不到相對應項目，仍繼續處理（只是不顯示）
        if self.jobs_model.find_row_by_id(job_id) < 0:
            pass

        processor = FFmpegWrapperProcessor(**processor_args)
        processor.progress.connect(self.on_job_progress)
        processor.status.connect(self.on_job_status)
        processor.job_finished.connect(self.on_job_finished)
        processor.error.connect(self.on_job_error)
        processor.finished.connect(processor.deleteLater)
        processor.finished.connect(lambda job_id=job_id: self.on_thread_finished(job_id))

        self.active_processors[job_id] = processor
        self.update_active_count()
        self.update_queue_count()
        processor.start()

    def cancel_job(self, job_id):
        job_in_queue = next((job for job in self.job_queue if job['job_id'] == job_id), None)
        if job_in_queue:
            self.job_queue.remove(job_in_queue)
            self.jobs_model.set_state(job_id, "cancel", "已取消")
            self.update_queue_count()
            return

        if job_id in self.active_processors:
            self.active_processors[job_id].cancel()
            self.jobs_model.set_state(job_id, "cancel", "取消中…")

    def on_job_progress(self, job_id, progress):
        row = self.jobs_model.find_row_by_id(job_id)
        if row >= 0:
            self.jobs_model.update_progress(job_id, progress)

    def on_job_status(self, job_id, status):
        row = self.jobs_model.find_row_by_id(job_id)
        if row >= 0:
            # running 狀態
            self.jobs_model.set_state(job_id, "running", status)

    def on_job_finished(self, job_id, output_file):
        row = self.jobs_model.find_row_by_id(job_id)
        if row >= 0:
            self.jobs_model.set_state(job_id, "done", "完成", output_file)

    def on_job_error(self, job_id, error_message):
        row = self.jobs_model.find_row_by_id(job_id)
        if row >= 0:
            self.jobs_model.set_state(job_id, "error", f"錯誤: {error_message}")

    def on_thread_finished(self, job_id):
        if job_id in self.active_processors:
            del self.active_processors[job_id]
        self.update_active_count()
        self.process_next_in_queue()

    def update_active_count(self):
        active_count = len(self.active_processors)
        self.active_count_label.setText(f"進行中: {active_count}")

    def update_queue_count(self):
        queue_count = len(self.job_queue)
        self.pending_count_label.setText(f"佇列中: {queue_count}")

    def clear_finished_jobs(self):
        # 清除模型內已完成/取消/錯誤之項目
        kept: list[JobItem] = []
        for item in self.jobs_model.items:
            if item.state == "running" or item.state == "queued":
                kept.append(item)
        if len(kept) != len(self.jobs_model.items):
            self.jobs_model.beginResetModel()
            self.jobs_model.items = kept
            self.jobs_model.endResetModel()

    # --- Jobs view interactions ---
    def on_jobs_double_clicked(self, index: QModelIndex):
        item: JobItem = index.data(Qt.ItemDataRole.UserRole)
        if not item:
            return
        if item.state in ("running", "queued"):
            self.cancel_job(item.job_id)
        elif item.state == "done" and item.output_file and os.path.exists(item.output_file):
            subprocess.run(["open", "-R", item.output_file])

    def on_jobs_context_menu(self, pos):
        index = self.jobs_view.indexAt(pos)
        if not index.isValid():
            return
        item: JobItem = index.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        if item.state in ("running", "queued"):
            act_cancel = menu.addAction("取消")
            act = menu.exec(self.jobs_view.mapToGlobal(pos))
            if act == act_cancel:
                self.cancel_job(item.job_id)
            return
        if item.state == "done":
            act_open = menu.addAction("開啟檔案")
            act_reveal = menu.addAction("在 Finder 顯示")
            act_remove = menu.addAction("自列表移除")
            act = menu.exec(self.jobs_view.mapToGlobal(pos))
            if act == act_open and item.output_file and os.path.exists(item.output_file):
                subprocess.run(["open", item.output_file])
            elif act == act_reveal and item.output_file:
                subprocess.run(["open", "-R", item.output_file])
            elif act == act_remove:
                self.jobs_model.remove_row(index.row())
    def clear_selection(self):
        self.video_file = None
        self.start_image_file = None
        self.end_image_file = None
        self.video_label.setText("未選擇檔案")
        self.start_label.setText("未選擇檔案")
        self.end_label.setText("未選擇檔案")
        self.start_duration.setValue(3.0)
        self.end_duration.setValue(3.0)
        self.chk_prefer_copy.setChecked(True)
        self.chk_use_hw.setChecked(True)
        if hasattr(self, 'same_image_checkbox'):
            self.same_image_checkbox.setChecked(False)
        if hasattr(self, 'auto_output_checkbox'):
            self.auto_output_checkbox.setChecked(True)
        if hasattr(self, 'end_btn'):
            self.end_btn.setEnabled(True)
        self.preview_label.clear()
        self.preview_label.setText("請選擇檔案進行預覽")
        self.info_text.setText("檔案資訊將顯示在此處...")
        self.check_all_files_selected()

    # --- 處理 DropZone 與視窗拖放 ---
    def handle_dropped_files(self, paths):
        try:
            video_exts = ('.mp4', '.mov', '.mkv', '.avi')
            image_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')
            for path in paths:
                lower = path.lower()
                if lower.endswith(video_exts):
                    self.video_file = path
                    self.video_label.setText(os.path.basename(path))
                elif lower.endswith(image_exts):
                    if not self.start_image_file:
                        self.start_image_file = path
                        self.start_label.setText(os.path.basename(path))
                        if hasattr(self, 'same_image_checkbox') and self.same_image_checkbox.isChecked():
                            self.end_image_file = path
                            self.end_label.setText(f"與開頭相同: {os.path.basename(path)}")
                    elif (hasattr(self, 'same_image_checkbox') and self.same_image_checkbox.isChecked()):
                        self.start_image_file = path
                        self.start_label.setText(os.path.basename(path))
                        self.end_image_file = path
                        self.end_label.setText(f"與開頭相同: {os.path.basename(path)}")
                    elif not self.end_image_file:
                        self.end_image_file = path
                        self.end_label.setText(os.path.basename(path))
            self.update_info_display()
            self.check_all_files_selected()
        except Exception:
            pass

    # --- 同圖選項邏輯 ---
    def on_same_image_changed(self, state):
        if state == 2:
            # 勾選：禁用結尾選擇，帶入與開頭相同
            if hasattr(self, 'end_btn'):
                self.end_btn.setEnabled(False)
            if self.start_image_file:
                self.end_image_file = self.start_image_file
                self.end_label.setText(f"與開頭相同: {os.path.basename(self.start_image_file)}")
            else:
                self.end_label.setText("請先選擇開頭圖片")
        else:
            # 取消勾選：允許單獨選擇結尾
            if hasattr(self, 'end_btn'):
                self.end_btn.setEnabled(True)
            self.end_image_file = None
            self.end_label.setText("未選擇檔案")
        self.update_info_display()
        self.check_all_files_selected()

    # --- 拖放支援 ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        try:
            urls = event.mimeData().urls()
            paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
            if paths:
                self.handle_dropped_files(paths)
            event.acceptProposedAction()
        except Exception:
            event.ignore()

    # --- 預覽切換 ---
    def toggle_preview_group(self):
        if hasattr(self, 'preview_group') and self.preview_group:
            self.preview_group.setVisible(self.chk_show_preview.isChecked())

    def closeEvent(self, event):
        if self.active_processors:
            reply = QMessageBox.question(
                self, '警告',
                f"還有 {len(self.active_processors)} 個工作正在進行中。\n確定要強制關閉嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

        self.job_queue.clear()
        for job_id, processor in list(self.active_processors.items()):
            processor.cancel()
            processor.wait()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = VideoEditorFFApp()
    win.show()
    sys.exit(app.exec())


