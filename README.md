<div align="center">

# OpenStack Lab

### Full installation guide for a three-node OpenStack HA learning lab

[![Docs](https://img.shields.io/badge/docs-full%20installation-2563eb?style=for-the-badge)](docs/FULL-INSTALLATION-GUIDE.md)
[![Ansible](https://img.shields.io/badge/deployment-Kolla--Ansible-111827?style=for-the-badge&logo=ansible)](https://docs.openstack.org/kolla-ansible/)

**Start with clean Ubuntu systems. Install the prerequisites, then build the cloud in order.**

</div>

This repository documents a from-scratch installation using Ubuntu Server 24.04 LTS and Kolla-Ansible. It is an operator-run procedure, not a one-command installer. Follow the [Full Installation Guide](docs/FULL-INSTALLATION-GUIDE.md) from Step 1; it deliberately assumes SSH and Ansible still need to be installed, even if they happen to exist on the current management VM.

## Target lab

| System | Target address | Kolla-Ansible roles |
|:--|:--|:--|
| Management VM | Separate, unique address | Deployment host; Git, SSH, Ansible, Kolla-Ansible, OpenStack CLI |
| Node 1 | `NODE1_MGMT_IP` | Control + network + compute |
| Node 2 | `NODE2_MGMT_IP` | Control + network + compute |
| Node 3 | `NODE3_MGMT_IP` | Control + network + compute |

The target hosts are a small learning environment, not production sizing. Confirm CPU, memory, disk, and network capacity against the Kolla-Ansible support matrix before deployment.

[![OpenStack lab architecture and 13-step full-installation map](diagrams/openstack-full-installation.svg)](diagrams/openstack-full-installation.svg)

_Visual overview only. Follow the [Full Installation Guide](docs/FULL-INSTALLATION-GUIDE.md) for the authoritative procedure and commands._

## Start here

1. Install Ubuntu Server 24.04 LTS on the management VM and all three nodes.
2. Follow every numbered step in [`docs/FULL-INSTALLATION-GUIDE.md`](docs/FULL-INSTALLATION-GUIDE.md), including installing OpenSSH and Ansible from a clean baseline.
3. Use the [architecture page](docs/architecture.md) to understand the target roles and network paths; it is a reference, not a second procedure.

## Important network and storage boundaries

- Replace each `NODE*_MGMT_IP` placeholder with a unique management address reserved outside DHCP.
- The guide requires a reserved internal VIP; choose an unused address on the management subnet before deployment.
- The baseline network design uses the management interface for host/API traffic and tunnels, and a separate provider interface for Neutron Layer-2 networking. The provider NIC must not have a host IP. Without an upstream router, that provider network is isolated and does not provide Internet access or floating-IP reachability.
- If you want management, tunnel, and provider traffic on three separate physical networks, add a third NIC per node before following the network procedure.
- Do not initialize or erase disks for Cinder until a dedicated device has been positively identified and the chosen storage backend and recovery plan are documented. Local LVM is not a replicated, highly available storage backend.
- Never commit passwords, private keys, generated Kolla passwords, cloud credentials, Terraform state, or local evidence.

## Repository map

| Path | Purpose |
|:--|:--|
| `docs/FULL-INSTALLATION-GUIDE.md` | Canonical 13-step clean-install procedure |
| `docs/architecture.md` | Target roles, network design, and service flow |
| `docs/AUTOMATION-APPROACH.md` | Safe automation and troubleshooting conventions |
| `docs/ANNEX-GITHUB-AUTH.md` | GitHub SSH authentication and safe push reminder |
| `diagrams/openstack-lab-architecture.svg` | Target topology diagram |
| `diagrams/openstack-full-installation.svg` | Privacy-safe architecture and ordered installation overview |
| `ansible/ansible.cfg` | Project Ansible defaults |

## Safety

- Use local console or another recovery path before changing node networking.
- Replace example interface names and network ranges with the values chosen during the installation; never guess a NIC, subnet, gateway, VIP, or disk.
- Keep Kolla-generated configuration and secrets under `/etc/kolla` with restrictive permissions; do not commit them.
- Test HA only after a successful deployment, with no important workloads running and a documented recovery path.

## License

No license file is currently included. Until one is added, others do not have an explicit license grant to reuse, modify, or redistribute this repository.
