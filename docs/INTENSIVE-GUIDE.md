# OpenStack Lab Intensive Guide

This guide is the shared operating manual for this lab. It is written for a VM engineer who is still building Linux confidence and who wants to avoid deleting the lab and starting over.

The rule is: understand one layer, verify it, save the evidence, then move forward.

## 1. Lab identity and assumptions

### Physical layout

| System | Address | Planned role | Important note |
|---|---:|---|---|
| Management VM | must be unique | Hermes, Git, Ansible | must not reuse a node address |
| Node 1 | `192.168.0.200` | Controller | APIs and control-plane services |
| Node 2 | `192.168.0.201` | Network | Neutron and virtual networking |
| Node 3 | `192.168.0.202` | Compute | KVM/libvirt and Nova compute |

Each physical node has 16 GB RAM, four CPU cores, a normal management interface, and a USB NIC intended for private/internal connectivity.

The current discovery evidence shows:

- management interface: `enp0s31f6`
- USB NIC on Node 1: `enx00e04c2c1678`
- USB NIC on Node 2: `enx00e04c557e58`
- USB NIC on Node 3: `enx00e04c304688`
- the USB NICs are currently down
- time synchronization is active
- the disks already contain LVM-backed storage, including an existing Cinder volume pool

Do not assume these names will remain unchanged after hardware changes. Re-run discovery when hardware or operating-system networking changes.

## 2. What we are building

The first milestone is not HA. It is a small, understandable OpenStack cloud that can launch one test instance.

```text
                              User / Operator
                                     |
                         SSH, Ansible, OpenStack CLI
                                     |
                         +-----------+-----------+
                         | Management LAN .0/24  |
                         +-----------+-----------+
                                     |
       +-----------------------------+-----------------------------+
       |                             |                             |
+------+-------+               +-----+------+                +-----+------+
| Node 1       |               | Node 2     |                | Node 3     |
| .200         |               | .201       |                | .202       |
| Controller   |               | Network    |                | Compute    |
|              |               |            |                |            |
| Keystone     |               | Neutron    |                | Nova       |
| Glance       |               | DHCP/L3    |                | libvirt    |
| Placement    |               | OVS/bridge |                | KVM        |
| Nova API     |               |            |                |            |
+------+-------+               +-----+------+                +-----+------+
       |                             |                             |
       +=============================+=============================+
                 Private/internal network over USB NICs
```

### Service flow for a test instance

```text
1. User authenticates with Keystone.
2. User asks Nova API to create an instance.
3. Nova scheduler selects the compute node.
4. Glance supplies the image.
5. Placement reports available CPU and RAM.
6. Neutron creates the port and network plumbing.
7. Nova-compute asks libvirt/KVM to start the guest.
8. The guest receives network configuration from Neutron DHCP.
9. Optional provider/external networking gives the guest a floating IP.
```

### Network layers

```text
Layer A: Management/API network
  Existing LAN, SSH, Ansible, OpenStack API, DNS, package downloads.

Layer B: Internal/tunnel network
  USB NICs, private node-to-node communication, tenant/tunnel traffic.

Layer C: Provider/external network
  Optional path for floating IPs. It needs a deliberate physical and
  switch/router design. It must not be invented by guessing a NIC.
```

## 3. The anti-reset operating method

When a command fails, the lab is not lost. The failure is a location marker.

### The six-step recovery loop

1. Stop at the first failed command.
2. Save the complete command and output under `evidence/`.
3. Identify the phase: Linux, SSH, network, time, controller, network node, compute, storage, or application.
4. Run a read-only diagnostic for that phase.
5. Change one thing only.
6. Re-run the phase check before touching later phases.

Never do this as a first response:

- reinstall the operating system
- delete `/etc` configuration
- recreate a volume group
- run `pvcreate` because a guide used `/dev/sdb`
- add HA to hide a broken single-node deployment
- copy commands from a different OpenStack release

### Evidence convention

```text
evidence/
  discovery-YYYYMMDDTHHMMSSZ.txt
  time-hosts-YYYYMMDDTHHMMSSZ.txt
  phase-01-ssh.txt
  phase-02-network.txt
  incidents.md
```

A good incident entry contains:

```text
Date/time:
Phase:
Command:
Observed error:
What I expected:
What I checked:
Change made:
Verification result:
Rollback:
```

## 4. Phase 1 — Linux and recovery basics

### Goal

Become comfortable enough with Linux to inspect a system without guessing.

### Commands to practice on the management VM

```bash
pwd
ls -la
cd /home/joe/fishbone
find . -maxdepth 2 -type f
id
whoami
ip -brief address
ip route
systemctl --failed
journalctl -p warning -b
```

### File editing

Start with `nano`:

```bash
nano notes.txt
```

- type text
- `Ctrl+O` saves
- press Enter to confirm
- `Ctrl+X` exits

For system files, always make a backup before editing:

```bash
sudo cp /etc/hosts /etc/hosts.bak.$(date +%Y%m%d%H%M%S)
```

