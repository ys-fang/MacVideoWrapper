# 影片編輯器 - 打包說明

## 📦 打包方案選擇

### 🚀 **推薦方案：PyInstaller（跨平台）**
- ✅ 優秀的依賴處理能力
- ✅ 自動解決複雜模組依賴問題
- ✅ 生成 .app 包和單一執行檔
- ✅ 跨平台支援
- ✅ 較小的檔案大小（約 72MB）

### 🔄 **備選方案：py2app（macOS 專用）**
- ✅ 創建真正的 macOS .app 包
- ✅ 最佳用戶體驗，可直接拖拽到 Applications
- ✅ 支援 macOS 原生特性
- ⚠️ 在新版 macOS 上可能遇到依賴問題

## 🛠 打包步驟

### **方法一：使用自動打包腳本（推薦）**

```bash
# 1. 啟動虛擬環境
source venv/bin/activate

# 2. 使用 PyInstaller 打包（推薦）
./build_app.sh pyinstaller

# 或使用 py2app 打包
./build_app.sh py2app
```

### **方法二：手動打包**

#### **使用 PyInstaller（推薦）：**
```bash
# 1. 啟動虛擬環境
source venv/bin/activate

# 2. 安裝 PyInstaller
pip install pyinstaller

# 3. 執行打包腳本
python3 build_pyinstaller.py

# 4. 或直接使用命令
pyinstaller --onefile --windowed --name="影片編輯器" --add-data="video_wrapper.py:." --hidden-import=moviepy.editor --hidden-import=moviepy video_wrapper.py
```

#### **使用 py2app：**
```bash
# 1. 啟動虛擬環境
source venv/bin/activate

# 2. 安裝 py2app
pip install py2app

# 3. 執行打包
python3 setup.py py2app

# 4. 結果位置
ls dist/影片編輯器.app
```

## 📁 輸出結果

### **py2app 輸出：**
```
dist/
└── 影片編輯器.app/          # macOS 應用程式包
    ├── Contents/
    │   ├── Info.plist      # 應用程式資訊
    │   ├── MacOS/          # 執行檔案
    │   └── Resources/      # 資源文件
```

### **PyInstaller 輸出：**
```
dist/
├── 影片編輯器              # 單一執行檔案（約 95MB）
└── 影片編輯器.app/          # macOS 應用程式包
    ├── Contents/
    │   ├── Info.plist      # 應用程式資訊
    │   ├── MacOS/          # 執行檔案
    │   └── Resources/      # 資源文件
```

## 🚀 安裝和使用

### **py2app 版本：**
1. 將 `影片編輯器.app` 拖拽到 Applications 資料夾
2. 在 Launchpad 中找到並啟動應用程式
3. 或直接雙擊 .app 檔案運行

### **PyInstaller 版本：**
1. **應用程式包：** 將 `影片編輯器.app` 拖拽到 Applications 資料夾
2. **單一執行檔：** 直接雙擊 `影片編輯器` 執行檔案
3. **終端機運行：** `./dist/影片編輯器` 或 `./dist/影片編輯器.app/Contents/MacOS/影片編輯器`

## ⚠️ 注意事項

### **macOS 安全性設定：**
第一次運行時可能會遇到安全性警告：

1. **「無法驗證開發者」錯誤：**
   - 系統偏好設定 → 安全性與隱私權
   - 點擊「仍要開啟」

2. **或使用命令解除限制：**
   ```bash
   sudo xattr -r -d com.apple.quarantine /path/to/影片編輯器.app
   ```

### **FFmpeg 依賴：**
應用程式需要 FFmpeg 支援，確保系統已安裝：
```bash
# 使用 Homebrew 安裝
brew install ffmpeg

# 或在打包時包含 FFmpeg 二進制檔案
```

### **檔案大小：**
- PyInstaller：約 95 MB（單一執行檔）+ 應用程式包
- py2app：約 200-500 MB（包含完整 Python 環境）

## 🔧 故障排除

### **常見問題：**

1. **ModuleNotFoundError：**
   ```bash
   # 確保所有依賴都已安裝
   pip install -r requirements.txt
   ```

2. **打包失敗：**
   ```bash
   # 清理並重新打包
   rm -rf build/ dist/
   ./build_app.sh py2app
   ```

