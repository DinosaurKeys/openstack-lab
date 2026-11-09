#!/usr/bin/env python3
"""Read-only service overview and explicit one-service operator action."""
import argparse
import concurrent.futures
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys

SERVICES = (
    'mariadb', 'rabbitmq', 'haproxy', 'placement_api', 'nova_api', 'neutron_server',
    'nova_compute', 'nova_conductor', 'nova_scheduler', 'neutron_openvswitch_agent',
    'neutron_l3_agent', 'neutron_dhcp_agent', 'neutron_metadata_agent', 'cinder_scheduler',
)
TARGET_GROUPS = ('control', 'compute', 'network', 'storage')
REQUIRED_UNIT_GROUPS = {
    'mariadb': 'mariadb', 'rabbitmq': 'rabbitmq', 'placement_api': 'placement-api',
    'nova_api': 'nova-api', 'neutron_server': 'neutron-server', 'nova_compute': 'compute',
}
RESTART_SERVICES = frozenset({
    'nova_compute', 'nova_conductor', 'nova_scheduler', 'placement_api', 'nova_api',
    'neutron_server', 'neutron_openvswitch_agent', 'neutron_l3_agent',
    'neutron_dhcp_agent', 'neutron_metadata_agent', 'cinder_scheduler',
})
ROOT = Path(__file__).resolve().parents[1]
HOST = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
ROW = re.compile(r'^LAB_UNIT\|([a-z0-9_]+)\|([a-z-]+)\|([a-z-]+)\s*$', re.M)


def hosts_for_groups(inventory, groups):
    hosts, visited = [], set()
    def visit(name):
        if name in visited:
            return
        visited.add(name)
        group = inventory.get(name, {})
        if not isinstance(group, dict):
            return
        for host in group.get('hosts', []):
            if isinstance(host, str) and host not in hosts:
                hosts.append(host)
        for child in group.get('children', []):
            if isinstance(child, str):
                visit(child)
    for name in groups:
        visit(name)
    return hosts


def inventory_hosts(inventory):
    return hosts_for_groups(inventory, TARGET_GROUPS)


def read_inventory(path):
    try:
        proc = subprocess.run(['ansible-inventory', '-i', path, '--list'], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True, timeout=30)
        if proc.returncode != 0:
            return None, []
        inventory = json.loads(proc.stdout)
        if not isinstance(inventory, dict):
            return None, []
        hosts = inventory_hosts(inventory)
        if not hosts or any(len(h) > 128 or not HOST.fullmatch(h) or h.lower() == 'localhost' for h in hosts):
            return None, []
        return inventory, hosts
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return None, []


def observe_node(host, inventory_path):
    names = ' '.join(shlex.quote(n) for n in SERVICES)
    command = (
        'for s in ' + names + '; do u="kolla-${s}-container.service"; '
        'load=$(systemctl show "$u" -p LoadState --value 2>/dev/null) || load=unknown; '
        'state=$(systemctl show "$u" -p ActiveState --value 2>/dev/null) || state=unknown; '
        'printf "LAB_UNIT|%s|%s|%s\\n" "$s" "$load" "$state"; done'
    )
    try:
        proc = subprocess.run(['ansible', host + ',', '-i', inventory_path, '-e', '{"ansible_become": false}',
                               '-m', 'ansible.builtin.shell', '-a', command], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True, timeout=40,
                              env=dict(os.environ, ANSIBLE_BECOME_ASK_PASS='false'))
        if proc.returncode != 0:
            return {name: 'BLOCKED' for name in SERVICES}
        found = {}
        for match in ROW.finditer(proc.stdout):
            name, load, active = match.groups()
            if name not in SERVICES or name in found:
                return {service: 'BLOCKED' for service in SERVICES}
            if load == 'not-found':
                found[name] = 'ABSENT'
            elif load != 'loaded':
                found[name] = 'BLOCKED'
            elif active == 'active':
                found[name] = 'ACTIVE'
            elif active == 'activating':
                found[name] = 'STARTING'
            elif active == 'inactive':
                found[name] = 'STOPPED'
            elif active == 'failed':
                found[name] = 'FAILED'
            else:
                found[name] = 'BLOCKED'
        return {name: found.get(name, 'BLOCKED') for name in SERVICES}
    except (OSError, subprocess.TimeoutExpired):
        return {name: 'BLOCKED' for name in SERVICES}


