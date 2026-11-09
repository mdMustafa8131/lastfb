import json

p = "data/pages.json"
d = json.load(open(p, encoding="utf-8"))
pairs = d.items() if isinstance(d, dict) else [(i.get("id"), i) for i in d]
for k, v in pairs:
    if str(k) == "100737239401306":
        v["enabled"] = False
        v["access_token"] = ""
        print("disabled", k)
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)