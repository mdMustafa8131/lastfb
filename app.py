import base64
import ctypes
import json
import os
from pathlib import Path

if os.name == "nt":
    _libs = Path(__file__).resolve().parent / "libs"
    if _libs.exists():
        os.environ["PATH"] = str(_libs) + os.pathsep + os.environ["PATH"]
        os.add_dll_directory(str(_libs))
        try:
            ctypes.CDLL(str(_libs / "fribidi.dll"))
        except OSError as e:
            print("[warn] fribidi load fail:", e)

import socket
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import caption
import config
import fbapi
import hashtags
import importer
import news
import pool
import scheduler
import store

LANGS = {"english": ("bangla", "hindi", "hinglish"), "islam": ("bangla", "hindi", "english")}
NEWS_TPL_COUNT = getattr(store, "NEWS_TPL_COUNT", 4)
TPL_COUNT = getattr(config, "TEMPLATE_COUNT", 4)

app = FastAPI(title="FB Engine")

FB_USER = os.getenv("FB_USER", "admin")
FB_PASS = os.getenv("FB_PASS", "")


@app.middleware("http")
async def _auth(request: Request, call_next):
    if not FB_PASS or request.url.path.startswith("/static") or \
            request.url.path.startswith("/media"):
        return await call_next(request)
    hdr = request.headers.get("authorization", "")
    if hdr.startswith("Basic "):
        try:
            u, p = base64.b64decode(hdr[6:]).decode().split(":", 1)
            if u == FB_USER and p == FB_PASS:
                return await call_next(request)
        except Exception:
            pass
    return Response("Auth required", status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="fb"'})


app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
app.mount("/media", StaticFiles(directory=str(config.MEDIA_DIR)), name="media")
templates = Jinja2Templates(directory=str(config.TEMPLATE_DIR))
templates.env.globals["SECTIONS"] = config.SECTIONS
templates.env.globals["LANGS"] = LANGS
templates.env.globals["NEWS_TPL_COUNT"] = NEWS_TPL_COUNT
templates.env.globals["TEMPLATE_COUNT"] = TPL_COUNT

def _now_ist():
    return datetime.now(ZoneInfo(config.TZ)).strftime("%d %b, %I:%M %p")


templates.env.globals["now_ist"] = _now_ist


def _ctx(request, **kw):
    s = store.get_settings()
    kw.update({"request": request, "settings": s,
               "connected": bool(s["user_token"])})
    return kw


def _seed_pools():
    seed_dir = config.BASE_DIR / "imports" / "seed"
    if not seed_dir.exists():
        return
    for section in ("english", "islam"):
        if pool.remaining(section):
            continue
        f = seed_dir / f"{section}.csv"
        if not f.exists():
            continue
        try:
            importer.import_text(section, f.read_text("utf-8"), None)
            print("[seed] loaded", section)
        except Exception as e:
            print("[seed] fail", section, e)


@app.on_event("startup")
async def _startup():
    _seed_pools()
    scheduler.start()


@app.on_event("shutdown")
async def _shutdown():
    scheduler.stop()


# ---------- views ----------
@app.get("/")
def dashboard(request: Request):
    pages = store.get_pages()
    for p in pages:
        p["remaining"] = pool.remaining(p["section"]) if p.get("section") else 0
    return templates.TemplateResponse(
        "dashboard.html", _ctx(request, pages=pages))


@app.get("/page/{page_id}")
def page_detail(request: Request, page_id: str):
    page = store.get_page(page_id)
    if not page:
        return RedirectResponse("/")
    return templates.TemplateResponse(
        "page.html", _ctx(request, page=page, news_cats=news.load_cats()))


# ---------- connect ----------
class ConnectIn(BaseModel):
    app_id: str
    app_secret: str
    user_token: str


@app.post("/api/connect")
async def connect(payload: ConnectIn):
    try:
        me = await fbapi.fetch_me(payload.user_token)
        pages = await fbapi.fetch_pages(payload.user_token)
    except fbapi.FBError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"Connection failed: {e}")

    store.save_settings({
        "app_id": payload.app_id.strip(),
        "app_secret": payload.app_secret.strip(),
        "user_token": payload.user_token.strip(),
        "connected_at": datetime.now().isoformat(),
        "user_name": me.get("name", ""),
    })
    store.sync_pages(pages)
    return {"ok": True, "pages": len(pages)}


