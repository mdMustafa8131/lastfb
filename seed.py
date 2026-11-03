import os
from pathlib import Path

_libs = Path(__file__).resolve().parent / "libs"
if _libs.exists():
    os.environ["PATH"] = str(_libs) + os.pathsep + os.environ["PATH"]
    os.add_dll_directory(str(_libs))
import pool
import queue

queue.add_items("english", [
    {"english": "The early morning air feels different when you have slept well.",
     "bangla": "ভালো ঘুমের পর ভোরের বাতাস অন্যরকম লাগে।",
     "hindi": "अच्छी नींद के बाद सुबह की हवा अलग लगती है।",
     "hinglish": "Achhi neend ke baad subah ki hawa alag lagti hai."},
    {"english": "Small habits build a life quietly.",
     "bangla": "ছোট অভ্যাস নিঃশব্দে একটি জীবন গড়ে তোলে।",
     "hindi": "छोटी आदतें चुपचाप एक जीवन बनाती हैं।",
     "hinglish": "Chhoti aadatein chupchap ek zindagi banati hain."},
    {"english": "Silence is often the loudest answer.",
     "bangla": "নীরবতা প্রায়ই সবচেয়ে জোরে উত্তর।",
     "hindi": "मौन अक्सर सबसे तेज़ उत्तर होता है।",
     "hinglish": "Maun aksar sabse tez jawab hota hai."},
    {"english": "What does it mean to be truly patient?",
     "bangla": "সত্যিই ধৈর্যশীল হওয়ার মানে কী?",
     "hindi": "सच में धैर्यवान होने का मतलब क्या है?",
     "hinglish": "Sach me dhairyavan hone ka matlab kya hai?"},
] * 3)

queue.add_items("islam", [
    {"hadith_roman": "Actions are judged by intentions, and every person will get what he intended.",
     "english": "Actions are judged by intentions, and every person will get what he intended.",
     "bangla": "কর্মের মূল্যায়ন নিয়তের ভিত্তিতে, আর প্রত্যেকে তাই পাবে যা সে নিয়ত করেছে।",
     "source": "Sahih al-Bukhari 1"},
])