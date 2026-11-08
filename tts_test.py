import asyncio
import voice

p, d = asyncio.run(voice.build([
    ("english", "Actions are judged by intentions."),
    ("hinglish", "Niyat ke hisaab se amal ka hukm hai."),
], "male"))
print(p, d)