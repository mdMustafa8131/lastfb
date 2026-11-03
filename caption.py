TAGS = {"hindi": "HI", "bangla": "BN", "hinglish": "HG", "english": "EN"}


def build(section, items, langs, tags):
    tag_line = " ".join(tags)
    parts = []

    if section == "news":
        it = items[0]
        parts.append(it.get("title", "").strip())
        if it.get("url"):
            parts.append("")
            parts.append(it["url"])
        parts.append("")
        parts.append(tag_line)
        return "\n".join(parts).strip()