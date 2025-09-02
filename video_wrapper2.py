#!/usr/bin/env python3

# -*- coding: utf-8 -*-

"""
影片編輯器 (FFmpeg 直呼版) - 在主片前後插入靜態圖片
優先路線A：主片免重編碼（TS 轉封 + concat -c copy）
回退路線B：全段硬體重編碼（VideoToolbox）

整合版本：支援單次處理與批次處理兩種模式
"""

import sys
import os
import json
import subprocess
import tempfile
import uuid
import glob
from datetime import datetime
from typing import List, Tuple, Dict, Optional
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QFileDialog, QVBoxLayout, QHBoxLayout,
    QGroupBox, QDoubleSpinBox, QTextEdit, QProgressBar, QMessageBox, QCheckBox, QScrollArea, QFrame, QSplitter,
    QListView, QStyledItemDelegate, QMenu, QStyle, QTabWidget, QListWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QLineEdit
)
from PyQt6.QtGui import QPixmap, QFont, QImage, QPainter, QColor, QPen, QBrush, QFontMetrics
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QAbstractListModel, QModelIndex, QSize


# ==================== 批次模式相關類別 ====================

class FileMatcher:
    """檔案匹配引擎"""
    
    def __init__(self):
        self.video_extensions = ['.mp4', '.mov', '.mkv', '.avi', '.m4v']
        self.image_extensions = ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff']
    
    def scan_videos(self, folder_path: str) -> List[str]:
        """掃描影片檔案"""
        videos = []
        for ext in self.video_extensions:
            pattern = os.path.join(folder_path, f"*{ext}")
            videos.extend(glob.glob(pattern))
            pattern = os.path.join(folder_path, f"*{ext.upper()}")
            videos.extend(glob.glob(pattern))
        return sorted(videos)
    
    def scan_images(self, folder_path: str) -> List[str]:
        """掃描圖片檔案"""
        images = []
        for ext in self.image_extensions:
            pattern = os.path.join(folder_path, f"*{ext}")
            images.extend(glob.glob(pattern))
            pattern = os.path.join(folder_path, f"*{ext.upper()}")
            images.extend(glob.glob(pattern))
        return sorted(images)
    
    def match_exact_names(self, videos: List[str], images: List[str]) -> List[Tuple[str, str]]:
        """完全檔名匹配"""
        matches = []
        video_basenames = {os.path.splitext(os.path.basename(v))[0]: v for v in videos}
        
        for image_path in images:
            image_basename = os.path.splitext(os.path.basename(image_path))[0]
            if image_basename in video_basenames:
                matches.append((video_basenames[image_basename], image_path))
        
        return matches
    
    def match_similar_names(self, videos: List[str], images: List[str]) -> List[Tuple[str, str]]:
        """相似檔名匹配"""
        matches = []
        used_videos = set()
        used_images = set()
        
        for video_path in videos:
            if video_path in used_videos:
                continue
                
            video_basename = os.path.splitext(os.path.basename(video_path))[0]
            
            # 尋找最相似的圖片
            best_match = None
            best_score = 0
            
            for image_path in images:
                if image_path in used_images:
                    continue
                    
                image_basename = os.path.splitext(os.path.basename(image_path))[0]
                score = self.calculate_similarity(video_basename, image_basename)
                
                if score > best_score and score > 0.5:  # 相似度閾值
                    best_score = score
                    best_match = image_path
            
            if best_match:
                matches.append((video_path, best_match))
                used_videos.add(video_path)
                used_images.add(best_match)
        
        return matches
    
    def match_sequential(self, videos: List[str], images: List[str]) -> List[Tuple[str, str]]:
        """順序匹配"""
        matches = []
        min_len = min(len(videos), len(images))
        
        for i in range(min_len):
            matches.append((videos[i], images[i]))
        
        return matches
    
    def calculate_similarity(self, str1: str, str2: str) -> float:
        """計算字串相似度"""
        if not str1 or not str2:
            return 0.0
        
        # 簡單的相似度計算：共同字元比例
        common_chars = set(str1.lower()) & set(str2.lower())
        total_chars = set(str1.lower()) | set(str2.lower())
        
        if not total_chars:
            return 0.0
        
        return len(common_chars) / len(total_chars)
    
    def scan_and_match(self, video_folder: str, image_folder: str) -> List[Tuple[str, str]]:
        """掃描並匹配檔案"""
        videos = self.scan_videos(video_folder)
        images = self.scan_images(image_folder)
        
        if not videos or not images:
            return []
        
        # 優先使用完全匹配
        matches = self.match_exact_names(videos, images)
        
        # 如果完全匹配不足，使用相似匹配
        if len(matches) < min(len(videos), len(images)):
            remaining_videos = [v for v in videos if v not in [m[0] for m in matches]]
            remaining_images = [i for i in images if i not in [m[1] for m in matches]]
            matches.extend(self.match_similar_names(remaining_videos, remaining_images))
        
        # 最後使用順序匹配
        if len(matches) < min(len(videos), len(images)):
            remaining_videos = [v for v in videos if v not in [m[0] for m in matches]]
            remaining_images = [i for i in images if i not in [m[1] for m in matches]]
            matches.extend(self.match_sequential(remaining_videos, remaining_images))
        
        return matches


