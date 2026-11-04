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


async def post_reel(page, video_path, message):
    token = page["access_token"]
    pid = page["id"]
    size = video_path.stat().st_size

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            f"{config.GRAPH}/{pid}/video_reels",
            data={"upload_phase": "start", "access_token": token},
        )
        try:
            data = r.json()
        except Exception:
            data = {}
        if r.status_code >= 400 or "error" in data:
            raise PostError((data.get("error") or {}).get("message") or f"start HTTP {r.status_code}")

        video_id = data.get("video_id")
        upload_url = data.get("upload_url")
        if not video_id or not upload_url:
            raise PostError(f"start: no upload_url ({data})")

        with open(video_path, "rb") as fh:
            up = await client.post(
                upload_url,
                headers={
                    "Authorization": f"OAuth {token}",
                    "offset": "0",
                    "file_size": str(size),
                },
                content=fh.read(),
            )
        if up.status_code >= 400:
            raise PostError(f"upload HTTP {up.status_code}: {up.text[:160]}")

        f = await client.post(
            f"{config.GRAPH}/{pid}/video_reels",
            data={
                "upload_phase": "finish",
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": message,
                "access_token": token,
            },
        )
        try:
            fdata = f.json()
        except Exception:
            fdata = {}
        if f.status_code >= 400 or "error" in fdata:
            raise PostError((fdata.get("error") or {}).get("message") or f"finish HTTP {f.status_code}")

    return video_id