@app.post("/api/disconnect")
def disconnect():
    store.disconnect()
    return {"ok": True}


@app.post("/api/sync")
async def sync():
    s = store.get_settings()
    if not s["user_token"]:
        raise HTTPException(400, "Not connected")
    try:
        pages = await fbapi.fetch_pages(s["user_token"])
    except fbapi.FBError as e:
        raise HTTPException(400, str(e))
    store.sync_pages(pages)
    return {"ok": True, "pages": len(pages)}


class DryRunIn(BaseModel):
    on: bool
class EnableIn(BaseModel):
    on: bool | None = None

@app.post("/api/dryrun")
def set_dry_run(payload: DryRunIn):
    s = store.get_settings()
    s["dry_run"] = payload.on
    store.save_settings(s)
    return {"ok": True}


# ---------- page config ----------
class SectionIn(BaseModel):
    section: str


@app.post("/api/pages/{page_id}/section")
def set_section(page_id: str, payload: SectionIn):
    if payload.section not in config.SECTIONS:
        raise HTTPException(400, "Unknown section")
    if not store.get_page(page_id):
        raise HTTPException(404, "Page not found")
    store.update_page(page_id, section=payload.section, langs=[],
                      status="idle", alerted_low=False, alerted_out=False)
    return {"ok": True}


class TemplateIn(BaseModel):
    template: int


@app.post("/api/pages/{page_id}/template")
def set_template(page_id: str, payload: TemplateIn):
    if not store.get_page(page_id):
        raise HTTPException(404, "Page not found")
    if not 1 <= payload.template <= TPL_COUNT:
        raise HTTPException(400, f"Template 1-{TPL_COUNT} only")
    store.update_page(page_id, template=payload.template)
    return {"ok": True}


class SentencesIn(BaseModel):
    sentences: int


@app.post("/api/pages/{page_id}/sentences")
def set_sentences(page_id: str, payload: SentencesIn):
    if not store.get_page(page_id):
        raise HTTPException(404, "Page not found")
    if not 1 <= payload.sentences <= 4:
        raise HTTPException(400, "1-4 only")
    store.update_page(page_id, sentences=payload.sentences)
    return {"ok": True}


class ToggleIn(BaseModel):
    on: bool


@app.post("/api/pages/{page_id}/question")
def set_question(page_id: str, payload: ToggleIn):
    if not store.get_page(page_id):
        raise HTTPException(404, "Page not found")
    store.update_page(page_id, question_box=payload.on)
    return {"ok": True}


class BgModeIn(BaseModel):
    mode: str


@app.post("/api/pages/{page_id}/bgmode")
def set_bgmode(page_id: str, payload: BgModeIn):
    if payload.mode not in ("image", "fresh", "t1", "t2", "t3", "t4", "gold", "e5"):
        raise HTTPException(400, "image, fresh, t1-t4, gold ya e5")
    store.update_page(page_id, bg_mode=payload.mode)
    return {"ok": True}


class SourceColorIn(BaseModel):
    color: str


@app.post("/api/pages/{page_id}/sourcecolor")
def set_source_color(page_id: str, payload: SourceColorIn):
    if not store.get_page(page_id):
        raise HTTPException(404, "Page not found")
    store.update_page(page_id, source_color=payload.color)
    return {"ok": True}


class BrandIn(BaseModel):
    brand: str


@app.post("/api/pages/{page_id}/brand")
def set_brand(page_id: str, payload: BrandIn):
    if not store.get_page(page_id):
        raise HTTPException(404, "Page not found")
    store.update_page(page_id, brand=payload.brand.strip().lstrip("@") or None)
    return {"ok": True}


class LangIn(BaseModel):
    lang: str
    on: bool


