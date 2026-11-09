# tests/test_credential_store.py
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp.login import CredentialStore, LoginError, SERVICE

class FakeKeyring:
    def __init__(self): self.store = {}
    def get_password(self, service, account): return self.store.get((service, account))
    def set_password(self, service, account, password): self.store[(service, account)] = password
    def delete_password(self, service, account): self.store.pop((service, account), None)

def test_set_get_delete():
    kr = FakeKeyring()
    cs = CredentialStore(backend=kr)
    assert cs.get_password("13800000000") is None
    cs.set_password("13800000000", "secret")
    assert kr.store[(SERVICE, "13800000000")] == "secret"
    assert cs.get_password("13800000000") == "secret"
    cs.delete_password("13800000000")
    assert cs.get_password("13800000000") is None

def test_keyring_unavailable_raises_login_error():
    class Broken:
        def get_password(self, *a): raise RuntimeError("no backend")
        def set_password(self, *a): raise RuntimeError("no backend")
        def delete_password(self, *a): raise RuntimeError("no backend")
    cs = CredentialStore(backend=Broken())
    with pytest.raises(LoginError):
        cs.set_password("x", "y")