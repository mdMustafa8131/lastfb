"""Background photo + music folder manage (per section)."""
import shutil

import config
import reel

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ROOTS = {"bg": config.BG_DIR, "music": config.MUSIC_DIR}
EXTS = {"bg": IMG_EXT, "music": reel.MUSIC_EXT}
SKIP = {"t1", "t2", "t3", "t4"}


def _safe(name):
    return "".join(c for c in name.strip().replace(" ", "_")
                   if c.isalnum() or c in "_-")[:40]


def _root(kind, section):
    return ROOTS[kind] / section


def _dir(kind, section, cat):
    return _root(kind, section) / _safe(cat)


def list_(kind, section):
    root = _root(kind, section)
    root.mkdir(parents=True, exist_ok=True)
    out = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and d.name not in SKIP:
            out.append({"name": d.name,
                        "count": len([f for f in d.iterdir() if f.suffix.lower() in EXTS[kind]])})
    return out


def loose(kind, section):
    root = _root(kind, section)
    root.mkdir(parents=True, exist_ok=True)
    return len([f for f in root.iterdir() if f.is_file() and f.suffix.lower() in EXTS[kind]])


def create(kind, section, name):
    n = _safe(name)
    if not n:
        return None
    _dir(kind, section, n).mkdir(parents=True, exist_ok=True)
    return n


def delete(kind, section, name):
    d = _dir(kind, section, name)
    if d.exists() and d.is_dir():
        shutil.rmtree(d)
        return True
    return False


def files(kind, section, cat):
    d = _dir(kind, section, cat)
    if not d.exists():
        return []
    return sorted([f.name for f in d.iterdir() if f.suffix.lower() in EXTS[kind]])


def add(kind, section, cat, filename, data):
    n = "".join(c for c in filename if c.isalnum() or c in "._-")[:60]
    if not n or not any(n.lower().endswith(e) for e in EXTS[kind]):
        return None
    d = _dir(kind, section, cat)
    d.mkdir(parents=True, exist_ok=True)
    (d / n).write_bytes(data)
    return n


def remove(kind, section, cat, name):
    p = _dir(kind, section, cat) / name
    p.unlink(missing_ok=True)