#!/bin/bash

# 影片編輯器 - 自動打包腳本
# 支持 PyInstaller 打包
# 修復版本：解決了臨時檔案寫入問題

set -e

echo "🚀 影片編輯器 - 自動打包腳本 (修復版本)"
echo "=================================="

# 檢查參數，預設使用 PyInstaller
BUILD_METHOD=${1:-"pyinstaller"}

echo "📦 選擇的打包方式：$BUILD_METHOD"

# 啟動虛擬環境
if [ -d "venv" ]; then
    echo "🔧 啟動虛擬環境..."
    source venv/bin/activate
else
    echo "❌ 虛擬環境不存在，請先運行 ./setup.sh"
    exit 1
fi

# 清理舊的打包文件
echo "🧹 清理舊的打包文件..."
rm -rf build/
rm -rf dist/

if [ "$BUILD_METHOD" = "pyinstaller" ]; then
    echo "📱 使用 PyInstaller 打包應用程式（修復版本）..."
    
    echo "📥 安裝 PyInstaller..."
    pip install pyinstaller
    
    echo "⚙️  執行打包..."
    
    # 生成單一執行檔
    echo "1️⃣ 生成單一執行檔..."
    pyinstaller --onefile --windowed --name="影片編輯器_單一檔案" \
        --add-data="video_wrapper.py:." \
        --hidden-import=moviepy.editor \
        --hidden-import=moviepy \
        video_wrapper.py --noconfirm
    
    # 生成 .app 包
    echo "2️⃣ 生成 .app 包..."
    pyinstaller --onedir --windowed --name="影片編輯器" \
        --add-data="video_wrapper.py:." \
        --hidden-import=moviepy.editor \
        --hidden-import=moviepy \
        video_wrapper.py --noconfirm
        
    echo ""
    echo "✅ PyInstaller 打包完成！"
    echo "📁 輸出檔案："
    echo "   - 單一執行檔：dist/影片編輯器_單一檔案 (~95MB)"
    echo "   - .app 包：dist/影片編輯器.app (~200MB)"
    echo ""
    echo "🔧 修復說明："
    echo "   - 已解決 FFmpeg 臨時檔案寫入問題"
    echo "   - 使用系統臨時目錄，避免權限錯誤"
    echo "   - 添加了更好的清理機制"

elif [ "$BUILD_METHOD" = "py2app" ]; then
    echo "📱 使用 py2app 打包 macOS 應用程式..."
    
    echo "📥 安裝 py2app..."
    pip install py2app
    
    echo "⚙️  執行打包..."
    if python setup.py py2app; then
        echo "✅ py2app 打包成功！"
        echo "📁 應用程式位置：dist/影片編輯器.app"
        echo "💾 應用程式大小：$(du -sh dist/影片編輯器.app | cut -f1)"
    else
        echo "❌ py2app 打包失敗"
        echo "💡 建議改用 PyInstaller："
        echo "   ./build_app.sh pyinstaller"
        exit 1
    fi

else
    echo "❌ 未知的打包方式：$BUILD_METHOD"
    echo "支持的方式："
    echo "  ./build_app.sh pyinstaller  (推薦，已修復)"
    echo "  ./build_app.sh py2app"
    exit 1
fi

echo ""
echo "🎉 打包完成！" 