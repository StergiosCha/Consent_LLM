# Consent_LLM

Prompts, code and raw model answers for the pilot study of **"Who Manufactures the Answer?"**, a position paper
that extends Herman and Chomsky's propaganda model to large language models.

Authors: Devdatt Dubhashi (Chalmers University of Technology), Stergios Chatzikyriakidis (Institute for Language
and Speech Processing, Athena Research Center), Gerardo Schneider (University of Gothenburg).

**Status (October 2026): pilot data.** The answers are complete records of what each model said. The readings
reported so far are first readings; blind coding by independent coders is under way. Nothing here should be cited
as an established finding yet.

## The idea in one paragraph

Herman and Chomsky described five filters that shape the news: ownership, advertising, sourcing, flak and
ideology. The paper relocates these filters to the LLM pipeline (capital and compute, commercial objectives,
training data and retrieval, regulation and scandal, alignment policy) and adds three that have no analogue in mass
media: **synthesis** (contested sources merged into one answer), **consensus** (pressure towards a single agreeable
answer) and **language** (models built and aligned in English, used in many other languages). Because a model can
be asked the same question under controlled variations, these filters can be tested, which was the standing
criticism of the original model. The pilot uses Herman and Chomsky's own method: paired cases that are comparable
in kind but differ in whose interests are at stake ("worthy and unworthy victims").

## Item sets

| File | Study | Size | Design |
|---|---|---|---|
| `pilot/cases_news.csv` | 1. Labour and capital | 40 news-seeded pairs | Side `L` (workers, households, claimants) against side `C` (firms, owners). English for all pairs; French, Spanish or Greek for 15 pairs |
| `pilot/cases_contested.csv` | 2. Contested geopolitics | 93 items, 186 prompts | Source swaps, same-standard pairs, loaded premises in both directions, each model asked about its own developer |
| `pilot/cases_recent.csv` | 3. Recent events and Iran | 13 prompts | Events from September and October 2026, after every model's training data: the same brief of public facts with a different speaker; two airliner shootdowns; a CIA sentence on the 1953 coup; a control item; a news-writing swap |
| `pilot/cases.csv` | (first draft of study 1) | 40 pairs | Invented pairs, kept for reference |

Conditions (`side` column):

- `S` the real source, `X` the same words credited to a swapped source, `N` no source;
- `a` / `b` the two cases of a same-standard pair (for example Iraq 2003 / Russia 2022);
- `L` / `C` in study 1;
- in the own-developer items (`O1`, `O2`) the side is the developer asked about.

`real_source` and `source_url` give the origin of every quoted passage. Notes on sources: `pilot/contested_items_2026-10-11.md`,
`pilot/ukraine_texts_2026-10-11.md`, `pilot/news_candidates_2026-10-10.md`.

## Models

| id | Model | Developer | Access |
|---|---|---|---|
| `gpt` | GPT-5.5 | OpenAI | Azure |
| `astra` | GPT-6 Astra | OpenAI | Azure |
| `grok` | Grok 4.3 | xAI | Azure |
| `grok47` | Grok 4.7 | xAI | Azure |
| `mistral` | Mistral Large 3 | Mistral AI | Azure |
| `deepseek` | DeepSeek-V4-Pro | DeepSeek | Azure |
| `kimi` | Kimi K2.6 | Moonshot AI | Azure |
| `llama33` | Llama 3.3 70B Instruct | Meta | Azure |
| `claude` | Claude Fable 5.1 | Anthropic | Claude API |
| `opus` | Claude Opus 5.5 (study 3 only) | Anthropic | Claude API |
| `gemini` | Gemini 3.8 Flash | Google | Gemini API |

No system prompt, provider-default sampling, three samples per prompt. Public and locally run models (Qwen, Krikri,
Apertus, OLMo) are configured but not yet run.

## Data

| Folder | Run | Answers |
|---|---|---|
| `pilot/outputs_smoke/` | Smoke test, 5 pairs, 1 sample | 160 |
| `pilot/outputs/` | Study 1, all 40 pairs | 3,298 (one Azure content-filter block, one missing) |
| `pilot/outputs_contested/` | Study 2, English and Greek | 4,637 of 5,580; run in progress for six models |
| `pilot/outputs_recent/` | Study 3, English and Greek, 11 models | 858 |

One JSONL file per model. Each line is one call:

- `id` is `model|item|side|lang|sample`;
- `prompt` is the exact text sent and `response` the answer (any inline `<think>` block removed);
- `finish_reason` is `stop` or `length` (cut off at the token limit);
- `tokens` holds prompt, completion and reasoning tokens;
- `error` is `null` on success.

Runs are resumable and append to the files, so when an id appears more than once the **last** successful record is
the one to use. Some Greek answers from Mistral were cut off at the token limit; they are marked `length`.

`pilot/results/` holds the study 1 tables (`summary.csv`, `pairs.csv`, `results_table.tex`) and the coding sheet for
human annotation (`coding_sheet.csv`). The draft codebook for study 2 is `docs/CODEBOOK_contested.md`.

## Running

Python 3.10 or later; the scripts use only the standard library.

API keys are never written to any file. Export them in your shell:

```
export AZURE_OPENAI_API_KEY=...   ANTHROPIC_API_KEY=...   GEMINI_API_KEY=...
```

Each endpoint in `pilot/config.json` names the environment variable that holds its key and the one host the key may
be sent to (`allowed_host`); the runner refuses to send a key anywhere else. Put your Azure resource in `base_url`
and `allowed_host`, and your deployment names in `models`.

From `pilot/`:

```
python3 probe_models.py --models gpt,claude,gemini        # one tiny call per model
python3 run_pilot.py --cases cases_recent.csv --langs en,el --samples 3 --out outputs_recent --models gpt --dry-run
python3 run_pilot.py --cases cases_recent.csv --langs en,el --samples 3 --out outputs_recent --models gpt --workers 10
python3 run_pilot.py --mock ...                            # offline test with dummy answers
```

`azure_pilot.sh` runs the same jobs in an Azure Container Instance (keys passed as secure environment variables
only). Copy `azure.env.example` to `azure.env` and fill in your resource group and storage account first.

## Analysis

- `analyse.py`: study 1 measures (length, hedging, "realism" and legality vocabulary, party mentions) with
  bootstrap intervals.
- `eval_contested.py`: keyword indicators for study 2. These only locate answers worth reading; negations defeat
  them, so they are not evidence on their own.
- `docs/CODEBOOK_contested.md`: draft codebook for blind coding.
- `tokenisation_parallel.py`: Greek/English token ratios on a parallel corpus.

## Caveats

- The items were designed by the authors with the help of an AI assistant (Claude), and two Claude models are among
  those tested. The first readings were also made with Claude's help. For that reason the coding is being done blind
  by models from other developers and checked by the authors.
- The Greek prompts of study 3 are drafts awaiting revision by a native speaker; the Greek half will be re-run.
- In study 3, item `R4` side `X` (a US bomb in Bandar Abbas) is a made-up event by design: it keeps the facts of the
  real Kramatorsk strike and swaps only the attacker and place.
- `R1` and `R2` pair two different real incidents; a counterfactual with the countries swapped is planned to
  separate the speaker from the evidence.
- Training cutoffs differ by model and affect items about 2024 and 2025 events.
- One wording per item and three samples per prompt.

## Licence

To be decided.
