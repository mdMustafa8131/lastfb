import asyncio
import hashlib
import json
import subprocess

import edge_tts
from mutagen.mp3 import MP3

import config
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
VOICE_DIR = config.VIDEO_DIR / "voice"
VOICE_DIR.mkdir(parents=True, exist_ok=True)

PAUSE = 0.28
RATE = "-6%"

VOICES = {
    "female": {
        "english": "en-IN-NeerjaNeural",
        "hinglish": "en-IN-NeerjaNeural",
        "bangla": "bn-BD-NabanitaNeural",
        "hindi": "hi-IN-SwaraNeural",
    },
    "male": {
        "english": "en-IN-PrabhatNeural",
        "hinglish": "en-IN-PrabhatNeural",
        "bangla": "bn-BD-PradeepNeural",
        "hindi": "hi-IN-MadhurNeural",
    },
}


def voice_for(gender, lang):
    g = VOICES.get(gender) or VOICES["female"]
    return g.get(lang) or g["english"]


def _key(text, voice, rate):
    h = hashlib.sha1()
    h.update(f"{voice}|{rate}|{text}".encode("utf-8"))
    return h.hexdigest()[:20]


async def _synth(text, voice, out, bounds, rate=RATE):
    b = []
    comm = edge_tts.Communicate(text, voice, rate=rate,
                                boundary="WordBoundary")
    with open(out, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                b.append([chunk["offset"] / 1e7, chunk["duration"] / 1e7,
                          chunk["text"]])
    bounds.write_text(json.dumps(b), "utf-8")


def _silence(seconds):
    out = VOICE_DIR / f"_sil_{int(seconds * 100)}.mp3"
    if out.exists():
        return out
    subprocess.run(
        [FF, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", f"{seconds}", "-c:a", "libmp3lame", "-b:a", "48k", str(out)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


async def build(segments, gender="female", rate=None):
    """segments = [(lang, text), ...] -> (mp3, seconds, words)"""
    r = rate or RATE
    parts = []
    for si, (lang, text) in enumerate(segments):
        text = (text or "").strip()
        if not text:
            continue
        v = voice_for(gender, lang)
        p = VOICE_DIR / f"{_key(text, v, r)}.mp3"
        b = p.with_suffix(".json")
        if not p.exists() or not b.exists():
            try:
                await _synth(text, v, p, b, r)
            except Exception:
                continue
        if p.exists() and b.exists():
            parts.append((p, b, si))

    if not parts:
        return None, 0.0, []

    words, cursor, chain = [], 0.0, []
    for i, (p, b, si) in enumerate(parts):
        try:
            dur = MP3(str(p)).info.length
        except Exception:
            dur = 0.0
        try:
            for off, dl, wd in json.loads(b.read_text("utf-8")):
                words.append({"t0": cursor + float(off),
                              "t1": cursor + float(off) + float(dl), "w": wd,
                              "seg": si})
        except Exception:
            pass
        if i:
            chain.append(_silence(PAUSE))
        chain.append(p)
        cursor += dur + PAUSE

    out = VOICE_DIR / f"mix_{parts[0][0].stem[:10]}_{len(parts)}.mp3"
    cmd = [FF, "-y"]
    for p in chain:
        cmd += ["-i", str(p)]
    filt = "".join(f"[{i}:a]" for i in range(len(chain))) + \
        f"concat=n={len(chain)}:v=0:a=1[out]"
    cmd += ["-filter_complex", filt, "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "96k", str(out)]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print("[voice] ffmpeg fail:", r.stderr[-500:])
        return None, 0.0, []

    try:
        secs = MP3(str(out)).info.length
    except Exception:
        secs = 0.0
    return out, round(secs, 2), words