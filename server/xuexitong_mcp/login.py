"""首次登录引导：凭据存系统 keyring，本地表单采集，bsk 半自动登录（滑块人工）。"""
from __future__ import annotations

SERVICE = "xuexitong-mcp"


class LoginError(RuntimeError):
    pass


def _default_backend():
    try:
        import keyring  # type: ignore
        return keyring
    except ImportError as e:
        raise LoginError("未安装 keyring 依赖；请安装后重试，或手动在浏览器登录学习通。") from e


class CredentialStore:
    def __init__(self, backend=None):
        self._kr = backend if backend is not None else _default_backend()

    def get_password(self, account: str) -> str | None:
        try:
            return self._kr.get_password(SERVICE, account)
        except Exception as e:
            raise LoginError(f"系统凭据库不可用（{type(e).__name__}）；请手动在浏览器登录学习通。") from e

    def set_password(self, account: str, password: str) -> None:
        try:
            self._kr.set_password(SERVICE, account, password)
        except Exception as e:
            raise LoginError(f"无法写入系统凭据库（{type(e).__name__}）；请手动在浏览器登录学习通。") from e

    def delete_password(self, account: str) -> None:
        try:
            self._kr.delete_password(SERVICE, account)
        except Exception as e:
            raise LoginError(f"无法删除系统凭据（{type(e).__name__}）。") from e