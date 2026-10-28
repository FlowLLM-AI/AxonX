#!/usr/bin/env bash

set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

log() {
  printf '\n==> %s\n' "$1"
}

for command in git npm python; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    printf '错误：未找到必需命令：%s\n' "${command}" >&2
    exit 1
  fi
done

log "停止指定配置的 AxonX daemon 与 service"
python -m scripts.stop_daemon "$@"

log "快进当前分支的上游更新"
git pull --ff-only

log "安装前端依赖"
cd axonx_studio
npm ci

log "构建前端"
npm run build

log "安装后端依赖"
cd ..
python -m pip install -e . -e ./axonx_studio
python -m pip check

log "从源码安装三个研究插件"
axonx plugin install -e ./plugins/qlib_a158
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy

log "启动 AxonX 后端（同时托管前端）"
exec axonx app "$@"
