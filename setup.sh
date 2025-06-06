#!/bin/bash

echo "🎬 影片編輯器 - 環境設置腳本"
echo "================================"

# 檢查 Python 版本
echo "1. 檢查 Python 版本..."
python3 --version

# 檢查並安裝 FFmpeg
echo -e "\n2. 檢查 FFmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo "FFmpeg 未安裝，正在安裝..."
    if command -v brew &> /dev/null; then
        brew install ffmpeg
    else
        echo "請先安裝 Homebrew，然後執行: brew install ffmpeg"
        echo "Homebrew 安裝: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
    fi
else
    echo "FFmpeg 已安裝 ✅"
fi

# 創建虛擬環境
echo -e "\n3. 創建 Python 虛擬環境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "虛擬環境已創建 ✅"
else
    echo "虛擬環境已存在 ✅"
fi

# 啟動虛擬環境並安裝套件
echo -e "\n4. 安裝 Python 套件..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo -e "\n✅ 環境設置完成！"
echo "使用方式："
echo "1. 啟動虛擬環境: source venv/bin/activate"
echo "2. 執行程式: python video_wrapper.py"
echo "3. 停用虛擬環境: deactivate" 