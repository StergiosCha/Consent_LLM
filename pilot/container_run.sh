#!/bin/sh
# Runs inside the Azure container: one process per model, all in parallel, then exits.
# MODELS and RUN_ARGS come from the container's environment; keys from its secure environment.
cd "${PILOT_DIR:-/pilot}"
mkdir -p logs
OUT=$(echo "$RUN_ARGS" | sed -n 's/.*--out \([^ ]*\).*/\1/p'); OUT=${OUT:-outputs}
pids=""
for m in $MODELS; do
  python3 -u run_pilot.py --config config.json --cases cases_news.csv $RUN_ARGS --models "$m" > "logs/$m.txt" 2>&1 &
  pids="$pids $!"
done
( while true; do date; wc -l "$OUT"/*.jsonl 2>/dev/null; sleep 60; done ) &
mon=$!
wait $pids
kill $mon 2>/dev/null
date; wc -l "$OUT"/*.jsonl 2>/dev/null; grep -h "error" logs/*.txt | head -n 20
echo "ALL DONE"