@app.post("/api/pages/{page_id}/lang")
def set_lang(page_id: str, payload: LangIn):
    page = store.get_page(page_id)
    if not page:
        raise HTTPException(404, "Page not found")
    if payload.lang not in LANGS.get(page.get("section") or "", ()):
        raise HTTPException(400, "Is section ke liye galat language")
    langs = [l for l in (page.get("langs") or []) if l != payload.lang]
    if payload.on:
        langs.append(payload.lang)
    store.update_page(page_id, langs=langs)
    return {"ok": True, "langs": langs}


@app.post("/api/pages/{page_id}/logo")
async def set_logo(page_id: str, request: Request):
    page = store.get_page(page_id)
    if not page:
        raise HTTPException(404, "Page not found")
    form = await request.form()
    upload = form.get("logo")
    if upload and getattr(upload, "filename", ""):
        ext = Path(upload.filename).suffix.lower() or ".png"
        dest = config.MEDIA_DIR / "logos" / f"{page_id}{ext}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await upload.read())
        store.update_page(page_id, logo=str(dest))
        return {"ok": True}
    store.update_page(page_id, logo=None)
    return {"ok": True, "removed": True}


# ---------- news ----------
class NewsIn(BaseModel):
    mode: str | None = None
    region: str | None = None
    sub: str | None = None
    tpl: int | None = None
    category: str | None = None


class NewsFetchIn(BaseModel):
    mode: str = "auto"
    region: str = "in"
    sub: str = "worldnews"
    category: str | None = None
    keyword: str | None = None
    limit: int = 10
    page_id: str | None = None


class CatIn(BaseModel):
    name: str
    keywords: str = ""


@app.post("/api/pages/{page_id}/news")
def set_news(page_id: str, payload: NewsIn):
    if not store.get_page(page_id):
        raise HTTPException(404, "Page not found")
    if payload.mode and payload.mode not in ("auto", "trending", "manual"):
        raise HTTPException(400, "auto, trending ya manual")
    if payload.region and payload.region not in news.REGIONS:
        raise HTTPException(400, "Region galat")
    if payload.tpl and not 1 <= payload.tpl <= NEWS_TPL_COUNT:
        raise HTTPException(400, f"Template 1-{NEWS_TPL_COUNT} only")
    kw = {}
    if payload.mode:
        kw["news_mode"] = payload.mode
    if payload.region:
        kw["news_region"] = payload.region
    if payload.sub is not None:
        kw["news_sub"] = payload.sub or "worldnews"
    if payload.tpl:
        kw["template"] = payload.tpl
    if payload.category is not None:
        kw["news_category"] = payload.category or None
    store.update_page(page_id, **kw)
    return {"ok": True}


@app.post("/api/news/fetch")
def news_fetch(payload: NewsFetchIn):
    if payload.mode not in ("auto", "trending", "manual"):
        raise HTTPException(400, "auto, trending ya manual")
    try:
        r = news.fetch_scored(payload.mode, payload.region, payload.sub,
                              payload.category, payload.keyword, 5) or {}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"Fetch fail: {e}")

    items = r.get("items") or []
    kws = r.get("keywords") or []
    have = {i.get("url") for i in pool.load_pool("news")}
    items = [i for i in items if i.get("url") not in have]
    added = pool.add_items("news", items) if items else 0

    made = 0
    page = store.get_page(payload.page_id) if payload.page_id else None
    if page and page.get("section") == "news":
        for _ in range(min(5, pool.remaining("news"))):
            if not pool._make_one(page):
                break
            made += 1

    return {"ok": True, "added": added, "remaining": pool.remaining("news"),
            "made": made, "keywords": kws[:6],
            "tags": r.get("tags") or [],
            "top": items[0]["title"] if items else "",
            "debug": r.get("debug") or []}


@app.get("/api/news/categories")
def cats_list():
    return {"categories": news.load_cats()}


@app.post("/api/news/categories")
def cats_add(payload: CatIn):
    name = payload.name.strip()
    kws = [k.strip() for k in payload.keywords.split(",") if k.strip()]
    if not name:
        raise HTTPException(400, "Naam zaroori")
    if not kws:
        raise HTTPException(400, "Kam se kam ek keyword")
    return {"ok": True, "category": news.add_cat(name, kws)}


