# OpenStack Lab Intensive Guide

This guide is the shared operating manual for this lab. It is written for a VM engineer who is still building Linux confidence and who wants to avoid deleting the lab and starting over.

The rule is: understand one layer, verify it, save the evidence, then move forward.

## 1. Lab identity and confirmed role model

### Physical layout

| System | Address | Configured roles | Important note |
|---|---:|---|---|
| Management VM | must be unique | Hermes, Git, Ansible | must not reuse a node address |
| Node 1 | `192.168.0.200` | Controller + network + compute; HA member |
| Node 2 | `192.168.0.201` | Controller + network + compute; HA member |
| Node 3 | `192.168.0.202` | Controller + network + compute; HA member |

Per the lab owner, all three nodes have controller, network, and compute roles and are configured for HA. The phase names below are learning topics, not a proposal to split roles across nodes or deploy a new single-controller cloud. The exact HA implementation and current service state must still be read from the nodes before troubleshooting or failover actions.

Each physical node has 16 GB RAM and four CPU cores. It has a management interface and USB NIC hardware; discover each NIC's actual current role rather than assuming the USB NIC is private/internal.

An earlier discovery snapshot recorded the following observations; they have not been freshly verified as part of this documentation update. Treat them as historical until phase 3 is rerun:

- management interface: `enp0s31f6`
- USB NIC on Node 1: `enx00e04c2c1678`
- USB NIC on Node 2: `enx00e04c557e58`
- USB NIC on Node 3: `enx00e04c304688`
- the USB NICs are currently down
- time synchronization is active
- the disks already contain LVM-backed storage, including an existing Cinder volume pool

Do not assume these names will remain unchanged after hardware changes. Re-run discovery when hardware or operating-system networking changes.

## 2. What we are building

The existing three-node HA cluster is the environment we are learning and operating. The sequence below focuses on understanding and validating its components, then testing recovery safely; it is not a plan to install a new non-HA cloud.

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
| Controller   |               | Controller |                | Controller |
| Network      |               | Network    |                | Network    |
| Compute + HA |               | Compute+HA |                | Compute+HA |
| All roles are present on all three nodes; discover exact service placement. |
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
3. Identify the phase: Linux, SSH, network, time, controller services, network services, compute services, storage, HA, or application.
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

The earlier snapshot recorded USB NICs as visible but down. Re-discover all links, bridges, routes, and provider-network configuration before deciding their current purpose or changing network settings.

That earlier storage output showed an LVM-backed Cinder pool. Confirm current storage state before relying on it. Until verified:

- do not run `pvcreate`
- do not run `vgcreate`
- do not assume `/dev/sdb` is unused
- document the existing volume group and pool before changing storage

## 7. Phase 4 — Static networking

### Goal

Verify the existing address, route, DNS, bridge, and VLAN configuration while preserving SSH/API access. Create a reviewed change plan only if discovery shows a real problem; do not reconfigure a working HA cluster simply to follow a tutorial example.

### Network discovery and change plan

```text
Management/API network: record actual addresses, routes, gateway, DNS, and API endpoint path.
Internal/tunnel network: identify configured interfaces, bridges, VLANs, and overlay.
Provider/external network: identify the actual uplink and its relationship to the switch/LAN.
Do not create a second subnet or move a default route based on this example alone.
```

Do not assume a USB NIC is an isolated underlay or that any example subnet is correct. Confirm current cabling and configuration, and check for overlap with LAN, VPN, Docker, libvirt, and Wi-Fi networks.

### Safe change process

1. Collect interface, address, route, DNS, bridge, and VLAN state from all nodes.
2. Compare management reachability and the actual OpenStack network configuration.
3. If a change is necessary, identify its exact scope and expected failover impact.
4. Confirm a local console or other recovery path and obtain approval before applying it.
5. Validate the candidate configuration and rollback procedure before a one-node-at-a-time change.
6. Recheck SSH, API reachability, cluster health, and workload networking after each change.
7. Save redacted evidence and the result.

Do not add or move a default route based on an assumed interface role. Confirm the live routing design and failover implications first.

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

## 9. Phase 6 — Controller

### Goal

Understand and inspect the controller services across the existing HA cluster. Do not assume Node 1 is the only controller or bootstrap a new control plane. First discover where APIs, databases, message queues, and supporting services actually run and how they are monitored.

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

Understand how the existing Neutron/network services turn a logical network into Linux/OVS datapath state across the cluster. Identify which agents run on which nodes from live observations rather than assuming a dedicated network node.

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
- network agents, namespaces, bridges, and HA router state can be diagnosed on all relevant nodes

## 11. Phase 8 — Compute node

### Goal

Understand the compute service on each node and trace a test guest's scheduling, network, and storage path. Do not assume Node 3 is the only hypervisor; discover the actual placement and capacity first.

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

Start with reversible, explicitly scoped tests only after reviewing current quorum, workload placement, and recovery access. Because all three nodes run controller, network, and compute roles, do not assume a “network node” or “compute node” is a dedicated failure domain. Get approval before disrupting a node or service.

```text
1. Observe one service/agent and confirm which HA peers and workloads depend on it.
2. Test a single, approved service/agent failure scenario.
3. Use planned maintenance for a node-level test; all three nodes carry multiple roles.
4. Test a network-link interruption only if its real use and recovery path are known.
5. Verify API access, quorum, workload placement, guest connectivity, and storage behavior.
6. Restore the original state and record the observed recovery.
```

For each test record:

- what failed
- what remained available
- what alarms/logs appeared
- how long recovery took
- what manual action was needed

## 14. Phase 11 — Existing HA/VIP verification

### Goal

The owner reports that all three nodes are already configured for HA. This phase is to discover, document, and validate that configuration—not to add HA later or create an unplanned VIP.

A VIP by itself is not HA. A resilient design needs coordinated handling for:

- API services
- database replication
- message queue availability
- identity and token behavior
- image and control-plane storage
- network agents
- monitoring and fencing

Before any failure test, identify the real VIP owner mechanism, API proxy, database/quorum behavior, messaging topology, network-agent/router state, storage guarantees, and recovery procedure. A VIP move alone does not prove the service or data path survived. Run one scoped, approved, reversible test at a time and check user-visible API and workload behavior as well as process state.

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

## 18. Definition of done for this learning sequence

The first milestone is complete when:

- Ansible reaches all three nodes and can collect independent per-node observations.
- Management and internal network roles are understood.
- Controller, network, and compute services are mapped across all three nodes.
- All nodes have synchronized time.
- Controller APIs respond.
- Network services create a usable tenant network.
- Compute launches a test instance.
- Storage behavior is documented and tested if enabled.
- The existing HA mechanisms and their limits are documented, and an approved failure/recovery exercise is recorded.
- The repository contains enough evidence to resume without reinstalling.

The existing HA mechanisms, Terraform, and Grafana should be studied in sequence after the preceding checks and failure/recovery evidence are complete; HA is already configured, not a later build step.
