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
python -m pip install -e . ./axonx_studio

log "从源码安装三个研究插件"
axonx plugin install -e ./plugins/qlib_a158
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy

log "停止占用 1024 端口的旧进程"
python - <<'PY'
import os
import signal
import subprocess
import sys
import time

import psutil

PORT = 1024
GRACEFUL_TIMEOUT = 10


def fail(message):
    raise SystemExit(f"错误：{message}")


def permission_help():
    return (
        f"请先运行 sudo lsof -nP -iTCP:{PORT} -sTCP:LISTEN，确认旧服务的 PID，"
        "再运行 sudo kill -TERM <PID>；端口释放后运行 axonx start。\n"
        "sudo 会要求输入 Mac/Linux 登录密码（输入时不显示字符）。"
        "不要使用 sudo 运行整个 deploy.sh。"
    )


def listening_pids():
    # macOS denies system-wide psutil queries without root privileges.
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["lsof", "-nP", f"-iTCP:{PORT}", "-sTCP:LISTEN", "-t"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except FileNotFoundError:
            fail(f"未找到 lsof，无法查询 {PORT} 端口。请安装或恢复 lsof 后重试。")
        except (OSError, subprocess.TimeoutExpired) as error:
            fail(f"查询 {PORT} 端口失败：{error}\n{permission_help()}")
        # lsof returns 1 with no output when no matching listeners are visible.
        if result.stderr.strip() or result.returncode not in (0, 1) or (result.returncode == 1 and result.stdout.strip()):
            detail = result.stderr.strip() or f"lsof 退出码 {result.returncode}"
            fail(f"无法可靠查询 {PORT} 端口：{detail}\n{permission_help()}")
        try:
            pids = {int(pid) for pid in result.stdout.split()}
        except ValueError:
            fail(f"lsof 返回了无法识别的 PID，无法安全清理 {PORT} 端口。")
        if any(pid <= 0 for pid in pids):
            fail(f"lsof 返回了无效 PID，无法安全清理 {PORT} 端口。")
        return pids - {os.getpid()}

    try:
        connections = psutil.net_connections(kind="tcp")
    except psutil.AccessDenied:
        fail(f"当前用户无权查询系统 TCP 连接。\n{permission_help()}")
    except (OSError, psutil.Error) as error:
        fail(f"查询 {PORT} 端口失败：{error}")
    return {
        connection.pid
        for connection in connections
        if connection.pid is not None
        and connection.status == psutil.CONN_LISTEN
        and connection.laddr.port == PORT
        and connection.pid != os.getpid()
    }


def stop_process(pid, sig):
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        print(
            f"警告：当前用户无权停止监听 {PORT} 端口的进程 PID={pid}，跳过此进程并继续启动。\n"
            f"如果启动提示端口被占用，{permission_help()}",
            file=sys.stderr,
        )
        return False
    except OSError as error:
        fail(f"停止进程 PID={pid} 失败：{error}")
    return True


pids = listening_pids()
if not pids:
    print(f"当前用户权限范围内未发现监听 {PORT} 端口的进程")
    raise SystemExit(0)

print(f"正在停止监听 {PORT} 端口的进程：{', '.join(map(str, sorted(pids)))}")
skipped = set()
for pid in pids:
    if not stop_process(pid, signal.SIGTERM):
        skipped.add(pid)

deadline = time.monotonic() + GRACEFUL_TIMEOUT
remaining = listening_pids() - skipped
while remaining and time.monotonic() < deadline:
    time.sleep(0.2)
    remaining = listening_pids() - skipped

if remaining:
    print(f"进程未能及时退出，强制结束：{', '.join(map(str, sorted(remaining)))}")
    for pid in remaining:
        if not stop_process(pid, signal.SIGKILL):
            skipped.add(pid)

    deadline = time.monotonic() + 5
    while listening_pids() - skipped and time.monotonic() < deadline:
        time.sleep(0.1)

remaining = listening_pids() - skipped
if remaining:
    fail(
        f"无法释放 {PORT} 端口，仍在监听的进程："
        f"{', '.join(map(str, sorted(remaining)))}\n{permission_help()}"
    )

if skipped:
    print(f"已跳过无权停止的进程：{', '.join(map(str, sorted(skipped)))}；继续执行 axonx start")
else:
    print(f"端口 {PORT} 已释放")
PY

log "启动 AxonX 后端（同时托管前端）"
exec axonx start "$@"
