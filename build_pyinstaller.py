#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
影片編輯器 - PyInstaller 打包工具
支持生成單一執行檔或 .app 包
修復版本：解決了臨時檔案寫入問題
"""

import subprocess
import sys
import os

def run_pyinstaller(onefile=True):
    """執行 PyInstaller 打包"""
    base_name = "影片編輯器"
    
    # 基本參數
    cmd = ["pyinstaller"]
    
    if onefile:
        cmd.extend(["--onefile"])
        name = base_name + "_單一檔案"
    else:
        cmd.extend(["--onedir"])
        name = base_name
    
    cmd.extend([
        "--windowed",
        f"--name={name}",
        "--add-data=video_wrapper.py:.",
        "--hidden-import=moviepy.editor",
        "--hidden-import=moviepy",
        "video_wrapper.py",
        "--noconfirm"
    ])
    
    print(f"命令： {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ 打包成功！")
            if onefile:
                print(f"可執行檔位置：dist/{name}")
            else:
                print(f".app 包位置：dist/{name}.app")
            return True
        else:
            print("❌ 打包失敗：")
            print(result.stdout)
            print(result.stderr)
            return False
    except Exception as e:
        print(f"❌ 執行錯誤：{e}")
        return False

def main():
    print("影片編輯器 - PyInstaller 打包工具")
    print("修復版本：解決了臨時檔案寫入問題")
    print("=" * 50)
    
    print("選擇打包方式：")
    print("1. 單一執行檔")
    print("2. .app 包")
    print("3. 兩者都生成")
    
    choice = input("請輸入選擇 (1/2/3): ").strip()
    
    if choice == "1":
        print("正在生成單一執行檔...")
        run_pyinstaller(onefile=True)
    elif choice == "2":
        print("正在生成 .app 包...")
        run_pyinstaller(onefile=False)
    elif choice == "3":
        print("正在生成兩種格式...")
        print("\n1. 生成單一執行檔...")
        run_pyinstaller(onefile=True)
        print("\n2. 生成 .app 包...")
        run_pyinstaller(onefile=False)
    else:
        print("❌ 無效選擇")
        sys.exit(1)

if __name__ == "__main__":
    main() 