3. **運行時錯誤：**
   ```bash
   # 檢查依賴是否正確包含
   # 編輯 setup.py 或 build_pyinstaller.py 中的 includes 列表
   ```

## 📝 版本資訊

- **應用程式版本：** 2.0.0
- **Python 版本：** 3.13+
- **支援系統：** macOS 10.14+
- **主要功能：** 影片並行處理、開頭結尾圖片添加

## 🎯 效能優化

### **減少檔案大小：**
1. 排除不必要的模組（已在配置中設定）
2. 使用 UPX 壓縮（PyInstaller）
3. 使用 `--optimize 2` 參數

### **提升啟動速度：**
1. 使用 py2app 替代 PyInstaller
2. 預編譯 Python 檔案
3. 優化 import 語句

## 📮 發佈準備

### **創建安裝程式：**
```bash
# 使用 create-dmg 創建 DMG 檔案
brew install create-dmg

create-dmg \
  --volname "影片編輯器" \
  --window-pos 200 120 \
  --window-size 800 400 \
  --icon-size 100 \
  --app-drop-link 600 185 \
  "影片編輯器.dmg" \
  "dist/"
```

### **代碼簽署（可選）：**
```bash
# 如果有開發者憑證
codesign --deep --force --verify --verbose --sign "Developer ID Application: Your Name" "影片編輯器.app"
```

## 🐛 常見錯誤解決

### **Carbon.framework 錯誤**
在 macOS Big Sur（11.0）及更新版本上，可能會遇到：
```
OSError: dlopen(/System/Library/Carbon.framework/Carbon, 0x0006): tried: '/System/Library/Carbon.framework/Carbon' (no such file)
```

**解決方法：**
已在 `setup.py` 中設定 `argv_emulation: False` 來解決此問題。如果仍遇到問題，可以手動編輯：

```python
OPTIONS = {
    'argv_emulation': False,  # 禁用以解決 Carbon 問題
    # ... 其他設定
}
```

### **jaraco.text 依賴錯誤**
如果遇到 `ModuleNotFoundError: No module named 'jaraco.text'` 錯誤：

**解決方法：**
使用 PyInstaller 替代 py2app，PyInstaller 能更好地處理複雜的依賴關係：

```bash
# 清理並使用 PyInstaller 重新打包
rm -rf build/ dist/
pip install pyinstaller
pyinstaller --onefile --windowed --name="影片編輯器" --add-data="video_wrapper.py:." --hidden-import=moviepy.editor --hidden-import=moviepy video_wrapper.py
```

### **moviepy 依賴錯誤**
如果遇到 `ModuleNotFoundError: No module named 'moviepy'` 錯誤：

**解決方法：**
在 PyInstaller 命令中明確指定 moviepy 依賴：

```bash
# 確保在虛擬環境中運行
source venv/bin/activate

# 使用包含 moviepy 依賴的命令重新打包
pyinstaller --onefile --windowed --name="影片編輯器" --add-data="video_wrapper.py:." --hidden-import=moviepy.editor --hidden-import=moviepy video_wrapper.py
```

### **應用程式啟動問題**
如果應用程式無法正常啟動：

1. **檢查控制台日誌：**
   ```bash
   # 查看詳細錯誤信息
   /Applications/Utilities/Console.app
   ```

2. **從終端機運行：**
   ```bash
   # 直接運行以查看錯誤訊息
   ./dist/影片編輯器.app/Contents/MacOS/影片編輯器
   ```

3. **重新打包：**
   ```bash
   # 推薦使用 PyInstaller
   rm -rf build/ dist/
   ./build_app.sh pyinstaller
   ```

## 版本更新

### v2.1 (2024-06-06) - 臨時檔案修復版本
- ✅ **修復關鍵問題**：解決了 FFmpeg 無法在只讀檔案系統中創建臨時檔案的問題
- ✅ **改進功能**：使用系統臨時目錄和唯一檔案名避免衝突
- ✅ **增強穩定性**：添加了更好的臨時檔案清理機制

### v2.0 - 並行處理版本
- ✅ 完整的並行影片處理功能
- ✅ 現代化 PyQt6 深色主題界面
- ✅ 多線程工作管理
- ✅ 實時進度和狀態監控

## 打包工具

### 1. 自動打包腳本（推薦）

