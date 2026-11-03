import hashlib
import html
import json
import random
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from xml.etree import ElementTree as ET


try:
    import feedparser
except ModuleNotFoundError:      # feedparser na ho to bhi app boot ho jaye
    class _EmptyFeed(dict):
        entries = []

    class _FeedShim:
        @staticmethod
        def parse(*a, **k):
            return _EmptyFeed()

    feedparser = _FeedShim()
import httpx

import config

CAT_FILE = config.DATA_DIR / "news_categories.json"
POOL_FILE = config.DATA_DIR / "pool" / "news.json"
POOL_FILE.parent.mkdir(parents=True, exist_ok=True)

POSTED_FILE = config.DATA_DIR / "news_posted.json"
DEBUG_FILE = config.DATA_DIR / "news_debug.log"
COOLDOWN_H = 8
TREND_RSS = "https://trends.google.com/trending/rss?geo={geo}"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
      "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8"}
RSS_UA = dict(UA, **{"Accept": "application/rss+xml, application/xml, text/xml, */*"})

REGIONS = {
    "in": ("IN", "en-IN"), "us": ("US", "en-US"), "gb": ("GB", "en-GB"),
    "bd": ("BD", "en-BD"), "ae": ("AE", "en-AE"), "world": ("US", "en-US"),
}

GEO_SLUG = {"in": "india", "us": "united-states", "gb": "united-kingdom",
            "bd": "bangladesh", "ae": "united-arab-emirates", "world": "worldwide"}

SUBS = ("worldnews", "india", "IndianNews", "Cricket", "bollywood")

FEEDS = [
    "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "https://feeds.feedburner.com/ndtvnews-india-news",
    "https://www.thehindu.com/news/national/feeder/default.rss",
    "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml",
    "https://timesofindia.indiatimes.com/rssfeeds/1081479906.cms",
    "https://feeds.feedburner.com/ndtvmovies-latest",
    "https://indianexpress.com/section/entertainment/feed/",
    "https://www.thehindu.com/entertainment/feeder/default.rss",
    "https://www.hindustantimes.com/feeds/rss/entertainment/rssfeed.xml",
    "https://indianexpress.com/section/politics/feed/",
    "https://timesofindia.indiatimes.com/rssfeeds/4719148.cms",
    "https://feeds.feedburner.com/ndtvnews-sports-news",
    "https://www.scoopwhoop.com/rss/",
    "https://storypick.com/feed/",
    "https://www.thebetterindia.com/feed/",
    "https://indianexpress.com/section/sports/feed/",
    "https://www.thehindu.com/sport/feeder/default.rss",
    "https://www.hindustantimes.com/feeds/rss/cricket/rssfeed.xml",
    "https://indianexpress.com/section/technology/feed/",
    "https://www.thehindu.com/sci-tech/technology/feeder/default.rss",
    "https://indianexpress.com/section/business/feed/",
    "https://www.thehindu.com/business/feeder/default.rss",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://indianexpress.com/section/lifestyle/feed/",
    "https://www.thehindu.com/life-and-style/feeder/default.rss",
]

BAD_IMG = ("news.google.com", "gstatic.com", "googleusercontent.com",
           "google.com/images", "google.com/logos", "favicon", "sprite",
           "logo", "placeholder", "1x1", "blank.", "bing.com/th", "data:image")
JUNK_TAGS = {"text", "error", "footer", "header", "body", "html", "css", "js",
             "svg", "path", "main", "content", "title", "nav", "menu", "link",
             "button", "input", "form", "list", "item", "box", "wrap", "container"}
_SAFE = re.compile(r"[^\w\s\-\.,'\"()\[\]:;!?/&%$#@+*=<>|~`^{}\u0900-\u097F\u0980-\u09FF]", re.U)

_DEBUG = []


