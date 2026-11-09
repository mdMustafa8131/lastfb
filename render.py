import random
from pathlib import Path
import news_render
import httpx

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import config

W, H = 1080, 1350
M = 56
GAP = 16
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}

FONT_DIR = config.BASE_DIR / "assets" / "fonts"

_CANDIDATES = {
    "bold": ["NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf",
             "LiberationSans-Bold.ttf", "segoeuib.ttf"],
    "body": ["NotoSans-Regular.ttf", "DejaVuSans.ttf", "arial.ttf",
             "LiberationSans-Regular.ttf", "segoeui.ttf"],
    "bn": ["NotoSansBengali-Regular.ttf", "NotoSansBengali-Bold.ttf",
           "nirmala.ttf", "vrinda.ttf"],
    "hi": ["NotoSansDevanagari-Regular.ttf", "NotoSansDevanagari-Bold.ttf",
           "NotoSerifDevanagari-Regular.ttf", "nirmala.ttf", "mangal.ttf"],
}

_GLOBS = {
    "bn": ["*Bengali*.ttf"],
    "hi": ["*Devanagari*.ttf"],
    "body": ["*DejaVuSans*.ttf", "*LiberationSans-Regular*.ttf", "*NotoSans-Regular*.ttf"],
    "bold": ["*DejaVuSans*Bold*.ttf", "*LiberationSans-Bold*.ttf", "*NotoSans-Bold*.ttf"],
}

_SYSTEM_DIRS = [FONT_DIR, Path("/usr/share/fonts"), Path("C:/Windows/Fonts")]


def _font_path(key):
    for name in _CANDIDATES.get(key, []):
        for d in _SYSTEM_DIRS:
            p = d / name
            if p.exists():
                return str(p)
    for g in _GLOBS.get(key, []):
        for d in _SYSTEM_DIRS:
            if not d.exists():
                continue
            for p in sorted(d.rglob(g)):
                if p.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    return str(p)
    return None


_FONTS = {k: _font_path(k) for k in _CANDIDATES}


def _font(key, size):
    p = _FONTS.get(key) or _FONTS.get("body") or _FONTS.get("bold")
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


def _place(base, box, text, key, color, max_size, min_size, gap, align, valign,
           shadow, track=None, seg=None, lang=None):
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
        if track is not None and seg is not None:
            bb = d.textbbox((x, y), ln, font=font)
            track.setdefault(seg, []).append(
                {"x0": bb[0], "x1": bb[2], "y0": bb[1],
                 "y1": max(bb[3], y + size * 0.95),
                 "h": size, "k": lang or "english", "t": text, "yb": box[3]})
        if shadow:
            d.text((x + 2, y + 3), ln, font=font, fill=(0, 0, 0, 165))
        d.text((x, y), ln, font=font, fill=color)
        y += size * gap
    return Image.alpha_composite(base, layer)


def _block(base, box, text, key, color, max_size, min_size=16, gap=1.22,
           track=None, seg=None, lang=None):
    return _place(base, box, text, key, color, max_size, min_size, gap,
                  "left", "top", False, track, seg, lang)


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
    s = str(text or "")
    bn = sum(1 for c in s if 0x0980 <= ord(c) <= 0x09FF)
    hi = sum(1 for c in s if 0x0900 <= ord(c) <= 0x097F and c not in "।॥")
    if not bn and not hi:
        return "body"
    return "bn" if bn >= hi else "hi"


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
_CUR_CAT = ""


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


def _bg(section, *_a, **_k):
    cands = []
    if _CUR_CAT:
        cands.append(config.BG_DIR / section / _CUR_CAT)
    cands.append(config.BG_DIR / section)
    for folder in cands:
        files = [f for f in folder.iterdir()
                 if f.suffix.lower() in IMG_EXT] if folder.exists() else []
        if files:
            try:
                img = Image.open(random.choice(files)).convert("RGB")
                return ImageOps.fit(img, (W, H), Image.LANCZOS)
            except Exception:
                pass
    return _dark_bg(section)


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
    base = " ".join(str(item.get("hadith_roman") or "").split())
    hk = _detect_key(base)
    out = []
    for l in (langs or []):
        t = " ".join(str(item.get(l) or "").split())
        if not t or t == base:
            continue
        if _detect_key(t) == hk:
            continue
        out.append(l)
    return out


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


