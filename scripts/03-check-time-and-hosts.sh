#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
cd "$ROOT"
mkdir -p evidence
OUT="evidence/time-hosts-$(date -u +%Y%m%dT%H%M%SZ).txt"
{
  echo '== Step 5 check: hostname, resolver, time sync =='
  date -u
  ansible openstack_nodes -m shell -a 'hostnamectl --static; echo "-- resolv.conf --"; resolvectl status 2>/dev/null || cat /etc/resolv.conf; echo "-- timedatectl --"; timedatectl show -p NTPSynchronized -p TimeUSec 2>/dev/null || true; echo "-- chrony --"; chronyc tracking 2>/dev/null || true'
} | tee "$OUT"
printf '\nSaved evidence to %s\n' "$OUT"
printf '%s\n' 'A future apply step must be added only after OS, NIC names, DNS, and gateway are confirmed.'
