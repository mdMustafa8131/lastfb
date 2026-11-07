import asyncio
import json
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import caption
import render
import reel
import news
import config
import hashtags
import pool
import poster
import store

TZ = ZoneInfo(config.TZ)

_tasks = {}
_stop = asyncio.Event()
_loop = None


def _minutes(hhmm):
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def _in_window(now_min, start, end):
    s, e = _minutes(start), _minutes(end)
    if s == e:
        return True
    if s < e:
        return s <= now_min < e
    return now_min >= s or now_min < e


def _active(page, now):
    sch = page["schedule"]
    now_min = now.hour * 60 + now.minute
    if _in_window(now_min, sch["day"]["start"], sch["day"]["end"]):
        return sch["day"]
    if _in_window(now_min, sch["night"]["start"], sch["night"]["end"]):
        return sch["night"]
    return None


def _next_start(now, page):
    best = None
    for w in (page["schedule"]["day"], page["schedule"]["night"]):
        h, m = str(w["start"]).split(":")
        cand = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
        if cand <= now:
            cand += timedelta(days=1)
        if best is None or cand < best:
            best = cand
    return best


def _plan(page):
    now = datetime.now(TZ)
    w = _active(page, now)
    if not w:
        return _next_start(now, page)

    lo = max(1, int(w["min"]))
    hi = max(lo, int(w["max"]))
    target = now + timedelta(minutes=random.randint(lo, hi))

    if _in_window(target.hour * 60 + target.minute, w["start"], w["end"]):
        return target

    nxt = _next_start(now, page)
    nw = _active(page, nxt)
    if nw:
        nlo = max(1, int(nw["min"]))
        nhi = max(nlo, int(nw["max"]))
        nxt += timedelta(minutes=random.randint(nlo, nhi))
    return nxt


def _read_meta(image_path):
    meta = image_path.with_suffix(".json")
    if not meta.exists():
        return None
    try:
        return json.loads(meta.read_text("utf-8"))
    except Exception:
        return None


async def _post_once(page):
    files = pool.ready_files(page["id"])
    if not files:
        pool.fill_buffer(page, force=True)
        files = pool.ready_files(page["id"])
    if not files:
        store.update_page(page["id"], status="out_of_data", enabled=False)
        return

    image = files[0]
    meta = _read_meta(image)
    if not meta:
        image.unlink(missing_ok=True)
        return

    tags = page.get("hashtags") or []
    text = caption.build(page["section"], meta["items"], page.get("langs") or [], tags)

    use_reel = bool(page.get("reel")) and page["section"] in ("islam", "english")
    video = None
    pair = []
    if use_reel:
        cat = "general" if page["section"] == "english" else (
            (meta["items"][0].get("category") or "") if meta.get("items") else "")
        if page["section"] == "islam":
            full_i, plain_i = render.render_islam_gold_pair(
                meta["items"][0], page.get("langs") or [], cat)
        else:
            full_i, plain_i = render.render_english_clean_pair(
                meta["items"], page.get("langs") or [], page.get("brand_name"))
        pair = [full_i, plain_i]
        video, _m = reel.build(
            image, page["section"], cat, page.get("reel_mode") or "zoom",
            plain_path=plain_i, full_path=full_i,
            use_music=(True if page["section"] == "islam"
                       else bool(page.get("reel_music", True))))

        if not video:
            for p in pair:
                p.unlink(missing_ok=True)
            store.update_page(page["id"], status="reel_wait")
            return
    settings = store.get_settings()
    dry = bool(settings.get("dry_run"))
    ok = False
    last_err = ""
    for attempt in range(2):
        try:
            if dry:
                await asyncio.sleep(0.2)
                ok = True
            else:
                if video:
                    await poster.post_reel(page, video, text)
                else:
                    await poster.post_photo(page, image, text)
                ok = True
            break
        except Exception as e:
            last_err = str(e)[:200]
            await asyncio.sleep(2)

    if not ok:
        if video:
            video.unlink(missing_ok=True)
        for p in pair:
            p.unlink(missing_ok=True)
        store.update_page(page["id"], status="error", last_err=last_err,
                          fail_count=(page.get("fail_count") or 0) + 1)
        return

    if page["section"] == "news":
        for it in (meta.get("items") or []):
            news.mark_posted(it.get("url"))

    if video and not dry:
        video.unlink(missing_ok=True)
    for p in pair:
        p.unlink(missing_ok=True)
    image.unlink(missing_ok=True)
    image.with_suffix(".json").unlink(missing_ok=True)

    fresh = store.get_page(page["id"])
    if fresh:
        store.update_page(page["id"],
                          last_post_at=datetime.now(TZ).isoformat(),
                          posted_count=(fresh.get("posted_count") or 0) + 1,
                          status="idle",
                          fail_count=0)
        if len(pool.ready_files(page["id"])) <= 1:
            pool.fill_buffer(fresh)
        if not pool.remaining(page["section"]) and not pool.ready_files(page["id"]):
            store.update_page(page["id"], status="out_of_data", enabled=False)


