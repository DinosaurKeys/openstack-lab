"""Exercise the real playbook with all system-facing modules replaced by fakes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / 'ansible/playbooks/ensure-time-sync.yml'

# The action plugin records any attempted writes but never executes system commands.
PLUGIN = '''
import json, os
from ansible.plugins.action import ActionBase
class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):
        args = self._task.args
        cmd = args.get('cmd', '')
        log = os.environ['MOCK_LOG']
        with open(log, 'a') as f: f.write(json.dumps({'action': self._task.action, 'cmd': cmd, 'args': args}) + '\\n')
        zone = os.environ.get('MOCK_ZONE', 'Europe/Bucharest')
        state = os.environ['MOCK_STATE']
        if os.path.exists(state):
            with open(state) as f: zone = f.read()
        if cmd.startswith('getent hosts '):
            alias = cmd.split()[-1]
            output = {'node1': '192.0.2.1', 'node2': '192.0.2.2', 'node3': '192.0.2.3'}[alias] + ' ' + alias
        elif cmd == 'timedatectl show -p Timezone --value': output = zone
        elif cmd == 'timedatectl show -p NTPSynchronized --value': output = 'yes'
        elif cmd.startswith('systemctl is-active '): output = 'active'
        elif cmd == 'timedatectl list-timezones': output = 'Europe/Bucharest\\nUTC\\nEtc/UTC'
        elif cmd.startswith('timedatectl set-timezone '):
            with open(state, 'w') as f: f.write(cmd.split()[-1])
            return {'changed': True, 'rc': 0, 'stdout': '', 'stdout_lines': []}
        else: return {'failed': True, 'msg': 'Unexpected fake operation: ' + str(args)}
        return {'changed': False, 'rc': 0, 'stdout': output, 'stdout_lines': output.splitlines()}
'''

class TimezonePlaybookTests(unittest.TestCase):
    def run_playbook(self, variables=None, zone='Europe/Bucharest'):
        with tempfile.TemporaryDirectory(prefix='time-sync-', dir=os.environ.get('TMPDIR')) as td:
            p = Path(td)
            (p / 'action_plugins').mkdir()
            (p / 'action_plugins/mock_command.py').write_text(PLUGIN)
            text = PLAYBOOK.read_text().replace('ansible.builtin.command:', 'mock_command:')
            # Any accidental package/service operation is intercepted and fails closed.
            text = text.replace('ansible.builtin.apt:', 'mock_command:').replace('ansible.builtin.systemd_service:', 'mock_command:')
            allowed_modules = {'mock_command', 'ansible.builtin.assert', 'ansible.builtin.debug'}
            task_keys = {'name', 'register', 'changed_when', 'failed_when', 'when', 'loop', 'loop_control', 'retries', 'delay', 'until'}
            for play in yaml.safe_load(text):
                for task in play['tasks']:
                    self.assertEqual(len(set(task) - task_keys), 1, task)
                    self.assertTrue((set(task) - task_keys) <= allowed_modules, task)
            (p / 'play.yml').write_text(text)
            (p / 'inventory').write_text('[control]\nnode1 ansible_host=192.0.2.1\nnode2 ansible_host=192.0.2.2\nnode3 ansible_host=192.0.2.3\n[deployment]\nlocalhost ansible_connection=local\n')
            (p / 'ansible.cfg').write_text('[defaults]\n')
            env = os.environ.copy()
            env.update(ANSIBLE_ACTION_PLUGINS=str(p / 'action_plugins'), ANSIBLE_LOCAL_TEMP=str(p / 'local'), ANSIBLE_REMOTE_TEMP=str(p / 'remote'), ANSIBLE_NOCOLOR='1', ANSIBLE_CONFIG=str(p / 'ansible.cfg'), MOCK_LOG=str(p / 'log'), MOCK_STATE=str(p / 'state'), MOCK_ZONE=zone)
            command = ['ansible-playbook', '-i', str(p / 'inventory'), str(p / 'play.yml'), '--limit', 'node1']
            if variables: command += ['-e', json.dumps(variables)]
            result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=90)
            log = [json.loads(line) for line in (p / 'log').read_text().splitlines()] if (p / 'log').exists() else []
            return result.returncode, result.stdout, log

    def test_default_audit_accepts_bucharest_without_writes(self):
        code, output, log = self.run_playbook()
        self.assertEqual(code, 0, output)
        self.assertFalse(any(x['cmd'].startswith('timedatectl set-timezone ') for x in log))

    def test_audit_reports_timezone_mismatch_without_writes(self):
        code, output, log = self.run_playbook(zone='UTC')
        self.assertNotEqual(code, 0, output)
        self.assertIn('timezone=UTC', output)
        self.assertFalse(any(x['cmd'].startswith('timedatectl set-timezone ') for x in log))

    def test_apply_keeps_matching_timezone(self):
        code, output, log = self.run_playbook({'time_sync_apply': True})
        self.assertEqual(code, 0, output)
        self.assertFalse(any(x['cmd'].startswith('timedatectl set-timezone ') for x in log))

    def test_apply_changes_mismatched_timezone_to_lab_default(self):
        code, output, log = self.run_playbook({'time_sync_apply': True}, zone='UTC')
        self.assertEqual(code, 0, output)
        self.assertEqual([x['cmd'] for x in log if x['cmd'].startswith('timedatectl set-timezone ')], ['timedatectl set-timezone Europe/Bucharest'])

    def test_utc_override_audits_and_applies_only_when_requested(self):
        code, output, log = self.run_playbook({'time_sync_timezone': 'UTC'})
        self.assertNotEqual(code, 0, output)
        self.assertFalse(any(x['cmd'].startswith('timedatectl set-timezone ') for x in log))
        code, output, log = self.run_playbook({'time_sync_timezone': 'UTC', 'time_sync_apply': True})
        self.assertEqual(code, 0, output)
        self.assertEqual([x['cmd'] for x in log if x['cmd'].startswith('timedatectl set-timezone ')], ['timedatectl set-timezone UTC'])

    def test_guide_explains_timezone_and_management_vm_commands(self):
        text = (ROOT / 'docs/FULL-INSTALLATION-GUIDE.md').read_text()
        section = text.split('## Step 6 —', 1)[1].split('## Step 7 —', 1)[0]
        self.assertIn('Europe/Bucharest', section)
        self.assertIn('time_sync_timezone', section)
        self.assertIn('cd "$HOME/fishbone"', section)
        self.assertIn('source "$HOME/.venvs/kolla-2026.2/bin/activate"', section)
        self.assertIn('"time_sync_timezone": "Etc/UTC"', section)

    def test_invalid_timezone_is_rejected_before_any_write(self):
        code, output, log = self.run_playbook({'time_sync_apply': True, 'time_sync_timezone': 'Not/AZone'})
        self.assertNotEqual(code, 0, output)
        self.assertIn('Not/AZone', output)
        self.assertFalse(any(x['cmd'].startswith('timedatectl set-timezone ') or x['action'] != 'mock_command' or not x['cmd'] for x in log), log)

if __name__ == '__main__':
    unittest.main()