def render_rows(rows):
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    for i, row in enumerate(rows):
        print('  '.join(value.ljust(widths[j]) for j, value in enumerate(row)).rstrip())
        if i == 0:
            print('  '.join('-' * width for width in widths))


def cloud_heartbeats(cloud):
    rows, issue = [], False
    for kind, command in [('Compute services', ['compute', 'service', 'list']), ('Network agents', ['network', 'agent', 'list'])]:
        try:
            proc = subprocess.run(['openstack', '--os-cloud', cloud, *command, '-f', 'json'], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True, timeout=45)
            data = json.loads(proc.stdout) if proc.returncode == 0 else None
            if not isinstance(data, list) or not data or not all(isinstance(item, dict) for item in data):
                raise ValueError('unavailable or empty')
            for item in data:
                if kind == 'Compute services':
                    service, host = item.get('Binary', item.get('binary')), item.get('Host', item.get('host'))
                    state = str(item.get('State', item.get('state', ''))).lower()
                    admin = str(item.get('Status', item.get('status', ''))).lower()
                else:
                    service, host = item.get('Agent Type', item.get('agent_type')), item.get('Host', item.get('host'))
                    alive = str(item.get('Alive', item.get('alive', ''))).lower()
                    state = {'true': 'up', 'yes': 'up', ':-)': 'up', 'false': 'down', 'no': 'down', 'xxx': 'down'}.get(alive, '')
                    admin_raw = str(item.get('State', item.get('state', ''))).lower()
                    admin = {'true': 'enabled', 'up': 'enabled', 'false': 'disabled', 'down': 'disabled'}.get(admin_raw, admin_raw)
                if not isinstance(service, str) or not isinstance(host, str) or not re.fullmatch(r'[A-Za-z0-9_. -]{1,80}', service) or not HOST.fullmatch(host):
                    raise ValueError('invalid service identity')
                if state not in ('up', 'down') or admin not in ('enabled', 'disabled'):
                    raise ValueError('unrecognized status')
                rows.append([service, host, state.upper(), admin.upper()])
                if state != 'up' or admin != 'enabled':
                    issue = True
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
            rows.append([kind, '-', 'BLOCKED', '-'])
            issue = True
    return rows, issue


def cloud_workloads(cloud):
    try:
        proc = subprocess.run(['openstack', '--os-cloud', cloud, 'server', 'list', '--all-projects', '-f', 'json'],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True, timeout=45)
        data = json.loads(proc.stdout) if proc.returncode == 0 else None
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise ValueError('VM list unavailable')
        rows, issue = [], False
        for item in data:
            name, status = item.get('Name', item.get('name')), item.get('Status', item.get('status'))
            if not isinstance(name, str) or not name or len(name) > 128 or not isinstance(status, str) or not re.fullmatch(r'[A-Za-z_]{1,40}', status):
                raise ValueError('invalid VM data')
            clean_name = ''.join(char if char.isprintable() else f'\\u{ord(char):04x}' for char in name)
            state = status.upper()
            rows.append([clean_name, state])
            if state not in ('ACTIVE', 'SHUTOFF', 'PAUSED', 'SUSPENDED', 'SHELVED', 'SHELVED_OFFLOADED'):
                issue = True
        return rows or [['(none returned)', '-']], issue
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return [['VM list', 'BLOCKED']], True


