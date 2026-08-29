"""列出每把 key 實際能呼叫哪些模型。python try_models.py"""
import time

from dotenv import load_dotenv

load_dotenv()
from google import genai
from google.genai import types

from app import gemini

keys = gemini._keys()
print(f"{len(keys)} 把 key\n")

for ki, key in enumerate(keys):
    c = gemini._client_for(key)
    print(f"=== key #{ki} ({key[:8]}…) ===")
    for m in gemini._MODELS:
        try:
            r = c.models.generate_content(
                model=m, contents="回一個字", config=types.GenerateContentConfig(max_output_tokens=50)
            )
            print(f"  OK    {m}")
        except Exception as e:
            msg = str(e).splitlines()[0][:90]
            print(f"  FAIL  {m}  -> {msg}")
        time.sleep(2)
    print()
