#!/usr/bin/env bash

set -Eeuo pipefail

log() {
  printf '\n==> %s\n' "$1"
}

for command in git npm pip; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    printf '错误：未找到必需命令：%s\n' "${command}" >&2
    exit 1
  fi
done

log "更新 main 分支"
git checkout main
git pull --ff-only origin main

log "安装前端依赖"
cd axonx_studio
npm ci

log "构建前端"
npm run build

log "安装后端依赖"
cd ..
pip install -e .

log "启动 AxonX 后端（同时托管前端）"
exec axonx start
