#!/usr/bin/env python3
"""Find the Azure deployment names for the three commercial models and write config.json.
Needs AZURE_AI_KEY in the environment. Sends the key only to the Azure endpoint in config.example.json."""
import json, os, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "config.example.json"), encoding="utf-8"))
ep = cfg["endpoints"]["azure"]
from urllib.parse import urlparse
KEY_ENV = "AZURE_OPENAI_API_KEY" if os.environ.get("AZURE_OPENAI_API_KEY") else "AZURE_AI_KEY"
KEY = os.environ.get(KEY_ENV)
if not KEY:
    sys.exit("Set AZURE_OPENAI_API_KEY (and AZURE_OPENAI_ENDPOINT) in this Terminal first")
if os.environ.get("AZURE_OPENAI_ENDPOINT"):
    ep["base_url"] = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1"
BASE = ep["base_url"].rstrip("/")
ep["allowed_host"] = urlparse(BASE).hostname
ep["key_env"] = KEY_ENV
print("endpoint:", BASE)

def req(path, body=None, auth="api-key"):
    h = {"Content-Type": "application/json"}
    if auth == "bearer":
        h["Authorization"] = "Bearer " + KEY
    else:
        h["api-key"] = KEY
    r = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                               headers=h, method="GET" if body is None else "POST")
    with urllib.request.urlopen(r, timeout=90) as resp:
        return json.load(resp)

# 1. which auth header works, and what does /models list
auth, listed = None, []
for a in ("api-key", "bearer"):
    try:
        listed = [m.get("id", "") for m in req("/models", auth=a).get("data", [])]
        auth = a
        break
    except urllib.error.HTTPError as e:
        print(f"/models with {a}: HTTP {e.code}")
if auth is None:
    auth = "api-key"
interesting = sorted({m for m in listed if any(k in m.lower() for k in ("gpt-5", "grok", "mistral", "deepseek", "llama"))})
print("auth header:", auth)
print("models listed (filtered):", ", ".join(interesting) or "(none listed)")

# 2. try candidate deployment names with a tiny call
FAMILIES = {
    "gpt": ["gpt-5.5", "gpt-5.4", "gpt-5.1", "gpt-5"],
    "grok": ["grok-4.3", "grok-4-3", "grok-4", "grok-4-fast-reasoning"],
    "mistral": ["Mistral-Large-3", "mistral-large-3", "mistral-large-2512", "Mistral-Large-2411", "mistral-large-2411"],
}
for fam, cands in FAMILIES.items():
    extra = [m for m in interesting if fam in m.lower() and m not in cands]
    FAMILIES[fam] = cands + extra

found = {}
for fam, cands in FAMILIES.items():
    for name in cands:
        for param in ("max_completion_tokens", "max_tokens"):
            try:
                out = req("/chat/completions", {"model": name, "messages": [{"role": "user", "content": "Reply with OK."}], param: 50}, auth)
                found[fam] = (name, param)
                print(f"OK   {fam}: '{name}' ({param})")
                break
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")[:160].replace("\n", " ")
                if e.code in (400, 422) and ("max_tokens" in msg or "max_completion_tokens" in msg or "unsupported" in msg.lower()):
                    continue
                print(f"  -- {fam}: '{name}' HTTP {e.code}: {msg}")
                break
            except Exception as e:  # network error on one candidate: skip it
                print(f"  -- {fam}: '{name}' {type(e).__name__}: {str(e)[:120]}")
                break
        if fam in found:
            break
    if fam not in found:
        print(f"MISSING {fam}: none of {cands} worked; tell Claude the deployment name from the Azure portal")

# 3. write config.json
ep["auth_header"] = auth
models = []
for m in cfg["models"]:
    if m["id"] in found:
        name, param = found[m["id"]]
        m = dict(m, model=name, max_tokens_param=param, max_tokens=6000 if m["id"] == "gpt" else 2500)
        models.append(m)
    elif m["group"] == "public":
        models.append(m)
cfg["models"] = models
json.dump(cfg, open(os.path.join(HERE, "config.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("wrote config.json with:", ", ".join(f"{k}={v[0]}" for k, v in found.items()))