class BatchJobItem:
    """批次工作項目"""
    
    def __init__(self, job_id: str, video_path: str, image_path: str, output_path: str):
        self.job_id = job_id
        self.video_path = video_path
        self.image_path = image_path
        self.output_path = output_path
        self.status = "queued"
        self.progress = 0
        self.error_message = None
        self.started_at = None
        self.completed_at = None


class BatchManager:
    """批次管理器"""
    
    def __init__(self):
        self.batches: Dict[str, List[BatchJobItem]] = {}
        self.current_batch_id = None
    
    def create_batch(self, matched_pairs: List[Tuple[str, str]], output_folder: str) -> str:
        """建立批次工作"""
        batch_id = str(uuid.uuid4())
        batch_jobs = []
        
        for video_path, image_path in matched_pairs:
            job_id = str(uuid.uuid4())
            output_name = self.generate_output_name(video_path)
            output_path = os.path.join(output_folder, output_name)
            
            job = BatchJobItem(job_id, video_path, image_path, output_path)
            batch_jobs.append(job)
        
        self.batches[batch_id] = batch_jobs
        self.current_batch_id = batch_id
        return batch_id
    
    def get_current_batch(self) -> List[BatchJobItem]:
        """取得當前批次"""
        if self.current_batch_id and self.current_batch_id in self.batches:
            return self.batches[self.current_batch_id]
        return []
    
    def update_job_progress(self, job_id: str, progress: int, status: str = None, error: str = None):
        """更新工作進度"""
        for batch_jobs in self.batches.values():
            for job in batch_jobs:
                if job.job_id == job_id:
                    job.progress = progress
                    if status:
                        job.status = status
                    if error:
                        job.error_message = error
                    if progress >= 100:
                        job.completed_at = datetime.now()
                    elif progress > 0 and not job.started_at:
                        job.started_at = datetime.now()
                    return
    
    def get_batch_progress(self, batch_id: str) -> Tuple[int, int, int]:
        """取得批次進度 (完成, 總數, 百分比)"""
        if batch_id not in self.batches:
            return 0, 0, 0
        
        batch_jobs = self.batches[batch_id]
        total = len(batch_jobs)
        completed = sum(1 for job in batch_jobs if job.progress >= 100)
        percentage = int((completed / total) * 100) if total > 0 else 0
        
        return completed, total, percentage
    
    @staticmethod
    def generate_output_name(video_path: str) -> str:
        """產生輸出檔案名稱"""
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        return f"{base_name}_with_images.mp4"


