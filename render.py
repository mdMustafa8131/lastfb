import random
from pathlib import Path
import news_render

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import config

W, H = 1080, 1350
M = 56
GAP = 16
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}

FONT_DIR = config.BASE_DIR / "assets" / "fonts"

_CANDIDATES = {
    "bold": ["NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf"],
    "body": ["NotoSans-Regular.ttf", "DejaVuSans.ttf", "arial.ttf"],
    "bn": ["NotoSansBengali-Regular.ttf", "NotoSansBengali-Bold.ttf",
           "nirmala.ttf", "vrinda.ttf"],
    "hi": ["NotoSansDevanagari-Regular.ttf", "NotoSansDevanagari-Bold.ttf",
           "nirmala.ttf", "mangal.ttf"],
}

_SYSTEM_DIRS = [FONT_DIR, Path("/usr/share/fonts"), Path("C:/Windows/Fonts")]


def _font_path(key):
    for name in _CANDIDATES.get(key, []):
        for d in _SYSTEM_DIRS:
            p = d / name
            if p.exists():
                return str(p)
    return None


_FONTS = {k: _font_path(k) for k in _CANDIDATES}


def _font(key, size):
    p = _FONTS.get(key)
    if p:
        return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def _wrap(draw, text, font, max_w):
    words = str(text).split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _fit(draw, text, key, max_w, max_h, max_size, min_size=16, gap=1.22):
    size = max_size
    while size > min_size:
        font = _font(key, size)
        lines = _wrap(draw, text, font, max_w)
        if len(lines) * size * gap <= max_h:
            return font, lines, size
        size -= 2
    font = _font(key, min_size)
    return font, _wrap(draw, text, font, max_w), min_size


def _place(base, box, text, key, color, max_size, min_size, gap, align, valign, shadow):
    if not text:
        return base
    bw, bh = box[2] - box[0], box[3] - box[1]
    if bw <= 4 or bh <= 4:
        return base
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font, lines, size = _fit(d, text, key, bw, bh, max_size, min_size, gap)
    total_h = len(lines) * size * gap
    if valign == "bottom":
        y = box[3] - total_h
    elif valign == "top":
        y = box[1]
    else:
        y = box[1] + max(0, (bh - total_h) / 2)
    for ln in lines:
        w = d.textlength(ln, font=font)
        x = box[0] if align == "left" else box[0] + (bw - w) / 2
        if shadow:
            d.text((x + 2, y + 3), ln, font=font, fill=(0, 0, 0, 165))
        d.text((x, y), ln, font=font, fill=color)
        y += size * gap
    return Image.alpha_composite(base, layer)


def _block(base, box, text, key, color, max_size, min_size=16, gap=1.22):
    return _place(base, box, text, key, color, max_size, min_size, gap, "left", "top", False)


def _hline(base, y, alpha=190, x1=None, x2=None, color=(190, 196, 214)):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.line([(x1 if x1 else M + 34, y), (x2 if x2 else W - M - 34, y)],
           fill=color + (alpha,), width=1)
    layer = layer.filter(ImageFilter.GaussianBlur(1.1))
    return Image.alpha_composite(base, layer)


def _blur_panel(base, box, radius=34, strength=20, darken=120, color=(0, 0, 0)):
    box = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
    if box[2] - box[0] < 8 or box[3] - box[1] < 8:
        return base
    region = base.crop(box).filter(ImageFilter.GaussianBlur(strength)).convert("RGBA")
    region = Image.alpha_composite(region, Image.new("RGBA", region.size, color + (darken,)))
    mask = Image.new("L", region.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, region.size[0] - 1, region.size[1] - 1), radius=radius, fill=255)
    base.paste(region, box[:2], mask)
    return base


def _panel(base, box, fill, radius=26, outline=None, width=3):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    return Image.alpha_composite(base, layer)


def _detect_key(text):
    for ch in str(text or ""):
        o = ord(ch)
        if 0x0980 <= o <= 0x09FF:
            return "bn"
        if 0x0900 <= o <= 0x097F:
            return "hi"
    return "body"


