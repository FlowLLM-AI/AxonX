#!/usr/bin/env bash
set -euo pipefail

# Requires a running AxonX service, an installed a158 plugin, and historical
# Tushare partitions. The download step refreshes only the last seven days.
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
cd "$repo_root"

command -v axonx >/dev/null || { echo "axonx command not found" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 command not found" >&2; exit 1; }

echo "Installing Alpha158 plugin..." >&2
axonx plugin install plugins/a158 >&2

task_catalog=$(axonx exec)
for task in download_tushare_task a158_etl a158_factor a158_train a158_predict a158_backtest; do
    if ! grep -q "^${task}[[:space:]]" <<< "$task_catalog"; then
        echo "Task ${task} is not installed. Reinstall the a158 plugin before running this pipeline." >&2
        exit 1
    fi
done

submit_and_wait() {
    local stage=$1
    shift
    local response handle task_id run_id wait_response

    echo "Submitting ${stage}..." >&2
    response=$(axonx submit "$@") || return 1
    handle=$(printf '%s' "$response" | python3 -c '
import json, sys
response = json.load(sys.stdin)
if not response.get("success"):
    raise SystemExit("Submission failed: %s" % response.get("answer"))
print(response["answer"]["task_id"], response["answer"]["run_id"], sep="\t")
') || return 1
    IFS=$'\t' read -r task_id run_id <<< "$handle"
    echo "${stage}: ${task_id}" >&2

    if ! wait_response=$(axonx --timeout 86400 wait_task --task-id "$task_id" --run-id "$run_id"); then
        echo "${stage} failed: ${wait_response}" >&2
        return 1
    fi
    echo "${stage} succeeded" >&2
    printf '%s\n' "$task_id"
}

# The native and plugin tasks are submitted by their registered names.
submit_and_wait "Tushare download" --task download_tushare_task --days-back 7 >/dev/null
etl_id=$(submit_and_wait "Alpha158 ETL" --task a158_etl --start-date 20150101)
submit_and_wait "Factor analysis" --task a158_factor --source-tasks "[\"${etl_id}\"]" >/dev/null
train_id=$(submit_and_wait "LightGBM training" --task a158_train --source-tasks "[\"${etl_id}\"]" --train-start 20150101)
predict_id=$(submit_and_wait "Prediction" --task a158_predict --source-tasks "[\"${train_id}\"]")
backtest_id=$(submit_and_wait "Backtest" --task a158_backtest --source-tasks "[\"${predict_id}\"]")

echo "Pipeline complete: ${backtest_id}"
