<div align="center">

# OpenStack Lab

### A safe, phase-by-phase learning environment for a small OpenStack cluster

[![Docs](https://img.shields.io/badge/docs-learning%20guide-2563eb?style=for-the-badge)](docs/INTENSIVE-GUIDE.md)
[![Ansible](https://img.shields.io/badge/automation-Ansible-111827?style=for-the-badge&logo=ansible)](ansible/)

**Learn it. Verify it. Then automate it.**

</div>

> This is a learning lab, not a production installer. The scripts are intentionally read-only: they inspect and validate, but do not reconfigure networking, erase disks, or install OpenStack.

[Start with the guide](docs/INTENSIVE-GUIDE.md) · [Architecture](docs/architecture.md) · [Automation approach](docs/AUTOMATION-APPROACH.md) · [GitHub authentication annex](docs/ANNEX-GITHUB-AUTH.md) · [Scripts](scripts/)

## At a glance

| System | Address | Configured roles |
|:--|:--|:--|
| Management VM | Separate, unique address | Git, Ansible, operator tools |
| Node 1 | `192.168.0.200` | Controller + network + compute; part of HA cluster |
| Node 2 | `192.168.0.201` | Controller + network + compute; part of HA cluster |
| Node 3 | `192.168.0.202` | Controller + network + compute; part of HA cluster |

Per the lab owner, all three nodes are already configured for HA and each runs controller, network, and compute roles. The learning sequence below studies those layers; it does not imply a single-node role assignment.

Each physical node has 16 GB RAM and a 4-core Intel i5-6500T. The actual role of each USB NIC must be verified from the current configuration. **The management VM needs its own unique address**—do not overlap it with a node address.

![OpenStack lab architecture](diagrams/openstack-lab-architecture.svg)

## Start here

```bash
git clone https://github.com/DinosaurKeys/openstack-lab.git
cd openstack-lab
bash scripts/00-local-preflight.sh
```

Review and adjust `inventory/hosts.yml` for your actual hosts and SSH user, then test connectivity:

```bash
ansible-inventory --graph
bash scripts/01-verify-ssh-ansible.sh
```

The first SSH connection may ask you to verify a host key. Confirm it belongs to the intended node. The repository does not store SSH passwords or private keys.

## Learning sequence

1. Linux and recovery basics
2. SSH and Ansible
3. Discover interfaces and storage
4. Static networking
5. Time synchronization
6. Controller
7. Network node
8. Compute node
9. Cinder
10. Failure testing
11. HA/VIP — verify the existing configuration
12. Terraform
13. Grafana

All three nodes are already reported to run controller, network, and compute roles in the HA cluster. These phase names describe what to learn and inspect, not a plan to assign one role per node or add HA later. See the [intensive guide](docs/INTENSIVE-GUIDE.md) for the walkthrough and [automation approach](docs/AUTOMATION-APPROACH.md) for future non-interactive checks and troubleshooting.

## Repository map

| Path | Purpose |
|:--|:--|
| `docs/INTENSIVE-GUIDE.md` | Detailed phases, checks, and recovery guidance |
| `docs/architecture.md` | Network roles, traffic flows, and Mermaid build diagram |
| `docs/AUTOMATION-APPROACH.md` | Non-interactive checks, reporting, and safe troubleshooting design |
| `docs/ANNEX-GITHUB-AUTH.md` | SSH authentication and safe Git push reminder |
| `diagrams/openstack-lab-architecture.svg` | Standalone topology diagram |
| `inventory/hosts.yml` | Ansible host inventory; review before use |
| `ansible/ansible.cfg` | Project Ansible defaults |
| `scripts/` | Local preflight and read-only node checks |

## Safety boundaries

- Never guess a NIC, gateway, subnet, or disk identity.
- Do not apply network changes without console or other recovery access.
- Existing LVM metadata means a disk may already be in use; do not run `pvcreate` as a tutorial shortcut.
- A VIP alone is not proof of end-to-end HA; verify the existing HA behavior across controller, network, compute, and storage paths.
- Keep local discovery output under `evidence/`; it is ignored by Git because it may contain private infrastructure details.

## License

No license file is currently included. Until one is added, others do not have an explicit license grant to reuse, modify, or redistribute this repository.

## Read-only checks

The current scripts provide local preflight, SSH/Ansible connectivity, interface/storage discovery, and time/host checks:

- `scripts/00-local-preflight.sh`
- `scripts/01-verify-ssh-ansible.sh`
- `scripts/02-discover-nics-and-disks.sh`
- `scripts/03-check-time-and-hosts.sh`

These checks do not apply network, storage, or OpenStack changes. See [automation approach](docs/AUTOMATION-APPROACH.md) for how future node-operation scripts should handle authentication, partial failures, reports, and approval boundaries.

## Recovery rule

When something fails, keep the current files, record the exact command and error locally under ignored `evidence/`, run a read-only diagnostic, change one thing, and rerun the failed phase check. Do not reinstall or wipe a node as a first response.

Do not commit private keys, passwords, tokens, generated secret-bearing inventory, or local evidence.
