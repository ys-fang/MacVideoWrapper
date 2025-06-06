#!/usr/bin/env python3

# -*- coding: utf-8 -*-

"""
Mac 影片編輯器 - 添加開頭結尾靜態畫面 (PyQt6 並行處理版本)
需要安裝：pip install PyQt6 pillow opencv-python moviepy
需要安裝 FFmpeg：brew install ffmpeg
或者使用：pip install -r requirements.txt
"""

import sys
import os
import cv2
import subprocess
import threading
import uuid
import tempfile
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QFileDialog, QVBoxLayout, QHBoxLayout,
    QGroupBox, QSpinBox, QTextEdit, QProgressBar, QMessageBox, QDoubleSpinBox, QCheckBox,
    QScrollArea, QFrame, QSplitter
)
from PyQt6.QtGui import QPixmap, QFont, QColor, QImage
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer
from PIL import Image
from moviepy.editor import VideoFileClip, ImageClip, concatenate_videoclips

class VideoProcessor(QThread):
    """影片處理工作線程"""
    progress = pyqtSignal(str, int)  # 工作ID和進度信號
    status = pyqtSignal(str, str)    # 工作ID和狀態信號
    finished = pyqtSignal(str, str)  # 工作ID和輸出檔案路徑
    error = pyqtSignal(str, str)     # 工作ID和錯誤信號
    
    def __init__(self, job_id, video_file, start_image, end_image, start_duration, end_duration, output_file):
        super().__init__()
        self.job_id = job_id
        self.video_file = video_file
        self.start_image = start_image
        self.end_image = end_image
        self.start_duration = start_duration
        self.end_duration = end_duration
        self.output_file = output_file
        self.is_cancelled = False
    
    def cancel(self):
        """取消處理"""
        self.is_cancelled = True
    
    def run(self):
        temp_audio_path = None
        video_clip, start_clip, end_clip, final_clip = None, None, None, None
        
        try:
            if self.is_cancelled:
                return
                
            self.status.emit(self.job_id, "載入影片...")
            self.progress.emit(self.job_id, 10)
            
            video_clip = VideoFileClip(self.video_file)
            clips_to_concatenate = []
            
            if self.is_cancelled: return
            
            if self.start_image:
                self.status.emit(self.job_id, "處理開頭圖片...")
                self.progress.emit(self.job_id, 30)
                start_clip = ImageClip(self.start_image, duration=self.start_duration).resize((video_clip.w, video_clip.h))
                clips_to_concatenate.append(start_clip)
            
            if self.is_cancelled: return
            
            clips_to_concatenate.append(video_clip)
            
            if self.end_image:
                self.status.emit(self.job_id, "處理結尾圖片...")
                self.progress.emit(self.job_id, 50)
                end_clip = ImageClip(self.end_image, duration=self.end_duration).resize((video_clip.w, video_clip.h))
                clips_to_concatenate.append(end_clip)
            
            if self.is_cancelled: return
            
            self.status.emit(self.job_id, "合併影片...")
            self.progress.emit(self.job_id, 70)
            
            final_clip = concatenate_videoclips(clips_to_concatenate)
            
            if self.is_cancelled: return
            
            self.status.emit(self.job_id, "輸出影片...")
            self.progress.emit(self.job_id, 80)
            
            temp_dir = tempfile.gettempdir()
            temp_audio_path = os.path.join(temp_dir, f"temp-audio-{self.job_id}.m4a")
            
            final_clip.write_videofile(
                self.output_file,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=temp_audio_path,
                remove_temp=True,
                verbose=False,
                logger=None
            )
            
            if self.is_cancelled: return
            
            self.progress.emit(self.job_id, 100)
            self.status.emit(self.job_id, "處理完成！")
            self.finished.emit(self.job_id, self.output_file)
            
        except Exception as e:
            if not self.is_cancelled:
                self.error.emit(self.job_id, str(e))
        finally:
            # 確保所有資源都被釋放，無論成功、失敗或取消
            if start_clip:
                start_clip.close()
            if end_clip:
                end_clip.close()
            if final_clip:
                final_clip.close()
            if video_clip:
                video_clip.close()
            
            # 確保臨時檔案在任何情況下都被清理
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                except OSError:
                    pass

