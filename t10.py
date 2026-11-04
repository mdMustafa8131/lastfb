import asyncio
import store, config, httpx


async def go():
    p = store.get_page("770827062784222")
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(
            f"{config.GRAPH}/{p['id']}/posts",
            params={"fields": "created_time,status_type,permalink_url",
                    "limit": 3, "access_token": p["access_token"]},
        )
    print(r.text[:700])


asyncio.run(go())