def _hex_rgb(h, fallback=(8, 84, 48)):
    try:
        h = str(h).lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


_PALETTES = {
    "english": [((236, 238, 246), (208, 212, 228)),
                ((232, 240, 232), (198, 216, 202)),
                ((246, 236, 240), (220, 200, 210)),
                ((236, 236, 248), (206, 206, 232))],
    "islam": [((226, 236, 228), (196, 214, 200)),
              ((232, 238, 232), (200, 212, 202)),
              ((224, 234, 232), (194, 210, 206)),
              ((230, 234, 226), (198, 208, 196))],
}

_DEFAULT_BG = {}


def _gradient(section, idx=0):
    key = f"{section}{idx}"
    if key not in _DEFAULT_BG:
        pal = _PALETTES[section]
        top, bottom = pal[idx % len(pal)]
        img = Image.new("RGB", (W, H), top)
        d = ImageDraw.Draw(img)
        for y in range(H):
            t = y / H
            d.line([(0, y), (W, y)],
                   fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
        _DEFAULT_BG[key] = img
    return _DEFAULT_BG[key].copy()


def _dark_bg(section):
    key = section + "dark"
    if key not in _DEFAULT_BG:
        top, bottom = ((14, 16, 30), (46, 40, 72)) if section == "english" else ((10, 24, 20), (26, 52, 40))
        img = Image.new("RGB", (W, H), top)
        d = ImageDraw.Draw(img)
        for y in range(H):
            t = y / H
            d.line([(0, y), (W, y)],
                   fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
        _DEFAULT_BG[key] = img
    return _DEFAULT_BG[key].copy()


def _bg(section, mode="image", category=None):
    if mode.startswith("t"):
        idx = int(mode[1]) - 1
        if mode == "t2":
            return _dark_bg(section)
        return _gradient(section, idx)
    if mode == "fresh":
        return _gradient(section, 0)
    folders = []
    if category:
        folders.append(config.BG_DIR / section / category)
    folders.append(config.BG_DIR / section)
    for folder in folders:
        files = [f for f in folder.iterdir() if f.suffix.lower() in IMG_EXT] if folder.exists() else []
        if files:
            try:
                img = Image.open(random.choice(files)).convert("RGB")
                return ImageOps.fit(img, (W, H), Image.LANCZOS)
            except Exception:
                pass
    return _gradient(section, 0)


def _overlay(base, alpha, color=(0, 0, 0)):
    layer = Image.new("RGBA", base.size, color + (alpha,))
    return Image.alpha_composite(base, layer)


def _header(base, label, accent):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((M, M, M + 210, M + 52), radius=26, fill=accent)
    d.text((M + 22, M + 13), label, font=_font("bold", 24), fill=(255, 255, 255))
    return Image.alpha_composite(base, layer)


def _brand(img, name, logo_path, accent):
    label = ("@" + name) if name else ""
    probe = ImageDraw.Draw(img)
    font = _font("bold", 24)
    box_w = probe.textlength(label, font=font) if label else 0

    logo = None
    if logo_path and Path(logo_path).exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((44, 44), Image.LANCZOS)
        except Exception:
            logo = None

    pad = 14
    total_w = int(box_w) + (logo.width + 10 if logo else 0) + pad * 2
    if total_w < 40:
        return img

    h = 54
    x2, y2 = W - M, H - M
    x1, y1 = x2 - total_w, y2 - h

    img = _panel(img, (x1, y1, x2, y2), (255, 255, 255, 232), radius=27)
    cx = x1 + pad
    if logo:
        img.paste(logo, (int(cx), int(y1 + (h - logo.height) / 2)), logo)
        cx += logo.width + 10
    if label:
        img = _block(img, (int(cx), y1 + 14, x2 - pad, y2 - 14), label,
                     "bold", accent, 24, 14, gap=1.0)
    return img


TAGS = {"hindi": "HI", "bangla": "BN", "hinglish": "HG", "english": "EN"}
LANG_FONT = {"hindi": "hi", "bangla": "bn", "hinglish": "body", "english": "body"}
TAG_COLOR = {"hindi": (222, 68, 68), "bangla": (24, 146, 96),
             "hinglish": (128, 84, 214), "english": (52, 104, 216)}
BAR_COLORS = [(18, 168, 100), (232, 88, 128), (78, 108, 232),
              (232, 148, 32), (16, 152, 152), (176, 84, 208)]


def _trans_list(item, langs):
    return [l for l in (langs or []) if item.get(l)]


def _group(base, box, entries, max_size, min_size=16, gap=1.18, sep=True,
           shadow=True, blur=False, valign="center", line_color=(190, 196, 214)):
    entries = [(t, k, c) for t, k, c in entries if t]
    if not entries:
        return base, box[1]
    bw, bh = box[2] - box[0], box[3] - box[1]
    if bw <= 8 or bh <= 8:
        return base, box[1]

    probe = ImageDraw.Draw(base)
    size = max_size
    sep_h = 34
    while True:
        layout = []
        for t, k, c in entries:
            f = _font(k, size)
            lines = _wrap(probe, t, f, bw)
            layout.append((lines, f, c, len(lines) * size * gap))
        total = sum(x[3] for x in layout) + (sep_h * (len(entries) - 1) if sep else 0)
        if total <= bh or size <= min_size:
            break
        size -= 2

    if valign == "top":
        y = box[1]
    else:
        y = box[1] + max(0, (bh - total) / 2)

    if blur:
        base = _blur_panel(base, (box[0] - 20, y - 30, box[2] + 20, y + total + 30))

    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, (lines, f, c, h) in enumerate(layout):
        if sep and i > 0:
            base = Image.alpha_composite(base, layer)
            base = _hline(base, y + 8, 170, box[0], box[2], line_color)
            layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            y += sep_h
        for ln in lines:
            w = d.textlength(ln, font=f)
            x = box[0] + (bw - w) / 2
            if shadow:
                d.text((x + 2, y + 3), ln, font=f, fill=(0, 0, 0, 165))
            d.text((x, y), ln, font=f, fill=c)
            y += size * gap
    return Image.alpha_composite(base, layer), y


STYLE = {
    "image": dict(ink=(18, 22, 40), soft=(70, 78, 104), panel=(255, 255, 255, 246),
                  bar=True, border=False, dark=False, band=False, num=False, blur=False, ov=90),
    "fresh": dict(ink=(255, 255, 255), soft=(226, 232, 255), panel=None,
                  bar=False, border=False, dark=False, band=False, num=False, blur=True, ov=0),
    "t1": dict(ink=(20, 24, 42), soft=(72, 80, 108), panel=(255, 255, 255, 250),
               bar=False, border=True, dark=False, band=False, num=True, blur=False, ov=70),
    "t2": dict(ink=(240, 243, 255), soft=(176, 184, 208), panel=(12, 16, 30, 210),
               bar=True, border=False, dark=True, band=False, num=False, blur=False, ov=120),
    "t3": dict(ink=(255, 255, 255), soft=(58, 64, 84), panel=(255, 255, 255, 248),
               bar=False, border=False, dark=False, band=True, num=False, blur=False, ov=60),
    "t4": dict(ink=(22, 26, 44), soft=(74, 82, 110), panel=(255, 255, 255, 40),
               bar=False, border=True, dark=False, band=False, num=False, blur=False, ov=40),
}


def render_english(items, show_question, langs=None, mode="image"):
    st = STYLE.get(mode, STYLE["image"])
    accent = (18, 168, 100)
    content = list(items[:-1]) if show_question else list(items)
    question = items[-1] if show_question else None
    total = len(content) + (1 if question else 0)
    if total == 0:
        return _bg("english", mode).convert("RGBA")

    img = _overlay(_bg("english", mode).convert("RGBA"), st["ov"])
    img = _header(img, "ENGLISH", accent)

    top = M + 78
    avail = (H - M) - top
    bh = (avail - GAP * (total - 1)) / total
    y = top
    idx = 0

    for it in content:
        trans = _trans_list(it, langs)
        box = (M, y, W - M, y + bh)

        if st["blur"]:
            img = _blur_panel(img, (M + 4, y + 4, W - M - 4, y + bh - 4))
        if st["panel"]:
            img = _panel(img, box, st["panel"],
                         outline=BAR_COLORS[idx % len(BAR_COLORS)] if st["border"] else None,
                         width=3 if st["border"] else 0)
        if st["bar"]:
            img = _panel(img, (M, y, M + 12, y + bh), BAR_COLORS[idx % len(BAR_COLORS)], radius=6)

        x1, x2 = M + 34, W - M - 30
        if st["num"]:
            img = _block(img, (x1, y + 12, x1 + 70, y + 84), str(idx + 1), "bold",
                         BAR_COLORS[idx % len(BAR_COLORS)], 54, 24, gap=1.0)

        if st["band"]:
            img = _panel(img, (M, y, W - M, y + bh * 0.42), BAR_COLORS[idx % len(BAR_COLORS)],
                         radius=24)
            img = _block(img, (M + 30, y + 22, W - M - 30, y + bh * 0.42 - 18),
                         it["english"], _detect_key(it["english"]), (255, 255, 255),
                         int(min(90, max(28, bh * 0.20))), 18, gap=1.16)
            ty = y + bh * 0.42 + 16
        else:
            head_h = (bh - 44) * (0.40 if trans else 0.60)
            ox = x1 + (80 if st["num"] else 0)
            img = _block(img, (ox, y + 20, x2, y + 20 + head_h),
                         it["english"], _detect_key(it["english"]), st["ink"],
                         int(min(120, max(30, bh * 0.24))), 18, gap=1.16)
            ty = y + 20 + head_h + 14

        rest = (y + bh - 22) - ty
        if trans and rest > 40:
            step = rest / len(trans)
            for key in trans:
                img = _hline(img, ty - 8, 150, x1, x2,
                             (255, 255, 255) if st["dark"] or st["band"] else (190, 196, 214))
                img = _block(img, (x1, ty, x1 + 52, ty + 28), TAGS.get(key, "TR"),
                             "bold", TAG_COLOR.get(key, st["soft"]), 19, 14, gap=1.0)
                img = _block(img, (x1 + 62, ty, x2, ty + step - 8), it[key],
                             LANG_FONT.get(key, "body"), st["soft"],
                             int(min(44, max(20, bh * 0.10))), 16, gap=1.1)
                ty += step
        idx += 1
        y += bh + GAP

    if question:
        qh = H - M - y
        if st["blur"]:
            img = _blur_panel(img, (M + 4, y + 4, W - M - 4, H - M - 4))
        img = _panel(img, (M, y, W - M, H - M), BAR_COLORS[idx % len(BAR_COLORS)])
        img = _place(img, (M + 34, y + 22, W - M - 30, H - M - 56),
                     question["english"], _detect_key(question["english"]),
                     (255, 255, 255), 60, 24, 1.16, "center", "center", False)
        img = _hline(img, H - M - 52, 120, M + 34, W - M - 30, (255, 255, 255))
        img = _block(img, (M + 34, H - M - 46, W - M - 30, H - M - 14),
                     "Comment the meaning below \u2193", "bold", (255, 255, 255), 24, 15, gap=1.1)
    return img


IS_ACCENT = {"image": (15, 122, 74), "fresh": (15, 122, 74), "t1": (26, 108, 72),
             "t2": (212, 175, 55), "t3": (15, 122, 74), "t4": (120, 96, 32)}


def render_islam(item, langs=None, mode="image", source_color="#085430", category=None):
    accent = IS_ACCENT.get(mode, (15, 122, 74))
    dark = mode == "t2"
    ink = (255, 255, 255)
    soft = (214, 224, 232) if dark else (232, 238, 255)

    img = _overlay(_bg("islam", mode, category).convert("RGBA"),
                   135 if mode in ("image", "t2") else 70)
    img = _header(img, "HADITH", accent)

    trans = _trans_list(item, langs)
    top = M + 82
    bottom = H - M - 56

    entries = [(item["hadith_roman"], _detect_key(item["hadith_roman"]), ink)]
    entries += [(item[t], _detect_key(item[t]), soft) for t in trans]

    img, _ = _group(img, (M + 24, top, W - M - 24, bottom), entries, 72, 26,
                    sep=bool(trans), shadow=True, blur=mode == "fresh",
                    valign="center",
                    line_color=(255, 255, 255) if dark else (200, 208, 220))

    src = "Source: " + item["source"]
    probe = ImageDraw.Draw(img)
    font = _font("bold", 22)
    tw = probe.textlength(src, font=font)
    cy = H - M - 32
    box = (W / 2 - tw / 2 - 18, cy - 20, W / 2 + tw / 2 + 18, cy + 20)
    img = _blur_panel(img, box, radius=16, strength=14, darken=215,
                      color=_hex_rgb(source_color))
    img = _place(img, (box[0], box[1], box[2], box[3]), src, "bold",
                 (255, 255, 255), 22, 15, 1.1, "center", "center", False)
    return img

# ---------- gold frame design (islam only) ----------
_G_FONTS = {
    "bold": ["NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf"],
    "dev": ["NotoSansDevanagari-Bold.ttf", "NotoSansDevanagari-Regular.ttf",
            "Nirmala.ttf", "mangal.ttf"],
    "bn": ["NotoSansBengali-Bold.ttf", "NotoSansBengali-Regular.ttf",
           "Nirmala.ttf", "vrinda.ttf"],
}
_G_ALIAS = {"hi": "dev", "hindi": "dev", "devanagari": "dev", "dev": "dev",
            "bn": "bn", "bangla": "bn", "bengali": "bn"}


def _g_key(t):
    for ch in str(t):
        o = ord(ch)
        if 0x0900 <= o <= 0x097F:
            return "dev"
        if 0x0980 <= o <= 0x09FF:
            return "bn"
    return "bold"


def _g_font(k, s):
    k = _G_ALIAS.get(k, k)
    p = _G_FP.get(k) or _G_FP.get("bold")
    return ImageFont.truetype(p, s) if p else ImageFont.load_default(s)

_G_DIRS = [config.BASE_DIR / "assets" / "fonts", Path("/usr/share/fonts"),
           Path("C:/Windows/Fonts")]
GOLD = (212, 175, 55)


def _g_path(k):
    for n in _G_FONTS.get(k, []):
        for d in _G_DIRS:
            p = d / n
            if p.exists():
                return str(p)
    return None


_G_FP = {k: _g_path(k) for k in _G_FONTS}


def _g_font(k, s):
    p = _G_FP.get(k) or _G_FP.get("bold")
    return ImageFont.truetype(p, s) if p else ImageFont.load_default(s)


def _g_wrap(d, t, f, w):
    words = str(t).split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for x in words[1:]:
        tr = f"{cur} {x}"
        if d.textlength(tr, font=f) <= w:
            cur = tr
        else:
            lines.append(cur)
            cur = x
    lines.append(cur)
    return lines


def _g_text(img, box, txt, key, color, size, gap=1.25):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x1, y1, x2, y2 = box
    w = max(60, x2 - x1)
    f = _g_font(key, size)
    lines = _g_wrap(d, txt, f, w)
    while lines and len(lines) * (size + gap) > (y2 - y1) and size > 22:
        size -= 2
        f = _g_font(key, size)
        lines = _g_wrap(d, txt, f, w)
    total = len(lines) * (size + gap)
    y = y1 + max(0, ((y2 - y1) - total) // 2)
    for ln in lines:
        lw = d.textlength(ln, font=f)
        d.text((x1 + (w - lw) / 2, y), ln, font=f, fill=color + (255,))
        y += size + gap
    return Image.alpha_composite(img, layer)

# ---------- clean card design (english only) ----------
E_BG = (233, 233, 242)
E_INK = (18, 18, 22)
E_TAGS = [(34, 164, 93), (242, 84, 125), (59, 107, 245)]
E_TAGMAP = {"hindi": "HI", "bangla": "BN", "hinglish": "HG"}


def _e_left(img, box, txt, key, color, size, gap=1.25, tag=None, tag_color=None):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x1, y1, x2, y2 = box
    x = x1
    if tag:
        ft = _g_font("bold", int(size * 0.56))
        d.text((x, y1 + 6), tag, font=ft, fill=(tag_color or color) + (255,))
        x = x1 + d.textlength(tag, font=ft) + 20
    w = max(60, x2 - x)
    f = _g_font(key, size)
    lines = _g_wrap(d, txt, f, w)
    while lines and len(lines) * (size + gap) > (y2 - y1) and size > 16:
        size -= 1
        f = _g_font(key, size)
        lines = _g_wrap(d, txt, f, w)
    y = y1
    for ln in lines:
        d.text((x, y), ln, font=f, fill=color + (255,))
        y += size + gap
    return Image.alpha_composite(img, layer)


def render_english_clean(items, langs=None, brand_name=None):
    img = Image.new("RGBA", (W, H), E_BG + (255,))
    d = ImageDraw.Draw(img)

    fp = _g_font("bold", 30)
    tw = d.textlength("ENGLISH", font=fp)
    d.rounded_rectangle([48, 38, 48 + tw + 56, 38 + 58], radius=29, fill=(34, 164, 93, 255))
    d.text((76, 52), "ENGLISH", font=fp, fill=(255, 255, 255, 255))

    content = list(items)[:3]
    n = max(1, len(content))
    top = 130
    bottom = H - 92
    gap = 14
    ch = int((bottom - top - gap * (n - 1)) / n)
    rows = [l for l in (langs or []) if content and content[0].get(l)]

    for i, it in enumerate(content):
        y = top + i * (ch + gap)
        col = E_TAGS[i % 3]
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([48, y, W - 48, y + ch], radius=20, fill=(255, 255, 255, 255))
        d.rounded_rectangle([48, y, 58, y + ch], radius=5, fill=col + (255,))

        sbox_h = int(ch * 0.44)
        img = _e_left(img, (78, y + 20, W - 78, y + 20 + sbox_h),
                      it.get("english", ""), "bold", E_INK, 52, 1.22)

        yy = y + 24 + sbox_h
        d = ImageDraw.Draw(img)
        d.line([(78, yy), (W - 78, yy)], fill=(226, 226, 234, 255), width=2)
        yy += 18

        use = [k for k in rows if it.get(k)]
        rh = int((ch - (yy - y) - 22) / max(1, len(use)))
        for k in use:
            img = _e_left(img, (78, yy, W - 78, yy + rh), it[k], _g_key(it[k]),
                          (40, 40, 48), 34, 1.2, tag=E_TAGMAP.get(k, k[:2].upper()),
                          tag_color=col)
            yy += rh + 6
            d = ImageDraw.Draw(img)
            d.line([(78, yy - 3), (W - 78, yy - 3)], fill=(232, 232, 240, 255), width=1)

    if brand_name:
        fb = _g_font("bold", 28)
        txt = "@" + str(brand_name)
        tw2 = ImageDraw.Draw(img).textlength(txt, font=fb)
        ImageDraw.Draw(img).text((W - 48 - tw2, H - 62), txt, font=fb,
                                 fill=(34, 164, 93, 255))
    return img

def render_islam_gold(item, langs=None, category=None):
    img = _overlay(_bg("islam", "image", category).convert("RGBA"), 120)
    pad = 26

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        [pad, pad, W - pad, H - pad], radius=18, outline=GOLD + (255,), width=3)
    img = Image.alpha_composite(img, layer)

    img = _g_text(img, (pad + 20, pad + 24, W - pad - 20, pad + 70),
                  "HADEEZ-E-NABAWI", "bold", GOLD, 30, 1.0)

    d = ImageDraw.Draw(img)
    trans = [item[k] for k in (langs or []) if item.get(k)]
    foot_h = 70
    top = pad + 96
    bottom = H - pad - foot_h - 6
    avail_w = W - 2 * (pad + 34)
    hkey = _g_key(item["hadith_roman"])
    block = bottom - top

    size = 54
    hlines, th = [], 0
    while size > 20:
        f = _g_font(hkey, size)
        hlines = _g_wrap(d, item["hadith_roman"], f, avail_w)
        hh = len(hlines) * (size * 1.18)
        th = 0
        ok = hh <= block * 0.55
        if ok and trans:
            for t in trans:
                f2 = _g_font(_g_key(t), size)
                th += len(_g_wrap(d, t, f2, avail_w)) * (size * 1.18)
            ok = hh + th + 110 <= block
        if ok:
            break
        size -= 2

    hh = int(len(hlines) * (size * 1.18))
    gap_h = int(size * 0.18)
    group = hh + 46 + int(th) + (26 if trans else 0) + (58 if item.get("source") else 0)
    y = top + max(0, (block - group) // 2)

    img = _g_text(img, (pad + 34, y, W - pad - 34, y + hh),
                  item["hadith_roman"], hkey, (255, 255, 255), size, gap_h)
    y += hh + 18

    d = ImageDraw.Draw(img)
    d.rounded_rectangle([W / 2 - 60, y, W / 2 + 60, y + 3], radius=2, fill=GOLD + (255,))
    y += 28

    if trans:
        for t in trans:
            th1 = int(len(_g_wrap(ImageDraw.Draw(img), t, _g_font(_g_key(t), size),
                                  avail_w)) * (size * 1.18))
            img = _g_text(img, (pad + 34, y, W - pad - 34, y + th1), t,
                          _g_key(t), (240, 226, 190), size, gap_h)
            y += th1 + 6
        y += 10
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([W / 2 - 60, y, W / 2 + 60, y + 3], radius=2,
                            fill=GOLD + (255,))
        y += 20

    if item.get("source"):
        src = "Source: " + item["source"]
        f = _g_font("bold", 28)
        tw = ImageDraw.Draw(img).textlength(src, font=f)
        x1 = (W - tw) / 2
        pill = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(pill).rounded_rectangle(
            [x1 - 22, y - 6, x1 + tw + 22, y + 42], radius=14, fill=(12, 74, 44, 235))
        img = Image.alpha_composite(img, pill)
        img = _g_text(img, (pad + 40, y, W - pad - 40, y + 46),
                      src, "bold", (255, 255, 255), 28, 1.1)

    img = _g_text(img, (pad + 20, H - pad - foot_h, W - pad - 20, H - pad - 14),
                  "Follow to get daily new hadiths", "bold", (240, 240, 240), 22, 1.1)
    return img
def render(section, items, show_question=True, langs=None, mode="image",
           source_color="#085430", brand_name=None, logo_path=None, category=None):
    if section == "news":
        img = news_render.render(items[0], int(mode) if str(mode).isdigit() else 1)
        return img.convert("RGB") if img else None

    if section == "islam" and mode == "gold":
        return render_islam_gold(items[0], langs, category).convert("RGB")

    if section == "english" and mode == "e5":
        return render_english_clean(items, langs, brand_name).convert("RGB")

    if section == "english":
        img = render_english(items, show_question, langs, mode)
        accent = (18, 168, 100)
    else:
        img = render_islam(items[0], langs, mode, source_color, category)
        accent = IS_ACCENT.get(mode, (15, 122, 74))

    if brand_name or logo_path:
        img = _brand(img, brand_name, logo_path, accent)
    return img.convert("RGB")