def render_english(items, show_question, langs=None, mode="image", plain=False,
                   boxes=None, seps=None, track=None):
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
    ord_i = 0

    for it in content:
        trans = [k for k in ("bangla", "hindi", "hinglish")
                 if k in (langs or []) and it.get(k)] or [
            k for k in ("bangla", "hindi", "hinglish") if it.get(k)]
        print("[tr]", len(trans), trans, (it.get("english") or "")[:25])
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
            if not plain:
                img = _block(img, (M + 30, y + 22, W - M - 30, y + bh * 0.42 - 18),
                             it["english"], _detect_key(it["english"]), (255, 255, 255),
                             int(min(90, max(28, bh * 0.20))), 18, gap=1.16,
                             track=track, seg=ord_i, lang="english")
                ord_i += 1
            ty = y + bh * 0.42 + 16
        else:
            head_h = (bh - 44) * (0.40 if trans else 0.60)
            ox = x1 + (80 if st["num"] else 0)
            if not plain:
                img = _block(img, (ox, y + 20, x2, y + 20 + head_h),
                             it["english"], _detect_key(it["english"]), st["ink"],
                             int(min(120, max(30, bh * 0.24))), 18, gap=1.16,
                             track=track, seg=ord_i, lang="english")
                ord_i += 1
            ty = y + 20 + head_h + 14

        rest = (y + bh - 22) - ty
        if trans and rest > 40:
            step = rest / len(trans)
            for key in trans:
                img = _hline(img, ty - 8, 150, x1, x2,
                             (255, 255, 255) if st["dark"] or st["band"] else (190, 196, 214))
                if not plain:
                    img = _block(img, (x1, ty, x1 + 52, ty + 28), TAGS.get(key, "TR"),
                                 "bold", TAG_COLOR.get(key, st["soft"]), 19, 14, gap=1.0)
                    img = _block(img, (x1 + 62, ty, x2, ty + step - 8), it[key],
                                 LANG_FONT.get(key, "body"), st["soft"],
                                 int(min(44, max(20, bh * 0.10))), 16, gap=1.1,
                                 track=track, seg=ord_i, lang=key)
                    ord_i += 1
                ty += step
        idx += 1
        y += bh + GAP

    if question:
        if st["blur"]:
            img = _blur_panel(img, (M + 4, y + 4, W - M - 4, H - M - 4))
        img = _panel(img, (M, y, W - M, H - M), BAR_COLORS[idx % len(BAR_COLORS)])
        if not plain:
            img = _place(img, (M + 34, y + 22, W - M - 30, H - M - 56),
                         question["english"], _detect_key(question["english"]),
                         (255, 255, 255), 60, 24, 1.16, "center", "center", False,
                         track=track, seg=ord_i, lang="english")
            ord_i += 1
        img = _hline(img, H - M - 52, 120, M + 34, W - M - 30, (255, 255, 255))
        if not plain:
            img = _block(img, (M + 34, H - M - 46, W - M - 30, H - M - 14),
                         "Comment the meaning below \u2193", "bold", (255, 255, 255),
                         24, 15, gap=1.1)
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
    "bold": ["NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf",
             "LiberationSans-Bold.ttf"],
    "dev": ["NotoSansDevanagari-Bold.ttf", "NotoSansDevanagari-Regular.ttf",
            "NotoSerifDevanagari-Regular.ttf", "Nirmala.ttf", "mangal.ttf"],
    "bn": ["NotoSansBengali-Bold.ttf", "NotoSansBengali-Regular.ttf",
           "Nirmala.ttf", "vrinda.ttf"],
}
_G_DIRS = [config.BASE_DIR / "assets" / "fonts", Path("/usr/share/fonts"),
           Path("C:/Windows/Fonts")]
GOLD = (212, 175, 55)

_G_ALIAS = {"hi": "dev", "devanagari": "dev", "dev": "dev", "hindi": "dev",
            "bn": "bn", "bangla": "bn", "bengali": "bn"}

_G_GLOBS = {
    "dev": ["*Devanagari*.ttf"],
    "bn": ["*Bengali*.ttf"],
    "bold": ["*DejaVuSans*Bold*.ttf", "*LiberationSans-Bold*.ttf"],
}


def _g_path(k):
    for n in _G_FONTS.get(k, []):
        for d in _G_DIRS:
            p = d / n
            if p.exists():
                return str(p)
    for g in _G_GLOBS.get(k, []):
        for d in _G_DIRS:
            if not d.exists():
                continue
            for p in sorted(d.rglob(g)):
                if p.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    return str(p)
    return None


_G_FP = {k: _g_path(k) for k in _G_FONTS}

from PIL import features as _features

_RAQM = _features.check("raqm")


def _g_key(t):
    for ch in str(t):
        if ch in "।॥":
            continue
        o = ord(ch)
        if 0x0900 <= o <= 0x097F:
            return "dev"
        if 0x0980 <= o <= 0x09FF:
            return "bn"
    return "bold"