async def post_now(page_id):
    page = store.get_page(page_id)
    if not page:
        return {"ok": False, "error": "Page not found"}
    if not page.get("section"):
        return {"ok": False, "error": "Pehle section select karo"}

    files = pool.ready_files(page_id)
    if not files:
        pool.fill_buffer(page, force=True)
        files = pool.ready_files(page_id)
    if not files:
        return {"ok": False, "error": "Data pool khali hai"}

    image = files[0]
    meta = _read_meta(image)
    if not meta:
        image.unlink(missing_ok=True)
        return {"ok": False, "error": "Image meta nahi mila, dobara dabao"}

    tags = page.get("hashtags") or []
    text = caption.build(page["section"], meta["items"], page.get("langs") or [], tags)

    dry = bool(store.get_settings().get("dry_run"))
    use_reel = bool(page.get("reel")) and page["section"] in ("islam", "english")
    video = None
    pair = []

    if use_reel:
        cat = "general" if page["section"] == "english" else (
            (meta["items"][0].get("category") or "") if meta.get("items") else "")
        if page["section"] == "islam":
            full_i, plain_i = render.render_islam_gold_pair(
                meta["items"][0], page.get("langs") or [], cat)
        else:
            full_i, plain_i = render.render_english_clean_pair(
                meta["items"], page.get("langs") or [], page.get("brand_name"))
        pair = [full_i, plain_i]
        video, _m = reel.build(
            image, page["section"], cat, page.get("reel_mode") or "zoom",
            plain_path=plain_i, full_path=full_i,
            use_music=(True if page["section"] == "islam"
                       else bool(page.get("reel_music", True))))
        if not video:
            for p in pair:
                p.unlink(missing_ok=True)
            return {"ok": False, "error": "Reel ban nahi payi (music ya render fail)"}

    try:
        if not dry:
            if video:
                await poster.post_reel(page, video, text)
            else:
                await poster.post_photo(page, image, text)
    except Exception as e:
        if video:
            video.unlink(missing_ok=True)
        for p in pair:
            p.unlink(missing_ok=True)
        store.update_page(page_id, status="error", last_err=str(e)[:200],
                          fail_count=(page.get("fail_count") or 0) + 1)
        return {"ok": False, "error": str(e)[:200]}

    if video and not dry:
        video.unlink(missing_ok=True)
    for p in pair:
        p.unlink(missing_ok=True)

    if page["section"] == "news":
        for it in (meta.get("items") or []):
            news.mark_posted(it.get("url"))

    image.unlink(missing_ok=True)
    image.with_suffix(".json").unlink(missing_ok=True)

    fresh = store.get_page(page_id)
    if fresh:
        store.update_page(page_id,
                          last_post_at=datetime.now(TZ).isoformat(),
                          posted_count=(fresh.get("posted_count") or 0) + 1,
                          status="idle", fail_count=0)
        if len(pool.ready_files(page_id)) <= 1:
            pool.fill_buffer(fresh)

    return {"ok": True, "dry": dry, "reel": bool(video), "caption": text}


async def _run_page(page_id):
    while not _stop.is_set():
        page = store.get_page(page_id)
        if not page or not page["enabled"]:
            return

        target = _plan(page)
        store.update_page(page_id, next_post_at=target.isoformat(), status="waiting")

        wait = (target - datetime.now(TZ)).total_seconds()
        if wait > 0:
            try:
                await asyncio.wait_for(_stop.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass
            if _stop.is_set():
                return

        page = store.get_page(page_id)
        if not page or not page["enabled"]:
            return
        try:
            await _post_once(page)
        except Exception:
            store.update_page(page_id, status="error")
        await asyncio.sleep(1)


async def _supervise():
    while not _stop.is_set():
        try:
            pages = {p["id"]: p for p in store.get_pages()}
            for pid, t in list(_tasks.items()):
                if t.done() or pid not in pages or not pages[pid]["enabled"]:
                    _tasks.pop(pid, None)
                    if not t.done():
                        t.cancel()
            for pid, page in pages.items():
                if page["enabled"] and pid not in _tasks:
                    _tasks[pid] = asyncio.create_task(_run_page(pid))
                    print("[sched] task created", pid)
        except Exception as e:
            print("[sched] supervise error", e)
        await asyncio.sleep(5)


def start():
    global _loop
    _loop = asyncio.get_running_loop()
    _stop.clear()
    asyncio.create_task(_supervise())


def _restart_now(page_id):
    t = _tasks.pop(page_id, None)
    if t:
        t.cancel()
    page = store.get_page(page_id)
    if page and page["enabled"] and page_id not in _tasks:
        _tasks[page_id] = asyncio.create_task(_run_page(page_id))


def restart(page_id):
    if _loop is None:
        return
    _loop.call_soon_threadsafe(_restart_now, page_id)


def stop():
    _stop.set()
    for t in _tasks.values():
        t.cancel()
    _tasks.clear()