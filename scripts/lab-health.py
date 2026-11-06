#!/usr/bin/env python3
"""Read-only health checks. Output deliberately excludes command diagnostics and tokens."""
import argparse
import concurrent.futures
import re
import json
import shlex
import subprocess

TIMEOUT = 45


def group_hosts(inventory, groups):
    found, seen_groups = [], set()
    def visit(group):
        if group in seen_groups:
            return
        seen_groups.add(group)
        entry = inventory.get(group, {})
        if not isinstance(entry, dict):
            return
        for host in entry.get('hosts', []):
            if isinstance(host, str) and host not in found:
                found.append(host)
        for child in entry.get('children', []):
            visit(child)
    for group in groups:
        visit(group)
    return found


def run(args, suppress=False):
    try:
        p = subprocess.run(args, stdout=subprocess.DEVNULL if suppress else subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or '') + (('\n' + (p.stderr or '')) if args[0] == 'ansible' else '')
    except (OSError, subprocess.TimeoutExpired):
        return None, ''


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only lab health dashboard; no credentials or raw logs are displayed.')
    parser.add_argument('--inventory', default='/etc/kolla/multinode')
    parser.add_argument('--cloud', default='kolla-admin')
    parser.add_argument('--group', action='append', help='Target inventory group (repeatable; default: control, compute, network)')
    args = parser.parse_args(argv)
    issues = []
    def report(status, label):
        print(f'{status} {label}')
        if status != 'PASS':
            issues.append(status)
    rc, raw = run(['ansible-inventory', '-i', args.inventory, '--list'])
    inv = {}
    if rc == 0:
        try:
            inv = json.loads(raw)
            if not isinstance(inv, dict):
                raise ValueError()
        except (ValueError, TypeError):
            rc = None
    if rc != 0:
        report('BLOCKED', 'inventory unavailable or invalid')
    groups = args.group or ['control', 'compute', 'network']
    if rc == 0:
        for group in groups:
            if not group_hosts(inv, [group]):
                report('BLOCKED', f'inventory group {group} missing or empty')
    hosts = group_hosts(inv, groups)
    if not hosts:
        report('BLOCKED', 'target inventory groups missing or empty')
    else:
        report('PASS', f'inventory: {len(hosts)} unique target(s)')
    # Fixed, unprivileged probes; raw command output is never displayed.
    checks = [
        ('uptime', "awk '{printf \"HEALTH_VALUE=%d\\n\", $1}' /proc/uptime", 'seconds'),
        ('available memory', "awk '/^MemAvailable:/ {printf \"HEALTH_VALUE=%d\\n\", $2; found=1; exit ($2 < 262144)} END {if (!found) exit 2}' /proc/meminfo", 'KiB (minimum 262144)'),
        ('root disk', "df -Pk / | awk 'NR==2 {printf \"HEALTH_VALUE=%d\\n\", $5; found=1; exit ($5+0 >= 95)} END {if (!found) exit 2}'", '% used (limit <95%)'),
        ('docker', 'systemctl is-active --quiet docker', None),
        ('clock sync', 'test "$(timedatectl show -p NTPSynchronized --value)" = yes', None),
    ]
    jobs = []
    for host in hosts:
        for label, command, unit in checks:
            jobs.append((host, label, command, unit, False))
    for service, port in [('mariadb', 3306), ('rabbitmq', 5672)]:
        targets = group_hosts(inv, [service])
        if not targets and hosts:
            report('BLOCKED', f'{service}: inventory group missing or empty')
        for target in targets:
            variables = inv.get('_meta', {}).get('hostvars', {}).get(target, {})
            address = variables.get('ansible_host', target) if isinstance(variables, dict) else target
            if not isinstance(address, str) or not address:
                report('BLOCKED', f'{service}: invalid target address')
                continue
            for source in hosts:
                py = 'import socket,sys; s=socket.create_connection((sys.argv[1],int(sys.argv[2])),5); s.close()'
                cmd = 'python3 -c ' + shlex.quote(py) + ' ' + shlex.quote(address) + ' ' + str(port)
                jobs.append((source, f'{service} management-address TCP to {target}', cmd, None, True))
    def probe(job):
        host, label, command, unit, tcp = job
        rc, raw = run(['ansible', host + ',', '-i', args.inventory, '-e', json.dumps({'ansible_become': False}), '-m', 'ansible.builtin.shell', '-a', command])
        lower = raw.lower()
        blocked = rc is None or rc == 4 or any(x in lower for x in ('unreachable', 'missing sudo password', 'ssh connection', 'permission denied'))
        status = 'PASS' if rc == 0 else 'BLOCKED' if blocked or tcp else 'FAIL'
        value = ''
        if unit:
            match = re.search(r'^HEALTH_VALUE=(\d+)\s*$', raw, re.M)
            if match:
                value = f': {match.group(1)} {unit}'
            elif status == 'PASS':
                status = 'BLOCKED'
        return status, f'{host}: {label}{value}'
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for status, label in pool.map(probe, jobs):
            report(status, label)
    base = ['openstack', '--os-cloud', args.cloud]
    rc, _ = run(base + ['token', 'issue', '-f', 'value', '-c', 'expires'], suppress=True)
    if rc != 0:
        report('BLOCKED', 'cloud authentication unavailable')
    else:
        report('PASS', 'cloud authentication')
        def list_command(command):
            rc, raw = run(base + command + ['-f', 'json'])
            try:
                data = json.loads(raw) if rc == 0 else None
                return data if isinstance(data, list) and all(isinstance(x, dict) for x in data) else None
            except (ValueError, TypeError):
                return None
        catalog = list_command(['service', 'list'])
        service_types = {str(item.get('Type', item.get('type', ''))).lower() for item in catalog or []}
        required = {'identity', 'compute', 'network', 'image'}
        if catalog is None or not required.issubset(service_types):
            report('BLOCKED', 'registered services: required types missing or unavailable')
        else:
            report('PASS', 'registered services: required types present')
        endpoints = list_command(['endpoint', 'list'])
        enabled_types = {
            str(item.get('Service Type', item.get('service_type', ''))).lower()
            for item in endpoints or []
            if str(item.get('Enabled', item.get('enabled', ''))).lower() in ('true', 'yes', '1')
        }
        if endpoints is None or not required.issubset(enabled_types):
            report('BLOCKED', 'registered endpoints: required enabled types missing or unavailable')
        else:
            report('PASS', 'registered endpoints: required enabled types present (not individually probed)')
        for kind, command in [('compute', ['server', 'list']), ('network', ['network', 'list']), ('image', ['image', 'list'])]:
            if kind in service_types:
                report('PASS' if list_command(command) is not None else 'BLOCKED', f'cloud {kind} list')
        def service_health(label, command, network=False):
            data = list_command(command)
            if not data:
                report('BLOCKED', f'cloud {label}: unavailable or empty')
                return
            counts = {'up': 0, 'down': 0, 'enabled': 0, 'disabled': 0}
            for item in data:
                if network:
                    alive = item.get('Alive', item.get('alive'))
                    state = 'up' if alive is True or str(alive).lower() in ('true', 'yes', ':-)') else 'down' if alive is False or str(alive).lower() in ('false', 'no', 'xxx') else ''
                    admin = str(item.get('State', item.get('state', ''))).lower()
                    admin = {'up': 'enabled', 'down': 'disabled'}.get(admin, admin)
                else:
                    state = str(item.get('State', item.get('state', ''))).lower()
                    admin = str(item.get('Status', item.get('status', ''))).lower()
                if state not in ('up', 'down') or admin not in ('enabled', 'disabled'):
                    report('BLOCKED', f'cloud {label}: unrecognized status')
                    return
                counts[state] += 1
                counts[admin] += 1
            status = 'FAIL' if counts['down'] else 'REVIEW' if counts['disabled'] else 'PASS'
            report(status, f"cloud {label}: {counts['up']} up, {counts['down']} down, {counts['enabled']} enabled, {counts['disabled']} disabled")
        if 'compute' in service_types:
            service_health('reported compute service rows', ['compute', 'service', 'list'])
        if 'network' in service_types:
            service_health('reported network agent rows', ['network', 'agent', 'list'], network=True)
        if service_types.intersection({'volume', 'volumev2', 'volumev3', 'block-storage'}):
            report('PASS' if list_command(['volume', 'list']) is not None else 'BLOCKED', 'cloud volume list')
    print('NOTE TCP reachability does not prove Galera or RabbitMQ cluster health.')
    if issues:
        print('NEXT Check inventory and SSH access, then inspect failed services locally; BLOCKED means the check could not establish health.')
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
