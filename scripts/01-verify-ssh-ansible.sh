#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
cd "$ROOT"
printf '%s\n' '== Step 2 check: SSH + Ansible connectivity =='
printf '%s\n' 'This is a read-only connectivity test. It does not request or store passwords.'
ansible all -m ping
ansible openstack_nodes -m shell -a 'hostname; id -un; ip -brief address'
printf '%s\n' 'STEP 2 PASSED'
