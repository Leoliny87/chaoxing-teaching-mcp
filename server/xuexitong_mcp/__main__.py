"""xuexitong-mcp 命令行入口。"""
from __future__ import annotations

import argparse
import atexit
import sys

from . import __version__
from . import config as _config


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="xuexitong-mcp", description="学习通 MCP 服务器（基于 bsk 驱动本机 Chrome；角色由 config.toml 的 profile 决定）")
    ap.add_argument("--http", action="store_true", help="使用 Streamable HTTP 传输（默认 stdio）")
    ap.add_argument("--host", default="127.0.0.1", help="HTTP 监听地址（默认 127.0.0.1）")
    ap.add_argument("--port", type=int, default=8765, help="HTTP 端口（默认 8765），路径为 /mcp")
    ap.add_argument("--config", help="配置文件路径（默认 ~/.config/xuexitong-mcp/config.toml）")
    ap.add_argument("--list-tools", action="store_true", help="打印工具列表后退出")
    ap.add_argument("--version", action="version", version=__version__)
    a = ap.parse_args(argv)

    cfg = _config.load(a.config)
    from .server import TOOLS, _V2, _state, apply_policy, build_server, shutdown
    if a.list_tools:
        prof = apply_policy(cfg)
        print(f"# profile: {prof}", file=sys.stderr)
        for name, kind, desc, _ in TOOLS:
            if name in _state["allowed"]:
                print(f"{name:26s} [{kind}] {desc}")
        return
    srv = build_server(cfg, a.host, a.port)
    atexit.register(shutdown)
    try:
        if a.http:
            print(f"xuexitong-mcp: http://{a.host}:{a.port}/mcp", file=sys.stderr)
            if _V2:
                srv.run("streamable-http", host=a.host, port=a.port)
            else:
                srv.run("streamable-http")
        else:
            srv.run("stdio")
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()


if __name__ == "__main__":
    main()
