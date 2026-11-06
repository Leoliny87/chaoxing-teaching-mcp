"""Logging regression tests use synthetic secrets and mocked CLI only."""
# All identity fixtures in this file are synthetic and offline only.
import synthetic_data as F
from pathlib import Path
import io
import json
import logging
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from xuexitong_mcp.bsk import Bsk, BskError, _summarize_args, _RedactLogFilter

class LogPrivacyTests(unittest.TestCase):
    def make_browser(self):
        output = io.StringIO()
        logger = logging.Logger('synthetic-cli-log', logging.DEBUG)
        handler = logging.StreamHandler(output)
        handler.addFilter(_RedactLogFilter())
        logger.addHandler(handler)
        browser = Bsk.__new__(Bsk)
        browser.cfg = SimpleNamespace(bsk=lambda: 'fake-bsk-never-executed', t_command=45)
        browser.session = 'fake-session'
        browser.log = logger
        browser.calls = 0
        return browser, output

    def test_short_fill_payload_and_option_looking_value_are_not_logged(self):
        for payload in ['SYNTHETIC_PRIVATE_NOTE', '--json', '--session', 'line one\nSYNTHETIC_PRIVATE_NOTE']:
            out = _summarize_args(['fill', '@e3', '--value', payload, '--context', 'ctx-private'])
            self.assertNotIn(payload, out)
            self.assertNotIn('ctx-private', out)
            self.assertIn('fill', out)
            self.assertIn('--value', out)

    def test_short_and_long_evaluate_sources_are_not_logged_or_hashed(self):
        for source in ['SYNTHETIC_PRIVATE_JS()', '(async()=>{return "SYNTHETIC_PRIVATE_JS"})()', 'SYNTHETIC_PRIVATE_JS'*30]:
            out = _summarize_args(['evaluate', '--context', 'secret-context', source])
            self.assertNotIn('SYNTHETIC_PRIVATE_JS', out)
            self.assertNotIn('sha256', out)
            self.assertIn('evaluate', out)

    def test_urls_paths_selectors_and_expectations_are_not_logged(self):
        values=['https://example.invalid/SYNTHETIC_PRIVATE_PATH?token=SYNTHETIC_PRIVATE_TOKEN',
                '/path/to/local-user-resource', '[data-name="SYNTHETIC_PRIVATE_PERSON"]',
                '[{"target":"#field","field":"value","equals":"SYNTHETIC_PRIVATE_PERSON"}]']
        for verb,flag,value in [('navigate','--url',values[0]),('upload','--file',values[1]),
                                ('click','--selector',values[2]),('click','--expect',values[3])]:
            out=_summarize_args([verb,flag,value])
            self.assertNotIn('SYNTHETIC_PRIVATE',out)
            self.assertIn(verb,out)
            self.assertIn(flag,out)

    def test_equals_flags_end_of_options_and_control_characters_stay_private(self):
        for args in [['fill','--value=SYNTHETIC_PRIVATE_NOTE'], ['evaluate','--','--json\nSYNTHETIC_PRIVATE_JS'],
                     ['SYNTHETIC_PRIVATE_COMMAND','--SYNTHETIC_PRIVATE_FLAG'], ['tab','SYNTHETIC_PRIVATE_ACTION']]:
            out=_summarize_args(args)
            self.assertNotIn('SYNTHETIC_PRIVATE',out)
            self.assertNotIn('\n',out)

    def test_safe_command_shape_is_retained(self):
        out=_summarize_args(['cooperate','sync','--tab-id','123','--save-full','/private/file','--json'])
        self.assertTrue(out.startswith('cooperate sync '))
        self.assertIn('--tab-id',out); self.assertIn('--save-full',out); self.assertIn('--json',out)

    def test_cli_command_and_success_result_are_unchanged_without_log_payloads(self):
        browser,out=self.make_browser()
        payload='SYNTHETIC_PRIVATE_NOTE'
        args=['fill','@e3','--value',payload]
        response={'value':{'title':'SYNTHETIC_PRIVATE_RESPONSE','中文':'SYNTHETIC_PRIVATE_PERSON'}}
        completed=subprocess.CompletedProcess([],0,json.dumps(response),'SYNTHETIC_PRIVATE_STDERR')
        with patch('xuexitong_mcp.bsk.subprocess.run',return_value=completed) as run:
            result=browser.run(args)
        self.assertEqual(result,response)
        self.assertEqual(run.call_args.args[0],['fake-bsk-never-executed',*args,'--session','fake-session','--json'])
        self.assertEqual(run.call_count,1)
        self.assertNotIn('SYNTHETIC_PRIVATE',out.getvalue())
        self.assertIn('out_len=',out.getvalue());self.assertIn('err_len=',out.getvalue())

    def test_permission_denial_keeps_original_data_and_is_never_retried(self):
        browser,out=self.make_browser()
        error={'code':'permission_denied','message':'SYNTHETIC_PRIVATE_ERROR',
               'data':{'reason':'observation_changed','phase':'observation','effect_state':'none'}}
        completed=subprocess.CompletedProcess([],1,'',json.dumps(error))
        with patch('xuexitong_mcp.bsk.subprocess.run',return_value=completed) as run:
            with self.assertRaises(BskError) as caught:browser.run(['navigate','https://example.invalid/'])
        self.assertEqual(caught.exception.code,error['code'])
        self.assertEqual(caught.exception.message,error['message'])
        self.assertEqual(caught.exception.data,error['data'])
        self.assertEqual(run.call_count,1)
        self.assertNotIn('SYNTHETIC_PRIVATE',out.getvalue())

    def test_timeout_does_not_leak_input_or_trigger_a_second_command(self):
        browser,out=self.make_browser()
        with patch('xuexitong_mcp.bsk.subprocess.run',side_effect=subprocess.TimeoutExpired(F.CONTROL_013,45)) as run:
            with self.assertRaises(BskError) as caught:browser.run(['fill','@e1','--value','SYNTHETIC_PRIVATE_NOTE'])
        self.assertEqual(caught.exception.code,'timeout')
        self.assertEqual(run.call_count,1)
        self.assertNotIn('SYNTHETIC_PRIVATE',out.getvalue())

if __name__=='__main__':unittest.main()
