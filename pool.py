import json
import time
import uuid
import news

import config
import news_render
import render

POOL_DIR = config.DATA_DIR / "pool"
POOL_DIR.mkdir(parents=True, exist_ok=True)
BUFFER_TARGET = 3
LOW_DATA_AT = 10


def _pool_path(section):
    return POOL_DIR / f"{section}.json"


def load_pool(section):
    p = _pool_path(section)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return []


def save_pool(section, items):
    _pool_path(section).write_text(json.dumps(items, ensure_ascii=False, indent=2), "utf-8")


def remaining(section):
    return len([i for i in load_pool(section) if not i.get("used")])


def _langs(lang):
    if not lang:
        return []
    return [lang] if isinstance(lang, str) else list(lang)


def _matches(section, it, lang=None):
    if section == "news":
        if not it.get("title"):
            return False
        return not news.is_cooled(it.get("url") or "")
    if section == "english":
        if not it.get("english"):
            return False
        ls = _langs(lang)
        return True if not ls else any(bool(it.get(l)) for l in ls)
    return bool(it.get("hadith_roman"))


def remaining_lang(section, lang=None):
    return len([i for i in load_pool(section)
                if not i.get("used") and _matches(section, i, lang)])


def add_items(section, items):
    p = load_pool(section)
    for it in items:
        it["id"] = uuid.uuid4().hex[:12]
        it["used"] = False
        p.append(it)
    save_pool(section, p)
    return len(items)


def _take(section, count, lang=None):
    p = load_pool(section)
    avail = [i for i in p if not i.get("used") and _matches(section, i, lang)]
    ls = [l for l in (lang or []) if l]
    if ls:
        avail.sort(key=lambda i: sum(1 for l in ls if i.get(l)), reverse=True)
    if section == "news":
        avail.sort(key=lambda i: i.get("score") or 0, reverse=True)
    picked = avail[:count]
    if not picked:
        return []
    ids = {i["id"] for i in picked}
    for i in p:
        if i["id"] in ids:
            i["used"] = True
    save_pool(section, p)
    return picked


def ready_dir(page_id):
    d = config.READY_DIR / str(page_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def ready_files(page_id):
    d = ready_dir(page_id)
    return sorted([f for f in d.iterdir() if f.suffix.lower() == ".jpg"],
                  key=lambda f: f.stat().st_mtime)


def clear_ready(page_id):
    for f in ready_dir(page_id).iterdir():
        f.unlink(missing_ok=True)


def _need(page):
    section = page.get("section")
    if section in ("islam", "news"):
        return 1
    return max(1, min(4, int(page.get("sentences") or 4)))


def _make_news(page):
    tpl = int(page.get("template") or 1)
    for _ in range(3):
        items = _take("news", 1)
        if not items:
            return None
        item = items[0]
        img = news_render.render(item, tpl)
        if img is None:
            continue
        stamp = int(time.time() * 1000)
        out = ready_dir(page["id"]) / f"{stamp}_{uuid.uuid4().hex[:6]}.jpg"
        img.save(out, "JPEG", quality=92, optimize=True)
        out.with_suffix(".json").write_text(
            json.dumps({"items": items, "section": "news",
                        "template": tpl, "created": stamp},
                       ensure_ascii=False, indent=2), "utf-8")
        return out
    return None


def _make_one(page):
    section = page["section"]
    if section == "news":
        return _make_news(page)

    need = _need(page)
    items = _take(section, need, page.get("langs") or [])
    if not items:
        return None
    if len(items) < need:
        items = (items * need)[:need]

    img = render.render(section, items, bool(page.get("question_box", True)),
                        page.get("langs") or [], page.get("bg_mode") or "image",
                        page.get("source_color") or "#085430",
                        page.get("brand") or page.get("name"), page.get("logo"),
                        (items[0].get("category") or "general"))
    stamp = int(time.time() * 1000)
    out = ready_dir(page["id"]) / f"{stamp}_{uuid.uuid4().hex[:6]}.jpg"
    img.save(out, "JPEG", quality=92, optimize=True)
    out.with_suffix(".json").write_text(
        json.dumps({"items": items, "section": section,
                    "langs": page.get("langs") or [], "created": stamp},
                   ensure_ascii=False, indent=2), "utf-8")
    return out


def fill_buffer(page, force=False):
    if not page.get("section"):
        return 0
    have = len(ready_files(page["id"]))
    if not force and have > 1:
        return 0
    made = 0
    for _ in range(BUFFER_TARGET - have):
        if not remaining_lang(page["section"], page.get("langs") or []):
            break
        if not _make_one(page):
            break
        made += 1
    return made


def low_data(section, lang=None):
    return remaining_lang(section, lang) <= LOW_DATA_AT