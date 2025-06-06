#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk

def test_ui():
    root = tk.Tk()
    root.title("UI 測試")
    root.geometry("600x400")
    root.configure(bg='#f0f0f0')
    
    # 測試不同的字體
    fonts_to_test = [
        ('Helvetica', 12),
        ('Arial', 12),
        ('System', 12),
        ('Monaco', 12)
    ]
    
    main_frame = tk.Frame(root, bg='white', padx=20, pady=20)
    main_frame.pack(fill='both', expand=True, padx=20, pady=20)
    
    tk.Label(main_frame, text="字體測試", font=('Helvetica', 16, 'bold')).pack(pady=10)
    
    for i, (font_name, size) in enumerate(fonts_to_test):
        try:
            btn = tk.Button(main_frame, 
                           text=f"測試按鈕 - {font_name}", 
                           font=(font_name, size),
                           bg='#007AFF', fg='white',
                           height=2, relief='flat')
            btn.pack(fill='x', pady=5)
            
            label = tk.Label(main_frame, 
                           text=f"標籤文字 - {font_name}",
                           font=(font_name, size))
            label.pack(pady=2)
            
        except Exception as e:
            error_label = tk.Label(main_frame, 
                                 text=f"{font_name} 字體不可用: {str(e)}")
            error_label.pack(pady=2)
    
    root.mainloop()

if __name__ == "__main__":
    test_ui() 