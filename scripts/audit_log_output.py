"""Synthetic audit of known residual output risks; no browser or real data.

Exit 1 means at least one synthetic marker reached an output sink. This is
deliberately separate from the historical compatibility test counts.
"""
# All identity fixtures in this file are synthetic and offline only.
import synthetic_data as F
import argparse
import io
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ap = argparse.ArgumentParser()
args = ap.parse_args()
root = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(root/'server'))

def guard(event, values):
    if event.startswith('socket.') or event == 'subprocess.Popen':
        raise RuntimeError('Synthetic audit prohibits external access')
    if event == 'open' and isinstance(values[0], str) and any(part in values[0] for part in ('/.config/google-chrome/', '/.config/xuexitong-mcp/', '/.dsh', '/.ssh/')):
        raise RuntimeError('Synthetic audit prohibits private runtime files')

sys.addaudithook(guard)
from xuexitong_mcp import bsk, server

output = io.StringIO()
handler = logging.StreamHandler(output)
handler.addFilter(bsk._RedactLogFilter())
logger = logging.Logger('synthetic-public-output-audit', level=logging.DEBUG)
logger.addHandler(handler)
logger.propagate = False

browser = object.__new__(bsk.Bsk)
browser.log = logger
def fake_run(arguments, **kwargs):
    if arguments == ['browsers']:
        return {'value': [{'instance_id': 'synthetic-browser'}]}
    if arguments[:2] == ['session', 'start']:
        return {'browser_instance_id': 'synthetic-browser', 'session_id': F.CONTROL_008}
    raise AssertionError('Unexpected synthetic call')
browser.run = fake_run
browser._initialize_owned_tab = lambda: setattr(browser, 'tab', 42)
with patch.object(bsk, 'FIXED_BROWSER_INSTANCE', 'synthetic-browser'):
    browser.start_session()
session_retained = F.CONTROL_008 in output.getvalue()
output.seek(0)
output.truncate(0)

saved = dict(server._state)
try:
    server._state.update(client=SimpleNamespace(b=SimpleNamespace(log=logger)))
    def fail_synthetically():
        raise RuntimeError('SYNTHETIC_UNSTRUCTURED_CONTENT')
    result = server._wrap(fail_synthetically)()
    error_log_retained = 'SYNTHETIC_UNSTRUCTURED_CONTENT' in output.getvalue()
    error_result_retained = 'SYNTHETIC_UNSTRUCTURED_CONTENT' in json.dumps(result)
finally:
    server._state.clear()
    server._state.update(saved)

findings = {
    'session_marker_retained_in_log': session_retained,
    'unstructured_exception_marker_retained_in_log': error_log_retained,
    'unstructured_exception_marker_retained_in_tool_result': error_result_retained,
}
print(json.dumps({'core': True, 'synthetic_only': True,
                  'real_browser_used': False, 'raw_values_recorded': False,
                  'findings': findings, 'known_risk_count': sum(findings.values())}))
sys.exit(any(findings.values()))
