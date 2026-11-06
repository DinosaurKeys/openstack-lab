import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'lab-health.py'
spec = importlib.util.spec_from_file_location('lab_health', SCRIPT)
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)

def result(stdout='', code=0, stderr=''):
    return subprocess.CompletedProcess([], code, stdout, stderr)

def inventory():
    return {'control': {'hosts': ['fixture-a']}, 'compute': {'hosts': ['fixture-a', 'fixture-b']}, 'network': {'hosts': ['fixture-b']}, 'mariadb': {'hosts': ['fixture-a']}, 'rabbitmq': {'hosts': ['fixture-b']}, '_meta': {'hostvars': {}}}

def fake_run(args, **kwargs):
    if args[0] == 'ansible-inventory':
        return result(json.dumps(inventory()))
    if args[0] == 'ansible':
        return result('fixture-a | CHANGED | rc=0 >>\nHEALTH_VALUE=42\n')
    if args[0] == 'openstack':
        if 'service' in args and 'list' in args and 'compute' not in args:
            return result(json.dumps([{'Type': x} for x in ['identity', 'compute', 'network', 'image']]))
        if 'compute' in args and 'service' in args:
            return result(json.dumps([{'State': 'up', 'Status': 'enabled'}]))
        if 'endpoint' in args and 'list' in args:
            return result(json.dumps([{'Service Type': x, 'Enabled': True} for x in ['identity', 'compute', 'network', 'image']]))
        if 'agent' in args:
            return result(json.dumps([{'Alive': True, 'State': 'UP'}]))
        return result('[]')
    raise AssertionError(args)

