#!/usr/bin/env bash

set -Eeuo pipefail

log() {
  printf '\n==> %s\n' "$1"
}

for command in git npm python; do
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
python -m pip install -e .

log "停止占用 1024 端口的旧进程"
python - <<'PY'
import os
import signal
import time

import psutil

PORT = 1024
GRACEFUL_TIMEOUT = 10


def listening_pids():
    return {
        connection.pid
        for connection in psutil.net_connections(kind="tcp")
        if connection.pid is not None
        and connection.status == psutil.CONN_LISTEN
        and connection.laddr.port == PORT
        and connection.pid != os.getpid()
    }


pids = listening_pids()
if not pids:
    print(f"未发现监听 {PORT} 端口的进程")
    raise SystemExit(0)

print(f"正在停止监听 {PORT} 端口的进程：{', '.join(map(str, sorted(pids)))}")
for pid in pids:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

deadline = time.monotonic() + GRACEFUL_TIMEOUT
remaining = listening_pids()
while remaining and time.monotonic() < deadline:
    time.sleep(0.2)
    remaining = listening_pids()

if remaining:
    print(f"进程未能及时退出，强制结束：{', '.join(map(str, sorted(remaining)))}")
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    deadline = time.monotonic() + 5
    while listening_pids() and time.monotonic() < deadline:
        time.sleep(0.1)

remaining = listening_pids()
if remaining:
    raise SystemExit(
        f"无法释放 {PORT} 端口，仍在监听的进程："
        f"{', '.join(map(str, sorted(remaining)))}"
    )

print(f"端口 {PORT} 已释放")
PY

log "启动 AxonX 后端（同时托管前端）"
exec axonx start