def _g_font(k, s):
    k = _G_ALIAS.get(k, k)
    p = _G_FP.get(k) or _G_FP.get("bold")
    if not p:
        return ImageFont.load_default(s)
    if _RAQM:
        return ImageFont.truetype(p, s, layout_engine=ImageFont.Layout.RAQM)
    return ImageFont.truetype(p, s)


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


def _g_text(img, box, txt, key, color, size, gap=1.25, seg=None, track=None, lang=None):
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
        x = x1 + (w - lw) / 2
        if track is not None and seg is not None:
            bb = d.textbbox((x, y), ln, font=f)
            track.setdefault(seg, []).append(
                {"x0": bb[0], "x1": bb[2], "y0": bb[1],
                 "y1": max(bb[3], y + size * 0.95),
                 "h": size, "k": lang or "english", "t": txt, "yb": y2})
        d.text((x, y), ln, font=f, fill=color + (255,))
        y += size + gap
    return Image.alpha_composite(img, layer)


# ---------- clean card design (english only) ----------
E_BG = (233, 233, 242)
E_INK = (18, 18, 22)
E_TAGS = [(34, 164, 93), (242, 84, 125), (59, 107, 245)]
E_TAGMAP = {"hindi": "HI", "bangla": "BN", "hinglish": "HG"}


def _e_left(img, box, txt, key, color, size, gap=1.25, tag=None, tag_color=None,
            collect=None, lang=None, seg=None, track=None):
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
    step = int(size * 1.34)
    while lines and len(lines) * step > (y2 - y1) and size > 16:
        size -= 1
        f = _g_font(key, size)
        step = int(size * 1.34)
        lines = _g_wrap(d, txt, f, w)
    sp = d.textlength(" ", font=f)
    y = y1
    for ln in lines:
        bb = d.textbbox((x, y), ln, font=f) if ln else (x, y, x, y + size)
        if track is not None and seg is not None:
            track.setdefault(seg, []).append(
                {"x0": bb[0], "x1": bb[2], "y0": bb[1],
                 "y1": max(bb[3], y + size * 0.95),
                 "h": size, "k": lang or "english", "t": txt, "yb": y2})
        cx = x
        for word in ln.split():
            ww = d.textlength(word, font=f)
            d.text((cx, y), word, font=f, fill=color + (255,))
            if collect is not None:
                collect.append({"ls": x, "xe": cx + ww + sp,
                                "y": y + size * 0.34, "h": size * 0.58,
                                "k": lang or "english", "seg": seg})
            cx += ww + sp
        y += step
    return Image.alpha_composite(img, layer)


def render_english_clean(items, langs=None, brand_name=None, plain=False,
                         show_question=False, boxes=None, seps=None, track=None):
    img = Image.new("RGBA", (W, H), E_BG + (255,))
    d = ImageDraw.Draw(img)

    fp = _g_font("bold", 30)
    tw = d.textlength("ENGLISH", font=fp)
    d.rounded_rectangle([48, 38, 48 + tw + 56, 38 + 58], radius=29, fill=(34, 164, 93, 255))
    if not plain:
        d.text((76, 52), "ENGLISH", font=fp, fill=(255, 255, 255, 255))

    items = list(items)
    q = None
    if show_question and len(items) > 1:
        q = items[-1]
        items = items[:-1]
    content = items[:4]
    print("[q]", show_question, len(items), bool(q), len(content))
    n = max(1, len(content) + (1 if q else 0))
    top = 130
    bottom = H - 92
    gap = 14
    ch = int((bottom - top - gap * (n - 1)) / n)
    rows = list(langs or [])
    ord_i = 0

    for i, it in enumerate(content):
        sn = 0
        y = top + i * (ch + gap)
        col = E_TAGS[i % 3]
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([48, y, W - 48, y + ch], radius=20, fill=(255, 255, 255, 255))
        d.rounded_rectangle([48, y, 58, y + ch], radius=5, fill=col + (255,))
        if plain:
            continue

        sbox_h = int(ch * 0.44)
        img = _e_left(img, (78, y + 20, W - 78, y + 20 + sbox_h),
                      it.get("english", ""), "bold", E_INK, 52, 1.22,
                      collect=boxes, lang="english", seg=ord_i, track=track)
        ord_i += 1

        yy = y + 24 + sbox_h
        d = ImageDraw.Draw(img)
        d.line([(78, yy), (W - 78, yy)], fill=(226, 226, 234, 255), width=2)
        if seps is not None:
            seps.append({"y": yy, "k": "english", "n": 0,
                         "x1": 78, "x2": W - 78})
        yy += 18

        use = [k for k in ("bangla", "hindi", "hinglish") if k in rows and it.get(k)]
        rh = int((ch - (yy - y) - 22) / max(1, len(use)))
        for k in use:
            img = _e_left(img, (78, yy, W - 78, yy + rh), it[k], _g_key(it[k]),
                          (40, 40, 48), 34, 1.2, tag=E_TAGMAP.get(k, k[:2].upper()),
                          tag_color=col, collect=boxes, lang=k,
                          seg=ord_i, track=track)
            ord_i += 1
            yy += rh + 6
            d = ImageDraw.Draw(img)
            d.line([(78, yy - 3), (W - 78, yy - 3)], fill=(232, 232, 240, 255), width=1)
            sn += 1
            if seps is not None:
                seps.append({"y": yy - 3, "k": k, "n": sn,
                             "x1": 78, "x2": W - 78})

    if q:
        qy = top + len(content) * (ch + gap)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([48, qy, W - 48, bottom], radius=20, fill=(59, 107, 245, 255))
        if not plain:
            img = _e_left(img, (78, qy + 26, W - 78, bottom - 56),
                          q.get("english", ""), "bold", (255, 255, 255), 46, 1.3,
                          lang="english", seg=ord_i, track=track)
            ord_i += 1
            img = _block(img, (78, bottom - 50, W - 78, bottom - 18),
                         "Comment the meaning below \u2193", "bold", (255, 255, 255),
                         22, 14, gap=1.1)

    if plain:
        return img

    if brand_name:
        fb = _g_font("bold", 28)
        txt = "@" + str(brand_name)
        tw2 = ImageDraw.Draw(img).textlength(txt, font=fb)
        ImageDraw.Draw(img).text((W - 48 - tw2, H - 62), txt, font=fb, fill=(34, 164, 93, 255))
    return img


