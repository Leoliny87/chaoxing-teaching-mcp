"""Portable, process-isolated launcher; no stored credentials are distributed."""
import atexit
import json
import os
from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(root / 'server'))
os.environ.setdefault('BSK_AUTO_START', '0')
os.environ.setdefault('BSK_AUTO_UPDATE', 'off')
cache = Path.home() / '.cache/xuexitong-mcp/process-runs'
cache.mkdir(parents=True, exist_ok=True, mode=0o700)
run = Path(tempfile.mkdtemp(prefix='run-', dir=cache))
from xuexitong_mcp import bsk
bsk.STATE_FILE = run / 'state.json'

def clean_empty_run():
    try:
        if bsk.STATE_FILE.exists():
            data = json.loads(bsk.STATE_FILE.read_text())
            if data.get('session') or data.get('tab'):
                return
            bsk.STATE_FILE.unlink()
        run.rmdir()
    except (OSError, ValueError):
        pass

atexit.register(clean_empty_run)
from xuexitong_mcp.__main__ import main
main()
