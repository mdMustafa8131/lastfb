import asyncio
import hashlib
import json
import os
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

_ALT = {"bn-BD-NabanitaNeural": "bn-BD-PradeepNeural",
        "bn-BD-PradeepNeural": "bn-BD-NabanitaNeural",
        "hi-IN-SwaraNeural": "hi-IN-MadhurNeural",
        "hi-IN-MadhurNeural": "hi-IN-SwaraNeural"}

TRIES = 4


def voice_for(gender, lang):
    g = VOICES.get(gender) or VOICES["female"]
    return g.get(lang) or g["english"]


def _alt_voice(v):
    return _ALT.get(v)


def _key(text, voice, rate=None):
    h = hashlib.sha1()
    h.update(f"{voice}|{rate or RATE}|{text}".encode("utf-8"))
    return h.hexdigest()[:20]


async def _synth(text, voice, out, bounds, rate=None):
    tmp = out.with_suffix(".part")
    tmp.unlink(missing_ok=True)
    b = []
    comm = edge_tts.Communicate(text, voice, rate=rate or RATE,
                                boundary="WordBoundary")
    try:
        with open(tmp, "wb") as f:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    b.append([chunk["offset"] / 1e7, chunk["duration"] / 1e7,
                              chunk["text"]])
        if tmp.stat().st_size < 1000 or not b:
            raise RuntimeError("empty audio")
        os.replace(tmp, out)
        bounds.write_text(json.dumps(b), "utf-8")
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _silence(seconds):
    out = VOICE_DIR / f"_sil_{int(seconds * 100)}.mp3"
    if out.exists():
        return out
    subprocess.run(
        [FF, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", f"{seconds}", "-c:a", "libmp3lame", "-b:a", "48k", str(out)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


async def _segment(text, lang, v, p, b, r):
    if p.exists() and b.exists() and p.stat().st_size > 1000:
        return True

    p.unlink(missing_ok=True)
    b.unlink(missing_ok=True)
    alt = _alt_voice(v)

    for attempt in range(TRIES):
        try:
            await _synth(text, v, p, b, r)
            return True
        except Exception as e:
            print("[tts]", lang, "try", attempt + 1, type(e).__name__,
                  str(e)[:110])
        if attempt == 1 and alt:
            try:
                await _synth(text, alt, p, b, r)
                print("[tts]", lang, "alt voice chal gaya")
                return True
            except Exception as e:
                print("[tts]", lang, "alt fail", type(e).__name__)
        await asyncio.sleep(0.7 * (attempt + 1))

    return False


async def build(segments, gender="female", rate=None):
    """segments = [(lang, text), ...] -> (mp3, seconds, words, missed)"""
    r = rate or RATE
    parts = []
    missed = []
    for si, (lang, text) in enumerate(segments):
        text = (text or "").strip()
        if not text:
            continue
        v = voice_for(gender, lang)
        p = VOICE_DIR / f"{_key(text, v, r)}.mp3"
        b = p.with_suffix(".json")
        if await _segment(text, lang, v, p, b, r):
            parts.append((p, b, si))
        else:
            missed.append(lang)
            print("[tts]", lang, "SKIPPED", text[:45])

    if not parts:
        return None, 0.0, [], missed

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

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode:
        print("[voice] ffmpeg fail:", res.stderr[-400:])
        return None, 0.0, [], missed

    try:
        secs = MP3(str(out)).info.length
    except Exception:
        secs = 0.0
    return out, round(secs, 2), words, missed