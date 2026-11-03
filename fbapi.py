import httpx

import config


class FBError(Exception):
    pass


async def _get(path, params):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{config.GRAPH}{path}", params=params)
    data = r.json()
    if r.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        raise FBError(err.get("message") or f"Graph error {r.status_code}")
    return data


async def fetch_me(user_token):
    return await _get("/me", {"access_token": user_token, "fields": "id,name"})


async def fetch_pages(user_token):
    data = await _get(
        "/me/accounts",
        {
            "access_token": user_token,
            "fields": "id,name,category,access_token",
            "limit": 100,
        },
    )
    return data.get("data", [])