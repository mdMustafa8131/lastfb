import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MEDIA_DIR = BASE_DIR / "media"
IMPORT_DIR = BASE_DIR / "imports"
ARCHIVE_DIR = IMPORT_DIR / "archive"
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
BG_DIR = MEDIA_DIR / "backgrounds"
READY_DIR = MEDIA_DIR / "ready"
MUSIC_DIR = MEDIA_DIR / "music"
VIDEO_DIR = MEDIA_DIR / "video"
REEL_SECONDS = 15
REEL_FPS = 25

HOST = os.getenv("FBENGINE_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT") or os.getenv("FBENGINE_PORT", "8080"))
TZ = "Asia/Kolkata"

GRAPH_VERSION = os.getenv("FBENGINE_GRAPH_VERSION", "v21.0")
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"

SETTINGS_FILE = DATA_DIR / "settings.json"
PAGES_FILE = DATA_DIR / "pages.json"

SECTIONS = {"english": "English", "islam": "Islam", "news": "News"}

for _d in (DATA_DIR, MEDIA_DIR, IMPORT_DIR, ARCHIVE_DIR, READY_DIR, BG_DIR, MUSIC_DIR, VIDEO_DIR):
    _d.mkdir(parents=True, exist_ok=True)
for _sec in SECTIONS:
    (BG_DIR / _sec).mkdir(parents=True, exist_ok=True)
    (MUSIC_DIR / _sec).mkdir(parents=True, exist_ok=True)
for _cat in ("qabr", "jahannam", "jannat", "general"):
    (BG_DIR / "islam" / _cat).mkdir(parents=True, exist_ok=True)
    (MUSIC_DIR / "islam" / _cat).mkdir(parents=True, exist_ok=True)