def render_english_clean_pair(items, langs=None, brand_name=None,
                              show_question=False, boxes=None, seps=None,
                              track=None):
    """(text wali, bina-text wali) — dono ek hi layout pe."""
    import uuid
    full = render_english_clean(items, langs, brand_name,
                                show_question=show_question,
                                boxes=boxes, seps=seps, track=track).convert("RGB")
    plain = render_english_clean(items, langs, brand_name, plain=True,
                                 show_question=show_question).convert("RGB")
    tag = uuid.uuid4().hex[:8]
    fp = config.VIDEO_DIR / f"pair_{tag}_full.jpg"
    pp = config.VIDEO_DIR / f"pair_{tag}_plain.jpg"
    full.save(fp, "JPEG", quality=92)
    plain.save(pp, "JPEG", quality=92)
    return fp, pp


def render_english_pair(items, show_question=True, langs=None, mode="image",
                        brand_name=None, boxes=None, seps=None, track=None):
    """bg_mode wale template pe (text wali, bina-text wali)."""
    import uuid
    full = render_english(items, show_question, langs, mode, plain=False,
                          boxes=boxes, seps=seps, track=track)
    if brand_name:
        full = _brand(full, brand_name, None, (18, 168, 100))
    plain = render_english(items, show_question, langs, mode, plain=True)
    tag = uuid.uuid4().hex[:8]
    fp = config.VIDEO_DIR / f"pair_{tag}_full.jpg"
    pp = config.VIDEO_DIR / f"pair_{tag}_plain.jpg"
    full.convert("RGB").save(fp, "JPEG", quality=92)
    plain.convert("RGB").save(pp, "JPEG", quality=92)
    return fp, pp


