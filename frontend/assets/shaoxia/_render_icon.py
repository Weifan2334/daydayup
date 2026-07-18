"""Pillow 渲染少侠 logo 多尺寸 PNG。

输出：
- electron/icon.png (32x32)
- electron/icon-256.png (256x256, electron-builder 用)
- electron/tray.png (32x32 mono)

设计：
- 背景：圆角矩形 + 深竹青渐变 (#1f3a2a → #2c4f3e)
- 右上：弯月（米黄色圆 - 偏移覆盖形成月牙）
- 中心：少侠剪影（青衫 + 长剑 + 飘带）
- 左下 / 前景：斜竹叶
"""

import sys
from pathlib import Path
from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding='utf-8')

OUT = Path(__file__).resolve().parent.parent.parent.parent / 'electron'
OUT.mkdir(parents=True, exist_ok=True)

# 调色板（与 styles.css :root 严格一致）
COLORS = {
    'bg_top':    (0x1f, 0x3a, 0x2a),
    'bg_bot':    (0x0f, 0x1f, 0x1c),
    'moon':      (0xd6, 0xc3, 0x88),
    'moon_glow': (0xf5, 0xe9, 0xc8),
    'robe_lt':   (0x6f, 0x9a, 0x84),
    'robe_dk':   (0x3a, 0x5d, 0x4d),
    'skin':      (0xe8, 0xd4, 0xa8),
    'hair':      (0x1a, 0x1a, 0x1a),
    'sword':     (0xd8, 0xd2, 0xc4),
    'sword_hilt':(0x3a, 0x2a, 0x1c),
    'gold':      (0xb0, 0x8a, 0x3e),
    'red':       (0xa0, 0x40, 0x30),
    'bamboo':    (0x9f, 0xc4, 0xb0),
    'rock':      (0x1c, 0x2e, 0x26),
}


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw_bg(img: Image.Image, size: int):
    """圆角矩形 + 垂直渐变 + 远山层叠"""
    w, h = size, size
    px = img.load()
    radius = int(w * 0.18)
    for y in range(h):
        t = y / (h - 1)
        col = lerp(COLORS['bg_top'], COLORS['bg_bot'], t)
        for x in range(w):
            # 圆角遮罩
            inside = True
            for cx, cy in [(radius, radius), (w - radius - 1, radius),
                           (radius, h - radius - 1), (w - radius - 1, h - radius - 1)]:
                if x < radius and y < radius and (x - cx) ** 2 + (y - cy) ** 2 > radius ** 2:
                    inside = False
                if x > w - radius - 1 and y < radius and (x - cx) ** 2 + (y - cy) ** 2 > radius ** 2:
                    inside = False
                if x < radius and y > h - radius - 1 and (x - cx) ** 2 + (y - cy) ** 2 > radius ** 2:
                    inside = False
                if x > w - radius - 1 and y > h - radius - 1 and (x - cx) ** 2 + (y - cy) ** 2 > radius ** 2:
                    inside = False
            if inside:
                px[x, y] = col
    # 远山（底部 30% 区域，深一档）
    draw = ImageDraw.Draw(img)
    h2 = int(h * 0.7)
    draw.polygon([(0, h), (0, h2 + int(h * 0.04)),
                  (int(w * 0.18), h2 - int(h * 0.01)),
                  (int(w * 0.36), h2 + int(h * 0.03)),
                  (int(w * 0.55), h2 - int(h * 0.02)),
                  (int(w * 0.72), h2 + int(h * 0.04)),
                  (int(w * 0.88), h2 - int(h * 0.01)),
                  (w, h2 + int(h * 0.03)),
                  (w, h)], fill=(26, 58, 50))
    draw.polygon([(0, h), (0, h2 + int(h * 0.10)),
                  (int(w * 0.22), h2 + int(h * 0.04)),
                  (int(w * 0.42), h2 + int(h * 0.08)),
                  (int(w * 0.66), h2 + int(h * 0.03)),
                  (int(w * 0.84), h2 + int(h * 0.07)),
                  (w, h2 + int(h * 0.05)),
                  (w, h)], fill=(17, 39, 31))


def draw_moon(img: Image.Image, size: int):
    """右上弯月：用大圆减去偏移小圆（挖月牙）"""
    draw = ImageDraw.Draw(img)
    w, h = size, size
    cx, cy = int(w * 0.72), int(h * 0.24)
    r_outer = int(w * 0.10)
    r_inner = int(r_outer * 0.90)
    ox = int(r_outer * 0.30)
    # 用临时图层 mask 切月牙
    mask = Image.new('L', (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer], fill=255)
    md.ellipse([cx - r_inner + ox, cy - r_inner, cx + r_inner + ox, cy + r_inner], fill=0)
    moon_color = Image.new('RGB', (w, h), COLORS['moon_glow'])
    img.paste(moon_color, (0, 0), mask)


