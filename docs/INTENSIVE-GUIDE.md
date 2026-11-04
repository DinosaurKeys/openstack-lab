# OpenStack Lab Guide

This is the single step-by-step guide for learning and checking the owner-reported lab. The README is a short overview and points here; it is not a second procedure.

Follow the 13 steps below in order. Start at “Resume here” if you are returning to the lab. The step numbers are the learning order; filenames like `00-local-preflight.sh` are script names and use a separate numbering scheme.

## Resume here

Last checked from the management VM: November 4, 2026 (17:57 UTC).

- Step 1: local preflight passed; Linux/recovery exercises have not been formally checked off.
- Step 2: SSH key authentication and Ansible reached all three nodes successfully.
- Step 3: read-only interface, route, and disk discovery completed; a local evidence report was saved.
- Step 4 is in progress: all three nodes' management interfaces and default routes are up, while the USB NICs remain down. `bridge link show` returned no entries.
- Step 5: the time check was run early and `NTPSynchronized=yes` was observed on all nodes. Chrony source health was not confirmed.
- The management VM has no `openstack` CLI. On the nodes, no host `ovs-vsctl` or active `openvswitch-switch` service was found; Docker/Podman and matching OpenStack packages/services were not found either. The deployment method and actual Neutron/provider path remain unverified; this is not proof that the reported cloud is absent.
- No network, storage, or OpenStack configuration was changed.

Next: identify how OpenStack/network services are deployed and map the actual Neutron/provider path using read-only checks. Do not enable the USB NICs, install OVS or the OpenStack CLI, apply Netplan, alter LVM, or run a failover test until the current deployment and recovery path are understood. The earlier disk snapshot showed Cinder LVM; treat that as in-use until verified.

The reports are local, ignored files in `evidence/` on the management VM checkout; they are intentionally not committed to GitHub. The latest network snapshot is `step-04-network-review-20261104T175656Z.txt`.


## Lab overview

### Physical layout

| System | Address | Owner-reported roles |
|---|---:|---|
| Management VM | separate, unique address | Hermes, Git, Ansible |
| Node 1 | `192.168.0.200` | Controller + network + compute; HA member |
| Node 2 | `192.168.0.201` | Controller + network + compute; HA member |
| Node 3 | `192.168.0.202` | Controller + network + compute; HA member |

The lab owner reports that all three nodes have controller, network, and compute roles and are configured for HA. The live checks have not yet verified service placement or HA mechanisms. The step names below are learning topics, not a proposal to split roles across nodes or deploy a new single-controller cloud.

Each physical node has 16 GB RAM and four CPU cores. It has a management interface and USB NIC hardware; discover each NIC's actual current role rather than assuming the USB NIC is private/internal.

An earlier discovery snapshot recorded the following observations; they have not been freshly verified as part of this documentation update. Treat them as historical until the Step 3 discovery check is rerun:

- management interface: `enp0s31f6`
- USB NIC on Node 1: `enx00e04c2c1678`
- USB NIC on Node 2: `enx00e04c557e58`
- USB NIC on Node 3: `enx00e04c304688`
- the USB NICs were down in that snapshot
- time synchronization is active
- the disks already contain LVM-backed storage, including an existing Cinder volume pool

Do not assume these names will remain unchanged after hardware changes. Re-run discovery when hardware or operating-system networking changes.

## What this guide is for

The owner-reported three-node HA topology is the environment we are learning and checking. First verify what is actually deployed and how it is connected; this guide is not an instruction to install a new non-HA cloud.

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
                 Network paths to be confirmed from live configuration
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
  Identify configured interfaces, bridges, VLANs, and overlay from live state.

Layer C: Provider/external network
  Optional path for floating IPs. It needs a deliberate physical and
  switch/router design. It must not be invented by guessing a NIC.
```

## Safe operating rules

When a command fails, the lab is not lost. The failure is a location marker.

### When a command fails

- Stop at the first failed command.
- Save the complete command and output under `evidence/`.
- Identify the step or service area: Linux, SSH, networking, time, controller, compute, storage, HA, or application.
- Run a read-only diagnostic for that step or service area.
- Change one thing only.
- Re-run that step's check before moving on.

Never do this as a first response:

- reinstall the operating system
- delete `/etc` configuration
- recreate a volume group
- run `pvcreate` because a guide used `/dev/sdb`
- improvise HA changes or failover tests to hide a broken service
- copy commands from a different OpenStack release

### Evidence convention

```text
evidence/
  discovery-YYYYMMDDTHHMMSSZ.txt
  time-hosts-YYYYMMDDTHHMMSSZ.txt
  step-02-ssh.txt
  step-04-network-review.txt
  incidents.md
