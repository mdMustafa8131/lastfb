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
        


def parse_english(text, lang=None):
    out, errors = [], []
    for i, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        row = _clean(row)
        if not any(row):
            continue
        bangla = hindi = hinglish = ""
        if len(row) >= 4:
            english, bangla, hindi, hinglish = row[:4]
        elif len(row) == 2 and lang:
            english = row[0]
            if lang == "bangla":
                bangla = row[1]
            elif lang == "hindi":
                hindi = row[1]
            elif lang == "hinglish":
                hinglish = row[1]
        else:
            english = row[0] if row else ""
        if not english:
            errors.append(f"line {i}: pehla column (sentence) khali")
            continue
        out.append({"english": english, "bangla": bangla,
                    "hindi": hindi, "hinglish": hinglish})
    return out, errors


def parse_islam(text, lang=None):
    out, errors = [], []
    for i, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        row = _clean(row)
        if not any(row):
            continue

        if len(row) >= 4:
            hadith = row[0]
            trans = [row[1], row[2]]
            source = row[3]
        elif len(row) == 3:
            hadith = row[0]
            trans = [row[1]]
            source = row[2]
        elif len(row) == 2:
            hadith = row[0]
            trans = []
            source = row[1]
        else:
            errors.append(f"line {i}: format galat — hadith,translation,translation,source:category")
            continue

        if not hadith:
            errors.append(f"line {i}: hadith khali")
            continue

        source, category = _split_cat(source)
        if not source:
            errors.append(f"line {i}: source zaroori hai")
            continue

        english = bangla = ""
        for t in trans:
            if not t:
                continue
            l = _lang_of(t)
            if l == "bangla" and not bangla:
                bangla = t
            elif l == "hindi":
                hindi = t if "hindi" in locals() else t
            elif l == "english" and not english:
                english = t
            if l == "hindi":
                pass

        item = {"hadith_roman": hadith, "english": english,
                "bangla": bangla, "source": source, "category": category}
        for t in trans:
            if t and _lang_of(t) == "hindi":
                item["hindi"] = t
                break

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


def import_text(section, text, lang=None):
    parser = PARSERS[section]
    keys = KEYS[section]
    items, errors = parser(text, lang)

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