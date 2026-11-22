#!/usr/bin/env python3
"""BrowserSkill 浏览器守护：断连自动重开 Chrome，免人工点扩展弹窗。

环境 bug 根因（2026-11-23 实测）：Chrome 158 在 Wayland 会话默认走 Wayland 原生窗口，
BrowserSkill 扩展的 MV3 service worker 在该模式下不主动连 daemon，导致 bsk 实例反复
掉线、且重启 Chrome 也不自动重连（必须人工点扩展弹窗）。强制 --ozone-platform=x11
（Xwayland）后扩展启动即自动连 daemon，无需人工干预。

本守护周期性检查所需 bsk 实例是否在线；缺失时自动以 --ozone-platform=x11 重开对应
Chrome profile，扩展随之自动重连。仅管理本 MCP 自建的两个自动化 profile，绝不触碰
用户自己的浏览器窗口。

用法：
  BSK_HOME=/home/linyun/.local/state/ai395-browserskill BSK_AUTO_START=0 \
    python3 scripts/browser_watchdog.py [--interval 20] [--once]

profile 与实例映射可用环境变量覆盖：
  BSK_WATCH_TEACHER_PROFILE / BSK_WATCH_TEACHER_INSTANCE
  BSK_WATCH_STUDENT_PROFILE / BSK_WATCH_STUDENT_INSTANCE / BSK_WATCH_STUDENT_EXT
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

BSK = os.environ.get("XUEXITONG_MCP_BSK", "bsk")
CHROME = os.environ.get("BSK_WATCH_CHROME", "/opt/google/chrome/chrome")
HOME = os.path.expanduser("~")

# 仅管理这两个自动化 profile（教师默认 profile + 学生独立 profile）。
PROFILES = [
    {
        "name": "teacher",
        "instance": os.environ.get("BSK_WATCH_TEACHER_INSTANCE", "c41e7649"),
        "user_data_dir": os.environ.get("BSK_WATCH_TEACHER_PROFILE", f"{HOME}/.local/share/dsh-browser-skill-profile"),
        "load_extension": "",
    },
    {
        "name": "student",
        "instance": os.environ.get("BSK_WATCH_STUDENT_INSTANCE", "1e1e4951"),
        "user_data_dir": os.environ.get("BSK_WATCH_STUDENT_PROFILE", f"{HOME}/.local/share/dsh-browser-skill-profile-student"),
        "load_extension": os.environ.get("BSK_WATCH_STUDENT_EXT", f"{HOME}/.local/share/bsk-student-ext"),
    },
]


def _bsk(args: list[str]) -> dict | list:
    env = dict(os.environ, BSK_AUTO_START="0")
    r = subprocess.run([BSK, *args, "--json"], capture_output=True, text=True, env=env, timeout=30)
    try:
        return json.loads(r.stdout)
    except (ValueError, TypeError):
        return {}


def online_instances() -> set[str]:
    d = _bsk(["browsers"])
    rows = d if isinstance(d, list) else d.get("value", d.get("browsers", []))
    return {b.get("instance_id") for b in rows if isinstance(b, dict) and b.get("instance_id")}


def chrome_running(user_data_dir: str) -> bool:
    r = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True)
    needle = f"--user-data-dir={user_data_dir}"
    for line in r.stdout.splitlines():
        if needle in line and "--type=" not in line and "chrome" in line:
            return True
    return False


def launch(p: dict) -> None:
    args = [CHROME, f"--user-data-dir={p['user_data_dir']}", "--ozone-platform=x11",
            "--no-first-run", "--no-default-browser-check", "https://i.mooc.chaoxing.com/space/index"]
    if p.get("load_extension"):
        args.insert(2, f"--load-extension={p['load_extension']}")
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print(f"[watchdog] 以 X11 重开 {p['name']} Chrome (instance={p['instance']})", flush=True)


def kill_profile(user_data_dir: str) -> None:
    r = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True)
    needle = f"--user-data-dir={user_data_dir}"
    for line in r.stdout.splitlines():
        if needle in line and "chrome" in line:
            pid = line.split()[0]
            if pid.isdigit():
                try:
                    os.kill(int(pid), 9)
                except ProcessLookupError:
                    pass
    for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            os.unlink(os.path.join(user_data_dir, lock))
        except OSError:
            pass


def check_once(restart_stale: bool = False) -> None:
    online = online_instances()
    for p in PROFILES:
        if p["instance"] in online:
            continue
        running = chrome_running(p["user_data_dir"])
        if running and restart_stale:
            # 进程在但实例掉线（多为 Wayland 模式残留）：强制以 X11 重启
            print(f"[watchdog] {p['name']} 进程在但实例离线，X11 重启", flush=True)
            kill_profile(p["user_data_dir"])
            time.sleep(3)
            launch(p)
        elif not running:
            launch(p)
        else:
            print(f"[watchdog] {p['name']} 进程在、实例暂离线，等待扩展重连…", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=20.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--restart-stale", action="store_true", help="进程在但实例离线时强制 X11 重启")
    a = ap.parse_args()
    if a.once:
        check_once(a.restart_stale)
        return
    print(f"[watchdog] 守护启动，每 {a.interval}s 检查；所需实例: {[p['instance'] for p in PROFILES]}", flush=True)
    while True:
        try:
            check_once(a.restart_stale)
        except Exception as e:  # noqa: BLE001
            print(f"[watchdog] 检查异常: {e}", flush=True)
        time.sleep(a.interval)


if __name__ == "__main__":
    main()