def render_islam_gold(item, langs=None, category=None, plain=False, bg=None, track=None):
    img = _overlay((bg or _bg("islam", "image", category)).convert("RGBA"), 120)
    pad = 26

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        [pad, pad, W - pad, H - pad], radius=18, outline=GOLD + (255,), width=3)
    img = Image.alpha_composite(img, layer)

    if plain:
        return img

    img = _g_text(img, (pad + 20, pad + 24, W - pad - 20, pad + 70),
                  "HADEEZ-E-NABAWI", "bold", GOLD, 30, 1.0)

    d = ImageDraw.Draw(img)
    hkey = _g_key(item["hadith_roman"])
    _base = " ".join(str(item["hadith_roman"]).split())
    trans = [item[k] for k in (langs or [])
             if item.get(k)
             and " ".join(str(item[k]).split()) != _base
             and _g_key(item[k]) != hkey]
    foot_h = 70
    top = pad + 96
    bottom = H - pad - foot_h - 6
    avail_w = W - 2 * (pad + 34)
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

    hlang = "bangla" if hkey == "bn" else ("hindi" if hkey == "dev" else "english")
    img = _g_text(img, (pad + 34, y, W - pad - 34, y + hh),
                  item["hadith_roman"], hkey, (255, 255, 255), size, gap_h,
                  seg=0, track=track, lang=hlang)
    y += hh + 18

    d = ImageDraw.Draw(img)
    d.rounded_rectangle([W / 2 - 60, y, W / 2 + 60, y + 3], radius=2, fill=GOLD + (255,))
    y += 28

    if trans:
        for ti, t in enumerate(trans, start=1):
            th1 = int(len(_g_wrap(ImageDraw.Draw(img), t, _g_font(_g_key(t), size),
                                  avail_w)) * (size * 1.18))
            img = _g_text(img, (pad + 34, y, W - pad - 34, y + th1), t,
                          _g_key(t), (240, 226, 190), size, gap_h,
                          seg=ti, track=track,
                          lang=("bangla" if _g_key(t) == "bn" else
                                "hindi" if _g_key(t) == "dev" else "english"))
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
                      src, "bold", (255, 255, 255), 28, 1.1,
                      seg=len(trans) + 1, track=track, lang="english")

    img = _g_text(img, (pad + 20, H - pad - foot_h, W - pad - 20, H - pad - 14),
                  "Follow to get daily new hadiths", "bold", (240, 240, 240), 22, 1.1)
    return img


def render_islam_gold_pair(item, langs=None, category=None, track=None):
    """(text wali image, bina-text wali image) — dono ek hi photo pe."""
    import uuid
    global _CUR_CAT
    _CUR_CAT = category
    bg = _bg("islam", "image", category)
    full = render_islam_gold(item, langs, category, bg=bg, track=track).convert("RGB")
    plain = render_islam_gold(item, langs, category, plain=True, bg=bg).convert("RGB")
    tag = uuid.uuid4().hex[:8]
    fp = config.VIDEO_DIR / f"pair_{tag}_full.jpg"
    pp = config.VIDEO_DIR / f"pair_{tag}_plain.jpg"
    full.save(fp, "JPEG", quality=92)
    plain.save(pp, "JPEG", quality=92)
    return fp, pp


def render(section, items, show_question=True, langs=None, mode="image",
           source_color="#085430", brand_name=None, logo_path=None, category=None):
    global _CUR_CAT
    _CUR_CAT = str(category or "").strip() or (
        str((items[0].get("category") or "")).strip() if items else "")
    if section == "news":
        img = news_render.render(items[0], int(mode) if str(mode).isdigit() else 1)
        return img.convert("RGB") if img else None

    if section == "islam" and mode == "gold":
        return render_islam_gold(items[0], langs, category).convert("RGB")

    if section == "english" and mode == "e5":
        return render_english_clean(items, langs, brand_name,
                                    show_question=show_question).convert("RGB")

    if section == "english":
        img = render_english(items, show_question, langs, mode)
        accent = (18, 168, 100)
    else:
        img = render_islam(items[0], langs, mode, source_color, category)
        accent = IS_ACCENT.get(mode, (15, 122, 74))

    if brand_name or logo_path:
        img = _brand(img, brand_name, logo_path, accent)
    return img.convert("RGB")


async def post_reel(page, video_path, message):
    token = page["access_token"]
    pid = page["id"]
    size = video_path.stat().st_size

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            f"{config.GRAPH}/{pid}/video_reels",
            data={"upload_phase": "start", "access_token": token},
        )
        d = r.json()
        if r.status_code >= 400 or "error" in d:
            raise RuntimeError((d.get("error") or {}).get("message") or f"start HTTP {r.status_code}")

        video_id = d.get("video_id")
        upload_url = d.get("upload_url")
        if not video_id or not upload_url:
            raise RuntimeError("upload_url nahi mila")

        with open(video_path, "rb") as fh:
            up = await client.post(
                upload_url,
                headers={"Authorization": f"OAuth {token}", "offset": "0",
                         "file_size": str(size)},
                content=fh.read(),
            )
        if up.status_code >= 400:
            raise RuntimeError(f"upload HTTP {up.status_code}")

        f = await client.post(
            f"{config.GRAPH}/{pid}/video_reels",
            data={"upload_phase": "finish", "video_id": video_id,
                  "video_state": "PUBLISHED", "description": message,
                  "access_token": token},
        )
        fd = f.json()
        if f.status_code >= 400 or "error" in fd:
            raise RuntimeError((fd.get("error") or {}).get("message") or f"finish HTTP {f.status_code}")

    return video_id