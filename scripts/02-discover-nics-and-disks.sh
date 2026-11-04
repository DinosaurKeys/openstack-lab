#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
cd "$ROOT"
mkdir -p evidence
OUT="evidence/discovery-$(date -u +%Y%m%dT%H%M%SZ).txt"
{
  echo '== Safe discovery: interfaces, routes, disks =='
  date -u
  echo
  ansible openstack_nodes -m shell -a 'hostname; echo "-- links --"; ip -brief link; echo "-- addresses --"; ip -brief address; echo "-- routes --"; ip route; echo "-- disks --"; lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL'
} | tee "$OUT"
printf '\nSaved evidence to %s\n' "$OUT"
printf '%s\n' 'Do not write Netplan or run pvcreate until this output is reviewed.'
