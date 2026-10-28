#!/usr/bin/env bash
set -euo pipefail

# Historical Tushare partitions must already exist in the execution workspace.
# Nested stage options can be supplied as JSON, e.g. --train '{"num_threads":4}'.
exec axonx exec --task qlib_a158_research "$@"
