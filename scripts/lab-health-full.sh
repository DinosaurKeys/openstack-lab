#!/usr/bin/env bash
# Read-only host/cloud and privileged foundation health audits.
set -u
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
inventory=/etc/kolla/multinode
cloud=kolla-admin
while [ "$#" -gt 0 ]; do
  case "$1" in
    --inventory|--cloud)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        printf 'Missing value for %s\n' "$1" >&2; exit 2
      fi
      if [ "$1" = --inventory ]; then inventory=$2; else cloud=$2; fi
      shift 2 ;;
    -h|--help)
      printf 'Usage: bash scripts/lab-health-full.sh [--inventory PATH] [--cloud NAME]\n'
      printf 'Read-only host/cloud checks followed by a sudo-prompted container audit.\n'
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done
printf '\n=== Host and OpenStack API checks (read-only) ===\n'
python3 "$root/scripts/lab-health.py" --inventory "$inventory" --cloud "$cloud"
health_rc=$?
printf '\n=== MariaDB and RabbitMQ local container checks (read-only) ===\n'
printf 'Enter the node sudo password at the local prompt.\n'
ANSIBLE_DISPLAY_SKIPPED_HOSTS=false ansible-playbook -i "$inventory" \
  "$root/ansible/playbooks/lab-foundation-health.yml" -K
audit_rc=$?
printf '\n=== Summary ===\n'
[ "$health_rc" -eq 0 ] && printf 'Host/API checks: PASS\n' || printf 'Host/API checks: review FAIL/BLOCKED/REVIEW above\n'
[ "$audit_rc" -eq 0 ] && printf 'Foundation local checks: PASS\n' || printf 'Foundation local checks: incomplete or failed; review above\n'
printf 'Neither check verifies full Galera or RabbitMQ cluster membership.\n'
if [ "$health_rc" -ne 0 ] || [ "$audit_rc" -ne 0 ]; then exit 1; fi
