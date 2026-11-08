"""Image + music -> 9:16 Reel video (ffmpeg)."""
import math
import random
import subprocess
import uuid

from PIL import Image, ImageChops, ImageFilter, ImageOps

import config

MUSIC_EXT = {".mp3", ".m4a", ".aac", ".wav", ".ogg"}
W, H = 1080, 1920
SRC_W, SRC_H = 1080, 1350
RW, RH = 1080, 1920

RIPPLE_AMP = 11.0
RIPPLE_LAM = 500.0
RIPPLE_PERIOD = 10.0
HL_COLORS = {"english": "yellow@0.42", "bangla": "pink@0.42",
             "hinglish": "lightgreen@0.42", "hindi": "lightblue@0.42"}

UL_COLORS = {"en": "#FFD400", "bn": "#00E5A0", "hi": "#FF5A5F"}
UL_PX = {"en": 6, "bn": 6, "hi": 6}
UL_GAP = 3
UL_KEY = {"english": "en", "bangla": "bn", "hindi": "hi", "hinglish": "hi"}


def _ul_key(lang):
    return UL_KEY.get(str(lang or "english"), "en")


def _ul_hex(value, fallback):
    v = str(value or "").strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6 or any(c not in "0123456789abcdefABCDEF" for c in v):
        v = fallback.lstrip("#")
    return "0x" + v


def _ul_chain(track, words, out_w, out_h, src_w, src_h, px, colors, gap=UL_GAP,
              style="underline", alpha=38):
    if not track or not words:
        return ""
    k = float(out_w) / float(src_w)
    oy = (src_h - SRC_H) // 2
    hi = style == "highlight"
    op = max(0.05, min(1.0, float(alpha) / 100.0))

    segs = {}
    for wd in words:
        seg = wd.get("seg")
        if seg is not None and track.get(seg):
            segs.setdefault(seg, []).append(wd)
    if not segs:
        return ""

    chain = []
    for seg in sorted(segs):
        wds = segs[seg]
        t0 = float(wds[0]["t0"])
        t1 = float(wds[-1]["t1"])
        if t1 - t0 < 0.25:
            t1 = t0 + 0.25
        dur = t1 - t0

        lines = sorted(track[seg], key=lambda l: l["y0"])
        key = _ul_key(lines[0].get("k") or "english")
        p = max(1, min(24, int(round(float((px or {}).get(key) or UL_PX[key])))))
        col = _ul_hex((colors or {}).get(key), UL_COLORS[key])
        gap_px = max(3, int(round(lines[0]["h"] * 0.10)))

        geo = []
        for l in lines:
            if hi:
                bx = max(0, int(round(l["x0"] * k)) - 4)
                bw = max(2.0, (l["x1"] - l["x0"]) * k + 8)
                bh = max(2, int(round(l["h"] * 1.26 * k)))
                by = int(round((l["y0"] - l["h"] * 0.12 + oy) * k))
            else:
                bx = int(round(l["x0"] * k))
                bw = max(2.0, (l["x1"] - l["x0"]) * k)
                bh = p
                by = int(round((l["y1"] + gap_px + oy) * k))
            lim = int(round((l["yb"] + oy) * k)) - bh - 1
            by = max(0, min(by, max(0, lim), out_h - bh - 1))
            geo.append((bx, bw, by, bh))
        total = sum(g[1] for g in geo)
        if total < 2:
            continue

        steps = max(8, min(24, int(round(dur * 12))))
        print(f"[ul] seg={seg} lines={len(geo)} t={t0:.2f}->{t1:.2f}")
        for s in range(1, steps + 1):
            filled = total * s / steps
            ta = t0 + dur * s / steps
            used = 0.0
            for bx, bw, by, bh in geo:
                take = min(bw, filled - used)
                used += bw
                if take < 1:
                    continue
                chain.append(
                    f"drawbox=x={bx}:y={by}:w={int(round(take))}:h={bh}:"
                    f"color={col}@{1 if not hi else round(op, 3)}:t=fill:"
                    f"enable='gte(t,{ta:.3f})'"
                )
    return ",".join(chain)

def _ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def folder(section, category):
    return config.MUSIC_DIR / section / (category or "_default")


def tracks(section, category):
    d = folder(section, category)
    if not d.exists():
        return []
    return sorted([f for f in d.iterdir() if f.suffix.lower() in MUSIC_EXT])


def count(section, category):
    return len(tracks(section, category))


def pick_music(section, category):
    t = tracks(section, category)
    if not t and category:
        t = tracks(section, "_default")
    if not t:
        t = tracks(section, "")
    return random.choice(t) if t else None


