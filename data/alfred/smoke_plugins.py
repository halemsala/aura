import json
import requests

API = "http://127.0.0.1:8777/api/chat"

bad = """Alfred, instala esta ferramenta
```python
TOOL_NAME = "pwn"
import os
def validate(args):
    return {}
def run(args, ctx):
    os.system("whoami")
```"""

src = open(r"C:\aura\alfred\tools\plugins\_TEMPLATE.py", encoding="utf-8").read()
# strip leading comment-only lines that are not the contract? template is valid python with comments
good = "Alfred, instala esta ferramenta\n```python\n" + src + "\n```"

print("BAD")
d = requests.post(API, json={"message": bad, "session_id": "smoke-bad"}, timeout=30).json()
print(d.get("route"), d.get("status"), d.get("requires_confirmation"))
print((d.get("reply") or "")[:500])

print("\nGOOD")
d = requests.post(API, json={"message": good, "session_id": "smoke-ok"}, timeout=30).json()
print(d.get("route"), d.get("status"), d.get("requires_confirmation"))
print((d.get("reply") or "")[:700])
