"""Islam background photo + music folder manage."""
import shutil

import config
import reel

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ROOTS = {"bg": config.BG_DIR / "islam", "music": config.MUSIC_DIR / "islam"}
EXTS = {"bg": IMG_EXT, "music": reel.MUSIC_EXT}
SKIP = {"t1", "t2", "t3", "t4"}


def _safe(name):
    return "".join(c for c in name.strip().replace(" ", "_")
                   if c.isalnum() or c in "_-")[:40]


def _dir(kind, cat):
    return ROOTS[kind] / _safe(cat)


def list_(kind):
    root = ROOTS[kind]
    root.mkdir(parents=True, exist_ok=True)
    out = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and d.name not in SKIP:
            out.append({"name": d.name,
                        "count": len([f for f in d.iterdir() if f.suffix.lower() in EXTS[kind]])})
    return out


def loose(kind):
    root = ROOTS[kind]
    root.mkdir(parents=True, exist_ok=True)
    return len([f for f in root.iterdir() if f.is_file() and f.suffix.lower() in EXTS[kind]])


def create(kind, name):
    n = _safe(name)
    if not n:
        return None
    _dir(kind, n).mkdir(parents=True, exist_ok=True)
    return n


def delete(kind, name):
    d = _dir(kind, name)
    if d.exists() and d.is_dir():
        shutil.rmtree(d)
        return True
    return False


def files(kind, cat):
    d = _dir(kind, cat)
    if not d.exists():
        return []
    return sorted([f.name for f in d.iterdir() if f.suffix.lower() in EXTS[kind]])


def add(kind, cat, filename, data):
    n = "".join(c for c in filename if c.isalnum() or c in "._-")[:60]
    if not n or not any(n.lower().endswith(e) for e in EXTS[kind]):
        return None
    d = _dir(kind, cat)
    d.mkdir(parents=True, exist_ok=True)
    (d / n).write_bytes(data)
    return n


def remove(kind, cat, name):
    p = _dir(kind, cat) / name
    p.unlink(missing_ok=True)