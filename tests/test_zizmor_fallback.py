"""Exercise the Python embedded in the distributable workflow.

Run with: python -m unittest discover -s tests (requires PyYAML).
"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/zizmor-action.yml'
STEPS = yaml.safe_load(WORKFLOW.read_text())['jobs']['zizmor']['steps']


def script(step_id):
    run = next(step['run'] for step in STEPS if step.get('id') == step_id)
    return run.split("<<'PYEOF'\n", 1)[1].rsplit('PYEOF', 1)[0]


class FallbackTests(unittest.TestCase):
    def run_scan(self, responses, report=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / 'workspace'
            workflows = workspace / '.github/workflows'
            workflows.mkdir(parents=True)
            (workflows / 'bad.yml').write_text('name: bad\n')
            (workflows / 'good.yml').write_text('name: good\n')
            (workspace / '.github/zizmor.yml').write_text(
                'rules:\n  unpinned-uses:\n    disable: true\n')
            temp = root / 'temp'
            temp.mkdir()
            calls = []
            responses = iter(responses)

            def run(args, **kwargs):
                if args[0] == 'git':
                    return subprocess.CompletedProcess(args, 0, str(workspace), '')
                config = None
                if '--config' in args:
                    config = yaml.safe_load(Path(args[args.index('--config') + 1]).read_text())
                calls.append((args[-1], config,
                              (Path(kwargs['cwd']) / '.github/workflows/bad.yml').exists()))
                code, stdout, stderr = next(responses)
                return subprocess.CompletedProcess(args, code, stdout, stderr)

            env = dict(RUNNER_TEMP=str(temp), GITHUB_WORKSPACE=str(workspace),
                       GITHUB_STEP_SUMMARY=str(temp / 'summary'), GITHUB_OUTPUT=str(temp / 'output'),
                       GITHUB_SERVER_URL='https://github.com', GITHUB_REPOSITORY='owner/repo',
                       GITHUB_RUN_ID='1', LINK_SHA='abcdef123')
            with patch.dict(os.environ, env), patch('subprocess.run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as exit:
                    exec(compile(script('zizmor'), str(WORKFLOW), 'exec'), {})
                if report:
                    outputs = dict(line.split('=', 1) for line in (temp / 'output').read_text().splitlines())
                    with patch.dict(os.environ, ZIZMOR_OUTCOME='success' if exit.exception.code == 0 else 'failure',
                                    SCAN_COMPLETED=outputs.get('scan_completed', '')):
                        exec(compile(script('report'), str(WORKFLOW), 'exec'), {})
            self.assertTrue((workflows / 'bad.yml').exists())
            warning_data = json.loads((temp / 'zizmor-fallbacks.json').read_text())
            report_text = (temp / 'zizmor-report.md').read_text() if report else ''
            if report:
                self.assertEqual(report_text, (temp / 'summary').read_text())
            return exit.exception.code, calls, warning_data, (temp / 'zizmor').read_text(), report_text

    @staticmethod
    def crash(rule='impostor-commit', file='.github/workflows/bad.yml'):
        return 1, '', f"fatal: no audit was performed\n'{rule}' audit failed on file://./{file}\nCaused by: inaccessible repo\n"

    def test_file_scoped_retry_preserves_config_and_warns_both_reports(self):
        code, calls, warnings, raw, report = self.run_scan([
            self.crash(), (0, '', ''), (0, '', '')], report=True)
        self.assertEqual(code, 0)
        self.assertEqual([call[0] for call in calls], ['.', '.', '.github/workflows/bad.yml'])
        self.assertFalse(calls[1][2])
        self.assertIsNone(calls[1][1])  # Other files retain all configured audits.
        self.assertTrue(calls[2][1]['rules']['impostor-commit']['disable'])
        self.assertTrue(calls[2][1]['rules']['unpinned-uses']['disable'])
        self.assertEqual(len(warnings), 1)
        self.assertIn('⚠️ **Scan coverage is reduced.**', report)
        self.assertIn('impostor-commit', report)
        self.assertNotIn('✅', report)
        self.assertNotIn('crashed', report)
        self.assertIn('This does not indicate a failed security check', report)

    def test_multiple_rules_and_findings(self):
        finding = '::error file=.github/workflows/good.yml,line=1,title=artipacked::issue\n'
        code, calls, warnings, raw, report = self.run_scan([
            self.crash(), (14, finding, ''), self.crash('ref-confusion'), (0, '', '')], report=True)
        self.assertEqual(code, 14)
        self.assertEqual(len(warnings), 2)
        self.assertTrue(calls[-1][1]['rules']['impostor-commit']['disable'])
        self.assertTrue(calls[-1][1]['rules']['ref-confusion']['disable'])
        self.assertEqual(raw, finding)
        self.assertIn('1** finding', report)
        self.assertNotIn('scan could not complete', report)
        self.assertNotIn('scan step failed', report)
        self.assertIn('⚠️ **Scan coverage', report)
        self.assertEqual([line for line in report.splitlines() if line.startswith('- ')],
                         ['- `.github/workflows/bad.yml` (`impostor-commit`, `ref-confusion`)'])

    def test_multiple_files_are_isolated_independently(self):
        result = self.run_scan([self.crash(),
                                self.crash(file=".github/workflows/good.yml"),
                                (3, "", ""), (0, "", ""), (0, "", "")], report=True)
        self.assertEqual(result[0], 0)
        self.assertEqual(len(result[2]), 2)
        self.assertEqual([line for line in result[4].splitlines() if line.startswith("- ")],
                         ["- `.github/workflows/bad.yml` (`impostor-commit`)",
                          "- `.github/workflows/good.yml` (`impostor-commit`)"])
        self.assertEqual([call[0] for call in result[1][-2:]],
                         [".github/workflows/bad.yml", ".github/workflows/good.yml"])

    def test_repeat_exception_terminates(self):
        result = self.run_scan([self.crash(), (3, '', ''), self.crash()])
        self.assertEqual(result[0], 1)
        self.assertEqual(len(result[1]), 3)

    def test_unknown_failure_is_not_retried(self):
        result = self.run_scan([(1, '', 'fatal: invalid configuration')])
        self.assertEqual(result[0], 1)
        self.assertEqual(result[2], [])

    def test_outside_path_is_not_suppressed(self):
        result = self.run_scan([self.crash(file='../../outside.yml')])
        self.assertEqual(result[0], 1)
        self.assertEqual(result[2], [])

    def test_no_inputs_is_success(self):
        self.assertEqual(self.run_scan([(3, '', 'no inputs collected')])[0], 0)

    def test_findings_are_not_retried(self):
        result = self.run_scan([(14, '::error file=x,line=1,title=test::finding\n', '')], report=True)
        self.assertEqual(result[0], 14)
        self.assertEqual(len(result[1]), 1)
        self.assertIn('1** finding', result[4])
        self.assertNotIn('scan could not complete', result[4])
        self.assertNotIn('scan step failed', result[4])

    def test_fatal_error_after_findings_still_fails(self):
        result = self.run_scan([self.crash(),
                                (14, '::error file=x,line=1,title=test::finding\n', ''),
                                (1, '', 'network failure')], report=True)
        self.assertEqual(result[0], 1)
        self.assertIn('1** finding', result[4])
        self.assertIn('scan could not complete due to a scanner error', result[4])


if __name__ == '__main__':
    unittest.main()