def check(inventory_path, cloud):
    inventory, hosts = read_inventory(inventory_path)
    if not hosts:
        print('BLOCKED: inventory is unavailable, empty, or has an unsafe target alias.')
        return 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(hosts))) as pool:
        states = dict(zip(hosts, pool.map(lambda host: observe_node(host, inventory_path), hosts)))
    coverage_notes = []
    for service, group in REQUIRED_UNIT_GROUPS.items():
        expected = hosts_for_groups(inventory or {}, [group])
        for host in expected:
            if host not in states:
                coverage_notes.append(f'BLOCKED: expected {service} host {host} was not checked.')
            elif states[host][service] == 'ABSENT':
                states[host][service] = 'MISSING'
        if not expected and all(states[host][service] == 'ABSENT' for host in hosts):
            coverage_notes.append(f'BLOCKED: no {service} unit found and expected placement is unavailable.')
    print('\n=== Service units (read-only) ===')
    render_rows([['SERVICE', *hosts]] + [[service, *(states[host][service] for host in hosts)] for service in SERVICES])
    print('\nACTIVE means the systemd unit is active; it does not prove container, API, or cluster health.')
    print('ABSENT means the unit is not installed on that node; check whether it is expected there.')
    print('MISSING means a core unit is absent on a host in its expected inventory group.')
    print('BLOCKED means the check could not establish the unit state. STARTING may need time.')
    print('\n=== OpenStack reported heartbeats (read-only) ===')
    heartbeat_rows, heartbeat_issue = cloud_heartbeats(cloud)
    render_rows([['SERVICE OR AGENT', 'HOST', 'STATE', 'ADMIN']] + heartbeat_rows)
    compute_expected = set(hosts_for_groups(inventory or {}, ['compute']))
    compute_reported = {row[1] for row in heartbeat_rows if row[0] == 'nova-compute'}
    missing_compute = sorted(compute_expected - compute_reported)
    if missing_compute:
        coverage_notes.append('BLOCKED: no nova-compute heartbeat row for: ' + ', '.join(missing_compute))
    for note in coverage_notes:
        print(note)
    print('Compute heartbeat coverage uses inventory aliases and must be checked if service hostnames differ.')
    print('Other heartbeat types are only API-returned rows; missing expected agent hosts are not detected.')
    print('\n=== Reported VMs (read-only) ===')
    vm_rows, vm_issue = cloud_workloads(cloud)
    render_rows([['VM', 'STATUS']] + vm_rows)
    print('VM status alone does not prove guest connectivity or storage health.')
    print('Use --full for the host/cloud and MariaDB/RabbitMQ checks; add --ask-become-pass if needed.')
    unit_issue = any(value in ('BLOCKED', 'FAILED', 'STOPPED', 'STARTING', 'MISSING') for row in states.values() for value in row.values())
    return 1 if unit_issue or heartbeat_issue or vm_issue or coverage_notes else 0


