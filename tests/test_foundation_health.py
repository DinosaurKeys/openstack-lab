import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLAY = ROOT / 'ansible/playbooks/lab-foundation-health.yml'

class FoundationHealthTest(unittest.TestCase):
    def run_audit(self, mode, hostname='localhost', second_host=False, shards=False):
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
 case "$MODE" in wsrep_mismatch|wsrep_complete|wsrep_partial) if [ "$3" = test ] && [ "$5" = /etc/healthcheck.cnf ]; then exit 1; fi;; esac
 if [ "$3" = mariadb ]; then
  size=1; uuid=11111111-1111-4111-8111-111111111111
  case "$MODE" in wsrep_mismatch|wsrep_complete|wsrep_partial)
   size=2
   exec 9>"$STATE.lock"; flock 9
   n=$(cat "$STATE" 2>/dev/null || echo 0); n=$((n+1)); printf '%s' "$n" > "$STATE"
   if [ "$MODE" = wsrep_mismatch ] && [ "$n" -eq 2 ]; then uuid=22222222-2222-4222-8222-222222222222; fi
   if [ "$MODE" = wsrep_partial ] && [ "$n" -eq 2 ]; then exit 1; fi
   ;;
  esac
  case "$MODE" in
   wsrep_permission) echo SECRET-DIAGNOSTIC >&2; exit 1;;
   wsrep_malformed) echo SECRET-DIAGNOSTIC; exit 0;;
   wsrep_nonprimary) primary=Non-Primary;;
   wsrep_zero_uuid) primary=Primary; uuid=00000000-0000-0000-0000-000000000000;;
   wsrep_invalid_uuid) primary=Primary; uuid=INVALID-FIXTURE-UUID;;
   *) primary=Primary;;
  esac
  printf 'wsrep_cluster_status\t%s\nwsrep_local_state_comment\tSynced\nwsrep_ready\tON\nwsrep_connected\tON\nwsrep_cluster_size\t%s\nwsrep_cluster_state_uuid\t%s\n' "$primary" "$size" "$uuid"
  exit 0
 fi
 if [ "$MODE" = diagnostic_permission ] && [ "$3" != test ]; then echo 'permission denied SECRET-DIAGNOSTIC' >&2; exit 1; fi
 if [ "$MODE" = missing ] && [ "$3" != test ]; then exit 127; fi
 if [ "$MODE" = diagnostic ] && [ "$3" != test ]; then echo SECRET-DIAGNOSTIC; exit 1; fi
 echo SECRET-DIAGNOSTIC
fi
''')
            docker.chmod(0o755)
            inventory = p / 'inventory'
            inventory.write_text('[mariadb]\n' + hostname + ' ansible_connection=local ansible_become=false\n' + ('node-b ansible_connection=local ansible_become=false\n' if second_host else '') + '[rabbitmq]\n' + hostname + '\n' + ('[mariadb_shard_1]\nnode-a\n[mariadb_shard_2]\nnode-b\n' if shards else ''))
            env = dict(os.environ, PATH=d + ':' + os.environ['PATH'], MODE=mode, STATE=str(p / 'state'), ANSIBLE_NOCOLOR='1')
            result = subprocess.run(['ansible-playbook', '-i', str(inventory), str(PLAY)], capture_output=True, text=True, env=env)
            self.assertNotIn('SECRET-DIAGNOSTIC', result.stdout + result.stderr)
            self.assertIn('quorum', result.stdout)
            self.assertIn('changed=0', result.stdout)
            return result

    def test_running_services_pass_without_disclosing_output(self):
        result = self.run_audit('running')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS', result.stdout)

    def test_galera_cluster_is_checked_and_redacted(self):
        result = self.run_audit('running')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertRegex(result.stdout, r'Galera cluster: PASS')
        self.assertIn('Galera member: PASS', result.stdout)
        self.assertNotIn('11111111-1111-4111-8111-111111111111', result.stdout + result.stderr)

    def test_galera_fail_closed_on_bad_responses(self):
        for mode, status in [('wsrep_permission', 'BLOCKED'), ('wsrep_malformed', 'BLOCKED'), ('wsrep_nonprimary', 'FAIL')]:
            with self.subTest(mode=mode):
                result = self.run_audit(mode)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('Galera cluster: ' + status, result.stdout)
                self.assertNotIn('11111111-1111-4111-8111-111111111111', result.stdout + result.stderr)

        result = self.run_audit('wsrep_complete', hostname='node-a', second_host=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('Galera cluster: PASS', result.stdout)

    def test_invalid_galera_cluster_uuid_is_blocked(self):
        result = self.run_audit('wsrep_invalid_uuid')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('Galera cluster: BLOCKED', result.stdout)
        self.assertNotIn('INVALID-FIXTURE-UUID', result.stdout + result.stderr)

    def test_zero_galera_cluster_uuid_is_blocked(self):
        result = self.run_audit('wsrep_zero_uuid')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('Galera cluster: BLOCKED', result.stdout)

    def test_galera_partial_membership_is_blocked(self):
        result = self.run_audit('wsrep_partial', hostname='node-a', second_host=True)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('Galera cluster: BLOCKED', result.stdout)

    def test_multiple_shards_are_blocked(self):
        result = self.run_audit('wsrep_complete', hostname='node-a', second_host=True, shards=True)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('Galera cluster: BLOCKED', result.stdout)

    def test_galera_uuid_mismatch_fails(self):
        result = self.run_audit('wsrep_mismatch', hostname='node-a', second_host=True)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('Galera cluster: FAIL', result.stdout)
        self.assertNotIn('11111111-1111-4111-8111-111111111111', result.stdout + result.stderr)

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