def draw_swordsman(img: Image.Image, size: int):
    """少侠剪影（侧身立姿）+ 长剑（右上斜向左下）+ 飘带 + 脚下踩石"""
    draw = ImageDraw.Draw(img)
    w, h = size, size
    s = w / 256.0  # 缩放因子

    def S(v):
        return int(v * s)

    cx = int(w * 0.42)
    head_y = int(h * 0.30)

    # 头部
    head_r = S(20)
    draw.ellipse([cx - head_r, head_y - head_r, cx + head_r, head_y + head_r], fill=COLORS['skin'])

    # 高髻小球
    bun_r = S(10)
    draw.ellipse([cx - bun_r, head_y - head_r - S(20), cx + bun_r, head_y - head_r], fill=COLORS['hair'])

    # 飘发
    draw.polygon([(cx - S(8), head_y - S(15)),
                   (cx - S(28), head_y + S(8)),
                   (cx - S(38), head_y + S(20)),
                   (cx - S(22), head_y - S(2)),
                   (cx - S(10), head_y - S(12))], fill=COLORS['hair'])

    # 颈 + 衣领
    draw.polygon([(cx - S(8), head_y + head_r),
                   (cx, head_y + head_r + S(10)),
                   (cx + S(8), head_y + head_r),
                   (cx + S(6), head_y + head_r + S(5)),
                   (cx - S(6), head_y + head_r + S(5))], fill=(204, 224, 210))

    # 身体青衫（长袍梯形，从肩到脚）
    robe_top_w = S(50)
    robe_top_y = head_y + head_r + S(8)
    robe_bot_w = S(120)
    robe_bot_y = int(h * 0.82)
    draw.polygon([(cx - robe_top_w // 2, robe_top_y),
                   (cx + robe_top_w // 2, robe_top_y),
                   (cx + robe_bot_w // 2, robe_bot_y),
                   (cx - robe_bot_w // 2, robe_bot_y)], fill=COLORS['robe_lt'])
    # 衣襟叠层（中间深色条 + 边深色条）
    draw.polygon([(cx - S(18), robe_top_y + S(5)),
                   (cx, robe_top_y + S(12)),
                   (cx + S(2), robe_top_y + S(5)),
                   (cx + S(14), robe_bot_y - S(4)),
                   (cx + S(8), robe_bot_y),
                   (cx - S(12), robe_bot_y)], fill=COLORS['robe_dk'])

    # 腰带
    belt_y = int(robe_top_y + (robe_bot_y - robe_top_y) * 0.42)
    draw.rectangle([cx - S(40), belt_y - S(6), cx + S(40), belt_y + S(6)], fill=COLORS['sword_hilt'])
    draw.rectangle([cx - S(4), belt_y - S(8), cx + S(4), belt_y + S(14)], fill=COLORS['gold'])

    # 左臂（执剑后手）- 三角袖
    arm1 = [(cx - S(30), robe_top_y + S(15)),
             (cx - S(48), belt_y + S(8)),
             (cx - S(40), belt_y + S(28)),
             (cx - S(28), belt_y + S(20)),
             (cx - S(22), robe_top_y + S(35)),
             (cx - S(20), robe_top_y + S(20))]
    draw.polygon(arm1, fill=COLORS['robe_lt'])
    # 右手（剑把上方 - 浅肤色椭圆）
    draw.ellipse([cx - S(55), belt_y + S(2), cx - S(35), belt_y + S(22)], fill=COLORS['skin'])

    # 剑（右上斜向左下）：细线条
    sword_start = (cx - S(45), belt_y + S(12))
    sword_end = (cx + S(135), int(h * 0.78))
    # 剑身（白色细带）
    draw.line([sword_start, sword_end], fill=COLORS['sword'], width=S(4))
    # 剑身中高光线
    dx = sword_end[0] - sword_start[0]
    dy = sword_end[1] - sword_start[1]
    import math
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    mid = ((sword_start[0] + sword_end[0]) // 2 + int(px * S(2)),
            (sword_start[1] + sword_end[1]) // 2 + int(py * S(2)))
    draw.line([mid, ((mid[0] - int(ux * S(40)), mid[1] - int(uy * S(40))))],
              fill=COLORS['moon'], width=S(1))

    # 剑柄（深褐色，接在剑起点的反方向）
    hilt_end = (sword_start[0] - int(ux * S(18)), sword_start[1] - int(uy * S(18)))
    draw.line([sword_start, hilt_end], fill=COLORS['sword_hilt'], width=S(8))
    # 剑格（剑起点处金黄圆点）
    draw.ellipse([sword_start[0] - S(4), sword_start[1] - S(4),
                   sword_start[0] + S(4), sword_start[1] + S(4)], fill=COLORS['gold'])
    # 剑穗（从剑柄端延伸的红色曲线）
    tassel_end = (hilt_end[0] - int(ux * S(10) + px * S(6)),
                   hilt_end[1] - int(uy * S(10) + py * S(6)))
    draw.line([hilt_end, tassel_end], fill=COLORS['red'], width=S(3))

    # 右臂（自然下垂飘袖）
    sleeve_pts = [(cx + S(22), robe_top_y + S(15)),
                   (cx + S(55), belt_y - S(2)),
                   (cx + S(70), belt_y + S(40)),
                   (cx + S(58), int(h * 0.78)),
                   (cx + S(42), int(h * 0.80)),
                   (cx + S(38), belt_y + S(28)),
                   (cx + S(16), robe_top_y + S(35))]
    draw.polygon(sleeve_pts, fill=COLORS['robe_lt'])

    # 飘带（两条从腰侧延伸）
    draw.line([(cx + S(45), belt_y + S(8)),
                (cx + S(70), belt_y + S(45))],
               fill=COLORS['bamboo'], width=S(3))
    draw.line([(cx + S(50), belt_y + S(14)),
                (cx + S(78), belt_y + S(60))],
               fill=COLORS['bamboo'], width=S(2))

    # 脚下踩石（黑色椭圆）
    draw.ellipse([cx - S(75), int(h * 0.80) - S(6),
                   cx + S(75), int(h * 0.80) + S(16)],
                  fill=COLORS['rock'])


def draw_bamboo(img: Image.Image, size: int):
    """前景斜竹叶 + 右上远景竹叶"""
    draw = ImageDraw.Draw(img)
    w, h = size, size
    # 左下前景（3 条主茎）
    stems = [
        (int(w * 0.10), int(h * 0.78), int(w * 0.38), int(h * 0.72)),
        (int(w * 0.14), int(h * 0.86), int(w * 0.42), int(h * 0.80)),
        (int(w * 0.08), int(h * 0.92), int(w * 0.34), int(h * 0.86)),
    ]
    for x1, y1, x2, y2 in stems:
        draw.line([(x1, y1), (x2, y2)], fill=COLORS['bamboo'], width=2)
        # 叶片（小三角）
        for t in [0.25, 0.5, 0.75]:
            mx = x1 + (x2 - x1) * t
            my = y1 + (y2 - y1) * t
            draw.polygon([(mx, my),
                           (mx + 12, my - 4),
                           (mx + 14, my + 2)], fill=COLORS['bamboo'])

    # 右上远景（稀一点）
    stems2 = [
        (int(w * 0.82), int(h * 0.30), int(w * 0.95), int(h * 0.36)),
        (int(w * 0.84), int(h * 0.36), int(w * 0.96), int(h * 0.42)),
    ]
    for x1, y1, x2, y2 in stems2:
        draw.line([(x1, y1), (x2, y2)], fill=COLORS['bamboo'], width=1)


def draw_seal(img: Image.Image, size: int):
    """朱砂印「日」（右下落款）"""
    draw = ImageDraw.Draw(img)
    w, h = size, size
    sx, sy = int(w * 0.88), int(h * 0.92)
    sr = int(w * 0.06)
    # 半透明红方块（用 RGB 模拟：实际不透明以便 icon 清晰）
    draw.rectangle([sx - sr, sy - sr, sx + sr, sy + sr], fill=COLORS['red'])
    # 「日」字（用 line 笔画勾勒）
    cx = sx
    cy = sy - sr // 4
    arm = sr // 2
    draw.line([(cx - arm, cy - arm), (cx + arm, cy - arm)], fill=COLORS['moon_glow'], width=1)
    draw.line([(cx - arm, cy + arm), (cx + arm, cy + arm)], fill=COLORS['moon_glow'], width=1)
    draw.line([(cx - arm, cy - arm), (cx - arm, cy + arm)], fill=COLORS['moon_glow'], width=1)
    draw.line([(cx + arm, cy - arm), (cx + arm, cy + arm)], fill=COLORS['moon_glow'], width=1)
    draw.line([(cx - arm, cy), (cx + arm, cy)], fill=COLORS['moon_glow'], width=1)


def render(size: int, out_path: Path):
    img = Image.new('RGB', (size, size), COLORS['bg_top'])
    draw_bg(img, size)
    draw_moon(img, size)
    draw_swordsman(img, size)
    draw_bamboo(img, size)
    draw_seal(img, size)
    img.save(out_path, 'PNG', optimize=True)
    print(f'  {out_path.name}  {size}x{size}  ({out_path.stat().st_size} B)')


if __name__ == '__main__':
    targets = [
        (32,  OUT / 'icon.png'),       # 托盘 / 小图标
        (256, OUT / 'icon-256.png'),   # electron-builder win.icon
        (512, OUT / 'icon-512.png'),   # 备份高清
        (128, OUT / 'icon-128.png'),   # 备份中
    ]
    print(f'输出目录: {OUT}')
    for sz, p in targets:
        render(sz, p)
    print('OK')
