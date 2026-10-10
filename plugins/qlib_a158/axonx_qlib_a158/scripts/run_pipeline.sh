#!/usr/bin/env bash
set -euo pipefail

# Requires a running AxonX service, an installed qlib_a158 plugin, and historical
# Tushare partitions. The download step refreshes only the last 14 days.

# CLI connection settings are loaded from the caller's working directory.

command -v axonx >/dev/null || { echo "axonx command not found" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 command not found" >&2; exit 1; }

for task in download_tushare_task qlib_a158_etl qlib_a158_factor qlib_a158_train qlib_a158_predict qlib_a158_backtest; do
    if ! axonx get_task_definition --task "$task" >/dev/null; then
        echo "Task ${task} is not installed. Install the required Task on the selected service before running this pipeline." >&2
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

    if ! wait_response=$(axonx --client-timeout 86400 wait_task --task-id "$task_id" --run-id "$run_id"); then
        echo "${stage} failed: ${wait_response}" >&2
        return 1
    fi
    printf '%s' "$wait_response" | python3 -c '
import json, sys
response = json.load(sys.stdin)
if not response.get("success") or response.get("answer", {}).get("state") != "succeeded":
    raise SystemExit("Task did not succeed: %s" % response.get("answer"))
' || return 1
    echo "${stage} succeeded" >&2
    printf '%s\n' "$task_id"
}

# The native and plugin tasks are submitted by their registered names.
submit_and_wait "Tushare download" --task download_tushare_task --days-back 14 >/dev/null
etl_id=$(submit_and_wait "Alpha158 ETL" --task qlib_a158_etl --start-date 20150101)
submit_and_wait "Factor analysis" --task qlib_a158_factor --source-tasks "${etl_id}" >/dev/null
train_id=$(submit_and_wait "LightGBM training" --task qlib_a158_train --source-tasks "${etl_id}" --train-start 20150101 --train-end 20230101 --label-column label_return_rank)
predict_id=$(submit_and_wait "Prediction" --task qlib_a158_predict --source-tasks "${train_id}" --pred-start 20230101)
backtest_id=$(submit_and_wait "Backtest" --task qlib_a158_backtest --source-tasks "${predict_id}" --top-ns '[5,10,20,30]' --buy-cost-rate 0.0005 --sell-cost-rate 0.0015)

echo "Pipeline complete: ${backtest_id}"