### Completion criteria

You can explain the difference between:

- a file and a directory
- a process and a systemd service
- an IP address and a route
- a normal user and root
- a package and a running service

## 5. Phase 2 — SSH and Ansible

### Goal

The management VM can reach every node without storing passwords in the repository.

### Security model

- Use the normal user `joe`.
- Use an Ed25519 SSH key.
- Use Ansible privilege escalation only when required.
- Do not enable root SSH as a shortcut.
- Do not paste passwords, private keys, or MFA codes into chat.

### Check local tools

```bash
cd /home/joe/fishbone
bash scripts/00-local-preflight.sh
```

### Inventory

The inventory is in `inventory/hosts.yml`. Change only the values that are actually different in your lab.

```bash
ANSIBLE_CONFIG=/home/joe/fishbone/ansible/ansible.cfg \
  ansible-inventory --graph
```

### Verify connectivity

```bash
cd /home/joe/fishbone
bash scripts/01-verify-ssh-ansible.sh
```

Expected result:

- three `pong` responses
- each node reports its hostname and management address
- the script ends with `PHASE 1 PASSED`

### Common failure map

| Symptom | First check |
|---|---|
| timeout | `ping`, `ip route`, firewall, SSH service |
| permission denied | user name, authorized key, sudo rights |
| host key warning | confirm the address is the intended node |
| Python missing | install Python 3 on the node, then rerun |
| wrong node answers | duplicate IP or stale ARP; stop and fix addressing |

## 6. Phase 3 — Discover interfaces and storage

### Goal

Replace guesses with facts before changing networking or storage.

```bash
cd /home/joe/fishbone
bash scripts/02-discover-nics-and-disks.sh
```

Inspect:

```text
ip -brief link       interface names and link state
ip -brief address    assigned addresses
ip route             default route and connected networks
lsblk                disks, filesystems, mounts, LVM
```

### Current lab finding

The USB NICs are visible but down. This means the physical/internal network must be checked before creating an internal subnet.

The storage output already shows an LVM-backed Cinder pool. Therefore:

- do not run `pvcreate`
- do not run `vgcreate`
- do not assume `/dev/sdb` is unused
- document the existing volume group and pool before changing storage

## 7. Phase 4 — Static networking

### Goal

Give each host stable, predictable addresses while preserving SSH access.

### Proposed network design

```text
Management LAN: 192.168.0.0/24
  Node 1: 192.168.0.200/24
  Node 2: 192.168.0.201/24
  Node 3: 192.168.0.202/24
  Gateway: existing LAN gateway, normally 192.168.0.1

Private USB network: choose an unused subnet after checking the LAN
  Example only: 192.168.10.0/24
  Node 1: 192.168.10.2/24
  Node 2: 192.168.10.3/24
  Node 3: 192.168.10.4/24
  No default gateway on this isolated interface
```

The example private subnet is not automatically correct. Confirm it does not overlap with your LAN, VPN, Docker, libvirt, or Wi-Fi networks.

### Safe change process

1. Confirm a local console or another recovery path.
2. Confirm the USB cables/switch path.
3. Confirm the exact USB NIC name on each node.
4. Create a candidate Netplan file.
5. Check YAML syntax and routes.
6. Apply one node at a time.
7. Test SSH immediately.
8. Save the result.

Do not configure a default route on the isolated USB network. Keep the default route on the management interface unless the final design explicitly requires otherwise.

## 8. Phase 5 — Time synchronization

### Goal

All nodes agree on time before authentication, queues, databases, or OpenStack services are installed.

```bash
cd /home/joe/fishbone
bash scripts/03-check-time-and-hosts.sh
```

Useful checks on a node:

```bash
timedatectl
chronyc tracking
chronyc sources -v
```

Completion criteria:

- `NTPSynchronized=yes`
- a healthy time source is selected
- hostnames resolve consistently
- all nodes show the expected UTC time

## 9. Phase 6 — Controller bootstrap

### Goal

Build and understand the control plane on Node 1 before distributing complexity.

### Services and responsibilities

| Service | Responsibility |
|---|---|
| Keystone | identity, users, projects, tokens |
| Glance | image catalog and image storage |
| Placement | resource inventory and allocation |
| Nova API | compute API |
| Nova scheduler | chooses a compute host |
| Database | persistent service state |
| Message queue | service-to-service messaging |

### Deployment method gate

Choose one method for one OpenStack release. Do not mix snippets from manual packages, OpenStack-Ansible, Kolla, Juju, or DevStack.

The exact choice depends on:

- operating-system release
- supported OpenStack release
- free disk space
- KVM availability
- network design
- whether this is a manual learning build or an automation build

For learning, understand the official service order first. For repeatable deployment, use one supported automation project after its requirements are checked. The commands are deliberately not hard-coded here until the OS and release are confirmed.

### Controller checks

The controller phase is complete only when you can verify:

