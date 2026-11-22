#!/usr/bin/env python3
"""BrowserSkill 浏览器守护：用官方启动入口补开缺失的教师/学生 Chrome。

遵循 $DSH_HOME/AGENTS.md「ai395 上打开教师和学生 Chrome」：
- 通过 /home/linyun/.local/bin/ai395-open-learning-chrome {both|teacher|student}
  补开缺失的 Chrome（桌面用户 systemd + 原有独立资料，Wayland 桌面打开，已运行的复用）。
- 不杀 Chrome、不删资料锁、不用 --ozone-platform=x11、不用 --restart-stale。
- 扩展掉线时保留已有窗口；Chrome 启动与 BrowserSkill 接入分别核验。
- 学生历史实例 ID 1e1e4951、教师 c41e7649；目标离线时不以其他同名实例替代。

用法：
  BSK_HOME=/home/linyun/.local/state/ai395-browserskill BSK_AUTO_START=0 \
    python3 scripts/browser_watchdog.py [--interval 20] [--once]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time

BSK = os.environ.get("XUEXITONG_MCP_BSK", "bsk")
OPENER = os.environ.get("BSK_WATCH_OPENER", "/home/linyun/.local/bin/ai395-open-learning-chrome")

# 角色 -> 历史实例 ID（离线时只报告，不替换实例/不改扩展）。
ROLES = {
    "teacher": os.environ.get("BSK_WATCH_TEACHER_INSTANCE", "c41e7649"),
    "student": os.environ.get("BSK_WATCH_STUDENT_INSTANCE", "1e1e4951"),
}


def _bsk(args: list[str]) -> dict | list:
    env = dict(os.environ, BSK_AUTO_START="0")
    try:
        r = subprocess.run([BSK, *args, "--json"], capture_output=True, text=True, env=env, timeout=30)
        return json.loads(r.stdout)
    except (ValueError, TypeError, subprocess.TimeoutExpired):
        return {}


def online_instances() -> set[str]:
    d = _bsk(["browsers"])
    rows = d if isinstance(d, list) else d.get("value", d.get("browsers", []))
    return {b.get("instance_id") for b in rows if isinstance(b, dict) and b.get("instance_id")}


def open_chrome(role: str) -> None:
    # 官方入口补开缺失 Chrome；已运行的资料会被复用，不会重复开窗。
    try:
        r = subprocess.run([OPENER, role], capture_output=True, text=True, timeout=90)
        msg = (r.stdout or r.stderr or "").strip().splitlines()
        print(f"[watchdog] 补开 {role}: {msg[-1] if msg else 'done'}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[watchdog] 补开 {role} 异常: {e}", flush=True)


def check_once() -> None:
    online = online_instances()
    missing = [role for role, inst in ROLES.items() if inst not in online]
    if not missing:
        return
    # 官方入口 both 会复用已运行资料、只补开缺失者；逐角色调用亦可。
    for role in missing:
        open_chrome(role)
    # 接入核验：补开后仍离线的角色只报告（扩展掉线保留窗口，不杀进程）。
    time.sleep(8)
    online2 = online_instances()
    for role in missing:
        inst = ROLES[role]
        if inst not in online2:
            print(f"[watchdog] {role} Chrome 已补开但实例 {inst} 仍未接入 BrowserSkill（保留窗口，等待/需人工核对扩展）", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=20.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--restart-stale", action="store_true", help="已废弃，忽略（不再杀进程/X11 重启）")
    a = ap.parse_args()
    if a.once:
        check_once()
        return
    print(f"[watchdog] 守护启动（官方入口补开），每 {a.interval}s 检查；所需实例: {ROLES}", flush=True)
    while True:
        try:
            check_once()
        except Exception as e:  # noqa: BLE001
            print(f"[watchdog] 检查异常: {e}", flush=True)
        time.sleep(a.interval)


if __name__ == "__main__":
    main()