import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp import policy as P

TOOLS = [("login", "local_write"), ("logout", "local_write"), ("health_check", "read"),
         ("publish_notice", "write"), ("list_my_courses", "read")]


def test_login_logout_in_every_profile():
    for prof in ("student", "reviewer", "teacher"):
        allowed = P.allowed_tools(prof, TOOLS, [], [])
        assert "login" in allowed and "logout" in allowed, prof


def test_student_still_cannot_publish():
    allowed = P.allowed_tools("student", TOOLS, [], [])
    assert "publish_notice" not in allowed