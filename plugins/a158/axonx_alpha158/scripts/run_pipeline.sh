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
    local response task_id status state error

    echo "Submitting ${stage}..." >&2
    response=$(axonx submit "$@") || return 1
    task_id=$(printf '%s' "$response" | python3 -c '
import json, sys
response = json.load(sys.stdin)
if not response.get("success"):
    raise SystemExit("Submission failed: %s" % response.get("answer"))
print(response["answer"]["task_id"])
') || return 1
    if [[ -z $task_id ]]; then
        echo "${stage} submission returned an empty task ID" >&2
        return 1
    fi
    echo "${stage}: ${task_id}" >&2

    while :; do
        status=$(axonx status --task-id "$task_id") || return 1
        state=$(printf '%s' "$status" | python3 -c '
import json, sys
response = json.load(sys.stdin)
if not response.get("success"):
    raise SystemExit("Status request failed: %s" % response.get("answer"))
print(response["answer"]["state"])
') || return 1
        case "$state" in
            succeeded)
                echo "${stage} succeeded" >&2
                printf '%s\n' "$task_id"
                return 0
                ;;
            failed|cancelled)
                error=$(printf '%s' "$status" | python3 -c 'import json,sys; print(json.load(sys.stdin)["answer"].get("error", ""))') || return 1
                echo "${stage} ${state}: ${error}" >&2
                return 1
                ;;
            queued|running) sleep 5 ;;
            *) echo "Unexpected ${stage} state: ${state}" >&2; return 1 ;;
        esac
    done
}

# The native and plugin tasks are submitted by their registered names.
submit_and_wait "Tushare download" --task download_tushare_task --days-back 7 >/dev/null
etl_id=$(submit_and_wait "Alpha158 ETL" --task a158_etl --start-date 20150101)
submit_and_wait "Factor analysis" --task a158_factor --source-tasks "[\"${etl_id}\"]" >/dev/null
train_id=$(submit_and_wait "LightGBM training" --task a158_train --source-tasks "[\"${etl_id}\"]" --train-start 20150101)
predict_id=$(submit_and_wait "Prediction" --task a158_predict --source-tasks "[\"${train_id}\"]")
backtest_id=$(submit_and_wait "Backtest" --task a158_backtest --source-tasks "[\"${predict_id}\"]")

echo "Pipeline complete: ${backtest_id}"
