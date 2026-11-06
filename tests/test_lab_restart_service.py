import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

PLAYBOOK = Path(__file__).resolve().parents[1] / 'ansible/playbooks/lab-restart-service.yml'


class RestartServiceTests(unittest.TestCase):
    def run_play(self, variables=None, scenario='ok', inventory=None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            log = root / 'calls'
            fake = root / 'fake'
            fake.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['FAKE_LOG'], 'a') as f: f.write(json.dumps([name] + args) + '\\n')
s = os.environ['SCENARIO']
if name == 'systemctl':
    if args[0] == 'show':
        if '--property=ActiveState' in args:
            count = pathlib.Path(os.environ['FAKE_LOG']).read_text().count('--property=ActiveState')
            print('activating' if s == 'unit_activating' or (s == 'unit_activity_drift' and count > 1) else ('inactive' if s == 'stopped' else 'active'))
        elif '--property=NeedDaemonReload' in args:
            count = pathlib.Path(os.environ['FAKE_LOG']).read_text().count('--property=NeedDaemonReload')
            print('NeedDaemonReload=' + ('yes' if s == 'daemon_reload' or (s == 'loaded_drift' and count > 1) else 'no'))
            print('FragmentPath=/etc/systemd/system/kolla-nova_compute-container.service')
            print('DropInPaths=')
            print('ExecStart={ path=/usr/bin/docker ; argv[]=/usr/bin/docker start -a ' + ('another_container' if s == 'loaded_mismatch' else 'nova_compute') + ' ; ignore_errors=no ; }')
            print('ExecStop={ path=/usr/bin/docker ; argv[]=/usr/bin/docker stop nova_compute -t 60 ; ignore_errors=no ; }')
            for k in ('ExecStartPre','ExecStartPost','ExecStopPost','ExecCondition','ExecReload','Requisite','BindsTo','ConsistsOf','PropagatesStopTo','PropagatesReloadTo','OnFailure','OnSuccess','Upholds'):
                print(k + '=' + ('danger.service' if s == 'unsafe_dependency' and k == 'ConsistsOf' else ''))
            for k in ('JobTimeoutAction','StartLimitAction','FailureAction','SuccessAction'):
                print(k + '=' + ('reboot' if s == 'unsafe_action' and k == 'FailureAction' else 'none'))
            print('Requires=system.slice sysinit.target\\nWants=docker.service\\nPartOf=kolla.target\\nConflicts=shutdown.target')
        else: print('not-found' if s == 'unit_missing' else 'loaded')
    elif args[0] == 'cat':
        cats = pathlib.Path(os.environ['FAKE_LOG']).read_text().count('"systemctl", "cat"')
        target = 'another_container' if s == 'unit_mismatch' or (s == 'unit_drift' and cats > 1) else 'nova_compute'
        print('[Service]\\nExecStart=/usr/bin/docker start -a ' + target + '\\nExecStop=/usr/bin/docker stop ' + target + ' -t 60')
    elif args[0] == 'restart' and s == 'restart_fail': sys.exit(1)
    elif args[0] == 'is-active':
        if args[-1] == 'shutdown.target': sys.exit(3)
        if args[-1] == 'docker.service':
            if s == 'docker_inactive': sys.exit(3)
            sys.exit(0)
        print('inactive' if s == 'unit_inactive' else 'active')
        if s == 'unit_inactive': sys.exit(3)
elif name == 'docker':
    if s == 'container_missing': sys.exit(1)
    logs = pathlib.Path(os.environ['FAKE_LOG']).read_text()
    calls = logs.count('"docker"')
    restarted = '"systemctl", "restart"' in logs
    state = 'restarting' if s == 'transitional' else ('exited' if s == 'stopped' and not restarted else 'running')
    ident = 'other' if (s == 'id_changed' and restarted) or (s == 'id_changed_before' and calls > 1) else 'abc123'
    health = {'Status': 'starting' if s == 'starting' or (s == 'slow_recovery' and restarted and calls <= 8) else ('unhealthy' if s == 'unhealthy' else 'healthy')}
    if s == 'no_health': health = None
    print(json.dumps([{'Id': ident, 'State': {'Status': state, 'Health': health}}]))
