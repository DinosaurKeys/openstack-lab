import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import importlib.util
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / 'scripts' / 'lab-recover.sh'


class RecoveryInterfaceTest(unittest.TestCase):
    def run_command(self, *args, input_text=None, extra_env=None):
        env = dict(os.environ)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(['bash', str(WRAPPER), *args], text=True,
                              input=input_text, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=env, timeout=15)

    def test_help_explains_read_only_default_and_explicit_restart(self):
        result = self.run_command('--help')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('--check', result.stdout)
        self.assertIn('--restart', result.stdout)
        self.assertIn('read-only', result.stdout.lower())
        self.assertIn('nova_compute', result.stdout)
        self.assertIn('neutron_server', result.stdout)

    def test_read_only_check_displays_service_table(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
            p = Path(tmp)
            inventory = p / 'inventory'
            inventory.write_text('[control]\nnode-a\nnode-b\n')
            inventory_tool = p / 'ansible-inventory'
            inventory_tool.write_text('#!/usr/bin/python3\nimport json\nprint(json.dumps({"control":{"hosts":["node-a","node-b"]},"compute":{"hosts":["node-a","node-b"]},"network":{"hosts":["node-a","node-b"]},"_meta":{"hostvars":{"node-a":{},"node-b":{}}}}))\n')
            inventory_tool.chmod(0o755)
            ansible = p / 'ansible'
            ansible.write_text('#!/usr/bin/python3\nimport sys\nservices="mariadb rabbitmq haproxy nova_api placement_api neutron_server nova_compute nova_conductor nova_scheduler neutron_openvswitch_agent neutron_l3_agent neutron_dhcp_agent neutron_metadata_agent cinder_scheduler".split()\nprint("\\n".join("LAB_UNIT|"+n+"|"+("not-found|inactive" if n=="cinder_scheduler" else "loaded|active") for n in services))\n')
            ansible.chmod(0o755)
            cloud = p / 'openstack'
            cloud.write_text('#!/usr/bin/python3\nimport sys,json\nprint(json.dumps([] if "server" in sys.argv else [{"Binary":"nova-compute","Host":n,"State":"up","Status":"enabled"} for n in ("node-a","node-b")] if "compute" in sys.argv else [{"Agent Type":"Open vSwitch agent","Host":"node-b","Alive":True,"State":True}]))\n')
            cloud.chmod(0o755)
            marker = p / 'mutation-called'
            writer = p / 'ansible-playbook'
            writer.write_text('#!/bin/sh\ntouch "$MARKER"\n')
            writer.chmod(0o755)
            env = {'PATH': tmp + ':' + os.environ['PATH'], 'MARKER': str(marker)}
            result = self.run_command('--check', '--inventory', str(inventory), extra_env=env)
            self.assertFalse(marker.exists(), 'read-only check must never launch the restart playbook')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for value in ('node-a', 'node-b', 'nova_compute', 'ACTIVE', 'ABSENT'):
                self.assertIn(value, result.stdout)
            self.assertIn('not', result.stdout.lower())

    def test_unreachable_node_is_blocked_not_healthy(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
            p = Path(tmp)
            inventory = p / 'inventory'; inventory.write_text('fixture')
            inv = p / 'ansible-inventory'; inv.write_text('#!/usr/bin/python3\nimport json\nprint(json.dumps({"control":{"hosts":["node-a"]},"_meta":{"hostvars":{"node-a":{}}}}))\n'); inv.chmod(0o755)
            ansible = p / 'ansible'; ansible.write_text('#!/bin/sh\necho SECRET-RAW-OUTPUT\nexit 4\n'); ansible.chmod(0o755)
            cloud = p / 'openstack'; cloud.write_text('#!/bin/sh\nexit 1\n'); cloud.chmod(0o755)
            result = self.run_command('--check', '--inventory', str(inventory), extra_env={'PATH':tmp + ':' + os.environ['PATH']})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('BLOCKED', result.stdout)
            self.assertNotIn('SECRET-RAW-OUTPUT', result.stdout + result.stderr)

    def test_invalid_option_never_invokes_ansible(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
            marker = Path(tmp) / 'called'
            fake = Path(tmp) / 'ansible-playbook'
            fake.write_text('#!/bin/sh\ntouch "$MARKER"\n')
            fake.chmod(0o755)
            result = self.run_command('--bogus', extra_env={'PATH': tmp + ':' + os.environ['PATH'], 'MARKER': str(marker)})
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())

    def test_missing_inventory_value_does_not_run_commands(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
            marker = Path(tmp) / 'called'
            for name in ('ansible-inventory', 'ansible', 'ansible-playbook', 'openstack'):
                tool = Path(tmp) / name
                tool.write_text('#!/bin/sh\ntouch "$MARKER"\nexit 1\n')
                tool.chmod(0o755)
            result = self.run_command('--inventory', '--help', extra_env={'PATH': tmp + ':' + os.environ['PATH'], 'MARKER': str(marker)})
            self.assertFalse(marker.exists())
            self.assertTrue(result.returncode != 0 or 'usage:' in result.stdout.lower())

    def test_restart_requires_node_and_service(self):
        result = self.run_command('--restart')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('node', (result.stdout + result.stderr).lower())


class RecoveryRestartSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('lab_recover', ROOT / 'scripts/lab-recover.py')
        assert spec is not None and spec.loader is not None
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_read_only_check_shows_reported_service_heartbeats(self):
        with mock.patch.object(self.mod, 'read_inventory', return_value=({}, ['node-a'])), \
             mock.patch.object(self.mod, 'observe_node', return_value={name: 'ACTIVE' for name in self.mod.SERVICES}), \
             mock.patch.object(self.mod, 'cloud_heartbeats', create=True, return_value=([['nova-compute', 'node-a', 'UP', 'ENABLED']], False)), \
             mock.patch.object(self.mod, 'cloud_workloads', return_value=([['(none returned)', '-']], False)), \
             mock.patch('builtins.print') as printer:
            self.assertEqual(self.mod.main(['--check']), 0)
            text = '\n'.join(str(call) for call in printer.call_args_list)
            self.assertIn('nova-compute', text)
            self.assertIn('UP', text)

    def test_all_absent_units_are_not_a_success(self):
        inv = {'compute': {'hosts': ['node-a']}}
        with mock.patch.object(self.mod, 'read_inventory', return_value=(inv, ['node-a'])), \
             mock.patch.object(self.mod, 'observe_node', return_value={name: 'ABSENT' for name in self.mod.SERVICES}), \
             mock.patch.object(self.mod, 'cloud_heartbeats', return_value=([['nova-compute', 'node-a', 'UP', 'ENABLED']], False)), \
             mock.patch.object(self.mod, 'cloud_workloads', return_value=([['(none returned)', '-']], False)), \
             mock.patch('builtins.print'):
            self.assertNotEqual(self.mod.main(['--check']), 0)

    def test_missing_expected_compute_heartbeat_is_not_a_success(self):
        inv = {'compute': {'hosts': ['node-a', 'node-b']}}
        with mock.patch.object(self.mod, 'read_inventory', return_value=(inv, ['node-a', 'node-b'])), \
             mock.patch.object(self.mod, 'observe_node', return_value={name: 'ACTIVE' for name in self.mod.SERVICES}), \
             mock.patch.object(self.mod, 'cloud_heartbeats', return_value=([['nova-compute', 'node-a', 'UP', 'ENABLED']], False)), \
             mock.patch.object(self.mod, 'cloud_workloads', return_value=([['(none returned)', '-']], False)), \
             mock.patch('builtins.print'):
            self.assertNotEqual(self.mod.main(['--check']), 0)

    def test_long_host_names_are_not_silently_truncated(self):
        host_a = 'node-' + 'a' * 40 + '-one'
        host_b = 'node-' + 'a' * 40 + '-two'
        with mock.patch.object(self.mod, 'read_inventory', return_value=({}, [host_a, host_b])), \
             mock.patch.object(self.mod, 'observe_node', return_value={name: 'ACTIVE' for name in self.mod.SERVICES}), \
             mock.patch.object(self.mod, 'cloud_heartbeats', return_value=([['nova-compute', host_a, 'UP', 'ENABLED']], False)), \
             mock.patch.object(self.mod, 'cloud_workloads', return_value=([['(none returned)', '-']], False)), \
             mock.patch('builtins.print') as printer:
            self.mod.main(['--check'])
            text = '\n'.join(str(x) for x in printer.call_args_list)
            self.assertIn(host_a, text)
            self.assertIn(host_b, text)

    def test_observe_node_cannot_inherit_become_prompt(self):
        with mock.patch.dict('os.environ', {'ANSIBLE_BECOME_ASK_PASS': 'true'}), \
             mock.patch.object(self.mod.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, stdout='')) as run:
            self.mod.observe_node('node-a', '/fake/inventory')
            self.assertEqual(run.call_args.kwargs.get('env', {}).get('ANSIBLE_BECOME_ASK_PASS'), 'false')

    def test_full_mode_shows_table_then_runs_existing_full_dashboard(self):
        with mock.patch.object(self.mod, 'check', return_value=0) as check, \
             mock.patch.object(self.mod.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(self.mod.main(['--full', '--inventory', '/fake/inventory', '--cloud', 'sample']), 0)
            check.assert_called_once_with('/fake/inventory', 'sample')
            command = run.call_args.args[0]
            self.assertEqual(command[0], 'bash')
            self.assertTrue(command[1].endswith('scripts/lab-health-full.sh'))
            self.assertEqual(command[2:], ['--inventory', '/fake/inventory', '--cloud', 'sample'])

    def test_error_vm_is_reported_as_needing_review(self):
        self.assertTrue(hasattr(self.mod, 'cloud_workloads'), 'workload health reporting is missing')
        output = subprocess.CompletedProcess([], 0, stdout='[{"Name":"fixture-guest","Status":"ERROR"}]', stderr='')
        with mock.patch.object(self.mod.subprocess, 'run', return_value=output):
            rows, issue = self.mod.cloud_workloads('test-cloud')
        self.assertTrue(issue)
        self.assertEqual(rows, [['fixture-guest', 'ERROR']])

    def test_wrong_confirmation_never_calls_restart(self):
        inventory = {'_meta': {'hostvars': {'node-a': {'ansible_host': '192.0.2.10'}}}}
        with mock.patch.object(self.mod, 'read_inventory', return_value=(inventory, ['node-a'])), \
             mock.patch.object(self.mod, 'local_addresses', return_value={'192.0.2.99'}), \
             mock.patch('sys.stdin') as stdin, mock.patch('builtins.input', return_value='no'), \
             mock.patch.object(self.mod.subprocess, 'run') as run:
            stdin.isatty.return_value = True
            self.assertNotEqual(self.mod.main(['--restart', '--node', 'node-a', '--service', 'nova_compute']), 0)
            self.assertFalse(run.called, 'restart process must not be launched')

    def test_exact_confirmation_targets_only_selected_node_and_service(self):
        inventory = {'_meta': {'hostvars': {'node-a': {'ansible_host': '192.0.2.10'}}}}
        with mock.patch.object(self.mod, 'read_inventory', return_value=(inventory, ['node-a'])), \
             mock.patch.object(self.mod, 'local_addresses', return_value={'192.0.2.99'}), \
             mock.patch('sys.stdin') as stdin, mock.patch('builtins.input', return_value='RESTART node-a nova_compute'), \
             mock.patch.object(self.mod.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            stdin.isatty.return_value = True
            self.assertEqual(self.mod.main(['--restart', '--node', 'node-a', '--service', 'nova_compute']), 0)
            args = run.call_args.args[0]
            self.assertEqual(args[0], 'ansible-playbook')
            self.assertNotIn('-K', args)
            self.assertEqual(run.call_args.kwargs['env']['ANSIBLE_BECOME_FLAGS'], '-H -n')
            import json
            extra = json.loads(args[args.index('-e') + 1])
            self.assertEqual(extra, {'recovery_target': 'node-a', 'recovery_service': 'nova_compute', 'recovery_authorized': True, 'ansible_host': '192.0.2.10', 'ansible_connection': 'ssh', 'ansible_become_flags': '-H -n'})

    def test_restart_clears_inherited_prompt_unless_explicit(self):
        inventory = {'_meta': {'hostvars': {'node-a': {'ansible_host': '192.0.2.10'}}}}
        with mock.patch.dict('os.environ', {'ANSIBLE_BECOME_ASK_PASS': 'true'}), \
             mock.patch.object(self.mod, 'read_inventory', return_value=(inventory, ['node-a'])), \
             mock.patch.object(self.mod, 'local_addresses', return_value={'192.0.2.99'}), \
             mock.patch('sys.stdin') as stdin, mock.patch('builtins.input', return_value='RESTART node-a nova_compute'), \
             mock.patch.object(self.mod.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            stdin.isatty.return_value = True
            self.assertEqual(self.mod.main(['--restart', '--node', 'node-a', '--service', 'nova_compute']), 0)
            self.assertEqual(run.call_args.kwargs.get('env', {}).get('ANSIBLE_BECOME_ASK_PASS'), 'false')

    def test_restart_explicit_password_prompt(self):
        inventory = {'_meta': {'hostvars': {'node-a': {'ansible_host': '192.0.2.10'}}}}
        with mock.patch.object(self.mod, 'read_inventory', return_value=(inventory, ['node-a'])), \
             mock.patch.object(self.mod, 'local_addresses', return_value={'192.0.2.99'}), \
             mock.patch('sys.stdin') as stdin, mock.patch('builtins.input', return_value='RESTART node-a nova_compute'), \
             mock.patch.object(self.mod.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            stdin.isatty.return_value = True
            self.assertEqual(self.mod.main(['--restart', '--node', 'node-a', '--service', 'nova_compute', '-K']), 0)
            self.assertIn('-K', run.call_args.args[0])

    def test_restart_failure_suggests_password_option(self):
        inventory = {'_meta': {'hostvars': {'node-a': {'ansible_host': '192.0.2.10'}}}}
        with mock.patch.object(self.mod, 'read_inventory', return_value=(inventory, ['node-a'])), \
             mock.patch.object(self.mod, 'local_addresses', return_value={'192.0.2.99'}), \
             mock.patch('sys.stdin') as stdin, mock.patch('builtins.input', return_value='RESTART node-a nova_compute'), \
             mock.patch.object(self.mod.subprocess, 'run', return_value=subprocess.CompletedProcess([], 2)), \
             mock.patch('builtins.print') as printer:
            stdin.isatty.return_value = True
            self.assertNotEqual(self.mod.main(['--restart', '--node', 'node-a', '--service', 'nova_compute']), 0)
            self.assertIn('--ask-become-pass', str(printer.call_args_list))

    def test_full_forwards_explicit_password_option(self):
        with mock.patch.object(self.mod, 'check', return_value=0), \
             mock.patch.object(self.mod.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(self.mod.main(['--full', '--ask-become-pass']), 0)
            self.assertIn('--ask-become-pass', run.call_args.args[0])

    def test_management_nonloopback_address_never_restarts(self):
        fake_inv = {'_meta': {'hostvars': {'node-a': {'ansible_host': '192.0.2.50'}}}}
        with mock.patch.object(self.mod, 'read_inventory', return_value=(fake_inv, ['node-a'])), \
             mock.patch.object(self.mod, 'local_addresses', create=True, return_value={'192.0.2.50'}), \
             mock.patch('sys.stdin') as stdin, mock.patch('builtins.input', return_value='RESTART node-a nova_compute'), \
             mock.patch.object(self.mod.subprocess, 'run') as run:
            stdin.isatty.return_value = True
            self.assertNotEqual(self.mod.main(['--restart', '--node', 'node-a', '--service', 'nova_compute']), 0)
            self.assertFalse(run.called, 'restart process must not be launched')

    def test_inventory_change_after_confirmation_never_restarts(self):
        inv1 = {'_meta': {'hostvars': {'node-a': {'ansible_host': '192.0.2.10'}}}}
        inv2 = {'_meta': {'hostvars': {'node-a': {'ansible_host': '192.0.2.11'}}}}
        with mock.patch.object(self.mod, 'read_inventory', side_effect=[(inv1, ['node-a']), (inv2, ['node-a'])]), \
             mock.patch.object(self.mod, 'local_addresses', create=True, return_value={'192.0.2.99'}), \
             mock.patch('sys.stdin') as stdin, mock.patch('builtins.input', return_value='RESTART node-a nova_compute'), \
             mock.patch.object(self.mod.subprocess, 'run') as run:
            stdin.isatty.return_value = True
            self.assertNotEqual(self.mod.main(['--restart', '--node', 'node-a', '--service', 'nova_compute']), 0)
            self.assertFalse(run.called, 'restart process must not be launched')

    def test_management_local_connection_never_restarts(self):
        fake_inv = {'_meta': {'hostvars': {'node-a': {'ansible_connection': 'local'}}}}
        with mock.patch.object(self.mod, 'read_inventory', return_value=(fake_inv, ['node-a'])), \
             mock.patch('sys.stdin') as stdin, mock.patch('builtins.input', return_value='RESTART node-a nova_compute'), \
             mock.patch.object(self.mod.subprocess, 'run') as run:
            stdin.isatty.return_value = True
            self.assertNotEqual(self.mod.main(['--restart', '--node', 'node-a', '--service', 'nova_compute']), 0)
            self.assertFalse(run.called, 'restart process must not be launched')

    def test_wrong_service_or_target_never_calls_restart(self):
        with mock.patch.object(self.mod, 'read_inventory', return_value=({}, ['node-a'])), \
             mock.patch('sys.stdin') as stdin, mock.patch('builtins.input', return_value='RESTART'), \
             mock.patch.object(self.mod.subprocess, 'run') as run:
            stdin.isatty.return_value = True
            self.assertNotEqual(self.mod.main(['--restart', '--node', 'node-a', '--service', 'mariadb']), 0)
            self.assertNotEqual(self.mod.main(['--restart', '--node', 'node-a:node-b', '--service', 'nova_compute']), 0)
            self.assertNotEqual(self.mod.main(['--restart', '--node', 'node-b', '--service', 'nova_compute']), 0)
            self.assertFalse(run.called, 'restart process must not be launched')

    def test_no_tty_means_no_restart(self):
        inventory = {'_meta': {'hostvars': {'node-a': {'ansible_host': '192.0.2.10'}}}}
        with mock.patch.object(self.mod, 'read_inventory', return_value=(inventory, ['node-a'])), \
             mock.patch.object(self.mod, 'local_addresses', return_value={'192.0.2.99'}), \
             mock.patch('sys.stdin') as stdin, mock.patch.object(self.mod.subprocess, 'run') as run:
            stdin.isatty.return_value = False
            self.assertNotEqual(self.mod.main(['--restart', '--node', 'node-a', '--service', 'nova_compute']), 0)
            self.assertFalse(run.called, 'restart process must not be launched')


if __name__ == '__main__':
    unittest.main()
