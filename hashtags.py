import random
import re
import time

import httpx

CACHE_TTL = 1800
_cache = {}

TREND_SOURCES = [
    "https://trends24.in/india/",
    "https://trends24.in/bangladesh/",
    "https://trends24.in/worldwide/",
]

NICHE_SOURCES = {
    "islam": [
        "https://best-hashtags.com/hashtag/islam/",
        "https://best-hashtags.com/hashtag/hadith/",
        "https://best-hashtags.com/hashtag/quran/",
    ],
    "english": [
        "https://best-hashtags.com/hashtag/quotes/",
        "https://best-hashtags.com/hashtag/motivation/",
        "https://best-hashtags.com/hashtag/life/",
    ],
}

FALLBACK = {
    "english": [
        "love", "life", "motivation", "quotes", "dailyquotes", "inspiration",
        "mindset", "success", "growth", "positivity", "selflove", "thoughts",
        "quoteoftheday", "explore", "trending", "viral", "reels", "foryou",
        "knowledge", "learning", "wisdom", "peace", "calm", "bangla",
        "bengali", "banglaquotes", "hindi", "hindiquotes", "india", "desi",
        "goodvibes", "gratitude", "patience", "dailypost", "aesthetic",
    ],
    "islam": [
        "islam", "islamic", "quran", "hadith", "sunnah", "allah", "deen",
        "muslim", "islamicquotes", "islamicreminder", "dua", "blessed",
        "sabr", "tawakkul", "alhamdulillah", "subhanallah", "islamicpost",
        "dawah", "ummah", "bangla", "bengali", "hindi", "urdu", "romanurdu",
        "translation", "knowledge", "wisdom", "peace", "gratitude",
        "dailyreminder", "faith", "iman", "taqwa",
    ],
}

_HEX = re.compile(r"^[0-9a-fA-F]{6}$")
_TAG_RE = re.compile(r"#([A-Za-z][A-Za-z0-9_]{1,28})")
_BAD = {"follow", "followme", "like4like", "l4l", "f4f", "instadaily",
        "repost", "share", "tag", "tags", "hashtag", "hashtags"}


def _clean(tag):
    t = tag.strip().strip("#").strip()
    if not t or len(t) < 3:
        return None
    low = t.lower()
    if low in _BAD or _HEX.match(t) or low.isdigit():
        return None
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", t):
        return None
    return t


def _scrape(url):
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        if r.status_code != 200:
            return []
        return _TAG_RE.findall(r.text)
    except Exception:
        return []


def _collect(urls, limit):
    out, seen = [], set()
    for url in urls:
        for raw in _scrape(url):
            t = _clean(raw)
            if not t:
                continue
            low = t.lower()
            if low in seen:
                continue
            seen.add(low)
            out.append(t)
        if len(out) >= limit:
            break
    return out


def pool_tags(section=None):
    key = section or "all"
    stamp_key = key + "_at"
    if _cache.get(key) and time.time() - _cache.get(stamp_key, 0) < CACHE_TTL:
        return _cache[key]

    trending = _collect(TREND_SOURCES, 60)
    niche = _collect(NICHE_SOURCES.get(section or "", []), 60)

    seen = {t.lower() for t in trending}
    merged = trending + [t for t in niche if t.lower() not in seen]

    if len(merged) < 30:
        for t in FALLBACK.get(section) or FALLBACK["english"] + FALLBACK["islam"]:
            if t.lower() in seen:
                continue
            seen.add(t.lower())
            merged.append(t)

    _cache[key] = merged
    _cache[stamp_key] = time.time()
    return merged


def pick(count=20, minimum=20, maximum=40, section=None):
    tags = pool_tags(section) or FALLBACK["english"]
    n = max(minimum, min(maximum, count or minimum))
    n = min(n, len(tags))
    return ["#" + t for t in random.sample(tags, n)]