#!/usr/bin/env python3

"""
影片編輯器 - py2app 打包配置
使用方法：
1. pip install py2app
2. python3 setup.py py2app
"""

from setuptools import setup
import py2app
import sys

# APP 基本資訊
APP = ['video_wrapper.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': False,  # 禁用 argv_emulation 解決 Carbon.framework 問題
    'iconfile': None,  # 可以添加 .icns 圖標文件
    'plist': {
        'CFBundleName': '影片編輯器',
        'CFBundleDisplayName': '影片編輯器 - 並行處理',
        'CFBundleVersion': '2.0.0',
        'CFBundleShortVersionString': '2.0.0',
        'CFBundleIdentifier': 'com.videoeditor.app',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.14.0',
    },
    'packages': [
        'PyQt6', 
        'cv2', 
        'PIL', 
        'moviepy',
        'numpy',
        'imageio',
        'decorator',
        'tqdm',
        'requests',
        'proglog'
    ],
    'includes': [
        'PyQt6.QtCore',
        'PyQt6.QtGui', 
        'PyQt6.QtWidgets',
        'moviepy.editor',
        'cv2',
        'PIL.Image',
        'uuid',
        'datetime',
        'subprocess',
        'threading'
    ],
    'excludes': [
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'setuptools',
        'pkg_resources'
    ],
    'resources': [],
    'optimize': 2,
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
    name='影片編輯器',
    version='2.0.0',
    description='影片編輯器 - 並行處理版本',
    author='VideoEditor',
) 