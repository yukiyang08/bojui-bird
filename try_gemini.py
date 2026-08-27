"""本機測不揪鳥閒聊：python try_gemini.py 然後直接打字，Ctrl+C 離開"""
from dotenv import load_dotenv

load_dotenv()
from app import gemini

print(f"keys: {len(gemini._keys())} 把 · 模型 {gemini._models()}")
print("直接打字跟不揪鳥聊，Ctrl+C 離開\n")
while True:
    try:
        msg = input("你 > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        break
    if msg:
        print("鳥 >", gemini.chat(msg), "\n")
