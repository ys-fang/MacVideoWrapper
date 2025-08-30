#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
影片編輯器 v3 整合版本啟動腳本
支援單次處理與批次處理兩種模式
"""

import sys
import os

# 添加當前目錄到 Python 路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """主函數"""
    try:
        from video_wrapper2 import VideoEditorFFApp
        from PyQt6.QtWidgets import QApplication
        
        print("🚀 啟動影片編輯器 v3 整合版本...")
        print("✨ 新功能：支援單次處理與批次處理兩種模式")
        
        app = QApplication(sys.argv)
        win = VideoEditorFFApp()
        win.show()
        
        print("✅ 應用程式已啟動")
        print("📋 使用說明:")
        print("   🎬 單次處理模式：處理單一影片檔案")
        print("   📦 批次處理模式：批量處理多個影片檔案")
        print("   💡 兩種模式共用同一個處理佇列")
        
        return app.exec()
        
    except ImportError as e:
        print(f"❌ 導入錯誤: {e}")
        print("請確保已安裝 PyQt6 和相關依賴")
        return 1
    except Exception as e:
        print(f"❌ 啟動錯誤: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
