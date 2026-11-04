<div align="center">

# OpenStack Lab

### A guided walkthrough for learning and validating a reported three-node OpenStack HA lab

[![Docs](https://img.shields.io/badge/docs-learning%20guide-2563eb?style=for-the-badge)](docs/INTENSIVE-GUIDE.md)
[![Ansible](https://img.shields.io/badge/automation-Ansible-111827?style=for-the-badge&logo=ansible)](ansible/)

**Learn it. Verify it. Then automate it.**

</div>

> This repository is a learning and operations guide for the lab reported by its owner, not an installer. The included scripts are read-only checks; they do not reconfigure networking, erase disks, or install OpenStack.

[Resume here](docs/INTENSIVE-GUIDE.md#resume-here) · [Full guide](docs/INTENSIVE-GUIDE.md) · [Architecture](docs/architecture.md) · [Automation approach](docs/AUTOMATION-APPROACH.md)

## At a glance

| System | Address | Owner-reported roles |
|:--|:--|:--|
| Management VM | Separate, unique address | Git, Ansible, operator tools |
| Node 1 | `192.168.0.200` | Controller + network + compute; part of HA cluster |
| Node 2 | `192.168.0.201` | Controller + network + compute; part of HA cluster |
| Node 3 | `192.168.0.202` | Controller + network + compute; part of HA cluster |

The lab owner reports that all three nodes have controller, network, and compute roles and are configured for HA. Current service placement and HA mechanisms have not been independently verified; see [Resume here](docs/INTENSIVE-GUIDE.md#resume-here) before treating those labels as live service state.

Each physical node has 16 GB RAM and a 4-core Intel i5-6500T. The actual role of each USB NIC must be verified from the current configuration. **The management VM needs its own unique address**—do not overlap it with a node address.

![OpenStack lab architecture](diagrams/openstack-lab-architecture.svg)

## If you do not already have a local checkout

Use these clone commands only if you do not already have a checkout. For the existing lab, do not reinstall OpenStack or apply example networking. Start at the guide's [Resume here](docs/INTENSIVE-GUIDE.md#resume-here) section.

```bash
git clone https://github.com/DinosaurKeys/openstack-lab.git
cd openstack-lab
bash scripts/00-local-preflight.sh
```

As of November 4, 2026, safe checks from the management VM reached all three nodes over SSH/Ansible. The Step 4 network audit found all three nodes' management interfaces and routes up, but their USB NICs down; the actual OpenStack network/deployment path remains unverified. Start with the [Resume here](docs/INTENSIVE-GUIDE.md#resume-here) note; do not apply changes yet.

## The canonical sequence

The 13-step order is maintained in one place only: [`docs/INTENSIVE-GUIDE.md`](docs/INTENSIVE-GUIDE.md#the-13-learning-steps). According to the lab owner, controller, network, and compute roles are assigned across all three nodes; live service placement remains to be verified. HA is also owner-reported, so Step 11 verifies the setup rather than introducing it.

## What the check scripts do

These are utilities called from the guide when appropriate; their numeric filename prefixes do not correspond to learning steps.

| Script | Purpose |
|:--|:--|
| `00-local-preflight.sh` | Check local tools and inventory |
| `01-verify-ssh-ansible.sh` | Read-only SSH/Ansible connectivity check |
| `02-discover-nics-and-disks.sh` | Read-only interface, route, and disk inventory |
| `03-check-time-and-hosts.sh` | Read-only hostname, DNS, and time check |

The guide's resume section tells you what to do next; do not repeat a check just because it appears in this list.

## Repository map

| Path | Purpose |
|:--|:--|
| `docs/INTENSIVE-GUIDE.md` | Canonical 13-step guide and current resume point |
| `docs/architecture.md` | Reported roles, network layers, and conceptual traffic flows |
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

## Recovery rule

When something fails, keep the current files, record the exact command and error locally under ignored `evidence/`, run a read-only diagnostic, change one thing, and rerun that step's check. Do not reinstall or wipe a node as a first response.

Do not commit private keys, passwords, tokens, generated secret-bearing inventory, or local evidence.
