#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
產生應用程式圖示：
- 繪製 1024x1024 PNG（深色主題，含膠片框 + 圖片卡片 + 播放箭頭）
- 產生 macOS iconset 所有尺寸
- 轉出 .icns

輸出：
- assets/app_icon_1024.png
- assets/mac/app_icon.iconset/
- assets/mac/app_icon.icns
"""

import os
import sys
import subprocess
from math import sqrt
from PIL import Image, ImageDraw, ImageFilter


ROOT = os.path.abspath(os.path.dirname(__file__))
ASSETS_DIR = os.path.join(ROOT, "assets")
MAC_DIR = os.path.join(ASSETS_DIR, "mac")
ICONSET_DIR = os.path.join(MAC_DIR, "app_icon.iconset")
OUT_PNG = os.path.join(ASSETS_DIR, "app_icon_1024.png")
OUT_ICNS = os.path.join(MAC_DIR, "app_icon.icns")


def ensure_dirs():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(MAC_DIR, exist_ok=True)
    os.makedirs(ICONSET_DIR, exist_ok=True)


def draw_radial_gradient(size, inner_color, outer_color):
    w, h = size
    base = Image.new("RGBA", (w, h), outer_color)
    top = Image.new("RGBA", (w, h), inner_color)
    mask = Image.new("L", (w, h))
    md = ImageDraw.Draw(mask)
    # 從中心向外透明度遞減
    cx, cy = w // 2, h // 2
    max_r = int(sqrt(cx * cx + cy * cy))
    for r in range(max_r, 0, -4):
        alpha = int(max(0, min(255, 255 * (r / max_r))))
        md.ellipse((cx - r, cy - r, cx + r, cy + r), fill=alpha)
    # 柔化過渡
    mask = mask.filter(ImageFilter.GaussianBlur(radius=32))
    base.paste(top, (0, 0), mask)
    return base


def rounded_rectangle(draw: ImageDraw.ImageDraw, xy, radius, fill=None, outline=None, width=1):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_film_frame(draw: ImageDraw.ImageDraw, bbox, radius, fill, outline, hole_color):
    # 膠片主框
    rounded_rectangle(draw, bbox, radius=radius, fill=fill, outline=outline, width=6)
    # 兩側齒孔
    x0, y0, x1, y1 = bbox
    hole_w = 26
    hole_h = 40
    gap = 26
    inset_x = 22
    inset_y = 30
    y = y0 + inset_y
    while y + hole_h <= y1 - inset_y:
        # 左側
        draw.rounded_rectangle((x0 + inset_x, y, x0 + inset_x + hole_w, y + hole_h), radius=6, fill=hole_color)
        # 右側
        draw.rounded_rectangle((x1 - inset_x - hole_w, y, x1 - inset_x, y + hole_h), radius=6, fill=hole_color)
        y += hole_h + gap


def draw_picture_cards(draw: ImageDraw.ImageDraw, base_img: Image.Image, area):
    # 疊放的圖片卡片（代表開頭/結尾圖片）
    x0, y0, x1, y1 = area
    card_w = int((x1 - x0) * 0.44)
    card_h = int((y1 - y0) * 0.55)
    gap = 22
    # 後卡片（紫）
    bx0 = x0 + 20
    by0 = y0 + 18
    bx1 = bx0 + card_w
    by1 = by0 + card_h
    draw.rounded_rectangle((bx0, by0, bx1, by1), radius=28, fill=(167, 139, 250, 230))
    # 前卡片（青藍）
    fx0 = bx0 + gap
    fy0 = by0 + gap
    fx1 = fx0 + card_w
    fy1 = fy0 + card_h
    draw.rounded_rectangle((fx0, fy0, fx1, fy1), radius=28, fill=(79, 195, 247, 235))
    # 前卡片內畫一個簡化的山/太陽圖示
    pad = 28
    ix0, iy0, ix1, iy1 = fx0 + pad, fy0 + pad, fx1 - pad, fy1 - pad
    # 地平線
    draw.rounded_rectangle((ix0, iy0, ix1, iy1), radius=18, outline=(0, 0, 0, 40), width=3)
    # 太陽
    sun_r = 24
    draw.ellipse((ix1 - sun_r*2, iy0 + sun_r, ix1 - 0, iy0 + sun_r*3), fill=(255, 255, 255, 220))
    # 山
    mid_y = iy0 + (iy1 - iy0) * 0.62
    mountain = [
        (ix0 + 10, iy1 - 10),
        (ix0 + (ix1 - ix0) * 0.32, mid_y - 40),
        (ix0 + (ix1 - ix0) * 0.52, iy1 - 10),
    ]
    draw.polygon(mountain, fill=(0, 0, 0, 60))
    mountain2 = [
        (ix0 + (ix1 - ix0) * 0.45, iy1 - 10),
        (ix0 + (ix1 - ix0) * 0.70, mid_y - 26),
        (ix1 - 10, iy1 - 10),
    ]
    draw.polygon(mountain2, fill=(0, 0, 0, 60))


def draw_play_triangle(draw: ImageDraw.ImageDraw, base_img: Image.Image, area):
    # 右側播放箭頭（綠色，呼應 UI 主 CTA）
    x0, y0, x1, y1 = area
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    size = min(x1 - x0, y1 - y0)
    r = int(size * 0.32)
    tri = [
        (cx - int(r * 0.55), cy - int(r * 0.78)),
        (cx + r, cy),
        (cx - int(r * 0.55), cy + int(r * 0.78)),
    ]
    draw.polygon(tri, fill=(76, 175, 80, 245))
    # 外圈微光暈
    glow = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.polygon(tri, fill=(76, 175, 80, 140))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=18))
    base_img.alpha_composite(glow)


def make_base_png():
    size = (1024, 1024)
    # 背景：深藍灰漸層
    bg = draw_radial_gradient(size, inner_color=(28, 38, 50, 255), outer_color=(20, 22, 28, 255))
    img = Image.new("RGBA", size)
    img.alpha_composite(bg)
    d = ImageDraw.Draw(img)

    # 膠片框
    margin = 80
    frame_bbox = (margin, margin, size[0] - margin, size[1] - margin)
    draw_film_frame(
        d,
        bbox=frame_bbox,
        radius=72,
        fill=(35, 35, 35, 240),
        outline=(68, 68, 68, 255),
        hole_color=(22, 22, 22, 220),
    )

    # 內容區域
    x0, y0, x1, y1 = frame_bbox
    inset = 70
    content = (x0 + inset, y0 + inset, x1 - inset, y1 - inset)

    # 左側：圖片卡片
    cw0, cw1 = content[0], content[2]
    ch0, ch1 = content[1], content[3]
    left_area = (cw0, ch0, cw0 + int((cw1 - cw0) * 0.55), ch1)
    right_area = (cw0 + int((cw1 - cw0) * 0.58), ch0, cw1, ch1)
    draw_picture_cards(d, img, left_area)

    # 右側：播放箭頭
    draw_play_triangle(d, img, right_area)

    # 前景玻璃感覆蓋
    glass = Image.new("RGBA", size, (255, 255, 255, 0))
    gdraw = ImageDraw.Draw(glass)
    gdraw.ellipse((-300, -300, 900, 700), fill=(255, 255, 255, 24))
    glass = glass.filter(ImageFilter.GaussianBlur(radius=18))
    img.alpha_composite(glass)

    # 輕微銳化/柔化
    img = img.filter(ImageFilter.SMOOTH_MORE)
    img.save(OUT_PNG)
    return OUT_PNG


ICON_SIZES = [
    (16, False), (16, True),
    (32, False), (32, True),
    (128, False), (128, True),
    (256, False), (256, True),
    (512, False), (512, True),
]


def make_iconset_from_base(base_png):
    src = Image.open(base_png).convert("RGBA")
    for size, is_2x in ICON_SIZES:
        dim = size * (2 if is_2x else 1)
        target = src.resize((dim, dim), Image.LANCZOS)
        name = f"icon_{size}x{size}{'@2x' if is_2x else ''}.png"
        target.save(os.path.join(ICONSET_DIR, name))


def make_icns():
    # 使用 macOS iconutil
    cmd = ["iconutil", "-c", "icns", ICONSET_DIR, "-o", OUT_ICNS]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if res.returncode != 0:
            print("iconutil 失敗，輸出如下：")
            print(res.stdout)
            return False
        return True
    except FileNotFoundError:
        print("找不到 iconutil，請在 macOS 環境執行或手動轉檔。")
        return False


def main():
    ensure_dirs()
    base = make_base_png()
    print(f"已輸出：{base}")
    make_iconset_from_base(base)
    print(f"已輸出 iconset 至：{ICONSET_DIR}")
    if make_icns():
        print(f"已輸出 .icns：{OUT_ICNS}")
    else:
        print(".icns 轉檔未完成，請確認是否有 iconutil 指令。")


if __name__ == "__main__":
    sys.exit(main() or 0)


