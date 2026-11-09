# tests/test_intake_form.py
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp.login import validate_submission, LoginError

def test_valid_submission():
    acc, pwd = validate_submission({"account": "13800000000", "password": "secret"}, "tok", "tok")
    assert acc == "13800000000" and pwd == "secret"

def test_bad_token_rejected():
    with pytest.raises(LoginError):
        validate_submission({"account": "x", "password": "y"}, "bad", "tok")

def test_empty_account_rejected():
    with pytest.raises(LoginError):
        validate_submission({"account": "  ", "password": "y"}, "tok", "tok")

def test_empty_password_rejected():
    with pytest.raises(LoginError):
        validate_submission({"account": "x", "password": ""}, "tok", "tok")

def test_account_stripped():
    acc, _ = validate_submission({"account": " 13800000000 ", "password": "y"}, "tok", "tok")
    assert acc == "13800000000"