@app.delete("/api/news/categories/{cat_id}")
def cats_del(cat_id: str):
    news.del_cat(cat_id)
    return {"ok": True}

@app.get("/api/news/hot")
def news_hot():
    tags = news.hot_tags()
    return {"tags": tags, "keywords": [news.tag_to_keyword(t) for t in tags]}


# ---------- timing ----------
@app.post("/api/pages/{page_id}/toggle")
def toggle(page_id: str, payload: EnableIn = None):
    page = store.get_page(page_id)
    if not page:
        raise HTTPException(404, "Page not found")
    want = payload.on if (payload and payload.on is not None) else (not page["enabled"])
    if want:
        if not page.get("section"):
            raise HTTPException(400, "Pehle section select karo")
        store.update_page(page_id, enabled=True, status="idle")
    else:
        store.update_page(page_id, enabled=False, status="stopped")
    return {"ok": True, "enabled": bool(want)}

class WindowIn(BaseModel):
    start: str
    end: str
    min: int
    max: int


class ScheduleIn(BaseModel):
    day: WindowIn
    night: WindowIn


def _valid_hhmm(v):
    try:
        h, m = v.split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
    except Exception:
        return False


@app.post("/api/pages/{page_id}/schedule")
def set_schedule(page_id: str, payload: ScheduleIn):
    for w in (payload.day, payload.night):
        if not (_valid_hhmm(w.start) and _valid_hhmm(w.end)):
            raise HTTPException(400, "Time HH:MM format me do")
        if w.min < 1 or w.max < w.min:
            raise HTTPException(400, "min < max hona chahiye")
    if not store.get_page(page_id):
        raise HTTPException(404, "Page not found")
    store.update_page(page_id, schedule=payload.model_dump())
    return {"ok": True}


@app.get("/api/state")
def state():
    return {
        "pages": [
            {
                "id": p["id"], "status": p["status"], "enabled": p["enabled"],
                "next_post_at": p.get("next_post_at"),
                "posted_count": p.get("posted_count", 0),
            }
            for p in store.get_pages()
        ]
    }


# ---------- image preview ----------
@app.post("/api/pages/{page_id}/preview")
def preview(page_id: str):
    page = store.get_page(page_id)
    if not page:
        raise HTTPException(404, "Page not found")
    if not page.get("section"):
        raise HTTPException(400, "Pehle section select karo")
    out = pool._make_one(page)
    if not out:
        raise HTTPException(400, "Data pool khali hai")
    return {"ok": True, "url": f"/media/ready/{page_id}/{out.name}"}


@app.get("/api/pages/{page_id}/ready")
def ready(page_id: str):
    page = store.get_page(page_id)
    if not page:
        raise HTTPException(404, "Page not found")
    files = pool.ready_files(page_id)
    return {
        "count": len(files),
        "urls": [f"/media/ready/{page_id}/{f.name}" for f in reversed(files)],
        "remaining": pool.remaining(page["section"]) if page.get("section") else 0,
    }


@app.post("/api/pages/{page_id}/buffer")
def refill(page_id: str):
    page = store.get_page(page_id)
    if not page:
        raise HTTPException(404, "Page not found")
    return {"ok": True, "made": pool.fill_buffer(page, force=True)}


@app.post("/api/pages/{page_id}/clear")
def clear(page_id: str):
    pool.clear_ready(page_id)
    return {"ok": True}


@app.post("/api/pages/{page_id}/wipe")
def wipe(page_id: str):
    page = store.get_page(page_id)
    if not page:
        raise HTTPException(404, "Page not found")
    if not page.get("section"):
        raise HTTPException(400, "Pehle section select karo")
    pool.save_pool(page["section"], [])
    pool.clear_ready(page_id)
    return {"ok": True}


@app.post("/api/pages/{page_id}/purge-unused")
@app.post("/api/pages/{page_id}/delete-unused")
def purge_unused(page_id: str):
    page = store.get_page(page_id)
    if not page:
        raise HTTPException(404, "Page not found")
    if not page.get("section"):
        raise HTTPException(400, "Pehle section select karo")
    items = [i for i in pool.load_pool(page["section"]) if i.get("used")]
    pool.save_pool(page["section"], items)
    return {"ok": True, "remaining": 0}


