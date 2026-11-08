import csv
import io
from datetime import datetime

import config
import pool

MAX_ITEMS = 5000
CATS = {"qabr", "jahannam", "jannat", "general"}


def _clean(row):
    return [c.strip() for c in row]


def _split_cat(source):
    if ":" in source:
        s, _, c = source.rpartition(":")
        c = c.strip().lower()
        if c in CATS:
            return s.strip(), c
    return source, "general"


def _lang_of(text):
    for ch in str(text or ""):
        if ch in "।॥":
            continue
        o = ord(ch)
        

def parse_english(text, mapping=None, lang=None):
    out, errors = [], []
    for i, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        row = _clean(row)
        if not any(row):
            continue
        if mapping:
            mp = mapping
        elif len(row) == 2 and lang:
            mp = ["english", lang]
        else:
            mp = ["english", "bangla", "hindi", "hinglish"]
        item = {"english": "", "bangla": "", "hindi": "", "hinglish": ""}
        for idx, col in enumerate(row):
            if idx >= len(mp):
                break
            k = mp[idx]
            if k in item and col and not item[k]:
                item[k] = col
        if not item["english"]:
            errors.append(f"line {i}: sentence (english) khali ya column 1 me nahi")
            continue
        out.append(item)
    return out, errors


def parse_islam(text, mapping=None, lang=None):
    out, errors = [], []
    mp = mapping or ["hadith_roman", "bangla", "hinglish", "source"]
    for i, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        row = _clean(row)
        if not any(row):
            continue
        item = {"hadith_roman": "", "english": "", "bangla": "",
                "hindi": "", "hinglish": ""}
        source = ""
        for idx, col in enumerate(row):
            if idx >= len(mp):
                break
            k = mp[idx]
            if not col:
                continue
            if k == "source":
                source = col
            elif k in item and not item[k]:
                item[k] = col
        if not item["hadith_roman"]:
            errors.append(f"line {i}: hadith khali")
            continue
        source, category = _split_cat(source)
        if not source:
            errors.append(f"line {i}: source zaroori hai")
            continue
        item["source"] = source
        item["category"] = category
        out.append(item)
    return out, errors

PARSERS = {"english": parse_english, "islam": parse_islam}
KEYS = {"english": ("english", "bangla", "hindi", "hinglish"),
        "islam": ("hadith_roman", "english", "bangla", "hindi", "source")}


def archive(filename, raw):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c for c in filename if c.isalnum() or c in "._-")[:60]
    dest = config.ARCHIVE_DIR / f"{stamp}_{safe}"
    dest.write_text(raw, "utf-8")
    return dest


def import_text(section, text, lang=None, mapping=None):
    parser = PARSERS[section]
    keys = KEYS[section]
    items, errors = parser(text, lang, mapping)

    existing = {tuple(str(i.get(k, "")).strip() for k in keys)
                for i in pool.load_pool(section)}

    added, dup = [], 0
    for it in items:
        sig = tuple(str(it.get(k, "")).strip() for k in keys)
        if sig in existing:
            dup += 1
            continue
        existing.add(sig)
        added.append(it)
        if len(added) >= MAX_ITEMS:
            break

    if added:
        pool.add_items(section, added)

    return {
        "ok": True,
        "added": len(added),
        "duplicate": dup,
        "errors": errors[:30],
        "error_count": len(errors),
        "remaining": pool.remaining(section),
    }