def _dbg(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print("[news]", msg)
    _DEBUG.append(line)
    try:
        with DEBUG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _hash(url):
    return hashlib.sha1((url or "").encode("utf-8", "ignore")).hexdigest()[:16]


# ---------- categories ----------
BUILTIN_CATS = [{"id": "viral", "name": "Viral & Trending (auto)", "keywords": []}]


def load_cats():
    if not CAT_FILE.exists():
        return []
    try:
        return json.loads(CAT_FILE.read_text("utf-8"))
    except Exception:
        return []


def all_cats():
    return BUILTIN_CATS + load_cats()


def save_cats(cats):
    CAT_FILE.write_text(json.dumps(cats, ensure_ascii=False, indent=2), "utf-8")


def add_cat(name, keywords):
    cats = load_cats()
    cat = {"id": uuid.uuid4().hex[:8], "name": name.strip(),
           "keywords": [k.strip() for k in keywords if k.strip()]}
    cats.append(cat)
    save_cats(cats)
    return cat


def del_cat(cat_id):
    save_cats([c for c in load_cats() if c["id"] != cat_id])


# ---------- 8h cooldown ----------
def load_posted():
    if not POSTED_FILE.exists():
        return {}
    try:
        return json.loads(POSTED_FILE.read_text("utf-8"))
    except Exception:
        return {}


def save_posted(d):
    POSTED_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")


def prune_posted():
    now = time.time()
    d = {k: v for k, v in load_posted().items() if now - v < COOLDOWN_H * 3600}
    save_posted(d)
    return d


def is_cooled(url):
    v = load_posted().get(_hash(url))
    return bool(v) and (time.time() - v) < COOLDOWN_H * 3600


def mark_posted(url):
    if not url:
        return
    prune_posted()
    d = load_posted()
    d[_hash(url)] = time.time()
    save_posted(d)


# ---------- keywords ----------
def google_trends(region="in", limit=10):
    geo = REGIONS.get(region, REGIONS["in"])[0]
    out = []
    try:
        r = httpx.get(TREND_RSS.format(geo=geo), timeout=20, headers=RSS_UA,
                      follow_redirects=True)
        _dbg(f"trends geo={geo} status={r.status_code}")
        if r.status_code != 200:
            return out
        root = ET.fromstring(r.text)
        for it in root.iter("item"):
            t = (it.findtext("title") or "").strip()
            if t and t.lower() not in [x.lower() for x in out]:
                out.append(t)
            if len(out) >= limit:
                break
    except Exception as e:
        _dbg(f"trends fail: {e}")
    return out


def x_hashtags(region="in", limit=3):
    slug = GEO_SLUG.get(region, "worldwide")
    out = []
    for u in (f"https://trends24.in/{slug}/", "https://trends24.in/"):
        try:
            r = httpx.get(u, timeout=20, headers=UA, follow_redirects=True)
            _dbg(f"hashtags {u} status={r.status_code} len={len(r.text)}")
            if r.status_code != 200:
                continue
            found = []
            for p in (r"twitter\.com/search\?q=%23([A-Za-z0-9_]{2,30})",
                      r"x\.com/search\?q=%23([A-Za-z0-9_]{2,30})",
                      r">#([A-Za-z][A-Za-z0-9_]{2,30})<"):
                found += re.findall(p, r.text)
            _dbg(f"hashtags raw={len(found)} sample={found[:8]}")
            for m in found:
                if m.lower() in JUNK_TAGS:
                    continue
                if m.lower() not in [x.lower().lstrip("#") for x in out]:
                    out.append("#" + m)
                if len(out) >= limit:
                    return out
        except Exception as e:
            _dbg(f"hashtags fail {u}: {e}")
    return out[:limit]


# ---------- feeds ----------
def _one_feed(url):
    try:
        r = httpx.get(url, timeout=12, headers=RSS_UA, follow_redirects=True)
        if r.status_code != 200:
            return []
        return feedparser.parse(r.content).entries[:15]
    except Exception:
        return []


def img_from_entry(e):
    for a in ("media_content", "media_thumbnail"):
        v = getattr(e, a, None)
        if v and isinstance(v, list) and v[0].get("url"):
            return v[0]["url"]
    for l in getattr(e, "links", []) or []:
        if (l.get("type") or "").startswith("image") or l.get("rel") == "enclosure":
            if l.get("href"):
                return l.get("href")
    for en in getattr(e, "enclosures", []) or []:
        if (en.get("type") or "").startswith("image") and en.get("href"):
            return en["href"]
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', getattr(e, "description", "") or "")
    return html.unescape(m.group(1)) if m else ""


def _feeds(limit=400):
    out = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for ents in ex.map(_one_feed, FEEDS):
            for e in ents:
                title = (getattr(e, "title", "") or "").strip()
                link = getattr(e, "link", "") or ""
                if not title or not link:
                    continue
                out.append({"title": title, "url": link, "source": "",
                            "origin": "feed", "image": img_from_entry(e), "ts": 0})
                if len(out) >= limit:
                    break
            if len(out) >= limit:
                break
    _dbg(f"feeds items={len(out)}")
    return out


# ---------- google / bing / reddit ----------
def _google(query, region, limit):
    ceid = REGIONS.get(region, REGIONS["in"])
    q = httpx.QueryParams({"q": query})["q"]
    url = (f"https://news.google.com/rss/search?q={q}&hl={ceid[1]}"
           f"&gl={ceid[0]}&ceid={ceid[0]}:{ceid[1][-2:]}")
    out = []
    try:
        r = httpx.get(url, timeout=20, headers=RSS_UA, follow_redirects=True)
        ok = r.status_code == 200 and "<rss" in r.text[:600].lower()
        _dbg(f"google q='{query[:24]}' status={r.status_code} rss={ok}")
        if not ok:
            return out
        root = ET.fromstring(r.text)
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            if not title or not link:
                continue
            src = it.findtext("{http://news.google.com/rss}source") or ""
            out.append({"title": title, "url": link, "source": src,
                        "origin": "google", "image": "", "ts": 0})
            if len(out) >= limit:
                break
    except Exception as e:
        _dbg(f"google fail: {e}")
    return out


def _bing(query, region, limit):
    ceid = REGIONS.get(region, REGIONS["in"])
    out = []
    try:
        r = httpx.get("https://www.bing.com/news/search",
                      params={"q": query, "format": "rss", "cc": ceid[0]},
                      timeout=20, headers=RSS_UA, follow_redirects=True)
        ok = r.status_code == 200 and "<rss" in r.text[:600].lower()
        _dbg(f"bing q='{query[:24]}' status={r.status_code} rss={ok}")
        if not ok:
            return out
        root = ET.fromstring(r.text)
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            if not title or not link:
                continue
            out.append({"title": title, "url": link, "source": "",
                        "origin": "bing", "image": "", "ts": 0})
            if len(out) >= limit:
                break
    except Exception as e:
        _dbg(f"bing fail: {e}")
    return out


def _rjson(r):
    try:
        if "json" not in (r.headers.get("content-type") or ""):
            return {}
        return r.json()
    except Exception:
        return {}
RUA = {"User-Agent": "fbengine/1.0 (news bot)"}
INDIAN_SUBS = ("india", "IndianNews", "IndiaSpeaks", "Cricket", "bollywood")

def _reddit_rss(sub, limit):
    out = []
    for host in ("https://www.reddit.com", "https://old.reddit.com"):
        try:
            r = httpx.get(f"{host}/r/{sub}/top/.rss", params={"t": "day"},
                          timeout=20, headers=RSS_UA, follow_redirects=True)
            _dbg(f"reddit rss r/{sub} {host} status={r.status_code}")
            if r.status_code != 200:
                continue
            for e in feedparser.parse(r.content).entries[:limit]:
                title = (e.title or "").strip()
                link = e.link or ""
                if not title or not link:
                    continue
                out.append({"title": title, "url": link, "source": "r/" + sub,
                            "image": "", "origin": "reddit", "ts": 0, "eng": 0})
            if out:
                return out
        except Exception as e:
            _dbg(f"reddit rss fail r/{sub}: {e}")
    return out


def _arctic(sub, limit):
    out = []
    try:
        r = httpx.get("https://arctic-shift.photon-reddit.com/api/posts/search",
                      params={"subreddit": sub, "limit": min(limit, 25)},
                      timeout=25, headers=RUA, follow_redirects=True)
        _dbg(f"arctic r/{sub} status={r.status_code}")
        for d in _rjson(r).get("data", []):
            title = (d.get("title") or "").strip()
            link = "https://reddit.com" + (d.get("permalink") or "")
            img = d.get("url") if _is_img(d.get("url")) else ""
            if not title:
                continue
            out.append({"title": title, "url": link, "source": "r/" + sub,
                        "image": img, "origin": "reddit",
                        "ts": d.get("created_utc") or 0, "eng": d.get("score", 0)})
            if len(out) >= limit:
                break
    except Exception as e:
        _dbg(f"arctic fail r/{sub}: {e}")
    return out


def _reddit(sub, limit):
    out = []
    try:
        r = httpx.get(f"https://www.reddit.com/r/{sub}/top.json",
                      params={"t": "day", "limit": min(limit, 50), "raw_json": 1},
                      timeout=20, headers=RUA, follow_redirects=True)
        _dbg(f"reddit r/{sub} status={r.status_code}")
        for c in _rjson(r).get("data", {}).get("children", []):
            d = c.get("data", {})
            title = (d.get("title") or "").strip()
            p = (d.get("preview", {}) or {}).get("images", [])
            img = html.unescape(p[0]["source"]["url"]) if p else (
                d.get("url") if d.get("post_hint") == "image" else "")
            if not title:
                continue
            out.append({"title": title,
                        "url": "https://reddit.com" + (d.get("permalink") or ""),
                        "source": "r/" + sub, "image": img or "",
                        "origin": "reddit", "ts": d.get("created_utc") or 0,
                        "eng": d.get("score", 0)})
            if len(out) >= limit:
                break
    except Exception as e:
        _dbg(f"reddit fail r/{sub}: {e}")
    if out:
        return out

    out = _reddit_rss(sub, limit)
    if out:
        return out
    return _arctic(sub, limit)

SUB_BONUS = {"india": 2.5, "IndianNews": 2.0, "IndiaSpeaks": 1.2,
             "Cricket": 0.6, "bollywood": 0.0}


def reddit_top(limit=5):
    raw = []
    for s in INDIAN_SUBS:
        raw += _reddit(s, 20)

    seen, cand = set(), []
    for it in raw:
        h = _hash(it["url"])
        if h in seen or is_cooled(it["url"]):
            continue
        seen.add(h)
        it["id"] = h
        it["title"] = _clean_title(it["title"])
        if not it["title"]:
            continue
        cand.append(it)

    for it in cand:
        it["score"] = round(min(8, (it.get("eng") or 0) / 400)
                            + max(0, 3 - _age_h(it) / 8)
                            + SUB_BONUS.get((it.get("source") or "").replace("r/", ""), 0), 3)
    cand.sort(key=lambda x: x["score"], reverse=True)

    out, per = [], {}
    for it in cand:
        if len(out) >= limit:
            break
        s = it.get("source") or ""
        if per.get(s, 0) >= 2:
            continue
        if any(_similar(it["title"], p["title"]) for p in out):
            continue
        if not _ok_img(it.get("image")):
            it["image"] = _og_image(it["url"]) or _bing_img(it["title"])
        if not _img_ok_live(it["image"], it["url"]):
            it["image"] = ""
            continue
        per[s] = per.get(s, 0) + 1
        out.append(it)

    if len(out) < limit:
        for it in cand:
            if len(out) >= limit:
                break
            if it in out or any(_similar(it["title"], p["title"]) for p in out):
                continue
            out.append(it)
    return out

STOP = {"this", "that", "with", "from", "after", "over", "into", "will", "have",
        "been", "were", "what", "when", "where", "which", "their", "there",
        "about", "while", "says", "said", "amid", "more", "than", "then"}


def _t24_tags(slug, limit=5, skip=()):
    out = []
    skip = {s.lower() for s in skip}
    try:
        r = httpx.get(f"https://trends24.in/{slug}/", timeout=20, headers=UA,
                      follow_redirects=True)
        if r.status_code != 200:
            return out
        found = []
        for p in (r"twitter\.com/search\?q=%23([A-Za-z0-9_]{2,30})",
                  r"x\.com/search\?q=%23([A-Za-z0-9_]{2,30})",
                  r">#([A-Za-z][A-Za-z0-9_]{2,30})<"):
            found += re.findall(p, r.text)
        for m in found:
            if m.lower() in JUNK_TAGS or m.lower() in skip:
                continue
            if m.lower() not in [x.lower() for x in out]:
                out.append(m)
            if len(out) >= limit:
                break
    except Exception:
        pass
    return out

def _gn_topic(region="in"):
    ceid = REGIONS.get(region, REGIONS["in"])
    try:
        r = httpx.get("https://news.google.com/rss",
                      params={"hl": ceid[1], "gl": ceid[0],
                              "ceid": f"{ceid[0]}:{ceid[1][-2:]}"},
                      timeout=20, headers=RSS_UA, follow_redirects=True)
        if r.status_code != 200:
            return ""
        for e in feedparser.parse(r.content).entries[:10]:
            words = [w for w in re.findall(r"[A-Za-z]{4,}", e.title or "")
                     if w.lower() not in STOP]
            if words:
                return words[0]
    except Exception:
        pass
    return ""
def tag_to_keyword(tag):
    t = (tag or "").lstrip("#").replace("_", " ")
    t = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def hot_tags():
    out, skip = [], set()
    x = _t24_tags("india")
    if x:
        out.append("#" + x[0])
        skip.add(x[0].lower())
    for t in google_trends("us", 6):
        h = re.sub("[^\\w\u0900-\u097F\u0980-\u09FF]", "", t)
        if 3 <= len(h) <= 22 and h.lower() not in skip:
            out.append("#" + h)
            skip.add(h.lower())
            break
    if len(out) < 2:
        w = _t24_tags("worldwide", skip=skip)
        if w:
            out.append("#" + w[0])
            skip.add(w[0].lower())
    for t in google_trends("in", 6):
        h = re.sub(r"[^\w]", "", t)
        if 3 <= len(h) <= 22 and h.lower() not in skip:
            out.append("#" + h)
            skip.add(h.lower())
            break
    g = _gn_topic()
    if g and g.lower() not in skip:
        out.append("#" + g)
        skip.add(g.lower())
    if len(out) < 4:
        for t in google_trends("in", 10):
            h = re.sub(r"[^\w]", "", t)
            if 3 <= len(h) <= 22 and h.lower() not in skip:
                out.append("#" + h)
                skip.add(h.lower())
            if len(out) >= 4:
                break
    return list(dict.fromkeys(out))[:4]

# ---------- image helpers ----------
def _is_img(url):
    return bool(url) and str(url).lower().split("?")[0].endswith(
        (".jpg", ".jpeg", ".png", ".webp"))


def _ok_img(url):
    if not url or not str(url).startswith("http"):
        return False
    low = str(url).lower()
    return not any(b in low for b in BAD_IMG)


def _img_ok_live(url, ref=None):
    if not _ok_img(url):
        return False
    h = dict(UA)
    if ref:
        h["Referer"] = ref
    try:
        with httpx.stream("GET", url, timeout=15, headers=h,
                          follow_redirects=True) as r:
            if r.status_code != 200:
                return False
            if "image" not in (r.headers.get("content-type") or ""):
                return False
            cl = int(r.headers.get("content-length") or 0)
            if cl and cl < 12000:
                return False
            got = 0
            for chunk in r.iter_bytes(4096):
                got += len(chunk)
                if got >= 8192:
                    return True
            return got > 2000
    except Exception:
        return False


def _clean_title(t):
    t = _SAFE.sub(" ", t or "")
    t = re.sub(r"^\[[^\]]{1,30}\]\s*", "", t)
    t = re.sub(r"\s+", " ", t).strip(" -–—|·")
    return t[:160]


def _split_source(title):
    m = re.match(r"^(.*?)\s+[-–—]\s+([^-–—]{2,32})$", title or "")
    if m and len(m.group(1)) > 15:
        return m.group(1).strip(), m.group(2).strip()
    return (title or "").strip(), ""


def _domain(url):
    try:
        h = (httpx.URL(url).host or "").lower()
    except Exception:
        return ""
    for p in ("www.", "m.", "amp."):
        if h.startswith(p):
            h = h[len(p):]
    return h


def _bing_img(query):
    q = " ".join(str(query).split()[:7])
    try:
        r = httpx.get("https://www.bing.com/images/search",
                      params={"q": q, "form": "HDRSC2", "first": 1,
                              "qft": "+filterui:imagesize-large"},
                      timeout=20, headers=UA, follow_redirects=True)
        if r.status_code != 200:
            return ""
        for c in re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', r.text):
            if not _is_img(c) or not _ok_img(c):
                continue
            if re.search(r"(logo|icon|sprite|thumb|avatar)", c.lower()):
                continue
            return c
    except Exception:
        pass
    return ""


def _og_image(url):
    try:
        r = httpx.get(url, timeout=20, headers=UA, follow_redirects=True)
        for m in re.finditer(
                r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']'
                r'[^>]+content=["\']([^"\']+)', r.text, re.I):
            u = html.unescape(m.group(1))
            if _ok_img(u):
                return u
    except Exception:
        pass
    return ""


# ---------- scoring ----------
def _tag_words(tag):
    return [w.lower() for w in re.split(r"[#_\s]+", tag or "") if len(w) > 3]


def _kw_hits(title, keywords):
    t = (title or "").lower()
    return sum(1 for k in keywords if any(w in t for w in _tag_words(k)))

def _age_h(it):
    ts = it.get("ts")
    if ts:
        return max(0.0, (time.time() - ts) / 3600)
    return 4.0


def score_item(it, keywords, pos, total):
    hits = _kw_hits(it.get("title"), keywords)
    pos_score = (total - pos) / max(1, total) * 3
    fresh_score = max(0.0, 3 - _age_h(it) / 8)
    return round(hits * 3 + pos_score + fresh_score, 3)


def _similar(a, b):
    wa = {w.lower() for w in re.findall(r"\w+", a) if len(w) > 3}
    wb = {w.lower() for w in re.findall(r"\w+", b) if len(w) > 3}
    return len(wa & wb) >= 3

def fetch_scored(mode="auto", region="in", sub="worldnews", category=None,
                 keyword=None, limit=5):
    _DEBUG.clear()
    _dbg(f"--- start reddit mode limit={limit}")

    cand = reddit_top(limit * 3)
    _dbg(f"reddit items={len(cand)}")
    if not cand:
        raise ValueError("Reddit se kuch nahi mila — dobara try karo")

    picked = []
    for it in cand:
        if len(picked) >= limit:
            break
        if any(_similar(it["title"], p["title"]) for p in picked):
            continue
        it["source"] = it.get("source") or "reddit"
        picked.append(it)

    _dbg(f"final={len(picked)} with_img={sum(1 for i in picked if _ok_img(i.get('image')))}")
    return {"keywords": [], "tags": [], "items": picked, "debug": list(_DEBUG)}

def probe(query="top stories", region="in", sub="worldnews"):
    _DEBUG.clear()
    res = {"keywords": google_trends(region, 5), "hashtags": x_hashtags(region, 3)}
    f = _feeds(40)
    res["feeds"] = {"count": len(f),
                    "with_img": sum(1 for i in f if _ok_img(i.get("image")))}
    res["debug"] = list(_DEBUG)
    return res


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "auto"
    kw = sys.argv[2] if len(sys.argv) > 2 else None
    
    if m == "red":
        for it in reddit_top(8):
            print(f'{it["score"]:>6}  {it["source"]:<14} img={int(_ok_img(it["image"]))}  '
                  f'{it["title"][:70]}')
        raise SystemExit
    
    if m == "hot":
        for t in hot_tags():
            print(t)
        raise SystemExit

    if m == "probe":
        print(json.dumps(probe(), ensure_ascii=False, indent=2))
        raise SystemExit

    out = fetch_scored(m, "in", "worldnews", None, kw, 5)
    print("\nkeywords:", out["keywords"])
    for it in out["items"]:
        print(f'{it["score"]:>7}  {it["source"][:22]:<22} img={int(_ok_img(it["image"]))}  '
              f'{it["title"][:70]}')
    print("total:", len(out["items"]))