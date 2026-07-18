"""Pillow 渲染「极简版」少侠 logo 多尺寸 PNG。

设计原则：v0.3.4 — 简单明了，最多 2-3 个元素：
- 圆角矩形 + 深竹青底（无渐变，纯色）
- 居中竖直的一把长剑（剑格 + 剑身 + 剑柄 + 剑穗）
- 右上角一小弯月（可选点缀）

无少侠剪影、无远山、无竹叶、无朱砂印、无飘带。
"""

import sys, math
from pathlib import Path
from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding='utf-8')

OUT = Path(__file__).resolve().parent.parent.parent.parent / 'electron'
OUT.mkdir(parents=True, exist_ok=True)

# 调色板
COLORS = {
    'bg':         (0x22, 0x4a, 0x38),    # 平涂墨青
    'moon':       (0xe8, 0xd9, 0x9c),    # 古卷米黄
    'sword':      (0xd8, 0xd2, 0xc4),    # 银白剑身
    'sword_hl':   (0xf5, 0xe9, 0xc8),    # 剑身高光
    'gold':       (0xb0, 0x8a, 0x3e),    # 剑格金色
    'hilt':       (0x3a, 0x2a, 0x1c),    # 剑柄深褐
    'tassel':     (0xa0, 0x40, 0x30),    # 剑穗朱砂
}


def draw_bg(img: Image.Image, size: int):
    """纯色圆角矩形背景"""
    w, h = size, size
    r = int(w * 0.18)  # 圆角半径
    # 用 alpha mask 切圆角
    mask = Image.new('L', (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=r, fill=255)
    bg = Image.new('RGB', (w, h), COLORS['bg'])
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    out.paste(bg, (0, 0), mask)
    # 把半透明背景转成对应 RGB
    img.paste(out.convert('RGB'), (0, 0))


def draw_moon(img: Image.Image, size: int):
    """右上弯月（小一点）"""
    w, h = size, size
    cx, cy = int(w * 0.78), int(h * 0.22)
    r_outer = int(w * 0.06)
    r_inner = int(r_outer * 0.85)
    ox = int(r_outer * 0.3)
    mask = Image.new('L', (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer], fill=255)
    md.ellipse([cx - r_inner + ox, cy - r_inner, cx + r_inner + ox, cy + r_inner], fill=0)
    moon_layer = Image.new('RGB', (w, h), COLORS['moon'])
    img.paste(moon_layer, (0, 0), mask)


def draw_sword(img: Image.Image, size: int):
    """居中竖直的长剑（无斜角）

    布局（从上到下）：
      剑穗（朱红短线）0.18
      剑格（金黄圆）0.25
      剑身（银白长条）0.27-0.66
      剑柄（深褐短条）0.66-0.74
      收尾
    """
    w, h = size, size
    draw = ImageDraw.Draw(img)
    cx = int(w * 0.46)  # 偏左一点，留出右边月视觉平衡

    # 剑穗
    tassel_y0 = int(h * 0.22)
    tassel_y1 = int(h * 0.30)
    tassel_w = max(2, int(w * 0.012))
    draw.line([(cx, tassel_y0), (cx, tassel_y1)], fill=COLORS['tassel'], width=tassel_w)
    # 剑穗尾端穗头（小三角）
    draw.polygon([(cx - tassel_w * 2, tassel_y0),
                   (cx + tassel_w * 2, tassel_y0),
                   (cx, tassel_y0 - int(h * 0.015))], fill=COLORS['tassel'])

    # 剑格（金色横条）
    guard_y0 = int(h * 0.30)
    guard_y1 = int(h * 0.34)
    guard_w = max(8, int(w * 0.07))
    draw.rectangle([cx - guard_w, guard_y0, cx + guard_w, guard_y1], fill=COLORS['gold'])
    # 剑格中心圆点
    cr = max(2, int(w * 0.012))
    draw.ellipse([cx - cr, guard_y0, cx + cr, guard_y1], fill=COLORS['hilt'])

    # 剑身（双线：外白内高光）
    blade_x0 = cx - max(2, int(w * 0.012))
    blade_x1 = cx + max(2, int(w * 0.012))
    blade_y1 = int(h * 0.74)
    draw.rectangle([blade_x0, guard_y1, blade_x1, blade_y1], fill=COLORS['sword'])
    # 剑身高光线（居中，更亮、更窄）
    hl_w = max(1, int(w * 0.005))
    draw.rectangle([cx - hl_w, guard_y1, cx + hl_w, blade_y1], fill=COLORS['sword_hl'])
    # 剑尖（V 形斜切）
    blade_tip_y = int(h * 0.78)
    draw.polygon([(blade_x0, blade_y1), (blade_x1, blade_y1),
                   (cx, blade_tip_y)], fill=COLORS['sword'])

    # 剑柄（深褐短横）
    grip_y0 = int(h * 0.74)
    grip_y1 = int(h * 0.82)
    grip_w = max(6, int(w * 0.045))
    draw.rectangle([cx - grip_w, grip_y0, cx + grip_w, grip_y1], fill=COLORS['hilt'])
    # 剑柄缠绕纹（横线 3 段）
    for i in range(1, 4):
        ly = grip_y0 + (grip_y1 - grip_y0) * i // 4
        draw.line([(cx - grip_w, ly), (cx + grip_w, ly)], fill=COLORS['gold'], width=max(1, int(w * 0.005)))


def render(size: int, out_path: Path):
    img = Image.new('RGB', (size, size), (0, 0, 0))
    draw_bg(img, size)
    draw_sword(img, size)
    draw_moon(img, size)
    img.save(out_path, 'PNG', optimize=True)
    print(f'  {out_path.name}  {size}x{size}  ({out_path.stat().st_size} B)')


if __name__ == '__main__':
    targets = [
        (32,  OUT / 'icon.png'),
        (128, OUT / 'icon-128.png'),
        (256, OUT / 'icon-256.png'),
        (512, OUT / 'icon-512.png'),
    ]
    print(f'输出目录: {OUT}')
    print(f'风格: 极简 · 墨青底 + 居中长剑 + 右上小弯月')
    for sz, p in targets:
        render(sz, p)
    print('OK')
