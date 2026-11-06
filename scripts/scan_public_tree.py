"""Conservative artifact scanner: report rules/counts/relative paths, never values.

Use only on a selected export tree, not a home directory or credential store.
This is a heuristic publication check, not a complete security guarantee.
"""
from pathlib import Path
import collections
import json
import os
import re
import sys
from urllib.parse import urlsplit

root = Path(sys.argv[1]).resolve()
report = Path(sys.argv[2]).resolve()
rules = {
    'private_key': r'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----',
    'github_token': r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b',
    'cloud_key': r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'jwt': r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b',
    'api_key': r'\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b',
    'user_absolute_path': r'/(?:home|Users)/[^/\s"\']+',
    'private_network': r'\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2})\b',
    'private_tunnel': r'\b[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:ts\.net|trycloudflare\.com|ngrok\.io|ngrok-free\.app)\b',
    'email': r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
    'numeric_object': r'(?<![A-Za-z0-9_])\d{7,13}(?![A-Za-z0-9_])',
    'literal_control_identity': r'''(?:browser|instance)(?:_id|Id)?["']?\s*[:=]\s*["'][a-f0-9]{8,}["']''',
}
block = collections.Counter()
reviewed = collections.Counter()
count = size = 0
excluded_directories = {'.git', '.venv', 'venv', '__pycache__', 'node_modules', 'profile', 'profiles', 'screenshots', 'logs', 'quarantine', 'internal-review'}
excluded_extensions = {'.pyc', '.sqlite', '.db', '.log', '.png', '.jpg', '.jpeg', '.webp', '.mp4', '.zip', '.gz', '.whl'}
for current, dirs, names in os.walk(root, followlinks=False):
    for directory in list(dirs):
        p = Path(current)/directory
        if p.is_symlink() or directory in excluded_directories:
            block[('excluded_directory_or_symlink', p.relative_to(root).as_posix())] += 1
            dirs.remove(directory)
    for name in sorted(names):
        p = Path(current)/name
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            block[('symlink', rel)] += 1
            continue
        if name == '.env' or name.startswith('.env.') or p.suffix.lower() in excluded_extensions:
            block[('excluded_file', rel)] += 1
            continue
        raw = p.read_bytes()
        count += 1
        size += len(raw)
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            block[('non_text_file', rel)] += 1
            continue
        for rule, pattern in rules.items():
            for match in re.finditer(pattern, text, re.I if rule == 'literal_control_identity' else 0):
                value = match.group(0)
                category = None
                if rule == 'email' and value.endswith(('@example.invalid', '@example.com', '@example.org', '.test')):
                    category = 'synthetic_fixture'
                if rule == 'numeric_object':
                    if rel.startswith('provenance/'):
                        category = 'published_artifact_metadata'
                    elif value.startswith('0000') or value == '20990101':
                        category = 'synthetic_identifier_or_date'
                if category:
                    reviewed[(rule, category, rel)] += 1
                else:
                    block[(rule, rel)] += 1
        for url in re.findall(r'https?://[^\s"\'<>`]+', text):
            try:
                host = urlsplit(url).hostname or ''
            except ValueError:
                reviewed[('url_host', 'code_template', rel)] += 1
                continue
            if any(c in host for c in '{}()[]$\\'):
                category = 'code_template'
            elif host in {'127.0.0.1', 'localhost'} or host.endswith(('.invalid', '.test', 'example.com', 'example.org')):
                category = 'synthetic_or_loopback'
            elif any(host == d or host.endswith('.'+d) for d in ['chaoxing.com', 'xuexitong.com', 'cxwfw.com', 'wisweb.com', 'superlib.com', 'tencent.com', 'github.com', 'python.org', 'pypi.org']):
                category = 'public_platform_or_documentation'
            else:
                block[('unclassified_url_host', rel)] += 1
                continue
            reviewed[('url_host', category, rel)] += 1

result = {
    'scope': 'selected public export only', 'files_scanned': count, 'bytes_scanned': size,
    'blocking_findings': [{'rule': r, 'path': p, 'count': n} for (r, p), n in sorted(block.items())],
    'blocking_finding_count': sum(block.values()),
    'reviewed_matches': [{'rule': r, 'classification': c, 'path': p, 'count': n} for (r, c, p), n in sorted(reviewed.items())],
    'rules': list(rules), 'raw_values_in_report': False, 'uploaded': False,
}
report.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'files_scanned': count, 'blocking_findings': result['blocking_findings'], 'reviewed_match_count': sum(reviewed.values())}, ensure_ascii=False))
sys.exit(bool(block))
