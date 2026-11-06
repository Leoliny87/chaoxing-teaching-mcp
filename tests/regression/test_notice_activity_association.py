"""Activity cleanup must be linked by a real notice ID, never merely a title."""
# All identity fixtures in this file are synthetic and offline only.
import synthetic_data as F
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import shutil
import subprocess
import tempfile
import unittest

from xuexitong_mcp.ops_activity import ActivityOps
from xuexitong_mcp.ops_notice import NoticeOps
from xuexitong_mcp.xxt import Course, XxtError

COURSE = F.NUMERIC_004
CLASS = F.NUMERIC_005
NOTICE = "A"*32
ACTIVITY = F.NUMERIC_006


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.course = Course(id=COURSE, name="测试课程", cpi="", clazz_id=CLASS, classes=[{"clazz_id": CLASS, "name": "默认班级"}])
        self.activity = dict(activity_id=ACTIVITY, active_type=45, class_id=CLASS, notice_id=NOTICE,
                             title="unique test", start="2099-01-01 00:00:00")
        self.published = dict(state="published", course_id=COURSE, class_id=CLASS, notice_id=NOTICE, uuid="own-uuid")
        outer = self
        class Fake(NoticeOps):
            cfg = SimpleNamespace(log_dir=Path(outer.tmp.name))
            def ctx(self, _): return outer.course
            def activities(self, *args, **kwargs): return [deepcopy(outer.activity)]
        self.client = Fake()

    def journal(self, records):
        p = Path(self.tmp.name) / "notice-outcomes.jsonl"
        p.write_text("".join(json.dumps(r)+"\n" for r in records))

    def prepare(self):
        return self.client.prepare_linked_activity_deletion(COURSE, ACTIVITY, CLASS)

    def test_exact_published_id_records_one_verified_link(self):
        self.journal([self.published])
        first = self.prepare()
        second = self.prepare()
        self.assertEqual(first["notice_id"], NOTICE)
        self.assertEqual(second["target"], self.activity)
        records = [json.loads(l) for l in (Path(self.tmp.name)/"notice-outcomes.jsonl").read_text().splitlines()]
        links = [r for r in records if r["state"] == "linked_activity_observed"]
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["evidence_source"], "activeList.content.idCode")

    def test_title_match_without_owned_notice_id_is_insufficient(self):
        self.journal([{**self.published, "notice_id": "B"*32}])
        with self.assertRaises(XxtError): self.prepare()
        self.activity.pop("notice_id")
        self.journal([self.published])
        with self.assertRaises(XxtError): self.prepare()

    def test_wrong_class_or_course_and_duplicate_creation_records_rejected(self):
        for records in [[{**self.published, "class_id": F.CONTROL_019}],
                        [{**self.published, "course_id": F.CONTROL_019}],
                        [self.published, self.published]]:
            with self.subTest(records=records):
                self.journal(records)
                with self.assertRaises(XxtError): self.prepare()
        self.journal([self.published])
        self.activity["class_id"] = F.CONTROL_019
        with self.assertRaises(XxtError): self.prepare()

    def test_unconfirmed_deletion_is_not_retried(self):
        self.journal([self.published, {"state": "activity_delete_attempted", "activity_id": ACTIVITY}])
        with self.assertRaises(XxtError): self.prepare()

    def test_link_identity_change_is_rejected(self):
        self.journal([self.published])
        self.prepare()
        self.activity["notice_id"] = "B"*32
        with self.assertRaises(XxtError): self.prepare()

    def test_actual_javascript_mapping_requires_type_class_and_exact_idcode(self):
        node = shutil.which("node")
        self.assertIsNotNone(node)
        outer = self
        class Raw:
            fid = "test-fid"
            def ctx(self, _): return outer.course
            def on(self, origin, script):
                program = "const J=async()=>("+json.dumps(self.payload)+"); (async()=>{"+script+"})().then(x=>console.log(JSON.stringify(x)));"
                r = subprocess.run([node, "-e", program], text=True, capture_output=True, check=True, timeout=5)
                return json.loads(r.stdout)
        raw = Raw()
        base = dict(activeId=ACTIVITY, activeType=45, classId=CLASS, status="1", typeTitle="test", title="通知",
                    startTime="now", endTime="later", content=json.dumps({"creatorRealName": "not returned", "idCode": NOTICE}))
        for overrides, expected in [({}, NOTICE), ({"activeType": 43}, None), ({"classId": F.CONTROL_019}, None),
                                    ({"content": "bad"}, None), ({"content": json.dumps({"idCode": NOTICE+"x"})}, None),
                                    ({"content": json.dumps({"idCode": {"value": NOTICE}})}, None)]:
            raw.payload = {"result": 1, "data": {"activeList": [{**base, **overrides}]}}
            result = ActivityOps.activities(raw, COURSE)
            self.assertEqual(result[0].get("notice_id"), expected)
            self.assertNotIn("content", result[0])
            self.assertNotIn("creatorRealName", result[0])


if __name__ == "__main__": unittest.main()
