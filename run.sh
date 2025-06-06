#!/bin/bash

echo "🎬 啟動影片編輯器..."
cd "$(dirname "$0")"

# 檢查虛擬環境是否存在
if [ ! -d "venv" ]; then
    echo "❌ 虛擬環境不存在，請先執行 ./setup.sh"
    exit 1
fi

# 啟動虛擬環境並執行程式
source venv/bin/activate
python3 video_wrapper.py 