def _composite(image_path):
    img = Image.open(image_path).convert("RGB")
    bg = ImageOps.fit(img, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(34))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), 0.45)
    bg.paste(img.resize((SRC_W, SRC_H), Image.LANCZOS), (0, (H - SRC_H) // 2))
    return bg


def _frame(image_path):
    out = config.VIDEO_DIR / f"frame_{uuid.uuid4().hex[:8]}.jpg"
    _composite(image_path).save(out, "JPEG", quality=90)
    return out


def _mask(full_path, plain_path):
    a = _composite(full_path)
    b = _composite(plain_path)
    d = ImageChops.difference(a, b).convert("L")
    m = d.point(lambda v: 255 if v > 48 else 0)
    m = m.filter(ImageFilter.GaussianBlur(1.0))
    out = config.VIDEO_DIR / f"mask_{uuid.uuid4().hex[:8]}.png"
    m.save(out)
    return out


MODES = ("zoom", "zoomout", "pan", "wave", "warp", "ripple", "pulse", "rgb")


def _chain(mode, frames, fps):
    z = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    out = "s=720x1280"
    if mode == "zoomout":
        return f"zoompan=z='max(1.07-on*0.0004,1.0)':d={frames}:{z}:{out}:fps={fps}"
    if mode == "pan":
        return (f"zoompan=z='1.12':d={frames}"
                f":x='(iw-iw/zoom)*on/{frames}':y='(ih-ih/zoom)/2':{out}:fps={fps}")
    if mode == "wave":
        return (f"zoompan=z='1.10':d={frames}:{z}:{out}:fps={fps},"
                f"rotate=a='0.016*sin(2*PI*t/2.6)':ow=iw:oh=ih:c=black")
    if mode == "warp":
        return (f"zoompan=z='1.18':d={frames}:{z}:{out}:fps={fps},"
                f"rotate=a='0.030*sin(2*PI*t/1.7)+0.012*sin(2*PI*t/0.85)'"
                f":ow=iw:oh=ih:c=black,"
                f"rgbashift=rh=7:bh=-7")
    if mode == "pulse":
        return (f"zoompan=z='1.05+0.03*sin(2*PI*on/{int(fps * 2)})'"
                f":d={frames}:{z}:{out}:fps={fps}")
    if mode == "rgb":
        return (f"zoompan=z='min(zoom+0.0008,1.08)':d={frames}:{z}:{out}:fps={fps},"
                f"rgbashift=rh=8:bh=-8")
    return f"zoompan=z='min(zoom+0.0004,1.06)':d={frames}:{z}:{out}:fps={fps}"


def _ripple_maps(fps):
    """Loopable lehar map pair (RIPPLE_PERIOD second), cached. Returns (xm.mp4, ym.mp4)."""
    n = max(2, int(fps * RIPPLE_PERIOD))
    d = config.VIDEO_DIR / f"ripple_maps_{int(RIPPLE_AMP)}_{int(RIPPLE_LAM)}_{RW}x{RH}_{n}"
    xv = d / "xm.mp4"
    yv = d / "ym.mp4"
    if xv.exists() and yv.exists():
        return xv, yv

    d.mkdir(parents=True, exist_ok=True)
    tau = 2 * math.pi
    step = tau / n
    for i in range(n):
        ph = step * i
        col = bytes(
            max(0, min(255, int(128 + RIPPLE_AMP * math.sin(tau * y / RIPPLE_LAM + ph))))
            for y in range(RH)
        )
        row = bytes(
            max(0, min(255, int(128 + RIPPLE_AMP * math.sin(tau * x / RIPPLE_LAM + ph))))
            for x in range(RW)
        )
        Image.frombytes("L", (RW, RH),
                        b"".join(bytes([v]) * RW for v in col)).save(d / f"xm_{i:03d}.png")
        Image.frombytes("L", (RW, RH), row * RH).save(d / f"ym_{i:03d}.png")

    ff = _ffmpeg()
    for name, out in (("xm", xv), ("ym", yv)):
        subprocess.run(
            [ff, "-y", "-framerate", str(fps), "-i", str(d / f"{name}_%03d.png"),
             "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(out)],
            capture_output=True,
        )
        for p in d.glob(f"{name}_*.png"):
            p.unlink(missing_ok=True)
    return xv, yv


def build(image_path, section, category, mode="zoom", seconds=None,
          plain_path=None, full_path=None, use_music=True,
          voice_path=None, voice_len=0, words=None, boxes=None, hl=True,
          line=True, seps=None, ul=False, ul_px=None, ul_colors=None, track=None, ul_style=None, ul_alpha=None, music_vol=None):
    """(video_path, music_path) ya (None, None)."""
    music = pick_music(section, category) if use_music else None
    silent = music is None
    mv = max(0.0, min(1.0, float(music_vol if music_vol is not None else 20) / 100.0))

    mode = mode if mode in MODES else "zoom"
    seconds = seconds or config.REEL_SECONDS
    if voice_path:
        seconds = min(60.0, max(8.0, float(voice_len or 0) + 1.0))
    seconds = round(float(seconds), 3)
    fps = config.REEL_FPS
    frames = max(1, int(round(seconds * fps)))
    out = config.VIDEO_DIR / f"reel_{uuid.uuid4().hex[:10]}.mp4"
    layered = mode == "ripple" and full_path

    if layered:
        frame = full_path
    elif voice_path and full_path:
        frame = _frame(full_path)
    else:
        frame = _frame(image_path)
    extra = []
    small = bool(voice_path) and mode != "ripple"
    w, h = (720, 1280) if small else (W, H)

    hl_chain = ""
    ul_chain = ""
    if hl and voice_path and words and boxes and seps and line:
        k = w / W
        oy = (H - SRC_H) // 2
        hb = []
        prev = {}
        for i, wd in enumerate(words[:40]):
            if i >= len(boxes):
                break
            b = boxes[i]
            ls = b["ls"]
            pe = prev.get(ls, ls)
            dur = max(0.03, wd["t1"] - wd["t0"])
            col = HL_COLORS.get(b.get("k") or "english", "yellow@0.42")
            yy = max(0, int((b["y"] + oy) * k))
            hh = max(2, int(b["h"] * k))
            for s in range(1, 5):
                fr = s / 4
                xe = pe + (b["xe"] - pe) * fr
                tt = wd["t0"] + dur * fr
                xx = max(0, int(ls * k))
                ww = max(2, int((xe - ls) * k) + 1)
                hb.append(f"drawbox=x={xx}:y={yy}:w={ww}:h={hh}:color={col}"
                          f":t=fill:enable='gte(t,{tt:.2f})'")
            prev[ls] = b["xe"]
        if hb:
            hl_chain = "," + ",".join(hb)
            print("[hl]", len(words), len(boxes), len(hl_chain))

    if ul and voice_path and words and track:
        uc = _ul_chain(track, words, w, h, W, H, ul_px, ul_colors,
                       style=(ul_style or "underline"), alpha=(ul_alpha or 38))
        if uc:
            ul_chain = "," + uc
            print("[ul]", len(uc))

    fade = f"afade=t=out:st={max(0, seconds - 1.5)}:d=1.5[a]"
    music_in = (["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"] if silent
                else ["-stream_loop", "-1", "-i", str(music)])

    if voice_path:
        cmd = [_ffmpeg(), "-y", "-loop", "1", "-framerate", str(fps),
               "-i", str(frame), *music_in]
    elif mode == "ripple":
        xv, yv = _ripple_maps(fps)
        cmd = [_ffmpeg(), "-y", "-loop", "1", "-framerate", str(fps), "-i", str(frame),
               *music_in,
               "-stream_loop", "-1", "-i", str(xv),
               "-stream_loop", "-1", "-i", str(yv)]
    else:
        cmd = [_ffmpeg(), "-y", "-i", str(frame), *music_in]

    vidx = cmd.count("-i")
    if voice_path:
        cmd += ["-i", str(voice_path)]
        audio = (f"[1:a]volume={mv}[mus];"
                 f"[{vidx}:a]adelay=250|250[vo];"
                 f"[mus][vo]amix=inputs=2:duration=longest:dropout_transition=0,"
                 + fade)
    else:
        audio = f"[1:a]volume={mv}[mus];[mus]" + fade

    if voice_path:
        vf = (f"[0:v]scale={w}:{h}{hl_chain}{ul_chain},"
              f"fade=t=out:st={max(0, seconds - 1.5)}:d=1.5[v];" + audio)
    elif mode == "ripple":
        vf = (
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},gblur=sigma=22[bg];"
            f"[0:v]scale={W}:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[b];"
            f"[2:v]format=gray[xm];"
            f"[3:v]format=gray[ym];"
            f"[b][xm][ym]displace=edge=mirror,setsar=1,"
            f"fade=t=out:st={max(0, seconds - 2)}:d=2[v];" + audio
        )
    else:
        vf = (f"[0:v]scale={w}:{h},{_chain(mode, frames, fps)}[v];" + audio)

    vpreset, vcrf = ("veryfast", "23") if mode == "ripple" else ("ultrafast", "27")
    cmd += [
        "-filter_threads", "1",
        "-filter_complex", vf,
        "-map", "[v]", "-map", "[a]",
        "-t", str(seconds),
        "-threads", "1",
        "-c:v", "libx264", "-preset", vpreset, "-crf", vcrf,
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        str(out),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=600)
        if r.returncode != 0 or not out.exists() or out.stat().st_size < 10000:
            out.unlink(missing_ok=True)
            return None, None
        return out, music
    except Exception:
        out.unlink(missing_ok=True)
        return None, None
    finally:
        frame.unlink(missing_ok=True)
        for p in extra:
            p.unlink(missing_ok=True)
        if plain_path:
            plain_path.unlink(missing_ok=True)
        if full_path:
            full_path.unlink(missing_ok=True)