```bash
# 使用自動化腳本
python build_pyinstaller.py

# 選項：
# 1. 單一執行檔（~95MB）- 方便分發
# 2. .app 包（~200MB）- 原生 macOS 體驗  
# 3. 兩者都生成
```

### 2. 手動打包命令

```bash
# 啟動虛擬環境
source venv/bin/activate

# 生成單一執行檔
pyinstaller --onefile --windowed --name="影片編輯器_單一檔案" \
    --add-data="video_wrapper.py:." \
    --hidden-import=moviepy.editor \
    --hidden-import=moviepy \
    video_wrapper.py --noconfirm

# 生成 .app 包
pyinstaller --onedir --windowed --name="影片編輯器" \
    --add-data="video_wrapper.py:." \
    --hidden-import=moviepy.editor \
    --hidden-import=moviepy \
    video_wrapper.py --noconfirm
```

### 3. 快速打包腳本

```bash
# 一鍵打包腳本
./build_app.sh
```

## 重要修復說明

### 臨時檔案問題解決方案

**問題**：在 macOS 打包應用中，MoviePy 的 FFmpeg 無法在預設位置創建臨時音頻檔案，導致錯誤：
```
Error opening output temp-audio.m4a: Read-only file system
```

**解決方案**：
1. 使用 `tempfile.gettempdir()` 獲取系統可寫臨時目錄
2. 為每個工作生成唯一的臨時檔案名（使用 job_id）
3. 添加 backup 清理機制確保臨時檔案被正確刪除

**程式碼變更**：
```python
# 創建可寫入的臨時檔案路徑
temp_dir = tempfile.gettempdir()
temp_audio_path = os.path.join(temp_dir, f"temp-audio-{self.job_id}.m4a")

# 使用完整路徑而非相對路徑
final_clip.write_videofile(
    self.output_file,
    temp_audiofile=temp_audio_path,  # 使用完整路徑
    # ... 其他參數
)
```

## 系統需求

### 開發環境
- macOS 10.14+ 
- Python 3.8+
- FFmpeg (透過 Homebrew 安裝)

### 打包後應用
- macOS 10.14+
- 無需額外依賴（FFmpeg 已包含在 imageio-ffmpeg 中）

## 依賴清單

核心依賴（requirements.txt）：
```
PyQt6>=6.6.0
opencv-python>=4.8.0
Pillow>=10.0.0
moviepy>=1.0.3
imageio-ffmpeg>=0.4.8
```

打包依賴：
```
pyinstaller>=6.0.0
```

## 輸出檔案

打包後會在 `dist/` 目錄中生成：

1. **單一執行檔**：`影片編輯器_單一檔案` (~95MB)
   - 優點：單一檔案，易於分發
   - 缺點：啟動稍慢，檔案較大

2. **.app 包**：`影片編輯器.app/` (~200MB)
   - 優點：原生 macOS 體驗，啟動快速
   - 缺點：檔案夾結構，分發較複雜

## 測試驗證

使用測試腳本驗證打包結果：

```bash
# 測試打包的應用程式
./test_package.sh

# 測試內容：
# 1. 檔案存在性檢查
# 2. 基本功能測試
# 3. FFmpeg 依賴檢查
# 4. 臨時檔案處理測試
```

## 常見問題

### 1. FFmpeg 相關錯誤
**問題**：`Error opening output temp-audio.m4a`
**解決**：確保使用修復版本（v2.1+），該版本已解決臨時檔案問題

### 2. PyQt6 依賴錯誤
**問題**：`ModuleNotFoundError: No module named 'PyQt6'`
**解決**：確保在虛擬環境中打包：
```bash
source venv/bin/activate
python build_pyinstaller.py
```

### 3. 檔案權限問題
**問題**：應用無法執行
**解決**：
```bash
chmod +x dist/影片編輯器_單一檔案
```

### 4. moviepy 模組未找到
**問題**：`ModuleNotFoundError: No module named 'moviepy'`
**解決**：確保使用了 `--hidden-import=moviepy` 和 `--hidden-import=moviepy.editor` 參數

## 版本歷史

- **v2.1** - 臨時檔案修復版本
- **v2.0** - 並行處理 PyQt6 版本  
- **v1.0** - 基礎 Tkinter 版本（已棄用）

## 支援與維護

- 所有打包腳本和說明均已測試
- 修復了所有已知的打包和運行時問題
- 建議使用最新版本（v2.1+）以獲得最佳穩定性 