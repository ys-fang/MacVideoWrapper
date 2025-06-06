# 影片編輯器 (Video Wrapper)

一個簡單易用的桌面應用程式，可以為您的影片快速添加靜態的開頭和結尾圖片。採用序列佇列處理模式，穩定可靠。

![應用程式截圖](https://raw.githubusercontent.com/your-username/your-repo-name/main/screenshot.png)
*(請將上面的 URL 替換為您自己的截圖路徑)*

---

## ✨ 主要功能

- **序列處理**: 所有任務都會進入佇列依序處理，確保系統穩定，避免資源競爭導致的崩潰。
- **簡單易用**: 直觀的圖形化介面，輕鬆選擇影片和圖片。
- **預覽功能**: 在處理前可以預覽開頭、結尾圖片和影片的第一幀。
- **彈性選項**:
  - 可只加開頭、只加結尾，或兩者都加。
  - 可設定開頭/結尾圖片的顯示時長。
  - 提供「開頭與結尾圖片一樣」的便利選項。
- **深色主題**: 現代化的深色 UI。
- **跨平台**: 使用 PyQt6 和 Python，理論上可在多平台運行 (主要在 macOS 上開發與測試)。

## 🛠️ 安裝與設置

您需要先安裝 **Python 3.8+** 和 **FFmpeg**。

```bash
# 在 macOS 上使用 Homebrew 安裝 FFmpeg
brew install ffmpeg
```

然後，請依照以下步驟設置專案：

```bash
# 1. 克隆此儲存庫
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name

# 2. 建立並啟動虛擬環境 (推薦)
./setup.sh

# 3. 虛擬環境將被啟動，並安裝所有必要的 Python 依賴
# 如果您需要手動啟動：
source venv/bin/activate
```

## 🚀 如何運行

確保您已在虛擬環境中，然後執行：

```bash
./run.sh
```
或
```bash
python video_wrapper.py
```

## 📦 如何打包成獨立應用程式

本專案包含打包腳本，可以將應用程式打包成獨立的 macOS 應用程式 (`.app`) 或單一執行檔。

```bash
# 確保在虛擬環境中
source venv/bin/activate

# 執行打包腳本
./build_app.sh

# 這會使用 PyInstaller 在 dist/ 目錄下生成兩種版本：
# 1. dist/影片編輯器.app (macOS 應用程式包)
# 2. dist/影片編輯器_單一檔案 (單一執行檔)
```

詳細的打包說明請參考 [`BUILD_INSTRUCTIONS.md`](BUILD_INSTRUCTIONS.md)。

## 📄 授權條款

本專案採用 [MIT 授權條款](LICENSE)。

## 🙌 如何貢獻

歡迎任何形式的貢獻！如果您有好的想法或發現了問題，請隨時開一個 Issue 或提交 Pull Request。 