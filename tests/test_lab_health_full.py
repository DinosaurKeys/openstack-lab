import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / 'scripts/lab-health-full.sh'


class FullHealthTest(unittest.TestCase):
    def run_fake(self, health_rc=0, audit_rc=0, extra=(), inherited=None):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            log = p / 'calls'
            for name, rc in [('python3', health_rc), ('ansible-playbook', audit_rc)]:
                tool = p / name
                tool.write_text('#!/bin/sh\nprintf "%s\\n" "$(basename "$0") $*" >> "$CALL_LOG"\nprintf "ENV %s ask=%s flags=%s\\n" "$(basename "$0")" "${ANSIBLE_BECOME_ASK_PASS-unset}" "${ANSIBLE_BECOME_FLAGS-unset}" >> "$CALL_LOG"\nexit ' + str(rc) + '\n')
                tool.chmod(0o755)
            env = dict(os.environ, PATH=str(p) + ':' + os.environ['PATH'], CALL_LOG=str(log))
            env.update(inherited or {})
            result = subprocess.run(['bash', str(WRAPPER), *extra], text=True, capture_output=True, env=env, timeout=10)
            return result, log.read_text() if log.exists() else ''

    def test_runs_both_checks_without_password_prompt_by_default(self):
        result, calls = self.run_fake(extra=('--inventory', '/test/inventory', '--cloud', 'test-cloud'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('python3 ', calls)
        self.assertIn('--inventory /test/inventory --cloud test-cloud', calls)
        self.assertIn('ansible-playbook -i /test/inventory', calls)
        self.assertNotIn(' -K', calls)
        self.assertIn('"ansible_become_flags":"-H -n"', calls)

    def test_inherited_prompt_setting_cannot_prompt_by_default(self):
        result, calls = self.run_fake(inherited={'ANSIBLE_BECOME_ASK_PASS': 'true'})
        self.assertEqual(result.returncode, 0)
        self.assertIn('ENV python3 ask=false', calls)
        self.assertIn('ENV ansible-playbook ask=false', calls)

    def test_explicit_prompt_option_is_forwarded(self):
        result, calls = self.run_fake(extra=('--ask-become-pass',))
        self.assertEqual(result.returncode, 0)
        self.assertIn(' -K', calls)
        self.assertIn('ENV python3 ask=false', calls)
        self.assertIn('ENV ansible-playbook ask=true', calls)

    def test_missing_value_followed_by_option_runs_no_commands(self):
        for option in ('--inventory', '--cloud'):
            for value in ('--help', '--ask-become-pass', ''):
                with self.subTest(option=option, value=value):
                    result, calls = self.run_fake(extra=(option, value))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(calls, '')

    def test_failed_audit_offers_explicit_password_prompt(self):
        result, _ = self.run_fake(audit_rc=2)
        self.assertIn('--ask-become-pass', result.stdout + result.stderr)

    def test_continues_to_foundation_even_if_first_check_fails(self):
        result, calls = self.run_fake(health_rc=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ansible-playbook', calls)

    def test_returns_failure_when_foundation_fails(self):
        result, calls = self.run_fake(audit_rc=2)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ansible-playbook', calls)

    def test_invalid_option_never_runs_either(self):
        result, calls = self.run_fake(extra=('--invalid',))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, '')


if __name__ == '__main__':
    unittest.main()
