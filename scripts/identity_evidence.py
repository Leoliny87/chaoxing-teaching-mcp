"""Reproducible, value-free identity review for selected synthetic test sources.

No source is imported or executed. Counts are rule-specific review candidates,
not proof that a literal is private or that a test is safe.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

NARROW_KEYS = {
    'session', 'session_id', 'context', 'context_id', 'observation', 'observation_id',
    'course_id', 'courseId', 'clazz_id', 'class_id', 'classId',
    'person_id', 'personId', 'student_id',
}
BROAD_KEYS = NARROW_KEYS | {
    'id', 'browser', 'browser_id', 'browser_instance_id', 'instance_id', 'tab',
    'tab_id', 'notice_id', 'activity_id', 'work_id', 'assignment_id', 'bbsid',
    'cpi', 'fid', 'enc', 't', 'token', 'password', 'secret',
}


def scan(root):
    root = Path(root).resolve()
    files = sorted((root / 'tests').rglob('*.py'))
    if (root / 'scripts/audit_log_output.py').is_file():
        files.append(root / 'scripts/audit_log_output.py')
    entries = []
    for path in files:
        if path.is_symlink() or root not in path.resolve().parents:
            raise ValueError('External source link is not allowed')
        raw = path.read_bytes()
        tree = ast.parse(raw.decode('utf-8'))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        def record(value, key, rule):
            constant = isinstance(value, ast.Constant) and isinstance(value.value, (str, int))
            generated = isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name) and value.value.id == 'F'
            if not constant and not generated:
                return
            scope = []
            parent = value
            while parent in parents:
                parent = parents[parent]
                if isinstance(parent, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    scope.insert(0, parent.name)
            if generated:
                basis = 'central offline fixture factory: tests/fixtures/synthetic_data.py::' + value.attr
            elif any('Fake' in x or 'fake' in x or 'snapshot' in x for x in scope):
                basis = 'literal constructed in named mock or snapshot helper; review enclosing scope'
            elif any(x.startswith('test_') for x in scope):
                basis = 'literal in test-local fixture or expected assertion; review enclosing scope'
            else:
                basis = 'source-defined literal requiring manual contextual review'
            entries.append({'path': path.relative_to(root).as_posix(),
                'file_sha256': hashlib.sha256(raw).hexdigest(),
                'line': value.lineno, 'column_zero_based': value.col_offset,
                'category': key, 'rule': rule, 'scope': '.'.join(scope),
                'construction': 'generated_fixture_reference' if generated else 'literal',
                'basis': basis})
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value in NARROW_KEYS:
                        record(value, key.value, 'dict_identity')
                    elif isinstance(key, ast.Constant) and key.value in BROAD_KEYS:
                        record(value, key.value, 'dict_broad')
            elif isinstance(node, ast.keyword) and node.arg in BROAD_KEYS:
                record(node.value, node.arg, 'keyword_identity')
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    key = target.attr if isinstance(target, ast.Attribute) else target.id.lower() if isinstance(target, ast.Name) else None
                    if key in BROAD_KEYS:
                        record(node.value, key, 'assignment_identity')
    entries.sort(key=lambda x: (x['path'], x['line'], x['column_zero_based'], x['rule'], x['category']))
    return {'schema': 1, 'values_recorded': False,
        'narrow_dict_literal_count': sum(x['rule'] == 'dict_identity' and x['construction'] == 'literal' for x in entries),
        'generated_reference_count': sum(x['construction'] == 'generated_fixture_reference' for x in entries),
        'broad_candidate_count': len(entries),
        'rules': {'narrow_keys': sorted(NARROW_KEYS), 'broad_keys': sorted(BROAD_KEYS),
            'forms': ['dictionary values', 'keyword arguments', 'named or attribute assignments'],
            'exclusions': ['positional arguments', 'embedded JSON or HTML', 'arbitrary string matching', 'nonliteral computed expressions']},
        'items': entries}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('selected_project')
    args = parser.parse_args()
    print(json.dumps(scan(args.selected_project), ensure_ascii=False, indent=2))
