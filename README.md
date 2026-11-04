# OpenStack Lab — guided build

This repository is a learning lab, not an unattended production installer.

The design goal is simple: every phase can be run, checked, and understood before the next phase begins. Nothing in `scripts/` changes node networking or installs OpenStack automatically.

## Your current hardware

- Management VM: runs Hermes and Ansible.
- Node 1: `192.168.0.200` — intended controller.
- Node 2: `192.168.0.201` — intended network node.
- Node 3: `192.168.0.202` — intended compute node.
- Each physical node: 16 GB RAM, Intel i5-6500T, 4 cores.
- Each node has a USB NIC for internal connectivity.

Important: the management VM needs its own reachable address. Do not assign the same IP to the management VM and Node 1. If `.200` is currently the management VM's address, change the role/IP plan before continuing.

## Recommended learning sequence

1. Linux foundation and safe recovery habits.
2. Git and repository workflow.
3. SSH keys and Ansible connectivity.
4. Discover NIC names and disk layout; do not guess them.
5. Static management/internal networking.
6. Chrony and basic host validation.
7. A small, non-HA OpenStack deployment.
8. Add network and compute services.
9. Add block storage only after a dedicated disk is identified.
10. Test failure and recovery.
11. HA/VIP only after the non-HA lab works.
12. Terraform.
13. Prometheus/Grafana.

Do not restart from zero. At the end of each phase, save the evidence under `evidence/` and continue from the first failed check.

## Read the complete guide

Start with the intensive guide and architecture picture:

- `docs/INTENSIVE-GUIDE.md` — full phase-by-phase learning and recovery guide
- `docs/architecture.md` — diagrams, traffic paths, and flow chart
- `diagrams/openstack-lab-architecture.svg` — standalone architecture picture

Open the SVG locally with:

```bash
xdg-open /home/joe/fishbone/diagrams/openstack-lab-architecture.svg
```


```bash
cd /home/joe/fishbone
bash scripts/00-local-preflight.sh
```

Then edit `inventory/hosts.yml` if the management user or addresses differ. Test only what is safe:

```bash
ansible-inventory --graph
ansible all -m ping
bash scripts/01-verify-ssh-ansible.sh
```

The first SSH connection may ask whether to trust a host key. That is not a password. This project never stores passwords and never asks Hermes to receive one.

## Phase gates

A phase is complete only when its check passes and its evidence is saved.

- Phase 0: `scripts/00-local-preflight.sh`
- Phase 1: `scripts/01-verify-ssh-ansible.sh`
- Phase 2: inspect first with `scripts/02-discover-nics-and-disks.sh`; apply networking manually only after review
- Phase 3: `scripts/03-check-time-and-hosts.sh`
- Phase 4 onward: use the deployment documentation selected after the OS and release are confirmed

## Recovery rule

When something fails:

1. Keep the current directory and files.
2. Record the exact command and error in `evidence/INCIDENTS.md`.
3. Run the smallest diagnostic that can explain the failure.
4. Fix one cause.
5. Re-run the failed phase check.
6. Do not reinstall or wipe a node unless a documented recovery step says to.

## Repository layout

```text
inventory/hosts.yml              Ansible inventory; edit before use
docs/architecture.md             topology, flow, and low-level diagrams
ansible/ansible.cfg              safe Ansible defaults
scripts/00-local-preflight.sh    management VM checks
scripts/01-verify-ssh-ansible.sh Phase 1 connectivity check
scripts/02-discover-nics-and-disks.sh safe remote discovery
scripts/03-check-time-and-hosts.sh    Phase 2/3 checks
```

## Deployment method decision

Do not install OpenStack until the operating system and disks are known. The official OpenStack installation guide is a good manual learning path; it explicitly describes a minimum proof-of-concept rather than a production deployment. OpenStack-Ansible is the later automation path that matches this repository's Ansible goal, but its current documentation has specific supported operating systems and infrastructure/storage recommendations. We will select an exact release after collecting `os-release`, CPU virtualization, disk, NIC, and memory evidence.

For this lab, the learning path is:

1. Understand the services using the official manual sequence: Keystone, Glance, Placement, Nova, then Neutron; add Horizon and Cinder afterward.
2. Automate only after the manual concepts and phase checks are understood.
3. Use OpenStack-Ansible for repeatable deployment if the hosts meet its requirements.

References are kept in the plan rather than copied into scripts:

- OpenStack installation guide: https://docs.openstack.org/install-guide/
- OpenStack-Ansible deployment guide: https://docs.openstack.org/project-deploy-guide/openstack-ansible/latest/

## What is intentionally not automated yet

- Netplan application: a wrong NIC or default route can disconnect a node.
- Disk/LVM creation: `pvcreate` can destroy data.
- OpenStack installation: the correct method depends on the node OS, OpenStack release, virtualization support, and available storage.
- HA: three physical nodes with only one controller is not automatically a highly available control plane.

Those decisions come after the discovery checks. This is deliberate.

## Git

Git is already available if this repository was cloned successfully. Learn these commands:

```bash
git status
git diff
git log --oneline --decorate -5
git add .
git commit -m "Describe the change"
```

Do not commit private keys, passwords, tokens, or generated inventory containing secrets.
