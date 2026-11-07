TAGS = {"hindi": "HI", "bangla": "BN", "hinglish": "HG", "english": "EN"}

TRANS_ISLAM = ("bangla", "english", "hindi", "hinglish")
TRANS_ENG = ("bangla", "hindi", "hinglish")


def _clean(s):
    return (s or "").strip()


def build(section, items, langs, tags):
    langs = langs or []
    tag_line = " ".join(tags or []).strip()
    parts = []

    if section == "news":
        it = items[0]
        parts.append(_clean(it.get("title")))
        if it.get("url"):
            parts.append("")
            parts.append(it["url"])
        if tag_line:
            parts.append("")
            parts.append(tag_line)
        return "\n".join(parts).strip()

    it = items[0]
    if section == "english":
        head = _clean(it.get("english"))
        if head:
            parts.append(head)
        keys = TRANS_ENG
    else:
        head = _clean(it.get("hadith_roman"))
        if head:
            parts.append(head)
        keys = TRANS_ISLAM

    for k in keys:
        if k not in langs:
            continue
        val = _clean(it.get(k))
        if val and val != head:
            parts.append("")
            parts.append(val)

    if section != "english":
        src = _clean(it.get("source"))
        if src:
            parts.append("")
            parts.append("— " + src)

    if tag_line:
        parts.append("")
        parts.append(tag_line)

    return "\n".join(parts).strip()