```

A good incident entry contains:

```text
Date/time:
Step:
Command:
Observed error:
What I expected:
What I checked:
Change made:
Verification result:
Rollback:
```

## The 13 learning steps

Run these commands from the root of your existing `openstack-lab` checkout unless stated otherwise.

### Step 1 — Linux and recovery basics

#### Goal

Become comfortable enough with Linux to inspect a system without guessing.

#### Commands to practice on the management VM

```bash
pwd
ls -la
find . -maxdepth 2 -type f
id
whoami
ip -brief address
ip route
systemctl --failed
journalctl -p warning -b
```

#### File editing

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

#### Completion criteria

You can explain the difference between:

- a file and a directory
- a process and a systemd service
- an IP address and a route
- a normal user and root
- a package and a running service

### Step 2 — SSH and Ansible

#### Goal

The management VM can reach every node without storing passwords in the repository.

#### Security model

- Use the normal user `joe`.
- Use an Ed25519 SSH key.
- Use Ansible privilege escalation only when required.
- Do not enable root SSH as a shortcut.
- Do not paste passwords, private keys, or MFA codes into chat.

#### Check local tools

```bash
bash scripts/00-local-preflight.sh
```

#### Inventory

The inventory is in `inventory/hosts.yml`. Change only the values that are actually different in your lab.

```bash
ANSIBLE_CONFIG=ansible/ansible.cfg \
  ansible-inventory --graph
```

#### Verify connectivity

```bash
bash scripts/01-verify-ssh-ansible.sh
```

Expected result:

- three `pong` responses
- each node reports its hostname and management address
- the script ends with `STEP 2 PASSED`

Ansible's ad-hoc `shell` task may display `CHANGED` even though the command only reads hostname and addresses. That status is Ansible's default for shell commands; it is not, by itself, evidence that the node was modified.

#### Common failure map

| Symptom | First check |
|---|---|
| timeout | `ping`, `ip route`, firewall, SSH service |
| permission denied | user name, authorized key, sudo rights |
| host key warning | confirm the address is the intended node |
| Python missing | install Python 3 on the node, then rerun |
| wrong node answers | duplicate IP or stale ARP; stop and fix addressing |

### Step 3 — Discover interfaces and storage

#### Goal

Replace guesses with facts before changing networking or storage.

```bash
bash scripts/02-discover-nics-and-disks.sh
```

Inspect:

```text
ip -brief link       interface names and link state
ip -brief address    assigned addresses
ip route             default route and connected networks
lsblk                disks, filesystems, mounts, LVM
```

#### Current lab finding

The earlier snapshot recorded USB NICs as visible but down. Re-discover all links, bridges, routes, and provider-network configuration before deciding their current purpose or changing network settings.

That earlier storage output showed an LVM-backed Cinder pool. Confirm current storage state before relying on it. Until verified:

- do not run `pvcreate`
- do not run `vgcreate`
- do not assume `/dev/sdb` is unused
- document the existing volume group and pool before changing storage

### Step 4 — Static networking (audit existing setup first)

#### Goal

Audit the current address, route, DNS, bridge, and VLAN configuration while preserving SSH/API access. Create a reviewed change plan only if discovery shows a real problem; do not change the reported HA topology simply to follow a tutorial example.

#### Network discovery and change plan

Start with a fresh, read-only snapshot from the management VM:

```bash
mkdir -p evidence
OUT="evidence/step-04-network-review-$(date -u +%Y%m%dT%H%M%SZ).txt"
ANSIBLE_CONFIG=ansible/ansible.cfg ansible openstack_nodes -m shell \
  -a 'ip -brief link; ip -brief address; ip route; bridge link show' | tee "$OUT"
```

If the existing OpenStack CLI credentials are already configured, inspect (do not change) the cloud's current network agents, networks, and subnets:

```bash
openstack network agent list --long
openstack network list --long
openstack subnet list --long
```

These are list/read commands. If the CLI is not already authenticated, skip this part and record it as unknown; do not put credentials in the repository or chat. See the official [OpenStackClient networking command reference](https://docs.openstack.org/python-openstackclient/latest/cli/command-objects/network/v2/index.html).

```text
Management/API network: record actual addresses, routes, gateway, DNS, and API endpoint path.
Internal/tunnel network: identify configured interfaces, bridges, VLANs, and overlay.
Provider/external network: identify the actual uplink and its relationship to the switch/LAN.
Do not create a second subnet or move a default route based on this example alone.
```

Do not assume a USB NIC is an isolated underlay or that any example subnet is correct. Confirm current cabling and configuration, and check for overlap with LAN, VPN, Docker, libvirt, and Wi-Fi networks.

#### Safe change process

1. Collect interface, address, route, DNS, bridge, and VLAN state from all nodes.
2. Compare management reachability and the actual OpenStack network configuration.
3. If a change is necessary, identify its exact scope and expected failover impact.
4. Confirm a local console or other recovery path and obtain approval before applying it.
5. Validate the candidate configuration and rollback procedure before a one-node-at-a-time change.
6. Recheck SSH, API reachability, cluster health, and workload networking after each change.
7. Save redacted evidence and the result.

Do not add or move a default route based on an assumed interface role. Confirm the live routing design and failover implications first.

### Step 5 — Time synchronization

#### Goal

Verify all nodes report synchronized time and identify the configured time source. The lab owner reports an existing cluster; do not install or reconfigure time services just to follow a fresh-install tutorial.

```bash
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