- Keystone token issuance
- service catalog endpoints
- Glance image upload/list
- Placement resource inventory
- Nova service list
- API access from the management VM

## 10. Phase 7 — Network node

### Goal

Understand how Neutron turns a logical network into Linux/OVS datapath state.

Conceptual flow:

```text
OpenStack API request
        |
        v
Neutron server
        |
        +-- ML2 plugin and mechanism driver
        |
        +-- DHCP agent -> guest address configuration
        |
        +-- L3 agent -> routers and namespaces
        |
        +-- OVS/Linux bridge -> ports, tunnels, provider path
```

The final bridge and tunnel design depends on the selected Neutron backend. Discover the provider NIC before configuring external networking.

Completion criteria:

- Neutron agents are up
- a tenant network can be created
- a subnet can be created
- DHCP supplies an address to a test port
- the network node can be diagnosed using namespaces and bridge state

## 11. Phase 8 — Compute node

### Goal

Launch a guest on Node 3 and trace its complete path.

First verify hardware virtualization:

```bash
lscpu | grep -E 'Virtualization|Model name'
ls -l /dev/kvm
virsh list --all
```

A compute phase is not complete because a service is running. It is complete when:

1. Nova sees the compute service.
2. Placement reports resources.
3. An instance is scheduled.
4. The guest boots.
5. The guest gets a port and address.
6. Console/log inspection explains any failure.

## 12. Phase 9 — Cinder

### Goal

Provide block storage without damaging existing disks.

Cinder concepts:

```text
User -> Cinder API -> scheduler -> cinder-volume -> backend
                                      |
                                      +-- LVM/iSCSI/other backend
```

Before any storage command:

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL
pvs
vgs
lvs
findmnt
```

A disk is eligible only when its identity, capacity, and lack of important data are confirmed. Existing LVM metadata is evidence that the disk is already in use, not evidence that it is free.

Completion criteria:

- a volume type/backend is visible
- a small test volume can be created
- the volume can attach to a test instance
- the volume can be detached cleanly
- the data path and recovery procedure are documented

## 13. Phase 10 — Failure testing

Do not call the lab reliable until failure behavior is observed.

Start with reversible tests:

```text
1. Restart one service.
2. Stop and start one agent.
3. Reboot the compute node while no important workload runs.
4. Reboot the network node after confirming console access.
5. Temporarily disconnect the USB NIC, then restore it.
6. Verify services return and test instance state is understood.
```

For each test record:

- what failed
- what remained available
- what alarms/logs appeared
- how long recovery took
- what manual action was needed

## 14. Phase 11 — HA/VIP

### Goal

Only after the single-controller lab works, design a real control-plane failure domain.

A VIP by itself is not HA. A resilient design needs coordinated handling for:

- API services
- database replication
- message queue availability
- identity and token behavior
- image and control-plane storage
- network agents
- monitoring and fencing

With the current three-node role plan, Node 1 is the only controller. Keepalived can move an address, but it does not replicate Keystone, Nova, the database, or the message queue. Treat HA as a separate architecture project, not a switch to turn on.

## 15. Phase 12 — Terraform

Terraform belongs after the cloud can reliably create resources manually.

Learning order:

1. Create a network manually.
2. Create a subnet manually.
3. Create a security group.
4. Launch an instance.
5. Repeat the same work with Terraform.
6. Compare Terraform state with OpenStack state.

Never commit:

- passwords
- application credentials
- private keys
- `clouds.yaml` containing secrets
- Terraform state containing secrets

Use a protected secret store or environment variables.

## 16. Phase 13 — Grafana

Monitoring should answer operational questions:

- Are hosts up?
- Is time synchronized?
- Are disks full?
- Are OpenStack services up?
- Are Neutron agents alive?
- Is the compute node reporting resources?
- Are instances booting and receiving networks?

Build the monitoring stack in this order:

```text
node exporter / host metrics
        |
        v
Prometheus -> targets and alert rules -> Grafana dashboards
                                      |
                                      +-> OpenStack exporter/service metrics
```

Validate the Prometheus target directly before importing dashboards. A dashboard with no verified data is decoration, not monitoring.

## 17. Daily operating checklist

```text
[ ] I am in /home/joe/fishbone.
[ ] git status shows what changed.
[ ] I know which phase I am working on.
[ ] I have a recovery path before changing networking/storage.
[ ] I ran discovery instead of guessing.
[ ] I saved command output for the phase.
[ ] I changed one thing only.
[ ] I reran the phase check.
[ ] I did not commit secrets.
```

## 18. Definition of done for the first milestone

The first milestone is complete when:

- Ansible reaches all three nodes.
- Management and internal network roles are understood.
- All nodes have synchronized time.
- Controller APIs respond.
- Network services create a usable tenant network.
- Compute launches a test instance.
- Storage behavior is documented and tested if enabled.
- At least one failure/recovery exercise is recorded.
- The repository contains enough evidence to resume without reinstalling.

Only then should we begin HA, Terraform, or Grafana.