class JobWidget(QFrame):
    """單個處理工作的顯示控件"""
    cancel_requested = pyqtSignal(str)  # 取消工作信號
    
    def __init__(self, job_id, job_name):
        super().__init__()
        self.job_id = job_id
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("QFrame { background: #2a2a2a; border: 1px solid #444; border-radius: 4px; margin: 2px; padding: 5px; }")
        
        layout = QVBoxLayout(self)
        
        # 工作名稱和時間
        header_layout = QHBoxLayout()
        self.name_label = QLabel(job_name)
        self.name_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.time_label = QLabel(datetime.now().strftime("%H:%M:%S"))
        self.time_label.setStyleSheet("color: #888; font-size: 10px;")
        header_layout.addWidget(self.name_label)
        header_layout.addStretch()
        header_layout.addWidget(self.time_label)
        layout.addLayout(header_layout)
        
        # 進度條和狀態
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.status_label = QLabel("準備中...")
        self.status_label.setStyleSheet("color: #ccc; font-size: 10px;")
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        
        # 按鈕區域
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

class VideoEditorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("影片編輯器 - 序列處理模式")
        self.resize(1200, 800)
        self.setStyleSheet(self.get_dark_theme())

        # 檔案變數
        self.video_file = None
        self.start_image_file = None
        self.end_image_file = None
        
        # 處理器管理
        self.active_processors = {}
        self.job_widgets = {}
        self.job_queue = []
        # 設定為序列處理模式
        self.MAX_CONCURRENT_JOBS = 1
        
        # 主 widget 和分割器
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        
        # 創建分割器
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.splitter)
        
        # 左側：檔案選擇和預覽
        self.create_left_panel()
        # 右側：處理工作列表
        self.create_right_panel()
        
        # 設置分割器比例
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)

        # 初始化計數器顯示
        self.update_active_count()
        self.update_queue_count()

    def get_dark_theme(self):
        return """
            QWidget { background: #232323; color: #f0f0f0; }
            QGroupBox { background: #2c2c2c; border: 1px solid #444; border-radius: 6px; margin-top: 10px; }
            QGroupBox:title { color: #fff; subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }
            QLabel { color: #f0f0f0; font-size: 14px; }
            QPushButton { background: #007acc; color: #fff; border: 1px solid #444; border-radius: 4px; padding: 8px; font-size: 14px; }
            QPushButton:disabled { background: #444; color: #888; }
            QPushButton:hover { background: #0099ff; }
            QProgressBar { background: #2c2c2c; border: 1px solid #444; border-radius: 4px; text-align: center; color: #fff; }
            QProgressBar::chunk { background: #0078d4; }
            QTextEdit { background: #232323; color: #d0d0d0; border: 1px solid #444; border-radius: 4px; }
            QSpinBox, QDoubleSpinBox { background: #232323; color: #fff; border: 1px solid #444; border-radius: 4px; }
            QCheckBox { color: #f0f0f0; font-size: 13px; }
            QCheckBox::indicator { width: 15px; height: 15px; }
            QCheckBox::indicator:unchecked { background: #444; border: 1px solid #666; border-radius: 3px; }
            QCheckBox::indicator:checked { background: #007acc; border: 1px solid #007acc; border-radius: 3px; }
            QScrollArea { background: #1e1e1e; border: 1px solid #444; }
            QSplitter::handle { background: #444; }
        """

    def create_left_panel(self):
        """創建左側面板"""
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # 標題
        title = QLabel("影片編輯器 - 序列處理")
        title.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        subtitle = QLabel("所有工作將依序排隊處理")
        subtitle.setFont(QFont("Arial", 11))
        subtitle.setStyleSheet("color: #b0b0b0;")
        left_layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)
        left_layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        # 主內容
        content_layout = QHBoxLayout()
        
        # 檔案選擇
        content_layout.addWidget(self.create_file_group(), 1)
        # 預覽
        content_layout.addWidget(self.create_preview_group(), 1)
        
        left_layout.addLayout(content_layout)
        
        # 控制按鈕
        self.create_control_buttons(left_layout)
        
        self.splitter.addWidget(left_widget)

    def create_right_panel(self):
        """創建右側工作列表面板"""
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # 標題
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
        
        # 工作列表滾動區域
        self.jobs_scroll = QScrollArea()
        self.jobs_scroll.setWidgetResizable(True)
        self.jobs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.jobs_container = QWidget()
        self.jobs_layout = QVBoxLayout(self.jobs_container)
        self.jobs_layout.addStretch()  # 底部彈性空間
        
        self.jobs_scroll.setWidget(self.jobs_container)
        right_layout.addWidget(self.jobs_scroll)
        
        # 清除按鈕
        clear_all_btn = QPushButton("清除所有完成的工作")
        clear_all_btn.clicked.connect(self.clear_finished_jobs)
        right_layout.addWidget(clear_all_btn)
        
        self.splitter.addWidget(right_widget)

    def create_file_group(self):
        group = QGroupBox()
        vbox = QVBoxLayout()
        # 影片
        self.video_btn = QPushButton("選擇影片檔案")
        self.video_btn.clicked.connect(self.select_video_file)
        self.video_label = QLabel("未選擇檔案")
        vbox.addWidget(QLabel("選擇影片檔案"))
        vbox.addWidget(self.video_btn)
        vbox.addWidget(self.video_label)
        # 開頭圖片
        self.start_btn = QPushButton("選擇開頭圖片")
        self.start_btn.clicked.connect(self.select_start_image)
        self.start_label = QLabel("未選擇檔案")
        self.start_duration = QDoubleSpinBox()
        self.start_duration.setRange(0.1, 30.0)
        self.start_duration.setValue(3.0)
        self.start_duration.valueChanged.connect(self.update_info_display)
        vbox.addWidget(QLabel("選擇開頭圖片"))
        vbox.addWidget(self.start_btn)
        vbox.addWidget(self.start_label)
        vbox.addWidget(QLabel("顯示時間 (秒):"))
        vbox.addWidget(self.start_duration)
        
        # 開頭與結尾圖片一樣的選項
        self.same_image_checkbox = QCheckBox("開頭與結尾圖片一樣")
        self.same_image_checkbox.stateChanged.connect(self.on_same_image_changed)
        vbox.addWidget(self.same_image_checkbox)
        
        # 結尾圖片
        self.end_btn = QPushButton("選擇結尾圖片")
        self.end_btn.clicked.connect(self.select_end_image)
        self.end_label = QLabel("未選擇檔案")
        self.end_duration = QDoubleSpinBox()
        self.end_duration.setRange(0.1, 30.0)
        self.end_duration.setValue(3.0)
        self.end_duration.valueChanged.connect(self.update_info_display)
        vbox.addWidget(QLabel("選擇結尾圖片"))
        vbox.addWidget(self.end_btn)
        vbox.addWidget(self.end_label)
        vbox.addWidget(QLabel("顯示時間 (秒):"))
        vbox.addWidget(self.end_duration)
        group.setLayout(vbox)
        return group

    def create_preview_group(self):
        group = QGroupBox()
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel("預覽"))
        # 預覽畫面
        self.preview_label = QLabel("請選擇檔案進行預覽")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFixedSize(350, 200)
        self.preview_label.setStyleSheet("background: #111; border: 1px solid #444;")
        vbox.addWidget(self.preview_label)
        # 預覽按鈕
        btn_layout = QHBoxLayout()
        self.btn_preview_start = QPushButton("預覽開頭")
        self.btn_preview_start.clicked.connect(self.preview_start)
        self.btn_preview_video = QPushButton("預覽影片")
        self.btn_preview_video.clicked.connect(self.preview_video)
        self.btn_preview_end = QPushButton("預覽結尾")
        self.btn_preview_end.clicked.connect(self.preview_end)
        btn_layout.addWidget(self.btn_preview_start)
        btn_layout.addWidget(self.btn_preview_video)
        btn_layout.addWidget(self.btn_preview_end)
        vbox.addLayout(btn_layout)
        # 資訊顯示
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setText("檔案資訊將顯示在此處...")
        self.info_text.setMaximumHeight(120)
        vbox.addWidget(self.info_text)
        group.setLayout(vbox)
        return group

    def create_control_buttons(self, layout):
        hbox = QHBoxLayout()
        self.process_btn = QPushButton("加入處理隊列")
        self.process_btn.setEnabled(False)
        self.process_btn.clicked.connect(self.add_to_queue)
        self.clear_btn = QPushButton("清除檔案選擇")
        self.clear_btn.clicked.connect(self.clear_selection)
        hbox.addWidget(self.process_btn)
        hbox.addWidget(self.clear_btn)
        layout.addLayout(hbox)

    def select_video_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "選擇影片檔案", "", "影片檔案 (*.mp4 *.mov *.avi *.mkv *.wmv)")
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
            
            # 如果勾選了「開頭與結尾圖片一樣」，自動設定結尾圖片
            if self.same_image_checkbox.isChecked():
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

    def on_same_image_changed(self, state):
        """處理「開頭與結尾圖片一樣」checkbox 的變化"""
        if state == 2:  # 勾選狀態
            # 禁用結尾圖片選擇按鈕和標籤
            self.end_btn.setEnabled(False)
            # 如果已選擇開頭圖片，自動設定結尾圖片
            if self.start_image_file:
                self.end_image_file = self.start_image_file
                self.end_label.setText(f"與開頭相同: {os.path.basename(self.start_image_file)}")
            else:
                self.end_label.setText("請先選擇開頭圖片")
        else:  # 取消勾選
            # 啟用結尾圖片選擇按鈕
            self.end_btn.setEnabled(True)
            # 清除結尾圖片設定
            self.end_image_file = None
            self.end_label.setText("未選擇檔案")
        
            self.update_info_display()
            self.check_all_files_selected()

    def check_all_files_selected(self):
        """檢查是否已選擇必要的檔案"""
        # 必須有影片檔案，且至少有開頭或結尾圖片之一
        has_video = bool(self.video_file)
        has_start = bool(self.start_image_file)
        has_end = bool(self.end_image_file)
        
        if has_video and (has_start or has_end):
            self.process_btn.setEnabled(True)
        else:
            self.process_btn.setEnabled(False)

    def update_info_display(self):
        info = "檔案資訊:\n\n"
        if self.video_file:
            try:
                cap = cv2.VideoCapture(self.video_file)
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                duration = frame_count / fps if fps > 0 else 0
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                info += f"影片: {os.path.basename(self.video_file)}\n解析度: {width}x{height}\n時長: {duration:.1f} 秒\n幀率: {fps:.1f} FPS\n\n"
            except:
                info += f"影片: {os.path.basename(self.video_file)}\n無法讀取影片資訊\n\n"
        if self.start_image_file:
            try:
                img = Image.open(self.start_image_file)
                info += f"開頭圖片: {os.path.basename(self.start_image_file)}\n尺寸: {img.size[0]}x{img.size[1]}\n顯示時間: {self.start_duration.value()} 秒\n\n"
            except:
                info += f"開頭圖片: {os.path.basename(self.start_image_file)}\n\n"
        if self.end_image_file:
            try:
                img = Image.open(self.end_image_file)
                if self.same_image_checkbox.isChecked():
                    info += f"結尾圖片: 與開頭相同\n顯示時間: {self.end_duration.value()} 秒\n"
                else:
                    info += f"結尾圖片: {os.path.basename(self.end_image_file)}\n尺寸: {img.size[0]}x{img.size[1]}\n顯示時間: {self.end_duration.value()} 秒\n"
            except:
                info += f"結尾圖片: {os.path.basename(self.end_image_file)}\n"
        self.info_text.setText(info)

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
        cap = cv2.VideoCapture(self.video_file)
        ret, frame = cap.read()
        cap.release()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            img = QPixmap.fromImage(
                QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
            )
            self.preview_label.setPixmap(img.scaled(350, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.preview_label.setText("無法讀取影片幀")

    def preview_end(self):
        if not self.end_image_file:
            QMessageBox.warning(self, "警告", "請先選擇結尾圖片")
            return
        img = QPixmap(self.end_image_file)
        self.preview_label.setPixmap(img.scaled(350, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def add_to_queue(self):
        """加入處理隊列"""
        if not self.video_file:
            QMessageBox.critical(self, "錯誤", "請選擇影片檔案")
            return
        
        if not self.start_image_file and not self.end_image_file:
            QMessageBox.critical(self, "錯誤", "請至少選擇開頭或結尾圖片")
            return
        
        # 選擇輸出檔案
        default_name = f"processed_{os.path.splitext(os.path.basename(self.video_file))[0]}.mp4"
        output_file, _ = QFileDialog.getSaveFileName(
            self, "儲存處理後的影片", default_name, 
            "MP4 檔案 (*.mp4);;所有檔案 (*.*)"
        )
        
        if not output_file:
            return
        
        # 生成工作ID
        job_id = str(uuid.uuid4())
        job_name = os.path.basename(self.video_file)
        
        # 創建工作顯示控件
        job_widget = JobWidget(job_id, job_name)
        job_widget.cancel_requested.connect(self.cancel_job)
        
        # 添加到工作列表（插入到末尾之前）
        self.jobs_layout.insertWidget(self.jobs_layout.count() - 1, job_widget)
        self.job_widgets[job_id] = job_widget
        
        # 準備處理器參數
        processor_args = {
            'job_id': job_id,
            'video_file': self.video_file,
            'start_image': self.start_image_file,
            'end_image': self.end_image_file,
            'start_duration': self.start_duration.value(),
            'end_duration': self.end_duration.value(),
            'output_file': output_file
        }
        
        # 添加到佇列
        self.job_queue.append(processor_args)
        job_widget.update_status("已加入佇列...")
        job_widget.status_label.setStyleSheet("color: #ffc107; font-size: 10px;")
        
        self.update_queue_count()
        self.process_next_in_queue()
        
        QMessageBox.information(self, "成功", f"工作已加入處理隊列!\n\n影片: {job_name}\n輸出: {os.path.basename(output_file)}")

    def process_next_in_queue(self):
        """處理佇列中的下一個工作"""
        if not self.job_queue or len(self.active_processors) >= self.MAX_CONCURRENT_JOBS:
            return

        # 從佇列中取出下一個工作
        processor_args = self.job_queue.pop(0)
        job_id = processor_args['job_id']

        # 如果工作已被用戶清除，則跳過
        if job_id not in self.job_widgets:
            self.process_next_in_queue() # 嘗試下一個
            return

        # 創建並啟動處理器線程
        processor = VideoProcessor(**processor_args)
        
        # 連接信號
        processor.progress.connect(self.on_job_progress)
        processor.status.connect(self.on_job_status)
        processor.finished.connect(self.on_job_finished)
        processor.error.connect(self.on_job_error)
        
        self.active_processors[job_id] = processor
        self.update_active_count()
        self.update_queue_count()
        
        # 啟動線程
        processor.start()

    def cancel_job(self, job_id):
        """取消工作"""
        # 檢查工作是否在佇列中
        job_in_queue = next((job for job in self.job_queue if job['job_id'] == job_id), None)
        if job_in_queue:
            self.job_queue.remove(job_in_queue)
            if job_id in self.job_widgets:
                self.job_widgets[job_id].set_cancelled()
            self.update_queue_count()
            return
            
        # 如果工作正在處理中
        if job_id in self.active_processors:
            self.active_processors[job_id].cancel()
            self.active_processors[job_id].wait()  # 等待線程結束
            del self.active_processors[job_id]
            
        if job_id in self.job_widgets:
            self.job_widgets[job_id].set_cancelled()
            
        self.update_active_count()
        self.process_next_in_queue()

    def on_job_progress(self, job_id, progress):
        """更新工作進度"""
        if job_id in self.job_widgets:
            self.job_widgets[job_id].update_progress(progress)

    def on_job_status(self, job_id, status):
        """更新工作狀態"""
        if job_id in self.job_widgets:
            self.job_widgets[job_id].update_status(status)

    def on_job_finished(self, job_id, output_file):
        """工作完成回調"""
        if job_id in self.job_widgets:
            self.job_widgets[job_id].set_finished(output_file)
            
        if job_id in self.active_processors:
            del self.active_processors[job_id]
            
        self.update_active_count()
        self.process_next_in_queue()

    def on_job_error(self, job_id, error_message):
        """工作錯誤回調"""
        if job_id in self.job_widgets:
            self.job_widgets[job_id].set_error(error_message)
            
        if job_id in self.active_processors:
            del self.active_processors[job_id]
            
        self.update_active_count()
        self.process_next_in_queue()

    def update_active_count(self):
        """更新活躍工作數量顯示"""
        active_count = len(self.active_processors)
        if self.MAX_CONCURRENT_JOBS > 1:
            self.active_count_label.setText(f"進行中: {active_count}/{self.MAX_CONCURRENT_JOBS}")
        else:
            self.active_count_label.setText(f"進行中: {active_count}")

    def update_queue_count(self):
        """更新佇列中工作數量顯示"""
        queue_count = len(self.job_queue)
        self.pending_count_label.setText(f"佇列中: {queue_count}")

    def clear_finished_jobs(self):
        """清除所有已完成的工作"""
        to_remove = []
        for job_id, widget in self.job_widgets.items():
            if widget.cancel_btn.isEnabled() == False:  # 已完成或已取消的工作
                to_remove.append(job_id)
        
        for job_id in to_remove:
            widget = self.job_widgets[job_id]
            widget.setParent(None)
            widget.deleteLater()
            del self.job_widgets[job_id]

    def clear_selection(self):
        """清除檔案選擇"""
        self.video_file = None
        self.start_image_file = None
        self.end_image_file = None
        self.video_label.setText("未選擇檔案")
        self.start_label.setText("未選擇檔案")
        self.end_label.setText("未選擇檔案")
        self.start_duration.setValue(3.0)
        self.end_duration.setValue(3.0)
        self.same_image_checkbox.setChecked(False)
        self.end_btn.setEnabled(True)
        self.preview_label.clear()
        self.preview_label.setText("請選擇檔案進行預覽")
        self.info_text.setText("檔案資訊將顯示在此處...")
        self.check_all_files_selected()

    def closeEvent(self, event):
        """重寫關閉事件，確保線程安全退出"""
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

        # 清空佇列
        self.job_queue.clear()
        
        # 取消所有正在執行的線程
        for job_id, processor in list(self.active_processors.items()):
            print(f"正在取消工作 {job_id}...")
            processor.cancel()
            processor.wait() # 等待線程結束
            print(f"工作 {job_id} 已停止。")

        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = VideoEditorApp()
    win.show()
    sys.exit(app.exec()) 