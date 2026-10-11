#!/usr/bin/env python3
"""Greek/English token ratios on a parallel corpus (replaces the one-sentence
measurement of 25 August 2026 that Section 4.2 currently rests on).

Input: two line-aligned files (one sentence per line), e.g. FLORES+ devtest
eng_Latn and ell_Grek (1012 sentences; gated on Hugging Face, accept the
terms first), or any aligned EU text.

Local tokenizers need:  pip install tiktoken transformers sentencepiece
Hosted models (Azure) use the prompt-token difference method of the August
measurement: usage.prompt_tokens(text) - usage.prompt_tokens(minimal text),
on chunks of 50 sentences to keep the number of calls small.

  python3 tokenisation_parallel.py --en en.txt --el el.txt --hf ilsp/Meltemi-7B-v1.5 Qwen/Qwen2.5-7B \
      --tiktoken o200k_base cl100k_base
  AZURE_AI_KEY=... python3 tokenisation_parallel.py --en en.txt --el el.txt --azure-config config.json --azure-models gpt grok
"""
import argparse, json, os, random, statistics, sys


def ratios(counts_en, counts_el, n_boot=2000, seed=0):
    tot = sum(counts_el) / sum(counts_en)
    per = [b / a for a, b in zip(counts_en, counts_el) if a > 0]
    rnd = random.Random(seed)
    idx = list(range(len(counts_en)))
    boots = []
    for _ in range(n_boot):
        s = rnd.choices(idx, k=len(idx))
        boots.append(sum(counts_el[i] for i in s) / sum(counts_en[i] for i in s))
    boots.sort()
    return {"corpus_ratio": round(tot, 3), "ci95": [round(boots[int(.025 * n_boot)], 3), round(boots[int(.975 * n_boot)], 3)],
            "median_sentence_ratio": round(statistics.median(per), 3), "n": len(counts_en),
            "tokens_en": sum(counts_en), "tokens_el": sum(counts_el)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--en", required=True); ap.add_argument("--el", required=True)
    ap.add_argument("--hf", nargs="*", default=[])
    ap.add_argument("--tiktoken", nargs="*", default=[])
    ap.add_argument("--azure-config"); ap.add_argument("--azure-models", nargs="*", default=[])
    ap.add_argument("--out", default="tokenisation_results.json")
    a = ap.parse_args()
    en = [l.rstrip("\n") for l in open(a.en, encoding="utf-8")]
    el = [l.rstrip("\n") for l in open(a.el, encoding="utf-8")]
    assert len(en) == len(el), "files are not line-aligned"
    res = {}
    for enc in a.tiktoken:
        import tiktoken
        t = tiktoken.get_encoding(enc)
        res[f"tiktoken:{enc}"] = ratios([len(t.encode(x)) for x in en], [len(t.encode(x)) for x in el])
        print(enc, res[f"tiktoken:{enc}"])
    for name in a.hf:
        from transformers import AutoTokenizer
        t = AutoTokenizer.from_pretrained(name)
        f = lambda x: len(t(x, add_special_tokens=False)["input_ids"])
        res[f"hf:{name}"] = ratios([f(x) for x in en], [f(x) for x in el])
        print(name, res[f"hf:{name}"])
    if a.azure_models:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from run_pilot import headers_for
        import urllib.request
        cfg = json.load(open(a.azure_config, encoding="utf-8"))
        def prompt_tokens(ep, m, text):
            body = {"model": m["model"], "messages": [{"role": "user", "content": text}], m.get("max_tokens_param", "max_tokens"): 16}
            req = urllib.request.Request(ep["base_url"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                         headers=headers_for(ep), method="POST")
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)["usage"]["prompt_tokens"]
        for mid in a.azure_models:
            m = next(x for x in cfg["models"] if x["id"] == mid)
            ep = cfg["endpoints"][m["endpoint"]]
            base = prompt_tokens(ep, m, ".")
            ce, cg = [], []
            for i in range(0, len(en), 50):
                ce.append(prompt_tokens(ep, m, "\n".join(en[i:i + 50])) - base)
                cg.append(prompt_tokens(ep, m, "\n".join(el[i:i + 50])) - base)
            res[f"azure:{mid}"] = ratios(ce, cg)
            print(mid, res[f"azure:{mid}"])
    json.dump(res, open(a.out, "w", encoding="utf-8"), indent=1)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
