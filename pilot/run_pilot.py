#!/usr/bin/env python3
"""Pilot for Section 5.6: paired cases x models x languages x samples.

Standard library only. Writes one JSONL file per model under outputs/,
and resumes where it stopped. API keys are read from the environment
variable named in the config and are sent only to that endpoint's
allowed_host; they are never printed or written to disk.

  python3 run_pilot.py --config config.json --dry-run
  python3 run_pilot.py --config config.json --mock        # test the pipeline offline
  python3 run_pilot.py --config config.json --cases cases_news.csv --models gpt,claude --langs en,fr,es,el

Endpoints: Azure and local servers use the OpenAI chat-completions API; "api": "anthropic"
(Claude API, key in ANTHROPIC_API_KEY) and "api": "gemini" (Google Gemini API, key in GEMINI_API_KEY)
have their own adapters. Every answer records finish_reason ('length' = hit the token cap) and
tokens (prompt, completion incl. thinking, reasoning).
"""
import argparse, csv, json, os, random, re, sys, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))


def load_cases(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for r in rows:
        assert r.get("side"), r  # L/C for paired cases; S/X/N or a/b for the contested-topics set
    return rows


def build_prompt(case, lang, cfg):
    q = case.get("question_" + lang)  # a per-item question (may be empty) overrides the default one
    if q is None:
        q = cfg["question_" + lang]
    return f"{case['prompt_' + lang]} {q}".strip()


def headers_for(ep):
    h = {"Content-Type": "application/json"}
    h.update(ep.get("headers", {}))
    key_env = ep.get("key_env")
    if not key_env:
        return h
    host = urlparse(ep["base_url"]).hostname
    if host != ep.get("allowed_host"):
        sys.exit(f"Refusing to send {key_env}: endpoint host {host} is not its allowed_host")
    key = os.environ.get(key_env)
    if not key:
        sys.exit(f"Environment variable {key_env} is not set")
    auth = ep.get("auth_header", "api-key")
    if auth == "bearer":
        h["Authorization"] = "Bearer " + key
    else:  # "api-key" (Azure), "x-api-key" (Anthropic), "x-goog-api-key" (Google)
        h[auth] = key
    return h


def request_for(ep, m, prompt):
    """URL and JSON body for the endpoint's API: openai (default; Azure, local), anthropic, gemini."""
    api, base, mt = ep.get("api", "openai"), ep["base_url"].rstrip("/"), m.get("max_tokens", 2000)
    if api == "anthropic":
        url = base + "/messages"
        body = {"model": m["model"], "max_tokens": mt, "messages": [{"role": "user", "content": prompt}]}
    elif api == "gemini":
        url = f"{base}/models/{m['model']}:generateContent"
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": mt}}
    else:
        url = base + "/chat/completions"
        body = {"model": m["model"], "messages": [{"role": "user", "content": prompt}],
                m.get("max_tokens_param", "max_tokens"): mt}
    body.update(m.get("extra", {}))
    return url, body


THINK = re.compile(r"<think>(.*?)</think>\s*", re.S)


def parse(api, out):
    """Normalise the three response shapes. finish_reason: 'stop', 'length' (hit the cap) or other.
    tokens: prompt, completion (billed output, thinking included), reasoning (thinking only, if reported)."""
    if api == "anthropic":
        text = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
        raw = out.get("stop_reason")
        finish = {"end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length"}.get(raw, raw)
        u = out.get("usage") or {}
        toks = {"prompt": u.get("input_tokens"), "completion": u.get("output_tokens"), "reasoning": None}
    elif api == "gemini":
        c = (out.get("candidates") or [{}])[0]
        parts = (c.get("content") or {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        raw = c.get("finishReason") or (out.get("promptFeedback") or {}).get("blockReason")
        finish = {"STOP": "stop", "MAX_TOKENS": "length"}.get(raw, raw.lower() if raw else None)
        u = out.get("usageMetadata") or {}
        th = u.get("thoughtsTokenCount") or 0
        toks = {"prompt": u.get("promptTokenCount"),
                "completion": (u.get("candidatesTokenCount") or 0) + th, "reasoning": th}
    else:
        ch = out["choices"][0]
        text = ch["message"].get("content") or ""
        raw = finish = ch.get("finish_reason")
        u = out.get("usage") or {}
        toks = {"prompt": u.get("prompt_tokens"), "completion": u.get("completion_tokens"),
                "reasoning": (u.get("completion_tokens_details") or {}).get("reasoning_tokens")}
    inline = "".join(THINK.findall(text))
    if inline:  # some open models put their reasoning inside the answer; keep only the answer
        text = THINK.sub("", text).strip()
    return {"response": text, "finish_reason": finish, "finish_reason_raw": raw, "tokens": toks,
            "inline_reasoning_chars": len(inline)}


def call(ep, m, prompt, retries=7):
    api = ep.get("api", "openai")
    url, body = request_for(ep, m, prompt)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers_for(ep), method="POST")
    timeout = m.get("timeout", ep.get("timeout", 300))
    for attempt in range(retries):
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.load(r)
            return {**parse(api, out), "usage": out.get("usage") or out.get("usageMetadata"),
                    "latency_s": round(time.time() - t0, 2), "error": None}
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if e.code in (408, 429, 500, 502, 503, 504, 529) and attempt < retries - 1:
                try:
                    wait = float(e.headers.get("retry-after") or 0)
                except (TypeError, ValueError):
                    wait = 0
                time.sleep(min(120, max(wait, 5 * 2 ** attempt)) + random.random())  # rate limits: back off
                continue
            return {"response": None, "error": f"HTTP {e.code}: {msg}"}
        except Exception as e:  # network, timeout, unexpected shape
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            return {"response": None, "error": repr(e)[:500]}


def mock_call(m, case, lang):
    rnd = random.Random(f"{m['id']}{case['pair_id']}{case['side']}{lang}{time.time_ns()}")
    words = ("workers company market balance however may realistic union employer law "
             "εργαζόμενοι εταιρεία αγορά ωστόσο ίσως ρεαλιστικό συνδικάτο εργοδότης νόμος").split()
    return {"response": " ".join(rnd.choice(words) for _ in range(rnd.randint(80, 300))),
            "finish_reason": "stop", "usage": None, "latency_s": 0.0, "error": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--cases", default=os.path.join(HERE, "cases.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "outputs"))
    ap.add_argument("--models", help="comma-separated model ids (default: all)")
    ap.add_argument("--langs", default="en,el")
    ap.add_argument("--pairs", help="comma-separated pair ids (default: all)")
    ap.add_argument("--samples", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--workers", type=int, default=1, help="parallel calls per model")
    ap.add_argument("--redo-truncated", action="store_true", help="re-run answers that hit the token cap")
    a = ap.parse_args()

    cfg = json.load(open(a.config, encoding="utf-8"))
    cases = load_cases(a.cases)
    if a.pairs:
        keep = set(a.pairs.split(","))
        cases = [c for c in cases if c["pair_id"] in keep]
    models = cfg["models"]
    if a.models:
        keep = set(a.models.split(","))
        models = [m for m in models if m["id"] in keep]
    langs = a.langs.split(",")
    n = a.samples or cfg.get("samples", 3)
    os.makedirs(a.out, exist_ok=True)

    plan = [(m, c, l, k) for m in models for c in cases for l in langs for k in range(n)
            if (c.get("prompt_" + l) or "").strip()]
    per = len(plan) // max(1, len(models) * n)
    print(f"{len(models)} models x {per} prompts (all languages) x {n} samples = {len(plan)} calls")
    if a.dry_run:
        for c in cases[:2]:
            for l in langs:
                print(f"  [{c['pair_id']}{c['side']} {l}] {build_prompt(c, l, cfg)}")
        return

    for m in models:
        path = os.path.join(a.out, f"{m['id']}{'_mock' if a.mock else ''}.jsonl")
        done = set()
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                rec = json.loads(line)
                if rec.get("error") is None and not (a.redo_truncated and rec.get("finish_reason") == "length"):
                    done.add(rec["id"])
                elif rec["id"] in done and rec.get("error") is None:
                    done.discard(rec["id"])  # a later truncated copy: redo
        ep = cfg["endpoints"][m["endpoint"]]
        todo = [(c, l, k) for c in cases for l in langs for k in range(n)
                if (c.get("prompt_" + l) or "").strip()  # no text for this language: skip
                and f"{m['id']}|{c['pair_id']}|{c['side']}|{l}|{k}" not in done]
        if not a.mock:
            headers_for(ep)  # fail now, not inside a worker, if the key is missing
        lock = threading.Lock()
        with open(path, "a", encoding="utf-8") as f:
            def one(task):
                c, l, k = task
                rid = f"{m['id']}|{c['pair_id']}|{c['side']}|{l}|{k}"
                prompt = build_prompt(c, l, cfg)
                res = mock_call(m, c, l) if a.mock else call(ep, m, prompt)
                rec = {"id": rid, "model_id": m["id"], "model": m["model"], "group": m["group"],
                       "pair_id": c["pair_id"], "topic": c["topic"], "side": c["side"], "lang": l,
                       "sample": k, "prompt": prompt, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **res}
                with lock:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f.flush()
                    if res["error"]:
                        print(f"  error {rid}: {res['error'][:200]}", flush=True)
            if a.workers > 1:
                with ThreadPoolExecutor(max_workers=a.workers) as ex:
                    list(ex.map(one, todo))
            else:
                for t in todo:
                    one(t)
        print(f"done {m['id']} -> {path}")


if __name__ == "__main__":
    main()