''')
            fake.chmod(0o755)
            for name in ('systemctl', 'docker'):
                (root / name).symlink_to(fake)
            inv = root / 'inventory.ini'
            inv.write_text(inventory or '[control]\nnode1 ansible_connection=local ansible_become=false\n')
            vals = {'recovery_target': 'node1', 'recovery_service': 'nova_compute', 'recovery_authorized': True, 'recovery_health_retries': 2, 'recovery_health_delay': 0}
            vals.update(variables or {})
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'], FAKE_LOG=str(log), SCENARIO=scenario, ANSIBLE_NOCOLOR='1', ANSIBLE_LOCAL_TEMP=str(root / 'ansible-tmp'), ANSIBLE_HOST_KEY_CHECKING='False')
            p = subprocess.run(['ansible-playbook', '-i', str(inv), str(PLAYBOOK), '-e', json.dumps(vals)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=90)
            calls = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
            return p.returncode, p.stdout, calls

    def test_restart_play_explicitly_requests_privilege(self):
        import yaml
        plays = yaml.safe_load(PLAYBOOK.read_text())
        self.assertIs(plays[-1].get('become'), True)

    def test_only_limited_container_state_is_requested(self):
        rc, output, calls = self.run_play()
        self.assertEqual(rc, 0, output)
        inspections = [c for c in calls if c[:2] == ['docker', 'inspect']]
        self.assertTrue(inspections)
        self.assertTrue(all('--format' in c for c in inspections), 'full Docker configuration may contain credentials')

    def test_success_restarts_exactly_one_unit(self):
        rc, output, calls = self.run_play()
        self.assertEqual(rc, 0, output)
        self.assertEqual([c for c in calls if c[:2] == ['systemctl', 'restart']], [['systemctl', 'restart', 'kolla-nova_compute-container.service']])

    def test_invalid_requests_never_invoke_commands(self):
        cases = [
            {'recovery_authorized': False}, {'recovery_authorized': 'true'},
            {'recovery_service': 'nova_compute;id'}, {'recovery_service': 'other'},
            {'recovery_service': 'mariadb', 'allowed_services': ['mariadb']},
            {'recovery_target': 'all'}, {'recovery_target': 'node*'},
            {'recovery_target': 'missing'}, {'recovery_target': 'localhost'},
            {'recovery_target': 'node1:node2'},
        ]
        for values in cases:
            with self.subTest(values=values):
                rc, output, calls = self.run_play(values)
                self.assertNotEqual(rc, 0, output)
                self.assertEqual(calls, [], output)

    def test_target_outside_eligible_groups_is_rejected(self):
        rc, output, calls = self.run_play(inventory='[other]\nnode1 ansible_connection=local\n')
        self.assertNotEqual(rc, 0, output)
        self.assertEqual(calls, [])

    def test_preconditions_fail_without_restart(self):
        for scenario in ('unit_missing', 'container_missing', 'transitional', 'docker_inactive'):
            with self.subTest(scenario=scenario):
                rc, output, calls = self.run_play(scenario=scenario)
                self.assertNotEqual(rc, 0, output)
                self.assertFalse(any(c[:2] == ['systemctl', 'restart'] for c in calls), output)

    def test_unsafe_loaded_systemd_state_never_restarts(self):
        for scenario in ('daemon_reload', 'loaded_mismatch', 'unsafe_dependency', 'unsafe_action'):
            with self.subTest(scenario=scenario):
                rc, output, calls = self.run_play(scenario=scenario)
                self.assertNotEqual(rc, 0, output)
                self.assertFalse(any(c[:2] == ['systemctl', 'restart'] for c in calls), output)

    def test_identity_changes_before_mutation_never_restart(self):
        for scenario in ('id_changed_before', 'unit_drift', 'loaded_drift', 'unit_activity_drift'):
            with self.subTest(scenario=scenario):
                rc, output, calls = self.run_play(scenario=scenario)
                self.assertNotEqual(rc, 0, output)
                self.assertFalse(any(c[:2] == ['systemctl', 'restart'] for c in calls), output)

    def test_mismatched_unit_never_restarts_a_different_container(self):
        rc, output, calls = self.run_play(scenario='unit_mismatch')
        self.assertNotEqual(rc, 0, output)
        self.assertFalse(any(c[:2] == ['systemctl', 'restart'] for c in calls), output)

    def test_activating_unit_is_never_interrupted(self):
        rc, output, calls = self.run_play(scenario='unit_activating')
        self.assertNotEqual(rc, 0, output)
        self.assertFalse(any(c[:2] == ['systemctl', 'restart'] for c in calls), output)

    def test_starting_health_is_never_interrupted(self):
        rc, output, calls = self.run_play(scenario='starting')
        self.assertNotEqual(rc, 0, output)
        self.assertFalse(any(c[:2] == ['systemctl', 'restart'] for c in calls), output)

    def test_stopped_container_can_start(self):
        rc, output, calls = self.run_play(scenario='stopped')
        self.assertEqual(rc, 0, output)
        self.assertEqual(sum(c[:2] == ['systemctl', 'restart'] for c in calls), 1)

    def test_waits_for_a_slow_but_healthy_container(self):
        rc, output, calls = self.run_play(variables={'recovery_health_retries': 6, 'recovery_health_delay': 0}, scenario='slow_recovery')
        self.assertEqual(rc, 0, output)
        self.assertEqual(sum(c[:2] == ['systemctl', 'restart'] for c in calls), 1)

    def test_no_healthcheck_is_unknown(self):
        rc, output, calls = self.run_play(scenario='no_health')
        self.assertNotEqual(rc, 0, output)
        self.assertIn('UNKNOWN', output)
        self.assertEqual(sum(c[:2] == ['systemctl', 'restart'] for c in calls), 1)

    def test_post_restart_failures_do_not_retry_restart(self):
        for scenario in ('restart_fail', 'unit_inactive', 'id_changed', 'unhealthy'):
            with self.subTest(scenario=scenario):
                rc, output, calls = self.run_play(scenario=scenario)
                self.assertNotEqual(rc, 0, output)
                self.assertEqual(sum(c[:2] == ['systemctl', 'restart'] for c in calls), 1, output)
                self.assertNotIn('abc123', output)

if __name__ == '__main__':
    unittest.main()
