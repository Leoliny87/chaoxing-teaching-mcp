"""Fabricated inputs only; pure prototypes cannot access a browser or account."""
import importlib.util
from pathlib import Path
import unittest
import synthetic_data as F

path = Path(__file__).resolve().parents[2] / 'reference/assignment_contracts.py'
spec = importlib.util.spec_from_file_location('reference_assignment_contracts', path)
contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contracts)


class AssignmentContracts(unittest.TestCase):
    def editor(self):
        return {'path': '/mooc2-ans/work/goToWorkEditor', 'url_work_id': '',
                'course': F.NUMERIC_001, 'class_id': F.NUMERIC_002,
                'work_id': '', 'title': '新建作业20990101000000', 'editors': 0,
                'text': '题量 0 ，总分 0'}

    def test_empty_editor_is_bound_to_exact_course_and_class(self):
        editor = self.editor()
        contracts.validate_empty_editor(editor, F.NUMERIC_001, F.NUMERIC_002)
        for key in ('course', 'class_id', 'url_work_id', 'work_id'):
            with self.subTest(changed=key), self.assertRaises(ValueError):
                contracts.validate_empty_editor({**editor, key: 'synthetic-mismatch'}, F.NUMERIC_001, F.NUMERIC_002)

    def test_existing_questions_and_unexpected_title_are_rejected(self):
        for changed in ({'editors': 1}, {'title': 'synthetic existing template'}, {'text': '题量 1 ，总分 1'}):
            with self.subTest(changed=tuple(changed)), self.assertRaises(ValueError):
                contracts.validate_empty_editor({**self.editor(), **changed}, F.NUMERIC_001, F.NUMERIC_002)

    def test_exact_raw_label_is_preserved_with_surrounding_whitespace(self):
        target = {'selector': '#synthetic-control', 'visible_text': ' 完成 ', 'raw_text': '\n完成\t'}
        result = contracts.native_text_expectation(target, '完成')
        self.assertEqual(result['equals'], target['raw_text'])
        self.assertEqual(result['target'], target['selector'])

    def test_hidden_or_changed_label_stops_before_input(self):
        for raw in ('完成hidden', '', None):
            with self.subTest(kind=type(raw).__name__), self.assertRaises(ValueError):
                contracts.native_text_expectation({'selector': '#synthetic-control', 'visible_text': '完成', 'raw_text': raw}, '完成')

    def test_request_digest_changes_for_each_bound_argument(self):
        original = [F.NUMERIC_001, F.NUMERIC_002, 'synthetic title', 'synthetic question']
        baseline = contracts.request_digest(*original)
        for index in range(len(original)):
            changed = list(original)
            changed[index] += '-changed'
            with self.subTest(index=index):
                self.assertNotEqual(contracts.request_digest(*changed), baseline)
        self.assertEqual(contracts.request_digest(*original), baseline)
