# tests/test_login_config.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp.config import Config, load

def test_defaults_auto_login_on():
    c = Config()
    assert c.auto_login is True
    assert c.login_account == ""

def test_load_login_section(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[login]\nauto_login = false\nlogin_account = "13800000000"\n', encoding="utf-8")
    c = load(p)
    assert c.auto_login is False
    assert c.login_account == "13800000000"

def test_env_narrows_auto_login_off(tmp_path, monkeypatch):
    p = tmp_path / "config.toml"
    p.write_text('[login]\nauto_login = true\n', encoding="utf-8")
    monkeypatch.setenv("XUEXITONG_MCP_AUTO_LOGIN", "0")
    assert load(p).auto_login is False