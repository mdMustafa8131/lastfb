import httpx

import config


class PostError(Exception):
    pass


async def post_photo(page, image_path, message):
    url = f"{config.GRAPH}/{page['id']}/photos"
    async with httpx.AsyncClient(timeout=120) as client:
        with open(image_path, "rb") as fh:
            r = await client.post(
                url,
                data={"message": message, "access_token": page["access_token"]},
                files={"source": (image_path.name, fh, "image/jpeg")},
            )
    try:
        data = r.json()
    except Exception:
        data = {}
    if r.status_code >= 400 or "error" in data:
        raise PostError((data.get("error") or {}).get("message") or f"HTTP {r.status_code}")
    return data.get("id")