class DashboardTest(unittest.TestCase):
    def dashboard(self, runner=fake_run, args=None):
        output = io.StringIO()
        with patch.object(health.subprocess, 'run', side_effect=runner), contextlib.redirect_stdout(output):
            code = health.main(args or [])
        return code, output.getvalue()

    def test_help_is_available(self):
        completed = subprocess.run([sys.executable, str(SCRIPT), '--help'], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('--inventory', completed.stdout)
        self.assertIn('--cloud', completed.stdout)

    def test_healthy_inventory_and_cloud(self):
        code, output = self.dashboard()
        self.assertEqual(code, 0, output)
        self.assertIn('PASS', output)

    def test_inventory_error_is_blocked_and_redacted(self):
        code, output = self.dashboard(lambda *a, **k: result(code=1, stderr='password=supersecret'))
        self.assertNotEqual(code, 0)
        self.assertIn('BLOCKED', output)
        self.assertNotIn('supersecret', output)

    def test_missing_individual_target_group_is_blocked(self):
        def runner(args, **kwargs):
            if args[0] == 'ansible-inventory':
                data = inventory()
                del data['network']
                return result(json.dumps(data))
            return fake_run(args, **kwargs)
        code, output = self.dashboard(runner)
        self.assertNotEqual(code, 0)
        self.assertIn('BLOCKED inventory group network missing or empty', output)

    def test_disabled_but_up_service_needs_review_not_failure(self):
        def runner(args, **kwargs):
            if 'compute' in args and 'service' in args:
                return result(json.dumps([{'State': 'up', 'Status': 'disabled'}]))
            return fake_run(args, **kwargs)
        code, output = self.dashboard(runner)
        self.assertNotEqual(code, 0)
        self.assertIn('REVIEW cloud reported compute service rows', output)
        self.assertNotIn('FAIL cloud reported compute service rows', output)

    def test_empty_groups_block(self):
        code, output = self.dashboard(lambda *a, **k: result('{}'))
        self.assertNotEqual(code, 0)
        self.assertIn('BLOCKED', output)

    def test_timeout_is_blocked(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], 1)
        code, output = self.dashboard(timeout)
        self.assertNotEqual(code, 0)
        self.assertIn('BLOCKED', output)

    def test_cloud_502_is_not_pass(self):
        def runner(args, **kwargs):
            if args[0] == 'openstack':
                return result(code=1, stderr='502 Bad Gateway password=secret')
            return fake_run(args, **kwargs)
        code, output = self.dashboard(runner)
        self.assertNotEqual(code, 0)
        self.assertNotIn('secret', output)
        self.assertIn('BLOCKED cloud authentication unavailable', output)
        self.assertNotIn('PASS cloud authentication', output)

    def test_unreachable_host_fails(self):
        def runner(args, **kwargs):
            if args[0] == 'ansible':
                return result(code=4, stderr='UNREACHABLE')
            return fake_run(args, **kwargs)
        code, output = self.dashboard(runner)
        self.assertNotEqual(code, 0)
        self.assertIn('BLOCKED fixture-a: uptime', output)
        self.assertNotIn('FAIL fixture-a: uptime', output)

    def test_optional_cinder_is_checked_only_when_catalog_has_volume(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            if args[0] == 'openstack' and args[-4:-2] == ['service', 'list'] and 'compute' not in args:
                return result(json.dumps([{'Type': x} for x in ['identity', 'compute', 'network', 'image', 'volumev3']]))
            return fake_run(args, **kwargs)
        code, output = self.dashboard(runner)
        self.assertEqual(code, 0, output)
        self.assertTrue(any(c[0] == 'openstack' and 'volume' in c for c in calls))

    def test_ansible_unprivileged_and_token_output_suppressed(self):
        calls = []
        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return fake_run(args, **kwargs)
        self.dashboard(runner)
        for args, _ in calls:
            if args[0] == 'ansible':
                self.assertIn('{"ansible_become": false}', args)
                self.assertNotIn('-o', args)
        token, opts = next((a, k) for a, k in calls if 'token' in a)
        self.assertIn('expires', token)
        self.assertEqual(opts.get('stdout'), subprocess.DEVNULL)

    def test_missing_sudo_is_blocked_and_redacted(self):
        def runner(args, **kwargs):
            if args[0] == 'ansible':
                return result('Missing sudo password SECRET', code=1)
            return fake_run(args, **kwargs)
        _, output = self.dashboard(runner)
        self.assertIn('BLOCKED fixture-a: uptime', output)
        self.assertNotIn('SECRET', output)

    def test_service_health_down_disabled_and_empty(self):
        def runner(args, **kwargs):
            if 'compute' in args and 'service' in args:
                return result(json.dumps([{'State': 'down', 'Status': 'enabled'}, {'State': 'up', 'Status': 'disabled'}]))
            if 'agent' in args:
                return result('[]')
            return fake_run(args, **kwargs)
        code, output = self.dashboard(runner)
        self.assertNotEqual(code, 0)
        self.assertIn('FAIL cloud reported compute service rows', output)
        self.assertIn('down', output.lower())
        self.assertIn('disabled', output.lower())
        self.assertIn('BLOCKED cloud reported network agent rows', output)

    def test_missing_enabled_endpoint_blocks(self):
        def runner(args, **kwargs):
            if 'endpoint' in args and 'list' in args:
                return result(json.dumps([{'Service Type': 'identity', 'Enabled': True}]))
            return fake_run(args, **kwargs)
        code, output = self.dashboard(runner)
        self.assertNotEqual(code, 0)
        self.assertIn('BLOCKED registered endpoints', output)
        self.assertNotIn('PASS registered endpoints', output)

    def test_missing_catalog_required_services_blocks(self):
        def runner(args, **kwargs):
            if args[0] == 'openstack' and args[-4:-2] == ['service', 'list'] and 'compute' not in args:
                return result('[]')
            return fake_run(args, **kwargs)
        _, output = self.dashboard(runner)
        self.assertIn('BLOCKED registered services', output)

    def test_bad_memory_is_fail_not_pass(self):
        def runner(args, **kwargs):
            if args[0] == 'ansible' and '/proc/meminfo' in args[args.index('-a') + 1]:
                return result('fixture-a | FAILED | rc=1 >>\nHEALTH_VALUE=1', code=2)
            return fake_run(args, **kwargs)
        _, output = self.dashboard(runner)
        self.assertIn('FAIL fixture-a: available memory', output)

    def test_each_host_probe_targets_only_that_host(self):
        calls = []
        def runner(args, **kwargs):
            if args[0] == 'ansible':
                calls.append(args)
            return fake_run(args, **kwargs)
        self.dashboard(runner)
        self.assertEqual({args[1] for args in calls}, {'fixture-a,', 'fixture-b,'})
        self.assertTrue(all(args[args.index('-i') + 1] == '/etc/kolla/multinode' for args in calls))

    def test_tcp_failure_is_blocked_not_database_down(self):
        def runner(args, **kwargs):
            if args[0] == 'ansible' and 'socket.create_connection' in args[args.index('-a') + 1]:
                return result('connection refused', code=2)
            return fake_run(args, **kwargs)
        _, output = self.dashboard(runner)
        self.assertIn('BLOCKED fixture-a: mariadb management-address TCP', output)
        self.assertNotIn('FAIL fixture-a: mariadb', output)

    def test_inventory_warnings_do_not_corrupt_json(self):
        def runner(args, **kwargs):
            if args[0] == 'ansible-inventory':
                return result(json.dumps(inventory()), stderr='warning')
            return fake_run(args, **kwargs)
        _, output = self.dashboard(runner)
        self.assertIn('PASS inventory: 2 unique target(s)', output)
        self.assertNotIn('warning', output)

    def test_deduplicates_targets(self):
        hosts = health.group_hosts(inventory(), ['control', 'compute', 'network'])
        self.assertEqual(hosts, ['fixture-a', 'fixture-b'])

if __name__ == '__main__':
    unittest.main()
