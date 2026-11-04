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
          plain_path=None, full_path=None):
    """(video_path, music_path) ya (None, None)."""
    music = pick_music(section, category)
    if not music:
        return None, None

    mode = mode if mode in MODES else "zoom"
    seconds = seconds or config.REEL_SECONDS
    fps = config.REEL_FPS
    frames = seconds * fps
    out = config.VIDEO_DIR / f"reel_{uuid.uuid4().hex[:10]}.mp4"
    layered = mode == "ripple" and full_path

    frame = full_path if layered else _frame(image_path)
    extra = []

    fade = f"[1:a]afade=t=out:st={max(0, seconds - 1.5)}:d=1.5[a]"

    if mode == "ripple":
        xv, yv = _ripple_maps(fps)
        vf = (
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},gblur=sigma=22[bg];"
            f"[0:v]scale={W}:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[b];"
            f"[2:v]format=gray[xm];"
            f"[3:v]format=gray[ym];"
            f"[b][xm][ym]displace=edge=mirror,setsar=1,"
            f"fade=t=out:st={max(0, seconds - 2)}:d=2[v];" + fade
        )
        cmd = [_ffmpeg(), "-y", "-loop", "1", "-framerate", str(fps), "-i", str(frame),
               "-stream_loop", "-1", "-i", str(music),
               "-stream_loop", "-1", "-i", str(xv),
               "-stream_loop", "-1", "-i", str(yv)]
    else:
        vf = (f"[0:v]scale={W}:{H},{_chain(mode, frames, fps)}[v];" + fade)
        cmd = [_ffmpeg(), "-y", "-i", str(frame),
               "-stream_loop", "-1", "-i", str(music)]

    vpreset, vcrf = ("veryfast", "23") if mode == "ripple" else ("ultrafast", "27")
    cmd += [
        "-filter_complex", vf,
        "-map", "[v]", "-map", "[a]",
        "-t", str(seconds),
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