def local_addresses():
    proc = subprocess.run(['ip', '-j', 'address', 'show'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          stdin=subprocess.DEVNULL, text=True, timeout=10, check=True)
    records = json.loads(proc.stdout)
    if not isinstance(records, list):
        raise ValueError('invalid local network data')
    addresses = set()
    for interface in records:
        for entry in interface.get('addr_info', []):
            value = entry.get('local')
            if value:
                addresses.add(str(ipaddress.ip_address(value)))
    if not addresses:
        raise ValueError('no local network addresses')
    return addresses


def restart(inventory_path, node, service, ask_become_pass=False):
    if service not in RESTART_SERVICES:
        print('BLOCKED: service is not in the approved restart list; MariaDB and RabbitMQ are excluded.')
        return 2
    if not HOST.fullmatch(node) or node.lower() == 'localhost':
        print('BLOCKED: choose one exact inventory host alias, not a pattern or localhost.')
        return 2
    inventory, hosts = read_inventory(inventory_path)
    if node not in hosts:
        print('BLOCKED: the selected host was not found in the target inventory groups.')
        return 2
    metadata = (inventory or {}).get('_meta', {}).get('hostvars', {}).get(node, {})
    if not isinstance(metadata, dict):
        print('BLOCKED: target host variables are invalid.')
        return 2
    address = metadata.get('ansible_host', node)
    if not isinstance(address, str):
        print('BLOCKED: target address is invalid.')
        return 2
    try:
        target_ip = ipaddress.ip_address(address)
        local_ips = local_addresses()
    except (ValueError, OSError, subprocess.SubprocessError, TypeError):
        print('BLOCKED: target must have a literal IP and local interface addresses must be readable.')
        return 2
    if (str(metadata.get('ansible_connection', '')).lower() in ('local', 'ansible.builtin.local')
            or address.lower() in ('localhost', socket.gethostname().lower()) or target_ip.is_loopback
            or target_ip.is_unspecified or target_ip.is_multicast or str(target_ip) in local_ips):
        print('BLOCKED: a local, loopback, or invalid target cannot be restarted from this tool.')
        return 2
    connection = str(metadata.get('ansible_connection', 'ssh')).lower()
    if connection not in ('ssh', 'ansible.builtin.ssh'):
        print('BLOCKED: this action requires an SSH inventory connection.')
        return 2
    if not sys.stdin.isatty():
        print('BLOCKED: a local interactive terminal is required for confirmation.')
        return 2
    phrase = f'RESTART {node} {service}'
    print(f'\nSelected: {service} on {node} only (target address: {target_ip}).')
    print('This interrupts the service and may affect workloads. Review logs, dependencies, and the remaining replicas first.')
    print('Only this unit is requested; systemd dependencies may affect other units. A stopped unit can be started.')
    try:
        confirmation = input(f'Type {phrase} to proceed, or anything else to cancel: ')
    except (EOFError, KeyboardInterrupt):
        print('\nCancelled; no restart sent.')
        return 1
    if confirmation != phrase:
        print('Cancelled; no restart sent.')
        return 1
    fresh_inventory, fresh_hosts = read_inventory(inventory_path)
    if fresh_inventory != inventory or node not in fresh_hosts:
        print('BLOCKED: inventory changed during confirmation; no restart sent.')
        return 1
    try:
        if str(target_ip) in local_addresses():
            print('BLOCKED: target is now a local address; no restart sent.')
            return 1
    except (ValueError, OSError, subprocess.SubprocessError, TypeError):
        print('BLOCKED: local network state is unavailable; no restart sent.')
        return 1
    values = {'recovery_target': node, 'recovery_service': service, 'recovery_authorized': True,
              'ansible_host': str(target_ip), 'ansible_connection': 'ssh'}
    if metadata.get('ansible_user') or metadata.get('ansible_ssh_user'):
        values['ansible_user'] = metadata.get('ansible_user') or metadata.get('ansible_ssh_user')
    if metadata.get('ansible_port'):
        values['ansible_port'] = metadata['ansible_port']
    if not ask_become_pass:
        values['ansible_become_flags'] = '-H -n'
    extra = json.dumps(values)
    env = dict(os.environ, ANSIBLE_DISPLAY_SKIPPED_HOSTS='false',
               ANSIBLE_BECOME_ASK_PASS='true' if ask_become_pass else 'false')
    if not ask_become_pass:
        env['ANSIBLE_BECOME_FLAGS'] = '-H -n'
    command = ['ansible-playbook', '-i', inventory_path, str(ROOT / 'ansible/playbooks/lab-restart-service.yml')]
    if ask_become_pass:
        command.append('-K')
    command.extend(['-e', extra])
    try:
        result = subprocess.run(command, env=env, check=False).returncode
        if result and not ask_become_pass:
            print('Restart failed or was incomplete. Check the service state before any retry; if sudo needs a password, use --ask-become-pass.')
        return result
    except OSError:
        print('BLOCKED: ansible-playbook could not be started; no success claimed.')
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Read-only overview by default; selected restarts require explicit confirmation.',
        epilog='Approved restart names: ' + ', '.join(sorted(RESTART_SERVICES)) + '. MariaDB and RabbitMQ are excluded.',
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='read-only service overview (default)')
    mode.add_argument('--full', action='store_true', help='run the existing full, read-only foundation dashboard')
    mode.add_argument('--restart', action='store_true', help='restart one explicitly selected unit')
    parser.add_argument('--node', help='one exact inventory host alias')
    parser.add_argument('--service', help='one exact approved service name')
    parser.add_argument('--inventory', default='/etc/kolla/multinode')
    parser.add_argument('--cloud', default='kolla-admin')
    parser.add_argument('-K', '--ask-become-pass', action='store_true', help='prompt locally for the sudo password (with --full or --restart)')
    args = parser.parse_args(argv)
    if args.ask_become_pass and not (args.full or args.restart):
        parser.error('--ask-become-pass requires --full or --restart')
    if args.restart and (not args.node or not args.service):
        parser.error('--restart requires both --node and --service')
    if args.restart:
        return restart(args.inventory, args.node, args.service, args.ask_become_pass)
    if args.node or args.service:
        parser.error('--node and --service are only valid with --restart')
    if args.full:
        quick_result = check(args.inventory, args.cloud)
        sys.stdout.flush()
        try:
            command = ['bash', str(ROOT / 'scripts/lab-health-full.sh'), '--inventory', args.inventory, '--cloud', args.cloud]
            if args.ask_become_pass:
                command.append('--ask-become-pass')
            full_result = subprocess.run(command, check=False).returncode
            return 1 if quick_result or full_result else 0
        except OSError:
            print('BLOCKED: full health dashboard could not be started.')
            return 1
    return check(args.inventory, args.cloud)


if __name__ == '__main__':
    raise SystemExit(main())