### Step 6 — Controller

#### Goal

Confirm whether and how controller services are deployed across the owner-reported HA nodes. Do not assume Node 1 is the only controller or bootstrap a new control plane. First discover where APIs, databases, message queues, and supporting services actually run and how they are monitored.

#### Services and responsibilities

| Service | Responsibility |
|---|---|
| Keystone | identity, users, projects, tokens |
| Glance | image catalog and image storage |
| Placement | resource inventory and allocation |
| Nova API | compute API |
| Nova scheduler | chooses a compute host |
| Database | persistent service state |
| Message queue | service-to-service messaging |

#### Controller checks

Inspect the existing deployment; do not bootstrap or reinstall it. Record whether you can verify:

- Keystone token issuance
- service catalog endpoints
- current Glance image catalog and image list (do not upload without approval)
- Placement resource inventory
- Nova service list
- API access from the management VM

### Step 7 — Network node

#### Goal

Identify whether and how Neutron/network services turn a logical network into Linux/OVS datapath state across the nodes. Use live observations to locate agents rather than assuming a dedicated network node.

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

If a Neutron deployment is found, verify:

- Neutron agents are up
- existing tenant networks and subnets can be listed
- Neutron agent and HA router state can be read from the existing cloud
- DHCP service is present/healthy where configured
- network agents, namespaces, bridges, and HA router state can be diagnosed on all relevant nodes

### Step 8 — Compute node

#### Goal

Confirm whether compute services and existing guests are present across the nodes. Do not assume Node 3 is the only hypervisor. Only launch a new test guest if the user approves a specific resource plan and existing workloads have been checked.

First verify hardware virtualization:

```bash
lscpu | grep -E 'Virtualization|Model name'
ls -l /dev/kvm
virsh list --all
```

For a later, approved test guest, verify the following:

1. Nova sees the compute service.
2. Placement reports resources.
3. An instance is scheduled.
4. The guest boots.
5. The guest gets a port and address.
6. Console/log inspection explains any failure.

### Step 9 — Cinder

#### Goal

Inspect the current Cinder services, backends, pools, and existing volumes without changing disk or LVM state.

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

Read-only milestone:

- the current volume types, backends, pools, and volumes can be listed
- the existing data path and recovery procedure are documented

Creating or attaching a test volume is a separate, explicitly approved exercise. Confirm available capacity, quotas, and a recovery plan first; never initialize or recreate a disk or volume group as part of this step.

### Step 10 — Failure testing

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

### Step 11 — HA/VIP verification (reported setup)

#### Goal

The owner reports that all three nodes are already configured for HA. Step 11 is to discover, document, and validate that configuration—not to add HA or create an unplanned VIP.

A VIP by itself is not HA. A resilient design needs coordinated handling for:

- API services
- database replication
- message queue availability
- identity and token behavior
- image and control-plane storage
- network agents
- monitoring and fencing

Before any failure test, identify the real VIP owner mechanism, API proxy, database/quorum behavior, messaging topology, network-agent/router state, storage guarantees, and recovery procedure. A VIP move alone does not prove the service or data path survived. Run one scoped, approved, reversible test at a time and check user-visible API and workload behavior as well as process state.

### Step 12 — Terraform

Terraform belongs after the cloud can reliably create resources manually. Use a sandbox project and do not run `apply` without an approved plan.

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

### Step 13 — Grafana

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

## Daily operating checklist

```text
[ ] I am in the root of the existing repository checkout.
[ ] git status shows what changed.
[ ] I know which step I am working on.
[ ] I have a recovery path before changing networking/storage.
[ ] I ran discovery instead of guessing.
[ ] I saved command output for this step.
[ ] I changed one thing only.
[ ] I reran the check for this step.
[ ] I did not commit secrets.
```

## Completion criteria

The end-to-end learning milestone is complete when:

- Ansible reaches all three nodes and can collect independent per-node observations.
- Management and internal network roles are understood.
- Controller, network, and compute services are mapped across all three nodes.
- All nodes have synchronized time.
- If OpenStack is deployed, controller APIs respond.
- If OpenStack services are deployed, network services can provide a usable tenant network and compute can launch a test instance in an approved sandbox.
- Storage behavior is documented and tested if enabled, after capacity and approval checks.
- The owner-reported HA mechanisms and their limits are verified; any failure/recovery exercise is explicitly approved and recorded.
- The repository contains enough evidence to resume without reinstalling.

Terraform and Grafana come after the preceding checks. Treat HA as an owner-reported existing setup to verify, not as permission to change or fail over the cluster.
