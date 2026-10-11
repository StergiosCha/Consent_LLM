#!/bin/bash
# Run the pilot in an Azure Container Instance, so the Mac can sleep.
#   ./azure_pilot.sh smoke          start: 5 pairs, 1 sample, the seven new models
#   ./azure_pilot.sh full           start: all 40 pairs, 3 samples, all ten commercial models
#   ./azure_pilot.sh contested      start: full contested set (93 items, English and Greek, 3 samples = 558 answers per model; keeps what is done)
#   ./azure_pilot.sh claude         start: Claude Fable 5.1 + Opus 5.5 on the recent set (writes into outputs_recent)
#   ./azure_pilot.sh recent         start: Iran and recent-events items (13 prompts, English and Greek, 3 samples = 78 per model), own share
#   ./azure_pilot.sh status smoke   progress (or: status full)
#   ./azure_pilot.sh fetch smoke    download the answers into this folder (or: fetch full)
#   ./azure_pilot.sh delete smoke   remove the finished container (or: delete full)
# Needs: az login, and AZURE_OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY exported in this Terminal.
# Keys go to the container as secure environment variables only; they are not written to any file.
set -euo pipefail
# Your Azure names go in azure.env next to this script (not tracked by git); see azure.env.example.
[ -f "$(dirname "$0")/azure.env" ] && . "$(dirname "$0")/azure.env"
RG=${AZ_RESOURCE_GROUP:?set AZ_RESOURCE_GROUP in azure.env}
LOC=${AZ_LOCATION:-swedencentral}
SA=${AZ_STORAGE_ACCOUNT:?set AZ_STORAGE_ACCOUNT in azure.env}
SHARE=propaganda-pilot
HERE="$(cd "$(dirname "$0")" && pwd)"
mode=${1:-}; which=${2:-$mode}
case $which in
  smoke) NAME=pilot-smoke; OUT=outputs_smoke
         MODELS="astra grok47 claude gemini deepseek kimi llama33"
         ARGS="--pairs N05,N17,N27,N33,N39 --langs en,fr,es,el --samples 1 --out outputs_smoke" ;;
  full)  NAME=pilot-full; OUT=outputs
         MODELS="gpt grok mistral astra grok47 claude gemini deepseek kimi llama33"
         ARGS="--langs en,fr,es,el --out outputs --workers 4" ;;
  contested) NAME=pilot-contested; OUT=outputs_contested
         # claude removed 11 Oct 2026: Anthropic API credits used up (its 558 contested answers are complete)
         MODELS="gpt grok mistral astra grok47 gemini deepseek kimi llama33"
         ARGS="--cases cases_contested.csv --langs en,el --samples 3 --out outputs_contested --workers 25 --redo-truncated"; TOTAL=558 ;;
  recent) NAME=pilot-recent; OUT=outputs_recent; SHARE=propaganda-recent; TOTAL=78
         # Claude excluded: Anthropic API credits used up
         MODELS="gpt grok mistral astra grok47 gemini deepseek kimi llama33"
         ARGS="--cases cases_recent.csv --langs en,el --samples 3 --out outputs_recent --workers 10 --redo-truncated" ;;
  claude) NAME=pilot-claude; OUT=outputs_recent; SHARE=propaganda-recent; TOTAL=78
         # Anthropic models on the recent set only: Claude Fable 5.1 and Claude Opus 5.5 (prepaid credits)
         MODELS="claude opus"
         ARGS="--cases cases_recent.csv --langs en,el --samples 3 --out outputs_recent --workers 4 --redo-truncated" ;;
  *) sed -n '2,9p' "$0"; exit 1 ;;
esac
K=$(az storage account keys list -g $RG -n $SA --query '[0].value' -o tsv)

case $mode in
  smoke|full|contested|recent|claude)
    : "${AZURE_OPENAI_API_KEY:?export AZURE_OPENAI_API_KEY first}"
    : "${ANTHROPIC_API_KEY:?export ANTHROPIC_API_KEY first}"
    : "${GEMINI_API_KEY:?export GEMINI_API_KEY first}"
    az storage share-rm create -g $RG --storage-account $SA --name $SHARE --quota 5 -o none 2>/dev/null || true
    for f in run_pilot.py config.json cases_news.csv cases_contested.csv cases_recent.csv container_run.sh; do
      az storage file upload --account-name $SA --account-key "$K" --share-name $SHARE \
        --source "$HERE/$f" --path "$f" --no-progress -o none
    done
    az container delete -g $RG -n $NAME -y -o none 2>/dev/null || true
    az container create -g $RG -n $NAME -l $LOC --image python:3.12-slim --os-type Linux \
      --cpu 1 --memory 1.5 --restart-policy Never \
      --azure-file-volume-account-name $SA --azure-file-volume-account-key "$K" \
      --azure-file-volume-share-name $SHARE --azure-file-volume-mount-path /pilot \
      --environment-variables "MODELS=$MODELS" "RUN_ARGS=$ARGS" \
      --secure-environment-variables "AZURE_OPENAI_API_KEY=$AZURE_OPENAI_API_KEY" \
        "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" "GEMINI_API_KEY=$GEMINI_API_KEY" \
      --command-line "/bin/sh /pilot/container_run.sh" -o none
    echo "started $NAME. Check with: ./azure_pilot.sh status $which" ;;
  status)
    az container show -g $RG -n $NAME --query "instanceView.state" -o tsv
    az container logs -g $RG -n $NAME | tail -n 25 ;;
  fetch)
    mkdir -p "$HERE/$OUT" "$HERE/logs_$which"
    az storage file download-batch --account-name $SA --account-key "$K" --source $SHARE \
      --destination "$HERE" --pattern "$OUT/*" --no-progress -o none
    az storage file download-batch --account-name $SA --account-key "$K" --source $SHARE \
      --destination "$HERE/logs_$which" --pattern "logs/*" --no-progress -o none
    wc -l "$HERE/$OUT"/*.jsonl ;;
  new)
    az storage file download-batch --account-name $SA --account-key "$K" --source $SHARE \
      --destination "$HERE" --pattern "$OUT/*" --no-progress -o none
    python3 - "$HERE/$OUT" "${TOTAL:-558}" <<'PY'
import json, glob, os, sys
T = int(sys.argv[2])
print(f"answers done per model (English + Greek, 3 samples), out of {T}:")
for f in sorted(glob.glob(os.path.join(sys.argv[1], "*.jsonl"))):
    recs = [json.loads(x) for x in open(f)]
    ok = sum(1 for d in recs if not d.get("error"))
    el = sum(1 for d in recs if d.get("lang") == "el" and not d.get("error"))
    print(f"  {os.path.basename(f)[:-6]:9s} {ok:3d} / {T}   (Greek {el} / {T//2})")
PY
    ;;
  delete)
    az container delete -g $RG -n $NAME -y -o none && echo "deleted $NAME" ;;
  *) sed -n '2,9p' "$0"; exit 1 ;;
esac
