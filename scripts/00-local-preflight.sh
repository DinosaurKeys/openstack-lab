#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
printf '%s\n' '== Local preflight ==' "repo: $ROOT"
for cmd in git ssh ansible ansible-inventory; do
  if command -v "$cmd" >/dev/null 2>&1; then
    printf 'OK   %-18s %s\n' "$cmd" "$(command -v "$cmd")"
  else
    printf 'MISS %-18s install it on the management VM\n' "$cmd"
  fi
done
printf '\nGit state:\n'
git status --short --branch
printf '\nInventory graph:\n'
ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" ansible-inventory --graph
printf '\nSSH public key candidates:\n'
find "$HOME/.ssh" -maxdepth 1 -type f -name '*.pub' -printf '  %f\n' 2>/dev/null || true
printf '\nNext: edit inventory/hosts.yml if needed, then run scripts/01-verify-ssh-ansible.sh\n'
