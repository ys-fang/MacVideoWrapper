#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
影片編輯器 v2 - Mac M 系列獨立打包腳本
專門為 video_wrapper2.py 建立可獨立運作的 .app
"""

import os
import sys
import shutil
import subprocess
import tempfile
import json
from pathlib import Path

class VideoWrapper2MacBuilder:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.source_file = self.project_root / "video_wrapper2.py"
        self.assets_dir = self.project_root / "assets"
        self.build_dir = self.project_root / "build_v2"
        self.dist_dir = self.project_root / "dist"  # 使用 PyInstaller 預設的 dist 目錄
        self.app_name = "VideoWrapper2"
        self.app_bundle = self.dist_dir / f"{self.app_name}.app"
        
        # 清理舊的建置目錄
        self.clean_build_dirs()
        
    def clean_build_dirs(self):
        """清理舊的建置目錄"""
        print("🧹 清理舊的建置目錄...")
        for dir_path in [self.build_dir]:
            if dir_path.exists():
                shutil.rmtree(dir_path)
                print(f"   已刪除: {dir_path}")
        
        # 只清理舊的應用程式，保留其他檔案
        if self.app_bundle.exists():
            shutil.rmtree(self.app_bundle)
            print(f"   已刪除舊的應用程式: {self.app_bundle}")
    
    def check_dependencies(self):
        """檢查必要的依賴"""
        print("🔍 檢查依賴...")
        
        # 檢查 Python 版本
        if sys.version_info < (3, 8):
            raise RuntimeError("需要 Python 3.8 或更高版本")
        print(f"   Python 版本: {sys.version}")
        
        # 檢查源檔案
        if not self.source_file.exists():
            raise RuntimeError(f"找不到源檔案: {self.source_file}")
        print(f"   源檔案: {self.source_file}")
        
        # 檢查 assets
        if not self.assets_dir.exists():
            raise RuntimeError(f"找不到 assets 目錄: {self.assets_dir}")
        print(f"   Assets 目錄: {self.assets_dir}")
        
        # 檢查 FFmpeg 二進制檔案
        ffmpeg_path = self.assets_dir / "bin" / "mac" / "arm64" / "ffmpeg"
        ffprobe_path = self.assets_dir / "bin" / "mac" / "arm64" / "ffprobe"
        
        if not ffmpeg_path.exists():
            raise RuntimeError(f"找不到 FFmpeg: {ffmpeg_path}")
        if not ffprobe_path.exists():
            raise RuntimeError(f"找不到 FFprobe: {ffprobe_path}")
        print(f"   FFmpeg: {ffmpeg_path}")
        print(f"   FFprobe: {ffprobe_path}")
        
        # 檢查 PyInstaller
        try:
            import PyInstaller
            print(f"   PyInstaller: {PyInstaller.__version__}")
        except ImportError:
            raise RuntimeError("請先安裝 PyInstaller: pip install pyinstaller")
        
        # 檢查 PyQt6
        try:
            import PyQt6
            print(f"   PyQt6: 已安裝")
        except ImportError:
            raise RuntimeError("請先安裝 PyQt6: pip install PyQt6")
    
    def create_spec_file(self):
        """建立 PyInstaller spec 檔案"""
        print("📝 建立 PyInstaller spec 檔案...")
        
        # 檢查圖示檔案
        icon_path = self.assets_dir / "mac" / "videowrapper2.icns"
        if not icon_path.exists():
            # 如果新圖示不存在，使用舊圖示
            icon_path = self.assets_dir / "mac" / "app_icon.icns"
        icon_param = f"'{icon_path}'" if icon_path.exists() else "None"
        
        spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# 收集所有必要的檔案
a = Analysis(
    ['{self.source_file}'],
    pathex=[],
    binaries=[],
    datas=[
        ('{self.assets_dir}/bin/mac/arm64/ffmpeg', 'assets/bin/mac/arm64/'),
        ('{self.assets_dir}/bin/mac/arm64/ffprobe', 'assets/bin/mac/arm64/'),
        ('{self.assets_dir}/app_icon_1024.png', 'assets/'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui', 
        'PyQt6.QtWidgets',
        'PyQt6.sip',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{self.app_name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{self.app_name}',
)

# 建立 .app bundle
app = BUNDLE(
    coll,
    name='{self.app_name}.app',
    icon={icon_param},  # 使用自定義圖示
    bundle_identifier='com.videowrapper.app',
    distpath='{self.dist_dir}',  # 指定輸出目錄
    info_plist={{
        'CFBundleName': 'VideoWrapper2',
        'CFBundleDisplayName': 'VideoWrapper2',
        'CFBundleVersion': '3.0.0',
        'CFBundleShortVersionString': '3.0.0',
        'CFBundleExecutable': 'VideoWrapper2',
        'CFBundleIdentifier': 'com.videowrapper.app',
        'CFBundlePackageType': 'APPL',
        'CFBundleSignature': '????',
        'LSMinimumSystemVersion': '10.15.0',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'LSApplicationCategoryType': 'public.app-category.video',
        'CFBundleDocumentTypes': [
            {{
                'CFBundleTypeName': 'Video Files',
                'CFBundleTypeExtensions': ['mp4', 'mov', 'mkv', 'avi'],
                'CFBundleTypeRole': 'Viewer',
                'LSHandlerRank': 'Owner',
            }},
            {{
                'CFBundleTypeName': 'Image Files',
                'CFBundleTypeExtensions': ['png', 'jpg', 'jpeg', 'bmp', 'gif'],
                'CFBundleTypeRole': 'Viewer',
                'LSHandlerRank': 'Owner',
            }}
        ],
    }},
)
'''
        
        spec_file = self.project_root / f"{self.app_name}.spec"
        with open(spec_file, 'w', encoding='utf-8') as f:
            f.write(spec_content)
        
        print(f"   Spec 檔案已建立: {spec_file}")
        return spec_file
    
    def build_app(self, spec_file):
        """使用 PyInstaller 建置應用程式"""
        print("🔨 開始建置應用程式...")
        
        # 執行 PyInstaller
        cmd = [
            sys.executable, '-m', 'PyInstaller',
            '--clean',  # 清理快取
            '--noconfirm',  # 不詢問覆寫
            str(spec_file)
        ]
        
        print(f"   執行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print("❌ PyInstaller 建置失敗:")
            print(result.stdout)
            print(result.stderr)
            raise RuntimeError("PyInstaller 建置失敗")
        
        print("✅ PyInstaller 建置成功")
        print(result.stdout)
    
    def verify_app(self):
        """驗證建置的應用程式"""
        print("🔍 驗證應用程式...")
        
        if not self.app_bundle.exists():
            raise RuntimeError(f"找不到應用程式 bundle: {self.app_bundle}")
        
        # 檢查主要可執行檔案
        executable = self.app_bundle / "Contents" / "MacOS" / self.app_name
        if not executable.exists():
            raise RuntimeError(f"找不到可執行檔案: {executable}")
        
        # 檢查 assets
        assets_in_app = self.app_bundle / "Contents" / "Resources" / "assets"
        if not assets_in_app.exists():
            raise RuntimeError(f"找不到 assets 目錄: {assets_in_app}")
        
        ffmpeg_in_app = assets_in_app / "bin" / "mac" / "arm64" / "ffmpeg"
        ffprobe_in_app = assets_in_app / "bin" / "mac" / "arm64" / "ffprobe"
        
        if not ffmpeg_in_app.exists():
            raise RuntimeError(f"應用程式中找不到 FFmpeg: {ffmpeg_in_app}")
        if not ffprobe_in_app.exists():
            raise RuntimeError(f"應用程式中找不到 FFprobe: {ffprobe_in_app}")
        
        print(f"   ✅ 應用程式 bundle: {self.app_bundle}")
        print(f"   ✅ 可執行檔案: {executable}")
        print(f"   ✅ FFmpeg: {ffmpeg_in_app}")
        print(f"   ✅ FFprobe: {ffprobe_in_app}")
        
        # 檢查檔案大小
        app_size = self.get_dir_size(self.app_bundle)
        print(f"   📦 應用程式大小: {self.format_size(app_size)}")
    
    def get_dir_size(self, path):
        """計算目錄大小"""
        total = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total += os.path.getsize(filepath)
        return total
    
    def format_size(self, size_bytes):
        """格式化檔案大小"""
        if size_bytes == 0:
            return "0B"
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.1f}{size_names[i]}"
    
    def cleanup_spec_file(self, spec_file):
        """清理 spec 檔案"""
        if spec_file.exists():
            spec_file.unlink()
            print(f"🧹 已清理 spec 檔案: {spec_file}")
    
    def build(self):
        """執行完整的建置流程"""
        print("🚀 開始建置 VideoWrapper2 Mac 應用程式（整合版）")
        print("=" * 60)
        
        try:
            self.check_dependencies()
            spec_file = self.create_spec_file()
            self.build_app(spec_file)
            self.verify_app()
            self.cleanup_spec_file(spec_file)
            
            print("=" * 60)
            print("🎉 建置完成！")
            print(f"📱 應用程式位置: {self.app_bundle}")
            print(f"💡 您可以直接雙擊執行，或拖曳到 Applications 資料夾")
            print(f"✨ 應用程式名稱：VideoWrapper2")
            print(f"✨ 新功能：支援單次處理與批次處理兩種模式")
            
        except Exception as e:
            print(f"❌ 建置失敗: {e}")
            return False
        
        return True

def main():
    """主函數"""
    builder = VideoWrapper2MacBuilder()
    success = builder.build()
    
    if success:
        print("\n✅ 打包成功！")
        sys.exit(0)
    else:
        print("\n❌ 打包失敗！")
        sys.exit(1)

if __name__ == "__main__":
    main()