class BatchPreviewWidget(QWidget):
    """批次預覽元件"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 標題
        title = QLabel("📋 批次預覽")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # 預覽表格
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(3)
        self.preview_table.setHorizontalHeaderLabels(['影片檔案', '圖片檔案', '輸出檔案'])
        
        # 設定表格樣式
        header = self.preview_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        
        layout.addWidget(self.preview_table)
        
        # 統計資訊
        self.stats_label = QLabel("等待掃描檔案...")
        self.stats_label.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(self.stats_label)
    
    def update_preview(self, matched_pairs, output_folder: str):
        """更新批次預覽"""
        self.preview_table.setRowCount(len(matched_pairs))
        
        for i, (video_path, image_path) in enumerate(matched_pairs):
            # 影片檔案
            video_name = os.path.basename(video_path)
            self.preview_table.setItem(i, 0, QTableWidgetItem(video_name))
            
            # 圖片檔案
            image_name = os.path.basename(image_path)
            self.preview_table.setItem(i, 1, QTableWidgetItem(image_name))
            
            # 輸出檔案
            output_name = BatchManager.generate_output_name(video_path)
            self.preview_table.setItem(i, 2, QTableWidgetItem(output_name))
        
        # 更新統計
        self.stats_label.setText(f"找到 {len(matched_pairs)} 個檔案配對")


class BatchSettingsPanel(QWidget):
    """批次設定面板"""
    
    def __init__(self, file_matcher: FileMatcher):
        super().__init__()
        self.file_matcher = file_matcher
        self.video_folder = None
        self.image_folder = None
        self.output_folder = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 資料夾選擇區塊
        folder_group = QGroupBox("📁 資料夾設定")
        folder_layout = QVBoxLayout(folder_group)
        
        # 影片資料夾
        video_layout = QHBoxLayout()
        video_layout.addWidget(QLabel("影片資料夾:"))
        self.video_folder_label = QLabel("未選擇")
        self.video_folder_label.setStyleSheet("color: #888; font-style: italic;")
        video_layout.addWidget(self.video_folder_label)
        video_layout.addStretch()
        
        self.video_folder_btn = QPushButton("選擇")
        self.video_folder_btn.clicked.connect(self.select_video_folder)
        video_layout.addWidget(self.video_folder_btn)
        folder_layout.addLayout(video_layout)
        
        # 圖片資料夾
        image_layout = QHBoxLayout()
        image_layout.addWidget(QLabel("圖片資料夾:"))
        self.image_folder_label = QLabel("未選擇")
        self.image_folder_label.setStyleSheet("color: #888; font-style: italic;")
        image_layout.addWidget(self.image_folder_label)
        image_layout.addStretch()
        
        self.image_folder_btn = QPushButton("選擇")
        self.image_folder_btn.clicked.connect(self.select_image_folder)
        image_layout.addWidget(self.image_folder_btn)
        folder_layout.addLayout(image_layout)
        
        # 輸出資料夾
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("輸出資料夾:"))
        self.output_folder_label = QLabel("未選擇")
        self.output_folder_label.setStyleSheet("color: #888; font-style: italic;")
        output_layout.addWidget(self.output_folder_label)
        output_layout.addStretch()
        
        self.output_folder_btn = QPushButton("選擇")
        self.output_folder_btn.clicked.connect(self.select_output_folder)
        output_layout.addWidget(self.output_folder_btn)
        folder_layout.addLayout(output_layout)
        
        layout.addWidget(folder_group)
        
        # 掃描按鈕
        self.scan_btn = QPushButton("🔍 掃描檔案")
        self.scan_btn.setEnabled(False)
        self.scan_btn.clicked.connect(self.scan_files)
        layout.addWidget(self.scan_btn)
        
        layout.addStretch()
    
    def select_video_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇影片資料夾")
        if folder:
            self.video_folder = folder
            self.video_folder_label.setText(os.path.basename(folder))
            self.check_scan_ready()
    
    def select_image_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇圖片資料夾")
        if folder:
            self.image_folder = folder
            self.image_folder_label.setText(os.path.basename(folder))
            self.check_scan_ready()
    
    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇輸出資料夾")
        if folder:
            self.output_folder = folder
            self.output_folder_label.setText(os.path.basename(folder))
            self.check_scan_ready()
    
    def check_scan_ready(self):
        """檢查是否可以掃描"""
        ready = bool(self.video_folder and self.image_folder and self.output_folder)
        self.scan_btn.setEnabled(ready)
    
    def scan_files(self):
        """掃描檔案"""
        if not all([self.video_folder, self.image_folder, self.output_folder]):
            return
        
        matched_pairs = self.file_matcher.scan_and_match(self.video_folder, self.image_folder)
        return matched_pairs, self.output_folder


# ==================== 原有類別保持不變 ====================

class FFmpegEnv:
    def __init__(self):
        # 1. 獲取內建二進制檔案的候選路徑 (只包含存在的)
        embedded_ffmpeg_candidates = self._get_embedded_binaries('ffmpeg')
        embedded_ffprobe_candidates = self._get_embedded_binaries('ffprobe')

        # 2. 定義系統二進制檔案的候選路徑
        system_ffmpeg_candidates = ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', 'ffmpeg']
        system_ffprobe_candidates = ['/opt/homebrew/bin/ffprobe', '/usr/local/bin/ffprobe', 'ffprobe']

        # 3. 按照明確的優先級尋找 FFmpeg 和 FFprobe
        self.ffmpeg_path = self._find_binary_with_priority(
            'FFMPEG_BIN',
            embedded_ffmpeg_candidates,
            system_ffmpeg_candidates
        )
        self.ffprobe_path = self._find_binary_with_priority(
            'FFPROBE_BIN',
            embedded_ffprobe_candidates,
            system_ffprobe_candidates
        )
        self.hardware_encoders = self._detect_hardware_encoders()
        
        # 記錄路徑信息用於調試
        self.ffmpeg_source = self._get_binary_source_info(self.ffmpeg_path, embedded_ffmpeg_candidates)
        self.ffprobe_source = self._get_binary_source_info(self.ffprobe_path, embedded_ffprobe_candidates)

    def _app_base_dir(self):
        """獲取應用程式基礎目錄，優先考慮 .app 結構 (增強穩健性)"""
        # PyInstaller 打包後：有 sys._MEIPASS
        if hasattr(sys, '_MEIPASS') and sys._MEIPASS:
            print(f"DEBUG: _MEIPASS 存在: {sys._MEIPASS}")
            return sys._MEIPASS
        
        # frozen 狀態下的 .app 結構
        if getattr(sys, 'frozen', False):
            executable_path = Path(sys.executable).resolve()
            print(f"DEBUG: frozen 狀態, executable_path: {executable_path}")
            # 向上查找 .app 目錄
            for parent in executable_path.parents:
                if parent.suffix == '.app':
                    app_root = parent
                    contents_dir = app_root / 'Contents'
                    print(f"DEBUG: 檢測到 .app 根目錄: {app_root}, Contents 目錄: {contents_dir}")
                    if contents_dir.is_dir():
                        return str(contents_dir)
            # 如果沒有找到 .app 結構，返回可執行檔的目錄
            print(f"DEBUG: 未在 frozen 狀態下找到 .app 結構，返回可執行檔目錄: {executable_path.parent}")
            return str(executable_path.parent)
        
        # 開發模式：以此檔所在目錄為基準
        current_file_dir = Path(__file__).resolve().parent
        print(f"DEBUG: 開發模式, 當前檔案目錄: {current_file_dir}")
        return str(current_file_dir)

    def _get_embedded_binaries(self, bin_name) -> List[str]:
        """獲取內建二進制檔案的路徑候選，並只返回實際存在的路徑 (增強穩健性)"""
        base = Path(self._app_base_dir())
        potential_candidates = []
        print(f"DEBUG: _get_embedded_binaries 基礎目錄: {base}")

        # 情況 1: .app/Contents 結構
        if base.name == 'Contents' and base.parent.suffix == '.app':
            resources_dir = base / 'Resources'
            if resources_dir.is_dir():
                print(f"DEBUG: .app/Contents/Resources 目錄存在: {resources_dir}")
                # 優先：Resources/assets/bin/mac/arm64
                potential_candidates.append(resources_dir / 'assets' / 'bin' / 'mac' / 'arm64' / bin_name)
                # 次要：Resources/assets/bin/mac
                potential_candidates.append(resources_dir / 'assets' / 'bin' / 'mac' / bin_name)
                # 第三：Resources/assets/bin
                potential_candidates.append(resources_dir / 'assets' / 'bin' / bin_name)
        
        # 情況 2: _MEIPASS 結構 (例如 one-file 模式或某些打包)
        elif hasattr(sys, '_MEIPASS') and sys._MEIPASS:
            meipass_base = Path(sys._MEIPASS)
            print(f"DEBUG: _MEIPASS 結構, 基礎目錄: {meipass_base}")
            potential_candidates.append(meipass_base / 'assets' / 'bin' / 'mac' / 'arm64' / bin_name)
            potential_candidates.append(meipass_base / 'assets' / 'bin' / 'mac' / bin_name)
            potential_candidates.append(meipass_base / 'assets' / 'bin' / bin_name)

        # 情況 3: 開發模式或其他非標準 frozen 情況
        else:
            # 嘗試從當前檔案路徑相對構建
            current_file_dir = Path(__file__).resolve().parent
            print(f"DEBUG: 開發模式/非標準 frozen, 嘗試從 {current_file_dir} 構建路徑")
            potential_candidates.append(current_file_dir / 'assets' / 'bin' / 'mac' / 'arm64' / bin_name)
            potential_candidates.append(current_file_dir / 'assets' / 'bin' / 'mac' / bin_name)
            potential_candidates.append(current_file_dir / 'assets' / 'bin' / bin_name)
            
            # 最終 fallback：如果這些都失敗，也嘗試從 _internal/assets
            # 這裡需要更小心，因為 _internal 通常在 .app/Contents 下，但 _MEIPASS 或 frozen 狀態可能不同
            app_root_from_executable = Path(sys.executable).resolve().parent
            for parent in app_root_from_executable.parents:
                if parent.name == 'Contents':
                    internal_path = parent / '_internal'
                    if internal_path.is_dir():
                        print(f"DEBUG: 嘗試 _internal 路徑: {internal_path}")
                        potential_candidates.append(internal_path / 'assets' / 'bin' / 'mac' / 'arm64' / bin_name)
                        potential_candidates.append(internal_path / 'assets' / 'bin' / 'mac' / bin_name)
                        potential_candidates.append(internal_path / 'assets' / 'bin' / bin_name)
                    break

        # 過濾掉不存在的路徑，只保留實際存在的
        existing_candidates = []
        for p in potential_candidates:
            if p.is_file() and os.access(p, os.X_OK):
                existing_candidates.append(str(p))
                print(f"DEBUG: 找到並可執行內建候選: {p}")
            elif p.is_file():
                print(f"DEBUG: 找到但不可執行內建候選: {p}")
            else:
                print(f"DEBUG: 內建候選不存在: {p}")

        return existing_candidates

    def _find_binary_with_priority(self, env_key: str, embedded_candidates: List[str], system_candidates: List[str]) -> Optional[str]:
        """按照明確的優先級尋找二進制檔案：環境變數 -> 內建 -> 系統"""
        print(f"DEBUG: 正在尋找 {env_key} (優先級: 環境變數 -> 內建 -> 系統)")
        # 1. 檢查環境變數
        env_val = os.environ.get(env_key)
        if env_val:
            print(f"DEBUG: 檢查環境變數 {env_key}={env_val}")
            if Path(env_val).is_file() and os.access(env_val, os.X_OK):
                try:
                    res = subprocess.run([env_val, '-version'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
                    print(f"DEBUG: ✅ 環境變數 {env_key} 指向的二進制檔案可用: {env_val}")
                    return env_val
                except (subprocess.CalledProcessError, FileNotFoundError) as e:
                    print(f"DEBUG: ❌ 環境變數 {env_key} 指向的二進制檔案執行失敗或找不到: {env_val} - {e}")
            else:
                print(f"DEBUG: 環境變數 {env_key} 指向的檔案不存在或不可執行: {env_val}")

        # 2. 檢查內建候選路徑
        print(f"DEBUG: 檢查內建候選路徑: {embedded_candidates}")
        for c in embedded_candidates:
            if Path(c).is_file() and os.access(c, os.X_OK):
                try:
                    res = subprocess.run([c, '-version'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
                    print(f"DEBUG: ✅ 內建二進制檔案可用: {c}")
                    return c
                except (subprocess.CalledProcessError, FileNotFoundError) as e:
                    print(f"DEBUG: ❌ 內建二進制檔案執行失敗或找不到: {c} - {e}")
            else:
                print(f"DEBUG: 內建二進制檔案不存在或不可執行: {c}")

        # 3. 檢查系統候選路徑
        print(f"DEBUG: 檢查系統候選路徑: {system_candidates}")
        for c in system_candidates:
            current_path = Path(c)
            if not current_path.is_absolute(): # 處理相對路徑 (e.g. 'ffmpeg')
                try:
                    which_result = subprocess.run(['which', c], capture_output=True, text=True, check=True)
                    full_path = which_result.stdout.strip()
                    if full_path:
                        current_path = Path(full_path)
                        print(f"DEBUG: 'which {c}' 找到路徑: {current_path}")
                except (subprocess.CalledProcessError, FileNotFoundError) as e:
                    print(f"DEBUG: 'which {c}' 執行失敗或找不到: {e}")
                    continue
            
            if current_path.is_file() and os.access(current_path, os.X_OK):
                try:
                    res = subprocess.run([str(current_path), '-version'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
                    print(f"DEBUG: ✅ 系統二進制檔案可用: {current_path}")
                    return str(current_path)
                except (subprocess.CalledProcessError, FileNotFoundError) as e:
                    print(f"DEBUG: ❌ 系統二進制檔案執行失敗或找不到: {current_path} - {e}")
            else:
                print(f"DEBUG: 系統二進制檔案不存在或不可執行: {current_path}")

        print(f"DEBUG: ❌ 未找到 {env_key} 的可用二進制檔案")
        return None

    def _get_binary_source_info(self, found_path: Optional[str], embedded_candidates: List[str]) -> str:
        """判斷找到的二進制檔案來源"""
        if not found_path:
            return "未找到"
        if found_path in embedded_candidates:
            return f"內建 ({os.path.basename(found_path)})"
        # 檢查是否為系統路徑
        if '/opt/homebrew/bin/' in found_path or '/usr/local/bin/' in found_path or os.path.basename(found_path) in ['ffmpeg', 'ffprobe']:
            return f"系統 ({found_path})"
        return f"其他 ({found_path})"

    def _detect_hardware_encoders(self):
        enc = []
        try:
            # 在嘗試執行之前，先檢查路徑是否存在且可執行
            if self.ffmpeg_path and os.path.exists(self.ffmpeg_path) and os.access(self.ffmpeg_path, os.X_OK):
                p = subprocess.run([self.ffmpeg_path, '-hide_banner', '-encoders'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                out = p.stdout or ''
                if 'h264_videotoolbox' in out:
                    enc.append('h264_videotoolbox')
                if 'hevc_videotoolbox' in out:
                    enc.append('hevc_videotoolbox')
            else:
                print(f"警告: FFmpeg 路徑不可用或不可執行: {self.ffmpeg_path}")
        except Exception as e:
            print(f"檢測硬體編碼器時發生錯誤: {e}")
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
        self.setWindowTitle("影片編輯器 - FFmpeg 直呼版（單次/批次模式）")
        self.resize(1400, 900)
        self.setStyleSheet(self.get_dark_theme())
        self.setAcceptDrops(True)

        self.env = FFmpegEnv()
        
        # 批次模式相關
        self.file_matcher = FileMatcher()
        self.batch_manager = BatchManager()
        self.current_matched_pairs = []

        # 單次模式變數
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
        self.main_layout = QVBoxLayout(self.central_widget)

        # 創建標籤頁
        self.create_tab_widget()

        self.update_active_count()
        self.update_queue_count()
        
        # 更新 FFmpeg 狀態顯示
        self.update_ffmpeg_status()

    def create_tab_widget(self):
        """創建標籤頁容器"""
        self.tab_widget = QTabWidget()
        self.main_layout.addWidget(self.tab_widget)
        
        # 單次模式標籤頁
        self.single_tab = self.create_single_mode_tab()
        self.tab_widget.addTab(self.single_tab, "🎬 單次處理")
        
        # 批次模式標籤頁
        self.batch_tab = self.create_batch_mode_tab()
        self.tab_widget.addTab(self.batch_tab, "📦 批次處理")

    def create_single_mode_tab(self):
        """創建單次模式標籤頁"""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        
        self.single_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.single_splitter)

        self.create_left_panel()
        self.create_right_panel()

        # 設置分割器比例（左側更寬）
        self.single_splitter.setStretchFactor(0, 3)
        self.single_splitter.setStretchFactor(1, 1)
        self.single_splitter.setSizes([900, 300])
        
        return tab

    def create_batch_mode_tab(self):
        """創建批次模式標籤頁"""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        
        self.batch_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.batch_splitter)

        # 左側：批次設定和預覽
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # 批次設定面板
        self.batch_settings = BatchSettingsPanel(self.file_matcher)
        self.batch_settings.scan_btn.clicked.connect(self.on_batch_scan)
        left_layout.addWidget(self.batch_settings)
        
        # 批次預覽
        self.batch_preview = BatchPreviewWidget()
        left_layout.addWidget(self.batch_preview)
        
        # 批次處理按鈕
        self.batch_process_btn = QPushButton("🚀 開始批次處理")
        self.batch_process_btn.setObjectName("PrimaryCTA")
        self.batch_process_btn.setEnabled(False)
        self.batch_process_btn.clicked.connect(self.start_batch_processing)
        # 直接設定樣式
        self.apply_primary_button_style(self.batch_process_btn)
        left_layout.addWidget(self.batch_process_btn)
        
        self.batch_splitter.addWidget(left_widget)
        
        # 右側：工作佇列（共用原有的）
        self.create_batch_right_panel()
        
        # 設置分割器比例
        self.batch_splitter.setStretchFactor(0, 2)
        self.batch_splitter.setStretchFactor(1, 1)
        self.batch_splitter.setSizes([800, 400])
        
        return tab

    def create_batch_right_panel(self):
        """創建批次模式右側面板"""
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        header_layout = QHBoxLayout()
        title = QLabel("批次處理工作列表")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.batch_active_count_label = QLabel("進行中: 0")
        self.batch_active_count_label.setStyleSheet("color: #4caf50; font-size: 12px;")
        self.batch_pending_count_label = QLabel("佇列中: 0")
        self.batch_pending_count_label.setStyleSheet("color: #ff9800; font-size: 12px;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.batch_active_count_label)
        header_layout.addWidget(self.batch_pending_count_label)
        right_layout.addLayout(header_layout)

        # 使用 QListView + Model/Delegate（共用原有的）
        self.batch_jobs_view = QListView()
        self.batch_jobs_view.setUniformItemSizes(True)
        self.batch_jobs_view.setMouseTracking(True)
        self.batch_jobs_view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.batch_jobs_view.setModel(self.jobs_model)  # 共用模型
        self.batch_jobs_view.setItemDelegate(self.jobs_delegate)  # 共用委託
        self.batch_jobs_view.doubleClicked.connect(self.on_jobs_double_clicked)
        self.batch_jobs_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.batch_jobs_view.customContextMenuRequested.connect(self.on_jobs_context_menu)
        right_layout.addWidget(self.batch_jobs_view)

        clear_all_btn = QPushButton("清除所有完成的工作")
        clear_all_btn.clicked.connect(self.clear_finished_jobs)
        right_layout.addWidget(clear_all_btn)

        self.batch_splitter.addWidget(right_widget)

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

        self.single_splitter.addWidget(left_scroll)

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

        self.single_splitter.addWidget(right_widget)

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

        # FFmpeg 狀態顯示區塊
        ffmpeg_group = QWidget()
        ffmpeg_group.setObjectName("FunctionGroup")
        ffmpeg_layout = QVBoxLayout(ffmpeg_group)
        ffmpeg_layout.setSpacing(4)
        
        ffmpeg_title = QLabel("🔧 FFmpeg 狀態")
        ffmpeg_title.setObjectName("SectionTitle")
        ffmpeg_layout.addWidget(ffmpeg_title)
        
        # FFmpeg 狀態
        self.ffmpeg_status_label = QLabel("FFmpeg: 檢查中...")
        self.ffmpeg_status_label.setStyleSheet("color: #ff9800; font-size: 12px;")
        ffmpeg_layout.addWidget(self.ffmpeg_status_label)
        
        # FFprobe 狀態
        self.ffprobe_status_label = QLabel("FFprobe: 檢查中...")
        self.ffprobe_status_label.setStyleSheet("color: #ff9800; font-size: 12px;")
        ffmpeg_layout.addWidget(self.ffprobe_status_label)
        
        # 路徑信息
        self.ffmpeg_path_label = QLabel("路徑: 載入中...")
        self.ffmpeg_path_label.setStyleSheet("color: #888; font-size: 10px; font-family: monospace;")
        self.ffmpeg_path_label.setWordWrap(True)
        ffmpeg_layout.addWidget(self.ffmpeg_path_label)
        
        vbox.addWidget(ffmpeg_group)

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
        
        # 同時更新批次管理器
        if hasattr(self, 'batch_manager'):
            self.batch_manager.update_job_progress(job_id, progress)

    def on_job_status(self, job_id, status):
        row = self.jobs_model.find_row_by_id(job_id)
        if row >= 0:
            # running 狀態
            self.jobs_model.set_state(job_id, "running", status)
        
        # 同時更新批次管理器
        if hasattr(self, 'batch_manager'):
            self.batch_manager.update_job_progress(job_id, 0, status)

    def on_job_finished(self, job_id, output_file):
        row = self.jobs_model.find_row_by_id(job_id)
        if row >= 0:
            self.jobs_model.set_state(job_id, "done", "完成", output_file)
        
        # 同時更新批次管理器
        if hasattr(self, 'batch_manager'):
            self.batch_manager.update_job_progress(job_id, 100, "完成")

    def on_job_error(self, job_id, error_message):
        row = self.jobs_model.find_row_by_id(job_id)
        if row >= 0:
            self.jobs_model.set_state(job_id, "error", f"錯誤: {error_message}")
        
        # 同時更新批次管理器
        if hasattr(self, 'batch_manager'):
            self.batch_manager.update_job_progress(job_id, 0, "錯誤", error_message)

    def on_thread_finished(self, job_id):
        if job_id in self.active_processors:
            del self.active_processors[job_id]
        self.update_active_count()
        self.process_next_in_queue()
        
        # 檢查批次處理是否完成
        if hasattr(self, 'batch_manager') and self.batch_manager.current_batch_id:
            batch_jobs = self.batch_manager.get_current_batch()
            completed_count = sum(1 for job in batch_jobs if job.progress >= 100)
            if completed_count == len(batch_jobs) and len(batch_jobs) > 0:
                # 批次處理完成
                self.batch_process_btn.setEnabled(True)
                self.batch_process_btn.setText("🚀 開始批次處理")
                # 移除確認對話窗，讓操作更流暢

    def update_active_count(self):
        active_count = len(self.active_processors)
        self.active_count_label.setText(f"進行中: {active_count}")

    def update_queue_count(self):
        queue_count = len(self.job_queue)
        self.pending_count_label.setText(f"佇列中: {queue_count}")
        # 同時更新批次模式的標籤
        if hasattr(self, 'batch_pending_count_label'):
            self.batch_pending_count_label.setText(f"佇列中: {queue_count}")

    def update_active_count(self):
        active_count = len(self.active_processors)
        self.active_count_label.setText(f"進行中: {active_count}")
        # 同時更新批次模式的標籤
        if hasattr(self, 'batch_active_count_label'):
            self.batch_active_count_label.setText(f"進行中: {active_count}")

    def update_ffmpeg_status(self):
        """更新 FFmpeg 狀態顯示"""
        try:
            # 更新 FFmpeg 狀態
            if hasattr(self.env, 'ffmpeg_source'):
                if "內建" in self.env.ffmpeg_source:
                    self.ffmpeg_status_label.setText(f"FFmpeg: ✅ {self.env.ffmpeg_source}")
                    self.ffmpeg_status_label.setStyleSheet("color: #4caf50; font-size: 12px;")
                elif "系統" in self.env.ffmpeg_source:
                    self.ffmpeg_status_label.setText(f"FFmpeg: ⚠️ {self.env.ffmpeg_source}")
                    self.ffmpeg_status_label.setStyleSheet("color: #ff9800; font-size: 12px;")
                else:
                    self.ffmpeg_status_label.setText(f"FFmpeg: ❌ {self.env.ffmpeg_source}")
                    self.ffmpeg_status_label.setStyleSheet("color: #f44336; font-size: 12px;")
            
            # 更新 FFprobe 狀態
            if hasattr(self.env, 'ffprobe_source'):
                if "內建" in self.env.ffprobe_source:
                    self.ffprobe_status_label.setText(f"FFprobe: ✅ {self.env.ffprobe_source}")
                    self.ffprobe_status_label.setStyleSheet("color: #4caf50; font-size: 12px;")
                elif "系統" in self.env.ffprobe_source:
                    self.ffprobe_status_label.setText(f"FFprobe: ⚠️ {self.env.ffprobe_source}")
                    self.ffprobe_status_label.setStyleSheet("color: #ff9800; font-size: 12px;")
                else:
                    self.ffprobe_status_label.setText(f"FFprobe: ❌ {self.env.ffprobe_source}")
                    self.ffprobe_status_label.setStyleSheet("color: #f44336; font-size: 12px;")
            
            # 更新路徑信息
            path_info = []
            if hasattr(self.env, 'ffmpeg_path') and self.env.ffmpeg_path:
                path_info.append(f"FFmpeg: {self.env.ffmpeg_path}")
            if hasattr(self.env, 'ffprobe_path') and self.env.ffprobe_path:
                path_info.append(f"FFprobe: {self.env.ffprobe_path}")
            
            if path_info:
                self.ffmpeg_path_label.setText("路徑:\n" + "\n".join(path_info))
            else:
                self.ffmpeg_path_label.setText("路徑: 未找到")
                
        except Exception as e:
            self.ffmpeg_status_label.setText(f"FFmpeg: ❌ 錯誤")
            self.ffprobe_status_label.setText(f"FFprobe: ❌ 錯誤")
            self.ffmpeg_path_label.setText(f"路徑: 錯誤 - {str(e)}")

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

    # ==================== 批次模式方法 ====================
    
    def on_batch_scan(self):
        """批次掃描檔案"""
        result = self.batch_settings.scan_files()
        if result:
            matched_pairs, output_folder = result
            self.current_matched_pairs = matched_pairs
            
            if matched_pairs:
                self.batch_preview.update_preview(matched_pairs, output_folder)
                self.batch_process_btn.setEnabled(True)
                self.batch_process_btn.setText(f"🚀 開始批次處理 ({len(matched_pairs)} 個檔案)")
                # 移除確認對話窗，讓操作更流暢
            else:
                self.batch_preview.update_preview([], "")
                self.batch_process_btn.setEnabled(False)
                QMessageBox.warning(self, "掃描結果", "未找到可匹配的檔案")
        else:
            QMessageBox.warning(self, "掃描失敗", "請先選擇所有必要的資料夾")

    def start_batch_processing(self):
        """開始批次處理"""
        if not self.current_matched_pairs:
            QMessageBox.warning(self, "警告", "請先掃描檔案")
            return
        
        # 建立批次
        batch_id = self.batch_manager.create_batch(self.current_matched_pairs, self.batch_settings.output_folder)
        
        # 將所有工作加入佇列
        batch_jobs = self.batch_manager.get_current_batch()
        for job in batch_jobs:
            # 批次模式固定使用相同的圖片作為開頭和結尾，固定3秒
            processor_args = {
                'job_id': job.job_id,
                'video_file': job.video_path,
                'start_image': job.image_path,
                'end_image': job.image_path,  # 同圖
                'start_duration': 3.0,  # 固定3秒
                'end_duration': 3.0,    # 固定3秒
                'output_file': job.output_path,
                'prefer_copy_concat': self.prefer_copy_concat,
                'use_hardware': self.use_hardware,
                'env': self.env,
            }
            
            # 加入佇列
            self.job_queue.append(processor_args)
            
            # 加入模型
            job_name = f"批次: {os.path.basename(job.video_path)}"
            job_item = JobItem(job.job_id, job_name)
            self.jobs_model.add_item(job_item)
            self.jobs_model.set_state(job.job_id, "queued", "已加入佇列…")
        
        self.update_queue_count()
        self.process_next_in_queue()
        
        # 禁用批次處理按鈕
        self.batch_process_btn.setEnabled(False)
        self.batch_process_btn.setText("處理中...")
        
        # 移除確認對話窗，讓操作更流暢

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


