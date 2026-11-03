import io
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1350
M = 48
YELLOW = (255, 214, 10)
INK = (12, 12, 12)

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_CAND = {
    "bold": ["NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf"],
    "body": ["NotoSans-Regular.ttf", "DejaVuSans.ttf", "arial.ttf"],
    "dev": ["NotoSansDevanagari-Bold.ttf", "NotoSansDevanagari-Regular.ttf",
            "Nirmala.ttf", "mangal.ttf"],
    "bn": ["NotoSansBengali-Bold.ttf", "NotoSansBengali-Regular.ttf",
           "Nirmala.ttf", "vrinda.ttf"],
}
_DIRS = [FONT_DIR, Path("/usr/share/fonts"), Path("C:/Windows/Fonts")]

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def _fp(k):
    for n in _CAND.get(k, []):
        for d in _DIRS:
            p = d / n
            if p.exists():
                return str(p)
    return None


_F = {k: _fp(k) for k in _CAND}


def _font(k, s):
    p = _F.get(k)
    return ImageFont.truetype(p, s) if p else ImageFont.load_default(s)


def _detect(t):
    for ch in str(t):
        o = ord(ch)
        if 0x0900 <= o <= 0x097F:
            return "dev"
        if 0x0980 <= o <= 0x09FF:
            return "bn"
    return "bold"


def _wrap(d, t, f, w):
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


def _text(img, box, txt, kind, color, size, gap, align="center"):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x1, y1, x2, y2 = box
    w = max(60, x2 - x1)
    f = _font(kind, size)
    lines = _wrap(d, txt, f, w)
    while lines and len(lines) * (size + gap) > (y2 - y1) and size > 24:
        size -= 2
        f = _font(kind, size)
        lines = _wrap(d, txt, f, w)
    total = len(lines) * (size + gap)
    y = y1 + max(0, ((y2 - y1) - total) // 2)
    for ln in lines:
        lw = d.textlength(ln, font=f)
        x = x1 + (w - lw) / 2 if align == "center" else x1
        d.text((x, y), ln, font=f, fill=color + (255,))
        y += size + gap
    return Image.alpha_composite(img, layer)


def _band(img, box, color=YELLOW):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle(box, fill=color + (255,))
    return Image.alpha_composite(img, layer)


def _fetch_img(url, ref=None):
    if not url:
        return None
    h = {"User-Agent": _UA}
    if ref:
        h["Referer"] = ref
    urls = [url]
    if "scontent" in url:
        urls.insert(0, url.replace("dst-jpg_p1080x1080", "dst-jpg_p2048x2048"))
        urls.insert(0, url.replace("dst-jpg_s1080x1080", "dst-jpg_p2048x2048"))
    for u in urls:
        try:
            r = httpx.get(u, timeout=25, headers=h, follow_redirects=True)
            if r.status_code != 200 or "image" not in r.headers.get("content-type", ""):
                continue
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            if min(im.size) < 150:
                continue
            return im
        except Exception:
            continue
    return None


def _fallback_bg():
    top, bottom = (18, 24, 44), (52, 40, 96)
    im = Image.new("RGB", (W, H), top)
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)],
               fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return im


def _split(title):
    words = str(title).split()
    if len(words) < 6:
        return str(title), ""
    half = len(words) // 2
    return " ".join(words[:half]), " ".join(words[half:])


def render(item, tpl=1):
    img = _fetch_img(item.get("image", ""), item.get("url"))
    if img is None:
        img = _fallback_bg()

    bg = ImageOps.fit(img, (W, H), Image.LANCZOS).convert("RGBA")
    bg = Image.alpha_composite(bg, Image.new("RGBA", bg.size, (0, 0, 0, 30)))

    top_h = 300
    bot_h = 250
    top_txt, bot_txt = _split(item.get("title", ""))
    top_k = _detect(top_txt)
    bot_k = _detect(bot_txt)

    if tpl == 1:
        bg = _band(bg, (0, 0, W, top_h))
        bg = _text(bg, (M, 20, W - M, top_h - 20), top_txt, top_k, INK, 74, 26)
        if bot_txt:
            bg = _band(bg, (0, H - bot_h, W, H))
            bg = _text(bg, (M, H - bot_h + 20, W - M, H - 20), bot_txt, bot_k, INK, 74, 26)
    elif tpl == 2:
        bg = _band(bg, (0, 0, W, top_h - 40))
        bg = _text(bg, (M, 20, W - M, top_h - 60), top_txt, top_k, INK, 78, 26, "left")
        if bot_txt:
            bg = _band(bg, (0, H - 180, W, H))
            bg = _text(bg, (M, H - 160, W - M, H - 20), bot_txt, bot_k, INK, 40, 20, "left")
    elif tpl == 3:
        bg = _band(bg, (0, 0, W, top_h + 60))
        bg = _text(bg, (M, 30, W - M, top_h + 30), top_txt, top_k, INK, 70, 24)
        if bot_txt:
            bg = _band(bg, (0, H - 120, W, H))
            bg = _text(bg, (M, H - 100, W - M, H - 20), bot_txt, bot_k, INK, 46, 20)
    else:
        blur = bg.filter(ImageFilter.GaussianBlur(22))
        inner = ImageOps.fit(img, (W - 2 * M, int((W - 2 * M) * 1.1)), Image.LANCZOS).convert("RGBA")
        blur.paste(inner, (M, int((H - inner.height) / 2)))
        bg = blur
        bg = _band(bg, (0, 0, W, top_h - 60))
        bg = _text(bg, (M, 24, W - M, top_h - 80), top_txt, top_k, INK, 72, 24)
        if bot_txt:
            bg = _band(bg, (0, H - 150, W, H))
            bg = _text(bg, (M, H - 130, W - M, H - 20), bot_txt, bot_k, INK, 44, 20)

    d = ImageDraw.Draw(bg)
    d.text((W - M, 14), str(item.get("source", ""))[:28], font=_font("bold", 22),
           fill=INK, anchor="ra")
    return bg.convert("RGB")