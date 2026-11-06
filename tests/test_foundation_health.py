import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLAY = ROOT / 'ansible/playbooks/lab-foundation-health.yml'

class FoundationHealthTest(unittest.TestCase):
    def run_audit(self, mode, hostname='localhost'):
        self.assertTrue(PLAY.exists(), 'foundation health playbook missing')
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)
            docker = p / 'docker'
            docker.write_text('''#!/bin/sh
if [ "$1" = inspect ]; then
 case "$MODE" in
 stopped) echo 'exited none';;
 absent) echo 'Error: No such object: SECRET-DIAGNOSTIC' >&2; exit 1;;
 permission) echo 'permission denied SECRET-DIAGNOSTIC' >&2; exit 1;;
 unhealthy) echo 'running unhealthy';;
 starting) echo 'running starting';;
 *) echo 'running healthy';;
 esac
else
 if [ "$MODE" = diagnostic_permission ] && [ "$3" != test ]; then echo 'permission denied SECRET-DIAGNOSTIC' >&2; exit 1; fi
 if [ "$MODE" = missing ] && [ "$3" != test ]; then exit 127; fi
 if [ "$MODE" = diagnostic ] && [ "$3" != test ]; then echo SECRET-DIAGNOSTIC; exit 1; fi
 echo SECRET-DIAGNOSTIC
fi
''')
            docker.chmod(0o755)
            inventory = p / 'inventory'
            inventory.write_text('[mariadb]\n' + hostname + ' ansible_connection=local ansible_become=false\n[rabbitmq]\n' + hostname + '\n')
            env = dict(os.environ, PATH=d + ':' + os.environ['PATH'], MODE=mode, ANSIBLE_NOCOLOR='1')
            result = subprocess.run(['ansible-playbook', '-i', str(inventory), str(PLAY)], capture_output=True, text=True, env=env)
            self.assertNotIn('SECRET-DIAGNOSTIC', result.stdout + result.stderr)
            self.assertIn('quorum', result.stdout)
            self.assertIn('changed=0', result.stdout)
            return result

    def test_running_services_pass_without_disclosing_output(self):
        result = self.run_audit('running')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS', result.stdout)

    def test_pass_in_hostname_does_not_hide_failed_checks(self):
        result = self.run_audit('stopped', hostname='PASS-node')
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_unavailable_diagnostic_is_blocked(self):
        result = self.run_audit('missing')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertRegex(result.stdout, r'"status":\s*"\s*BLOCKED')

    def test_unreachable_members_are_blocked_and_redacted(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)
            ssh = p / 'ssh'
            ssh.write_text('#!/bin/sh\necho "SECRET-DIAGNOSTIC" >&2\nexit 255\n')
            ssh.chmod(0o755)
            inventory = p / 'inventory'
            inventory.write_text('[mariadb]\noffline-host ansible_host=127.0.0.1 ansible_connection=ssh ansible_become=false ansible_ssh_executable=' + str(ssh) + '\n[rabbitmq]\noffline-host\n')
            env = dict(os.environ, ANSIBLE_NOCOLOR='1', ANSIBLE_TIMEOUT='3')
            result = subprocess.run(['ansible-playbook', '-i', str(inventory), str(PLAY)], capture_output=True, text=True, env=env, timeout=35)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertRegex(result.stdout, r'"status":\s*"\s*BLOCKED')
            self.assertNotIn('SECRET-DIAGNOSTIC', result.stdout + result.stderr)

    def test_permission_denied_diagnostic_is_blocked(self):
        result = self.run_audit('diagnostic_permission')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertRegex(result.stdout, r'"status":\s*"\s*BLOCKED')

    def test_failure_modes_fail_closed(self):
        for mode, status in [('stopped', 'FAIL'), ('absent', 'FAIL'), ('permission', 'BLOCKED'), ('unhealthy', 'FAIL'), ('starting', 'BLOCKED'), ('diagnostic', 'FAIL')]:
            with self.subTest(mode=mode):
                result = self.run_audit(mode)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertRegex(result.stdout, rf'"status":\s*"\s*{status}')
