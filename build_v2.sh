#!/bin/zsh

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT_DIR"

echo "🧹 清理 dist/ 與 build/ ..."
rm -rf "$ROOT_DIR/dist" "$ROOT_DIR/build"

echo "📦 準備虛擬環境..."
if [ -d "$ROOT_DIR/venv" ]; then
  source "$ROOT_DIR/venv/bin/activate"
else
  echo "❌ 找不到 venv，請先執行 ./setup.sh"
  exit 1
fi

echo "📥 安裝/更新 PyInstaller 與必要依賴..."
pip install --upgrade pip >/dev/null
pip install pyinstaller >/dev/null

# 內嵌 ffmpeg/ffprobe 檢查（可用環境變數 SKIP_FFMPEG_CHECK=1 跳過）
FFMPEG_BIN="$ROOT_DIR/assets/bin/mac/arm64/ffmpeg"
FFPROBE_BIN="$ROOT_DIR/assets/bin/mac/arm64/ffprobe"
if [ "${SKIP_FFMPEG_CHECK:-0}" != "1" ]; then
  if [ ! -f "$FFMPEG_BIN" ] || [ ! -f "$FFPROBE_BIN" ]; then
    echo "❌ 缺少內嵌 ffmpeg/ffprobe："
    echo "   請放置實際的 arm64 二進位到："
    echo "   $FFMPEG_BIN"
    echo "   $FFPROBE_BIN"
    echo "   之後再次執行 ./build_v2.sh"
    exit 2
  fi
  if [ ! -x "$FFMPEG_BIN" ] || [ ! -x "$FFPROBE_BIN" ]; then
    chmod +x "$FFMPEG_BIN" "$FFPROBE_BIN" || true
  fi
fi

# 仍確保權限
if [ -f "$FFMPEG_BIN" ]; then chmod +x "$FFMPEG_BIN" || true; fi
if [ -f "$FFPROBE_BIN" ]; then chmod +x "$FFPROBE_BIN" || true; fi

echo "⚙️  使用 .spec 打包 .app ..."
pyinstaller --clean --noconfirm video_wrapper2.spec | cat

echo "✅ 完成：dist/影片編輯器.app"


