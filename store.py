import json
import threading
from datetime import datetime, timezone

import config

_lock = threading.RLock()

EMPTY_SETTINGS = {
    "app_id": "", "app_secret": "", "user_token": "",
    "connected_at": None, "user_name": "",
    "dry_run": True,
}

SECTION_DEFAULT_LANG = {"english": "hinglish", "islam": "bangla"}

DEFAULT_SCHEDULE = {
    "day": {"start": "06:00", "end": "22:00", "min": 40, "max": 70},
    "night": {"start": "22:00", "end": "06:00", "min": 60, "max": 120},
}
DEFAULT_SCHEDULE 


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read(path, default):
    with _lock:
        if not path.exists():
            return json.loads(json.dumps(default))
        try:
            return json.loads(path.read_text("utf-8"))
        except Exception:
            return json.loads(json.dumps(default))


def _write(path, data):
    with _lock:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(path)


def get_settings():
    s = _read(config.SETTINGS_FILE, EMPTY_SETTINGS)
    for k, v in EMPTY_SETTINGS.items():
        s.setdefault(k, v)
    return s


def save_settings(data):
    _write(config.SETTINGS_FILE, data)


def disconnect():
    _write(config.SETTINGS_FILE, EMPTY_SETTINGS)
    _write(config.PAGES_FILE, [])


def get_pages():
    return _read(config.PAGES_FILE, [])


def get_page(page_id):
    for p in get_pages():
        if p["id"] == str(page_id):
            return p
    return None


def _new_page(pid, name, category, token):
    return {
        "id": str(pid),
        "name": name,
        "category": category or "",
        "access_token": token,
        "section": None,
        "langs": [],
        "bg_mode": "image",
        "news_mode": "auto",
        "news_region": "in",
        "news_category": None,
        "news_sub": "worldnews",
        "source_color": "#085430",
        "logo": None,
        "brand": None,
        "sentences": 4,
        "question_box": True,
        "enabled": False,
        "status": "idle",
        "schedule": json.loads(json.dumps(DEFAULT_SCHEDULE)),
        "last_post_at": None,
        "next_post_at": None,
        "posted_count": 0,
        "fail_count": 0,
        "reel": False,
        "reel_music": True,
        "reel_mode": "zoom",
        "hashtags": [],
        "voice_on": False,
        "voice_gender": "female",
        "voice_on": False,
        "voice_gender": "female",
        "voice_rate": -6,
        "hl_on": True,
        "hl_on": True,
        "line_on": True,
        "ul_on": False,
        "ul_px_en": 6,
        "ul_px_bn": 6,
        "ul_px_hi": 6,
        "ul_color_en": "#FFD400",
        "ul_color_bn": "#00E5A0",
        "ul_color_hi": "#FF5A5F",
        "ul_color_en": "#FFD400",
        "ul_color_bn": "#00E5A0",
        "ul_color_hi": "#FF5A5F",
        "ul_style": "underline",
        "ul_alpha": 38,
        "music_vol": 20,
        "voice_rate": -6,
        "created_at": _now(),
    
    }


def sync_pages(fetched):
    with _lock:
        existing = {p["id"]: p for p in get_pages()}
        merged = []
        for f in fetched:
            pid = str(f["id"])
            if pid in existing:
                p = existing[pid]
                p["name"] = f.get("name", p["name"])
                p["category"] = f.get("category", p.get("category", ""))
                if f.get("access_token"):
                    p["access_token"] = f["access_token"]
            else:
                p = _new_page(pid, f.get("name", pid),
                              f.get("category", ""), f.get("access_token", ""))
            merged.append(p)
        _write(config.PAGES_FILE, merged)
    return merged


def update_page(page_id, **fields):
    with _lock:
        pages = get_pages()
        for p in pages:
            if p["id"] == str(page_id):
                p.update(fields)
                _write(config.PAGES_FILE, pages)
                return p
    return None