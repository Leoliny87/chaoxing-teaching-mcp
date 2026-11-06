"""Run the reviewed synthetic tests with fail-closed process-local I/O guards.

This guards accidental access by these reviewed tests; it is not a sandbox for
hostile Python/native code. Run in a disposable environment for untrusted code.
"""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import sysconfig
import tempfile
import unittest
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', choices=('all', 'compatibility'), default='all')
    parser.add_argument('--audit-logs', action='store_true')
    parser.add_argument('--guard-selftest', action='store_true')
    parser.add_argument('--reference', action='store_true', help='Explicitly test isolated reference prototypes; does not modify runtime source')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    node = shutil.which('node')
    if not node:
        raise SystemExit('Node.js is required; no tests were skipped or run.')
    node = str(Path(node).resolve())
    runtime_roots = {Path(sysconfig.get_path(k)).resolve()
                     for k in ('stdlib', 'platstdlib', 'purelib', 'platlib')}
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root / 'server'))
    sys.path.insert(0, str(root / 'tests/fixtures'))
    os.environ.clear()  # This child process only; no inherited credentials.
    os.environ.update({
        'PATH': str(Path(node).parent) + os.pathsep + os.defpath,
        'LANG': 'C.UTF-8',
        'XUEXITONG_MCP_BROWSER': 'synthetic-browser',
        'XUEXITONG_MCP_BOOTSTRAP_COURSE': '测试课程',
        'BSK_AUTO_START': '0', 'BSK_AUTO_UPDATE': 'off',
        'NODE_OPTIONS': '--require=' + str(root / 'scripts/offline_node_guard.cjs'),
    })
    # Only counts and categories are recorded, never attempted paths or values.
    denied = {}
    denial_sites = {}
    def refuse(category):
        denied[category] = denied.get(category, 0) + 1
        frame = sys._getframe(1)
        site = 'runtime_support'
        while frame:
            filename = frame.f_code.co_filename
            if filename.startswith(str(root) + os.sep) and filename != __file__:
                site = filename[len(str(root)) + 1:] + ':' + str(frame.f_lineno)
                break
            frame = frame.f_back
        key = category + '@' + site
        denial_sites[key] = denial_sites.get(key, 0) + 1
        raise PermissionError('Offline guard blocked ' + category)

    with tempfile.TemporaryDirectory(prefix='xxt-synthetic-') as name:
        scratch = Path(name).resolve()
        fake_home = scratch / 'home'
        fake_home.mkdir()
        old_tempdir = tempfile.tempdir
        tempfile.tempdir = str(scratch)
        os.environ['XUEXITONG_MCP_CONFIG'] = str(scratch / 'empty-config.toml')
        allowed_read = (root, scratch, *runtime_roots)
        # Use string operations: some tests intentionally patch Path.stat.
        def inside(value, directories, dir_fd=None):
            if not isinstance(value, (str, bytes, os.PathLike)):
                return isinstance(value, int)
            path = os.fsdecode(value)
            if dir_fd is not None and dir_fd != -1 and not os.path.isabs(path):
                try:
                    path = os.path.join(os.readlink('/proc/self/fd/' + str(dir_fd)), path)
                except OSError:
                    return False
            path = os.path.realpath(path)
            return any(path == str(d) or path.startswith(str(d) + os.sep)
                       for d in directories)
        def allowed_node(executable, argv, env):
            return (str(executable) == node and isinstance(argv, (list, tuple))
                    and len(argv) == 3 and argv[1] == '-e'
                    and (env is None or env.get('NODE_OPTIONS') == os.environ['NODE_OPTIONS']))
        def guard(event, values):
            if event.startswith('socket.'):
                refuse('network')
            if event in ('os.system', 'os.fork', 'os.forkpty'):
                refuse('external_process')
            if event in ('os.posix_spawn', 'os.posix_spawnp') and not allowed_node(*values[:3]):
                refuse('external_process')
            if event == 'subprocess.Popen':
                executable, argv, cwd, env = values
                if not allowed_node(executable, argv, env):
                    refuse('external_process')
            if event == 'open':
                path, mode, flags = values
                writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                if not inside(path, (scratch,) if writing else allowed_read):
                    refuse('file_write' if writing else 'file_read')
            if event in ('os.listdir', 'os.scandir') and not inside(values[0], allowed_read):
                refuse('directory_read')
            if event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.truncate'):
                dir_fd = values[1] if event in ('os.remove', 'os.rmdir') else values[2] if event in ('os.mkdir', 'os.chmod') else None
                if not inside(values[0], (scratch,), dir_fd):
                    refuse('file_mutation')
            if event in ('os.rename', 'os.link', 'os.symlink'):
                if not all(inside(value, (scratch,)) for value in values[:2]):
                    refuse('file_mutation')
        sys.addaudithook(guard)
        original_expanduser = os.path.expanduser
        def synthetic_expanduser(path):
            text = os.fsdecode(path)
            if text == '~' or text.startswith('~/'):
                resolved = str(fake_home) + text[1:]
                return os.fsencode(resolved) if isinstance(path, bytes) else resolved
            if text.startswith('~'):
                refuse('other_user_home')
            return original_expanduser(path)
        with patch.object(Path, 'home', return_value=fake_home), patch.object(os.path, 'expanduser', synthetic_expanduser):
            if args.guard_selftest:
                import socket
                import subprocess
                probes = {
                    'network': lambda: socket.socket(),
                    'external_process': lambda: subprocess.run(['bsk', 'doctor']),
                    'file_read': lambda: open('/synthetic-outside-root/never-created', 'rb'),
                    'file_write': lambda: open(root / 'should-not-exist', 'wb'),
                }
                outcomes = {}
                for category, probe in probes.items():
                    try:
                        probe()
                    except PermissionError:
                        outcomes[category] = True
                    else:
                        outcomes[category] = False
                js = "const fs=require('node:fs'); let n=0; for(const f of [()=>fetch('https://example.invalid'),()=>fs.readFileSync('/synthetic-outside-root'),()=>require('node:child_process').execSync('synthetic-command')]){try{f()}catch(e){n++}} console.log(n)"
                child = subprocess.run([node, '-e', js], check=True, capture_output=True, text=True, timeout=5)
                outcomes['node_guards'] = child.stdout.strip() == '3'
                print(json.dumps({'guard_probes': outcomes, 'denied_categories': denied}))
                return 0 if all(outcomes.values()) else 1
            from xuexitong_mcp import bsk
            bsk.STATE_FILE = scratch / 'state.json'
            from xuexitong_mcp import ops_activity
            def fixture_path(value, *parts):
                if value == '/etc/opt/chrome/policies/managed/xuexitong.json':
                    return scratch / 'absent-synthetic-policy.json'
                return Path(value, *parts)
            policy_patch = patch.object(ops_activity, 'Path', fixture_path)
            policy_patch.start()
            if args.reference:
                spec = importlib.util.spec_from_file_location('reference_wait', root / 'reference/passive_wait.py')
                prototype = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(prototype)
                from xuexitong_mcp.xxt import XxtBase
                XxtBase.wait_for = prototype.wait_for
            if args.audit_logs:
                sys.argv = [str(root / 'scripts/audit_log_output.py')]
                runpy.run_path(sys.argv[0], run_name='__main__')
                return 0
            files = sorted((root / 'tests/unit').glob('test_*.py'))
            files += sorted((root / 'tests/regression').glob('test_*.py'))
            files += sorted((root / 'tests').glob('test_*.py'))
            if args.suite == 'all':
                files += sorted((root / 'tests/known_gaps').glob('test_*.py'))
            if args.reference:
                files += sorted((root / 'tests/reference').glob('test_*.py'))
            suite = unittest.TestSuite()
            for index, file in enumerate(files):
                spec = importlib.util.spec_from_file_location('synthetic_test_' + str(index), file)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
            result = unittest.TextTestRunner(verbosity=1).run(suite)
            print(json.dumps({'suite': args.suite, 'tests_run': result.testsRun,
                'reference_prototypes_enabled': args.reference,
                'failures': len(result.failures), 'errors': len(result.errors),
                'skipped': len(result.skipped), 'expected_failures': len(result.expectedFailures),
                'unexpected_successes': len(result.unexpectedSuccesses),
                'denied_categories': denied, 'real_browser_used': False,
                'denial_sites': denial_sites,
                'live_platform_acceptance': False}))
            tempfile.tempdir = old_tempdir
            return int(not result.wasSuccessful())


if __name__ == '__main__':
    raise SystemExit(main())