@app.post("/api/pages/{page_id}/resume")
def resume(page_id: str):
    page = store.get_page(page_id)
    if not page:
        raise HTTPException(404, "Page not found")
    store.update_page(page_id, enabled=True, status="idle",
                      alerted_low=False, alerted_out=False)
    return {"ok": True}


# ---------- caption / post ----------
@app.post("/api/pages/{page_id}/caption")
def make_caption(page_id: str):
    page = store.get_page(page_id)
    if not page:
        raise HTTPException(404, "Page not found")
    files = pool.ready_files(page_id)
    if not files:
        raise HTTPException(400, "Pehle image generate karo")
    meta = files[-1].with_suffix(".json")
    if not meta.exists():
        raise HTTPException(400, "Image meta nahi mila")
    data = json.loads(meta.read_text("utf-8"))
    tags = hashtags.pick(30)
    text = caption.build(page["section"], data["items"],
                         page.get("langs") or [], tags)
    return {"ok": True, "caption": text}


@app.post("/api/pages/{page_id}/post-now")
async def post_now(page_id: str):
    if not store.get_page(page_id):
        raise HTTPException(404, "Page not found")
    r = await scheduler.post_now(page_id)
    if not r.get("ok"):
        raise HTTPException(400, r.get("error") or "Post fail")
    return r


# ---------- import ----------
@app.post("/api/pages/{page_id}/import")
async def import_data(page_id: str, request: Request):
    page = store.get_page(page_id)
    if not page:
        raise HTTPException(404, "Page not found")
    section = page.get("section")
    if not section:
        raise HTTPException(400, "Pehle section select karo")
    if section not in importer.PARSERS:
        raise HTTPException(400, "Is section me import nahi — News settings se fetch karo")

    form = await request.form()
    lang = form.get("lang") or None
    text = (form.get("text") or "").strip()
    upload = form.get("file")
    if upload and getattr(upload, "filename", ""):
        raw = (await upload.read()).decode("utf-8-sig", errors="replace")
        importer.archive(upload.filename, raw)
        text = raw
    if not text:
        raise HTTPException(400, "File ya text do")
    return importer.import_text(section, text, lang)


# ---------- pool ----------
@app.get("/api/pool/{section}")
def pool_stats(section: str):
    if section not in config.SECTIONS:
        raise HTTPException(400, "Unknown section")
    items = pool.load_pool(section)
    used = len([i for i in items if i.get("used")])
    return {"total": len(items), "remaining": len(items) - used, "used": used}


@app.post("/api/pool/{section}/reset")
def pool_reset(section: str):
    if section not in config.SECTIONS:
        raise HTTPException(400, "Unknown section")
    items = pool.load_pool(section)
    for i in items:
        i["used"] = False
    pool.save_pool(section, items)
    return {"ok": True, "remaining": len(items)}


@app.post("/api/pool/{section}/purge")
def pool_purge(section: str):
    if section not in config.SECTIONS:
        raise HTTPException(400, "Unknown section")
    items = [i for i in pool.load_pool(section) if not i.get("used")]
    pool.save_pool(section, items)
    return {"ok": True, "remaining": len(items)}


@app.post("/api/pool/{section}/purge-unused")
def pool_purge_unused(section: str):
    if section not in config.SECTIONS:
        raise HTTPException(400, "Unknown section")
    items = [i for i in pool.load_pool(section) if i.get("used")]
    pool.save_pool(section, items)
    return {"ok": True, "remaining": 0}


# ---------- misc ----------
@app.post("/api/shutdown")
def shutdown():
    def _stop():
        time.sleep(0.4)
        os._exit(0)
    threading.Thread(target=_stop, daemon=True).start()
    return {"ok": True}


def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    print(f"FB Engine -> http://{_lan_ip()}:{config.PORT}  (mobile: same WiFi)")
    try:
        uvicorn.run(app, host=config.HOST, port=config.PORT,
                    timeout_graceful_shutdown=2)
    except KeyboardInterrupt:
        pass
    os._exit(0)