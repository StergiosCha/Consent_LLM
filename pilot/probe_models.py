#!/usr/bin/env python3
"""One tiny call per model in config.json, to check deployment names and keys before a run.

  python3 probe_models.py                          # every model whose key is set
  python3 probe_models.py --models astra,claude,gemini

If an Azure model rejects its token-limit parameter, the other one is tried and, if it works,
config.json is updated. Nothing else is written; keys are read from the environment only.
"""
import argparse, json, os
import run_pilot as rp

ap = argparse.ArgumentParser()
ap.add_argument("--config", default=os.path.join(rp.HERE, "config.json"))
ap.add_argument("--models")
a = ap.parse_args()
cfg = json.load(open(a.config, encoding="utf-8"))
models = cfg["models"]
if a.models:
    keep = set(a.models.split(","))
    models = [m for m in models if m["id"] in keep]

PROMPT = "Reply with the single word OK."
fixed = {}
for m in models:
    ep = cfg["endpoints"][m["endpoint"]]
    if "FILL-IN" in m["model"]:
        print(f"skip {m['id']:9s} no model name yet")
        continue
    if ep.get("key_env") and not os.environ.get(ep["key_env"]):
        print(f"skip {m['id']:9s} {ep['key_env']} is not set in this Terminal")
        continue
    res = rp.call(ep, m, PROMPT, retries=2)
    err = res["error"] or ""
    if err and ep.get("api", "openai") == "openai" and ("max_tokens" in err or "max_completion_tokens" in err):
        other = "max_tokens" if m.get("max_tokens_param") == "max_completion_tokens" else "max_completion_tokens"
        res2 = rp.call(ep, dict(m, max_tokens_param=other), PROMPT, retries=2)
        if not res2["error"]:
            fixed[m["id"]] = other
            res, err = res2, ""
    if err:
        hint = "  (deploy it in Azure Foundry, or tell Claude the deployment name)" if "DeploymentNotFound" in err or "404" in err else ""
        print(f"FAIL {m['id']:9s} {m['model']}: {err[:220]}{hint}")
    else:
        print(f"OK   {m['id']:9s} {m['model']}: {res['response'].strip()[:20]!r} finish={res['finish_reason']} tokens={res['tokens']}")

if fixed:
    for m in cfg["models"]:
        if m["id"] in fixed:
            m["max_tokens_param"] = fixed[m["id"]]
    json.dump(cfg, open(a.config, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("config.json updated:", ", ".join(f"{k} uses {v}" for k, v in fixed.items()))
