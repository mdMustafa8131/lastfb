import asyncio
import edge_tts


async def main():
    c = edge_tts.Communicate("Hello there my friend.", "en-IN-PrabhatNeural")
    async for ch in c.stream(boundary="WordBoundary"):
        print(ch["type"], list(ch.keys()))


asyncio.run(main())