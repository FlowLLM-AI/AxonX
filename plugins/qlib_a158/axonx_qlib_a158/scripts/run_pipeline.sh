#!/usr/bin/env bash
set -euo pipefail

# Run in the execution environment with qlib_a158 installed and historical
# Tushare partitions prepared. No resident service is required.
command -v axonx >/dev/null || { echo "axonx command not found" >&2; exit 1; }
run_name="pipeline-$(date -u +%Y%m%dT%H%M%S)-$$"

run_stage() {
    local task_type=$1 registration=$2
    shift 2
    echo "Executing ${registration}..." >&2
    axonx exec --task "$registration" --task-name "$run_name" "$@" >&2 || return 1
    printf '%s#%s#%s\n' "$task_type" "$registration" "$run_name"
}

run_stage api download_tushare_task --days-back 14 >/dev/null
etl_id=$(run_stage etl qlib_a158_etl --start-date 20150101)
run_stage analysis qlib_a158_factor --upstream-task-ids "$etl_id" >/dev/null
train_id=$(run_stage train qlib_a158_train --upstream-task-ids "$etl_id" --train-start 20150101 --train-end 20230101 --label-column label_return_rank)
predict_id=$(run_stage predict qlib_a158_predict --upstream-task-ids "$train_id" --pred-start 20230101)
backtest_id=$(run_stage backtest qlib_a158_backtest --upstream-task-ids "$predict_id" --top-ns '[5,10,20,30]' --buy-cost-rate 0.0005 --sell-cost-rate 0.0015)

echo "Pipeline complete: ${backtest_id}"
