# OpenStack Lab — Full Installation Guide

This is the canonical, from-scratch installation procedure for the lab. It is not a pre-check or a “resume where the existing machines happen to be” guide. Assume the management VM and all three nodes are newly installed; install SSH and Ansible even if the tools are already present on another machine.

Follow the numbered steps in order. The deployment method is Kolla-Ansible, installed in a Python virtual environment on a separate management VM. The pinned baseline is Ubuntu Server 24.04 LTS and Kolla-Ansible `stable/2026.2`; do not mix commands, container images, or constraints from another OpenStack series.

[![OpenStack lab architecture and 13-step installation map](../diagrams/openstack-full-installation.svg)](../diagrams/openstack-full-installation.svg)

_At-a-glance map only. The numbered instructions below are the authoritative steps and commands; optional Steps 11–13 follow a tested core cloud._

Official references used by this procedure:

- [Kolla-Ansible 2026.2 Quickstart](https://docs.openstack.org/kolla-ansible/2026.2/user/quickstart.html)
- [Kolla-Ansible 2026.2 Multinode Deployment](https://docs.openstack.org/kolla-ansible/2026.2/user/multinode.html)
- [Kolla-Ansible 2026.2 Support Matrix](https://docs.openstack.org/kolla-ansible/2026.2/user/support-matrix)
- [Kolla-Ansible 2026.2 Series Release Notes](https://docs.openstack.org/releasenotes/kolla-ansible/2026.2.html)
- [Kolla-Ansible Production Architecture Guide](https://docs.openstack.org/kolla-ansible/2026.2/admin/production-architecture-guide.html)
- [Kolla-Ansible Cinder Guide](https://docs.openstack.org/kolla-ansible/2026.2/reference/storage/cinder-guide.html)
- [Kolla-Ansible 2026.2 Grafana Guide](https://docs.openstack.org/kolla-ansible/2026.2/reference/logging-and-monitoring/grafana-guide.html)
- [Netplan MAC matching and interface naming](https://netplan.readthedocs.io/en/stable/matching-interface-by-mac-address/)
- [Netplan YAML reference](https://netplan.readthedocs.io/en/stable/netplan-yaml/)
- [Netplan command reference](https://netplan.readthedocs.io/en/stable/cli/)
- [Ubuntu Server installation tutorial](https://ubuntu.com/tutorials/install-ubuntu-server)

## Target installation

| Host | Planned management address | Kolla-Ansible groups |
|:--|:--|:--|
| Management VM | A unique address, not shared with a node | Deployment host only |
| Node 1 | `NODE1_MGMT_IP` | `control`, `network`, `compute` |
| Node 2 | `NODE2_MGMT_IP` | `control`, `network`, `compute` |
| Node 3 | `NODE3_MGMT_IP` | `control`, `network`, `compute` |

The table lists the required core-role placement. The upstream multinode inventory also has `monitoring` and `storage` groups; Step 5 removes its example hostnames, and the optional Grafana and Cinder steps add real hosts only when those services are selected.

All three physical nodes are intended to carry control, network, and compute services. An odd three-node control group supports quorum for clustered control-plane services, but it does not make every service or storage backend highly available. This is a small learning cluster, not a production design.

Kolla-Ansible’s published minimum host requirements are two network interfaces, 8 GB RAM, and 40 GB disk space. Confirm that every node meets these minimums and has sufficient additional capacity for images, logs, and the small test workloads. Combined control, network, and compute roles are resource-intensive; start with one small test instance and avoid enabling optional services until the core cloud is stable.

## Before starting

- Back up anything on the selected OS disks. Installing Ubuntu with “use entire disk” erases that selected disk.
- Confirm console or other recovery access to all nodes before changing network settings.
- Reserve the three node addresses outside the DHCP pool. Choose a free internal VIP on the management subnet before deployment.
- Use the same hostnames and administrator account on every node. This guide uses `manager`, `node1`, `node2`, and `node3`, and the placeholder `ADMIN_USER`.
- The management VM must have its own unique address and must be able to reach all three nodes.
- Keep generated Kolla passwords, `clouds.yaml`, SSH private keys, and other secrets out of Git and chat.
- Commands that change configuration are written for the clean-install target. Do not run them against an existing, data-bearing cloud without first adapting the plan and obtaining approval.

## Step 1 — Install Ubuntu Server

Install Ubuntu Server 24.04 LTS (amd64) on the management VM and on each physical node. Follow the [Ubuntu Server installation tutorial](https://ubuntu.com/tutorials/install-ubuntu-server).

During installation:

1. Assign the hostnames `manager` (management VM), `node1`, `node2`, and `node3`.
2. Create the same normal administrator account on each machine; do not enable root SSH login.
3. Use the intended OS disk only. Do not select or erase a disk intended for later Cinder storage.
4. Give each machine a unique management address. For the physical nodes, use the planned addresses in the table only after reserving them in the router/DHCP server or confirming the static-address plan.
5. Keep the management VM on the same reachable management network as the nodes.
6. Install only the base OS. Do not manually install OpenStack services, OVS, Docker, or KVM deployment containers; Kolla-Ansible handles the OpenStack host dependencies later.

After the first boot, sign in locally or through the hypervisor console as the administrator account and install operating-system updates:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

Repeat on all four machines. Reconnect after each reboot.

Completion: all four systems boot into Ubuntu Server 24.04, have unique hostnames and addresses, and the three node addresses are reserved.

## Step 2 — Install SSH and create key-based access

Install the SSH packages explicitly on the fresh systems. On the management VM:

```bash
sudo apt update
sudo apt install -y openssh-client openssh-server git python3 python3-venv
sudo systemctl enable --now ssh
```

On each node:

```bash
sudo apt update
sudo apt install -y openssh-server python3 sudo
sudo systemctl enable --now ssh
```

On the management VM, create a dedicated Ed25519 key:

```bash
ssh-keygen -t ed25519 -a 64 -f ~/.ssh/openstack_lab_ed25519
```

Install the public key for the administrator account on each node. Prefer adding the public key through the Ubuntu installer or local console. If using `ssh-copy-id`, run it directly in the management VM terminal; it may ask for the initial account password. Do not put that password in a script, inventory, repository, or chat:

```bash
ADMIN_USER="REPLACE_WITH_ADMIN_USER"
NODE1_MGMT_IP="REPLACE_WITH_NODE1_ADDRESS"
NODE2_MGMT_IP="REPLACE_WITH_NODE2_ADDRESS"
NODE3_MGMT_IP="REPLACE_WITH_NODE3_ADDRESS"
ssh-copy-id -i ~/.ssh/openstack_lab_ed25519.pub "${ADMIN_USER}@${NODE1_MGMT_IP}"
ssh-copy-id -i ~/.ssh/openstack_lab_ed25519.pub "${ADMIN_USER}@${NODE2_MGMT_IP}"
ssh-copy-id -i ~/.ssh/openstack_lab_ed25519.pub "${ADMIN_USER}@${NODE3_MGMT_IP}"
```

Replace the values at the top with the account and addresses chosen in Step 1. If the key has a passphrase, load it into a local SSH agent before running Ansible:

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/openstack_lab_ed25519
```

Accept an SSH host key only after confirming the address belongs to the intended node. Do not disable host-key checking.

Completion: SSH to each node with the dedicated key returns its expected hostname without asking for the node account password.

## Step 3 — Install Ansible and Kolla-Ansible on the management VM

Use a dedicated Python virtual environment. Kolla-Ansible 2026.2 supports Ansible 13 or 14; install that supported range explicitly in the virtual environment before installing Kolla-Ansible. Do not mix this deployment environment with Ubuntu’s system Ansible packages.

```bash
sudo apt install -y git python3-dev libffi-dev gcc libssl-dev libdbus-glib-1-dev python3-venv
mkdir -p "$HOME/.venvs"
python3 -m venv "$HOME/.venvs/kolla-2026.2"
source "$HOME/.venvs/kolla-2026.2/bin/activate"
python -m pip install --upgrade pip
python -m pip install 'ansible>=13,<15'
python -m pip install 'git+https://opendev.org/openstack/kolla-ansible@stable/2026.2'
```

Create the Kolla configuration directory and copy the matching release’s examples:

```bash
sudo mkdir -p /etc/kolla
sudo chown "$USER":"$USER" /etc/kolla
cp -r "$VIRTUAL_ENV/share/kolla-ansible/etc_examples/kolla/"* /etc/kolla/
cp "$VIRTUAL_ENV/share/kolla-ansible/ansible/inventory/multinode" /etc/kolla/multinode
chmod 700 /etc/kolla
chmod 600 /etc/kolla/passwords.yml
kolla-ansible install-deps
```

Confirm the installed tools come from the virtual environment:

```bash
command -v ansible
ansible --version
kolla-ansible --version
```

Keep the virtual environment active for the remaining Kolla-Ansible commands. The `/etc/kolla/multinode` inventory is copied from the exact installed Kolla release; preserve its other groups and child-group mappings.

Completion: `ansible` and `kolla-ansible` run from the virtual environment, and `/etc/kolla/globals.yml`, `/etc/kolla/passwords.yml`, and `/etc/kolla/multinode` exist.

### Where Ansible is used after Step 3

- Step 4: Ansible can collect network facts, but the management-network cutover is performed one node at a time from a recovery console; losing SSH mid-change can strand a node.
- Step 5: Ansible parses and tests the Kolla inventory after you configure it.
- Step 6: A project playbook audits all four hosts and can optionally correct time settings with authorized privilege escalation.
- Steps 8–9: Kolla-Ansible invokes its own Ansible playbooks to bootstrap, check, and deploy the nodes. Step 7 edits the management host's Kolla configuration first.
- Steps 10–13: Use the OpenStack CLI, Kolla-Ansible, or Terraform as directed. Keep storage initialization and other destructive operations manual until devices and a recovery plan are approved.

## Step 4 — Plan and configure the node networks

Kolla needs a management interface and a separate Neutron external interface. For this two-interface baseline:

- The management NIC carries SSH, Ansible, API/database traffic, and the default Neutron tunnel traffic.
- The second NIC connects to the shared lab switch and is reserved for Neutron provider networking. It must be active at Layer 2 with no configured provider-subnet address or default route; an automatic IPv6 link-local address may still appear. Kolla/Neutron will attach it to the external bridge.
- This isolated provider network does not automatically have Internet access or a gateway. Add a separately designed upstream connection if floating IPs or external connectivity are required.
- If you require a separate tunnel/underlay network as well as management and provider networks, add a third interface per node before proceeding.

Identify each interface by MAC address and cable path from the physical console. Use these read-only commands on each node, and label the cables before changing configuration:

```bash
ip -brief link
ip -brief address
ip route
for p in /sys/class/net/*/address; do printf '%s ' "${p%/address}"; cat "$p"; done
```

On every host, use consistent names `mgmt0` and `provider0`; Kolla globals use those names on all three nodes. If the interface names differ across hosts, rename each adapter with a Netplan `match.macaddress` rule. Do not copy a MAC address from another node.

On each node, prepare the following YAML as an inactive draft first; the procedure below shows how to review and install it. Replace every `REPLACE_...` value with data inspected on that same node, including that node's management address. Preserve the correct existing gateway, DNS, and any required LAN routes; do not assume the example gateway is correct:

```yaml
network:
  version: 2
  ethernets:
    mgmt0:
      match:
        macaddress: "REPLACE_WITH_THIS_NODE_MANAGEMENT_MAC"
      set-name: mgmt0
      dhcp4: false
      dhcp6: false
      addresses: ["REPLACE_WITH_NODE1_MGMT_IP_CIDR"] # use node2/node3 address on those hosts
      routes:
        - to: default
          via: "REPLACE_WITH_MANAGEMENT_GATEWAY"
      nameservers:
        addresses: ["REPLACE_WITH_DNS_SERVER"]
    provider0:
      match:
        macaddress: "REPLACE_WITH_THIS_NODE_PROVIDER_NIC_MAC"
      set-name: provider0
      dhcp4: false
      dhcp6: false
      optional: true
```

### Back up the current configuration

Sequence to remember: inspect → back up → draft and review → install the new file → park the old file → generate → try → verify before moving to the next node.

Work on one node at a time. These commands assume that `/etc/netplan/50-cloud-init.yaml` is the existing file for this node; confirm the filename first and use the actual existing path consistently if it differs. Also check that no other active `/etc/netplan/*.yaml` file defines the same interfaces. On that node, create and verify a backup before changing any Netplan files. If this backup path already exists, stop and inspect it before rerunning the copy; `cp -a` can replace an existing destination.

```bash
backup="/root/50-cloud-init.yaml.pre-openstack.$(hostname)"
sudo cp -a /etc/netplan/50-cloud-init.yaml "$backup"
sudo cmp -s /etc/netplan/50-cloud-init.yaml "$backup" && echo "Backup verified: $backup"
```

`$(hostname)` runs the `hostname` command and inserts its output into the path. The first line stores that path in the `backup` shell variable; `"$backup"` uses the stored path in the following commands. The comparison prints the confirmation only when the backup matches the original. If it does not print `Backup verified`, stop.

### Create and review an inactive draft

Create the draft in the current user's home directory, not in `/etc/netplan`. Netplan will not use this `.draft` file, so you can review it before it affects networking. The `~` means the current user's home directory.

```bash
nano ~/90-openstack-lab.yaml.draft
```

Paste the YAML template above, save it in nano with Ctrl+O, Enter, and Ctrl+X, then display the saved file and check the MAC addresses, management address, gateway, DNS, and indentation:

```bash
cat ~/90-openstack-lab.yaml.draft
```

Do not proceed until the values match this node's inspected network data.

### Stage the replacement and validate it

After reviewing the draft, run these commands on that same node:

```bash
sudo install -o root -g root -m 600 ~/90-openstack-lab.yaml.draft /etc/netplan/90-openstack-lab.yaml
sudo mv /etc/netplan/50-cloud-init.yaml /etc/netplan/50-cloud-init.yaml.disabled
sudo netplan generate
```

`install` copies the draft and sets its owner, group, and permissions; it does not install a package. `mv` renames the old file rather than deleting it; the `.disabled` suffix keeps it out of Netplan's active `.yaml` files. `netplan generate` validates the YAML and builds backend configuration, but does not apply the network change. If any command reports an error, stop. Do not reboot while the new file is staged but not tested.

If `netplan generate` fails, restore the file set before retrying:

```bash
sudo mv /etc/netplan/90-openstack-lab.yaml /etc/netplan/90-openstack-lab.yaml.failed
sudo mv /etc/netplan/50-cloud-init.yaml.disabled /etc/netplan/50-cloud-init.yaml
sudo netplan generate
```

Correct the draft, review it again, and repeat the staging steps only after the old file is restored. Keep the verified backup.

### Test the cutover from a recovery console

Before applying the new network, confirm physical or virtual console access to this exact node; SSH alone is not an adequate recovery path. Run `netplan try` from that console and keep its countdown prompt open:

```bash
sudo netplan try
```

While the prompt waits, use a second terminal on the node (or another SSH session from the management VM) to check:

```bash
ip -brief link
ip -brief address
ip route
resolvectl dns
ping -c 3 REPLACE_WITH_MANAGEMENT_GATEWAY
```

Replace `REPLACE_WITH_MANAGEMENT_GATEWAY` with this node's actual numeric gateway address before running the ping. Accept the temporary configuration only when `mgmt0` has the planned management address, the default route uses `mgmt0` and the planned gateway, the gateway responds, and `provider0` is up with physical link detected (`LOWER_UP`). `provider0` must not have a configured IPv4 address; an automatic `fe80::` IPv6 link-local address alone is expected. Return to the `netplan try` prompt and press Enter to keep the settings only after these checks pass. Otherwise, do not accept; let the timer expire and keep the console open.

After a successful cutover, verify SSH connectivity from the management VM using this node's new address and the Step 2 key before changing the next node. The Kolla inventory does not exist in configured form until Step 5; after Step 5, verify Ansible connectivity as well. If a try fails or times out, verify the runtime network actually reverted; do not assume the on-disk filenames were restored. Inspect the files and use the restore commands above to return to the original `.yaml` file set before rebooting or retrying. Repeat this procedure for each node, using its own MAC addresses and management address.

### Later management-address changes

The copy-and-rename steps above are a one-time migration per node. For a later address change, edit that node's active `/etc/netplan/90-openstack-lab.yaml`, make a fresh backup as appropriate, run `sudo netplan generate`, then use `sudo netplan try` from a recovery console and repeat the checks. Do not repeat the migration of `50-cloud-init.yaml` unless deliberately changing the Netplan file layout again. After Kolla-Ansible is deployed, also update inventory, host mappings, and service configuration that reference the old address.

After all three nodes pass the network checks, add the host entries to `/etc/hosts` on all four machines, using the actual management VM address:

```text
NODE1_MGMT_IP node1
NODE2_MGMT_IP node2
NODE3_MGMT_IP node3
MANAGEMENT_VM_IP manager
```

Replace every `*_MGMT_IP` and `MANAGEMENT_VM_IP` token with the actual address chosen for that host. Back up and inspect each host's `/etc/hosts` first. Replace an existing `127.0.1.1 node1` (or corresponding node name) mapping rather than adding a conflicting duplicate; preserve localhost and IPv6 entries. Confirm that `node1`, `node2`, `node3`, and `manager` resolve consistently on every machine.

Completion: each node has stable management reachability, the USB/provider interface is connected to the intended switch without a configured provider-subnet address or default route, both interface names are consistent, and hostnames resolve consistently. An automatic IPv6 link-local address on the provider interface is expected.

## Step 5 — Configure the Kolla multinode inventory

Edit `/etc/kolla/multinode`, starting from the copied upstream inventory. Put all three nodes in each of the `control`, `network`, and `compute` groups. Keep the upstream child-group mappings, especially the load balancer mapping to the network group.

Before changing the inventory, make and verify a backup on the management VM:

```bash
cp -a /etc/kolla/multinode /etc/kolla/multinode.pre-step5
cmp -s /etc/kolla/multinode /etc/kolla/multinode.pre-step5 && echo "Inventory backup verified"
```

The first command preserves a copy; the second prints confirmation only when the two files match. Use `sudo` only if the current user does not own `/etc/kolla`.

The upstream file contains active example hosts such as `control01`, `network01`, `compute01`, `monitoring01`, and `storage01`. Replace every active example hostname with a real host from this lab or remove that entry if the optional role is not enabled; never leave these sample names for Ansible to target. Keep the upstream group sections and child-group mappings. For the base deployment, use the three physical nodes in the core groups and leave `monitoring` and `storage` host entries empty until Step 13 for monitoring and Step 11 for storage, respectively.

Edit the corresponding sections in the copied inventory as follows:

```ini
[control]
node1 ansible_host=NODE1_MGMT_IP
node2 ansible_host=NODE2_MGMT_IP
node3 ansible_host=NODE3_MGMT_IP

[network]
node1
node2
node3

[compute]
node1
node2
node3

[monitoring]
# Add real host aliases here in Step 13 if enabling monitoring.

[storage]
# Add real host aliases here in Step 11 if enabling Cinder storage.

[all:vars]
ansible_ssh_user=REPLACE_WITH_ADMIN_USER
ansible_become=True
ansible_private_key_file=REPLACE_WITH_HOME_PATH/.ssh/openstack_lab_ed25519
```

Replace all `NODE*_MGMT_IP`, `REPLACE_WITH_ADMIN_USER`, and `REPLACE_WITH_HOME_PATH` values with the clean-install addresses and account path. If the upstream sample already contains these group headers, edit those sections rather than adding duplicate groups. Remove its example host entries from optional groups before the base deployment; add only real host aliases later if enabling those services. Do not store a sudo password in the inventory. Use a locally approved secure privilege-escalation method; Kolla requires the deployment account to become root on target nodes.

Do not enable a Cinder backend or create storage volumes in this step. Storage is handled separately in Step 11; monitoring is handled separately in Step 13.

Check that Ansible sees exactly three nodes in all three roles and that SSH works:

```bash
ansible-inventory -i /etc/kolla/multinode --graph
ansible -i /etc/kolla/multinode control -m ping -e '{"ansible_become": false}'
```

The `control` group is the three physical nodes, so the local deployment host is not included in this SSH test. The temporary `ansible_become` override is only for the non-privileged ping check; Kolla deployment tasks still need the approved privilege-escalation method.

Ansible may warn about hyphens in the upstream group names. Preserve those release-provided names and mappings; do not rename groups to silence the warning.

Completion: each node appears in `control`, `network`, and `compute`; no upstream sample hostname remains active; the other Kolla groups and child-group mappings remain intact; Ansible returns `pong` from all three real nodes.

## Step 6 — Verify hostnames and time synchronization

Kolla-Ansible 2026.2 accepts any one active host time service from this list: `chrony`, `chronyd`, `ntp`, `ntpd`, or `systemd-timesyncd`. These are alternatives; you do not need to install all of them. On Ubuntu 24.04 LTS, `systemd-timesyncd` is normally enabled by default. Ubuntu changed the default to Chrony starting with 25.10. See [Ubuntu's time synchronization guide](https://ubuntu.com/server/docs/use-timedatectl-and-timesyncd/).

On the management VM, clone this repository if it is not already present, change to its root directory, and activate the Kolla virtual environment. The project playbook checks hostname resolution, timezone, clock synchronization, and active time services on the `control` nodes and the upstream inventory's `deployment` group (localhost). Audit mode is read-only:

```bash
ansible-playbook -i /etc/kolla/multinode \
  ansible/playbooks/ensure-time-sync.yml \
  -e '{"ansible_become": false}'
```

The long service list is one probe for several possible service names; the playbook reports each status. Missing or inactive alternatives are normal. At least one must be `active`, the timezone must be `UTC` or `Etc/UTC`, and `NTPSynchronized` must be `yes`. If all assertions pass on all four systems, Step 6 is complete. Do not install Chrony if `systemd-timesyncd` is already active and synchronized.

If the audit finds the timezone is not UTC, or finds no supported time service active, the playbook can correct it. It sets UTC when needed; it installs, enables, and starts Chrony only when none of the supported services is active. If a service is active but the clock is not synchronizing, it waits and reports failure rather than installing a second daemon. Review the audit result, then explicitly enable changes:

```bash
ansible-playbook -i /etc/kolla/multinode \
  ansible/playbooks/ensure-time-sync.yml \
  -e '{"time_sync_apply": true, "ansible_become": true}' \
  --become --ask-become-pass
```

`--ask-become-pass` (`-K`) prompts for the privilege-escalation password; never put it in the inventory. One password is used for the selected hosts. If host passwords differ, run the apply command with `--limit node1`, then `node2`, `node3`, and `localhost` (the management VM) separately. Installing Chrony may replace a conflicting time-service package: review your distribution's package changes before applying. The install path requires working APT repositories and reachable time servers.

The playbook is intentionally read-only by default. Its source is [`ansible/playbooks/ensure-time-sync.yml`](../ansible/playbooks/ensure-time-sync.yml). Completion means all four systems resolve each node name to its inventory address, use UTC, have one supported time service active, and report a synchronized clock.

## Step 7 — Configure Kolla globals and generated passwords

**Where:** Do this entire step on the management VM, not on each node. `/etc/kolla/globals.yml` tells Kolla-Ansible how to configure the nodes later; `/etc/kolla/passwords.yml` holds the generated service secrets. This step does not deploy OpenStack.

### 7.1 — Confirm the network details

Before editing, confirm that Step 4 established the same interface names on all three nodes. In the examples below, `mgmt0` is the management interface, and `provider0` is the separate provider-network interface. If you selected different names, use your verified names instead.

Choose a virtual IP (VIP) on the management subnet. This is a shared address used to reach OpenStack endpoints; it is **not** the address of a node or the management VM. Reserve it in the network's address plan, outside the DHCP allocation pool or through an appropriate reservation, and verify it is not assigned to another device. An unanswered ping alone does not prove an address is unused. Do not continue until the VIP and interface names are confirmed.

### 7.2 — Back up and edit the settings

On the management VM, with the Kolla virtual environment active, first create a backup. If the backup already exists, stop and inspect it rather than overwriting it:

```bash
if [ -e /etc/kolla/globals.yml.pre-step7 ]; then
  printf '%s\n' 'Backup already exists; inspect it before continuing.'
else
  cp -a /etc/kolla/globals.yml /etc/kolla/globals.yml.pre-step7 && \
    cmp -s /etc/kolla/globals.yml /etc/kolla/globals.yml.pre-step7 && \
    printf '%s\n' 'Backup verified.'
fi
```

Continue only if the backup is verified. Open the file on the management VM:

```bash
nano /etc/kolla/globals.yml
```

In nano, use Ctrl+W to find each setting below. Edit an existing setting or uncomment its line by removing the leading `#`; if it is absent, add it. Keep only **one active line per setting**. Replace the VIP placeholder with the address you reserved; leave the other lines in the file intact.

```yaml
kolla_base_distro: "ubuntu"
network_interface: "mgmt0"
neutron_external_interface: "provider0"
enable_neutron_provider_networks: true
kolla_internal_vip_address: "REPLACE_WITH_RESERVED_MANAGEMENT_VIP"
```

- `kolla_base_distro` selects Ubuntu-based Kolla images.
- `network_interface` selects the nodes' management interface.
- `neutron_external_interface` selects their separate provider interface; it must not have a configured provider-subnet address or default route.
- `enable_neutron_provider_networks` enables Neutron provider networks.
- `kolla_internal_vip_address` is the reserved shared management-network VIP.

Save with Ctrl+O, press Enter, then exit with Ctrl+X. Reopen the file if needed and check the five settings, spelling, indentation and the VIP. Confirm the `network` inventory group includes all three nodes. Do not paste passwords or other secrets into chat or Git.

### 7.3 — Generate service passwords

On the management VM, still in the Kolla virtual environment, generate any missing Kolla service passwords and restrict the file permissions:

```bash
kolla-genpwd
chmod 600 /etc/kolla/passwords.yml
```

Keep `/etc/kolla/passwords.yml` private and back it up securely; do not print it, copy it into Git, or share its contents. Preserve existing deployment passwords on reruns; don't replace or regenerate them blindly for an existing cloud.

**Step 7 is complete when:** the five settings use the verified interface names and reserved VIP, the globals backup is verified, and service passwords are generated and protected on the management VM. No node configuration is applied until a later Kolla-Ansible command.

## Step 8 — Bootstrap node dependencies and run Kolla prechecks

**Run this step on the management VM, not separately on the nodes.** Kolla-Ansible is an Ansible-based deployment tool: it reads `/etc/kolla/multinode` to learn where the hosts are, then runs its own Ansible playbooks over SSH. `bootstrap-servers` installs and configures host dependencies; `prechecks` tests whether the hosts are ready. Bootstrap changes the hosts, so review the [host configuration reference](https://docs.openstack.org/kolla-ansible/2026.2/reference/deployment-and-bootstrapping/bootstrap-servers.html) and maintain console access before proceeding.

### 8.1 — Understand SSH and sudo

SSH authenticates your normal administrator account to a node. Installing packages and configuring system services also requires root privileges. Ansible calls the switch to root **become** (usually implemented with `sudo`). A successful SSH or `ping` test does not prove become works.

For the interactive method below, the same become password must work on all selected hosts, including `localhost` if the inventory targets it. The password is entered at Ansible's terminal prompt; never put it in a command, environment variable, inventory, repository, or chat. This method does not grant passwordless sudo. Anyone with become privileges can make root-level changes, so secure the administrator and SSH accounts.

Test become from the management VM with the virtual environment active:

```bash
ansible -i /etc/kolla/multinode 'control:deployment' \
  -m ansible.builtin.command -a 'id -u' \
  -e '{"ansible_become": true}' --ask-become-pass
```

Enter the sudo password at `BECOME password:`. Each of the three nodes and `localhost` should return `0` and `rc=0`. `id -u` only reports the effective user ID; the command module may label it `CHANGED` even though this probe makes no configuration changes. If any host fails, stop and fix its SSH, sudo permission or password before bootstrap. If passwords differ, one prompt cannot supply all of them: stop and arrange a secure, individually configured credential method rather than storing plaintext passwords. Do not proceed based only on SSH ping.

### 8.2 — Tell Kolla's Ansible to prompt

The Kolla 2026.2 CLI's `bootstrap-servers` command does not expose Ansible's `--ask-become-pass` (`-K`) option. Instead, set Ansible's prompt option **in the same management-VM terminal** before running Kolla:

```bash
export ANSIBLE_BECOME_ASK_PASS=true
```

Type `true` literally: it means “ask for a password,” not the password itself. This command normally prints nothing. The setting lasts only in the current shell and its child processes; repeat it when starting a new terminal. Ansible asks for the password when a Kolla playbook starts. Enter it only at the prompt, and repeat if a later Kolla command prompts again. To remove this setting from the current shell after your work, run `unset ANSIBLE_BECOME_ASK_PASS`.

### 8.3 — Bootstrap, then check

First run bootstrap by itself:

```bash
kolla-ansible bootstrap-servers -i /etc/kolla/multinode
```

At the password prompt, enter the same become password you tested. Wait for the command to finish. It may install packages and change host configuration; it is not a read-only check. If the recap shows any failed or unreachable hosts, stop, examine the error, and do not proceed to prechecks.

Only after bootstrap succeeds, run:

```bash
kolla-ansible prechecks -i /etc/kolla/multinode
```

Enter the password again if prompted. Stop if prechecks fail; correct the underlying issue and rerun them. Warnings about hyphens in upstream group names are not by themselves a reason to rename those groups.

**Step 8 is complete when:** bootstrap and prechecks both finish successfully. Only then move to Step 9. Keep this same terminal's prompt setting for later Kolla commands, or set it again in a new terminal.

## Step 9 — Deploy OpenStack

Deploy the configured Kolla-Ansible release to all three nodes:

```bash
kolla-ansible deploy -i /etc/kolla/multinode
```

This is the step that installs and configures the OpenStack services. It can take a long time while container images are downloaded and services are initialized. Keep the management VM powered on and connected for the duration. If the playbook fails, preserve its output and use the Kolla troubleshooting guide; do not rerun destructive disk commands or switch releases to hide an error.

After the first deployment, validate the generated service configuration:

```bash
kolla-ansible validate-config -i /etc/kolla/multinode
```

Completion: deployment and configuration validation finish successfully, and the enabled service containers are running across their assigned hosts.

## Step 10 — Configure the OpenStack CLI and run a small cloud test

Install the matching OpenStack CLI in the same virtual environment:

```bash
python -m pip install python-openstackclient \
  -c https://releases.openstack.org/constraints/upper/2026.2
```

Generate the client configuration and protect the copy in the operator’s home directory:

```bash
kolla-ansible post-deploy -i /etc/kolla/multinode
install -d -m 700 "$HOME/.config/openstack"
install -m 600 /etc/kolla/clouds.yaml "$HOME/.config/openstack/clouds.yaml"
export OS_CLOUD=admin
openstack token issue
openstack service list
openstack endpoint list
openstack compute service list
openstack network list
```

For a workload test, first download a small test image from its publisher, verify its checksum, and store it outside this Git repository. Create a sandbox tenant network using an unused CIDR that does not overlap the management, VPN, or provider networks. Then create a tiny flavor, upload the image, and boot one test instance. Do not run Kolla’s `init-runonce` script blindly; its example networks and addresses may conflict with this lab’s actual network plan.

Example commands after setting `TENANT_CIDR` to a free private subnet and `IMAGE_FILE` to the verified image path:

```bash
export TENANT_CIDR="REPLACE_WITH_UNUSED_CIDR"
export IMAGE_FILE="$HOME/images/verified-test-image.qcow2"
test -f "$IMAGE_FILE" || { printf 'Image file not found: %s\n' "$IMAGE_FILE" >&2; exit 1; }
openstack flavor create lab.tiny --vcpus 1 --ram 512 --disk 1
openstack network create lab-private
openstack subnet create lab-private-subnet \
  --network lab-private --subnet-range "$TENANT_CIDR" --dhcp
openstack image create lab-test-image \
  --file "$IMAGE_FILE" --disk-format qcow2 --container-format bare --public
openstack server create lab-smoke \
  --flavor lab.tiny --image lab-test-image --network lab-private
openstack server show lab-smoke
```

Do not create a provider/external network until the Layer-2 switch, gateway, and address-allocation plan are explicit. A guest on the private overlay can boot without public/floating-IP connectivity.

Completion: the admin token is issued through the VIP, service and endpoint lists return, and one small sandbox instance reaches `ACTIVE` on the private network.

## Step 11 — Add block storage only after choosing a backend

The base cloud can be installed without Cinder. Choose and document a backend before enabling it:

- For replicated/high-availability block storage, use a supported shared or distributed backend such as a correctly designed Ceph deployment or a supported external storage system. Follow the corresponding Kolla guide and verify the driver’s active/active support.
- A local LVM Cinder backend is useful for a lab exercise but is not replicated storage. Kolla’s Cinder documentation also notes limitations for LVM in a multi-controller deployment. Do not label local LVM volumes highly available.

If you explicitly choose the LVM exercise, first identify a dedicated, expendable device by model, serial, and stable `/dev/disk/by-id/` path on every storage host. The following operations erase storage metadata. Do not run them until the device mapping, backup, and rollback plan are approved:

Before enabling the backend, add only the selected real host aliases to the inventory’s `[storage]` group and follow the 2026.2 Cinder guide’s `cinder-volume-lvm` mapping. The copied sample’s `storage01` is not a real host; do not leave it in the inventory. If no host has a safe dedicated device, skip Cinder and keep `[storage]` empty.

Run once per selected storage host, replacing the example path with that host’s own confirmed device. The commands below are destructive; the placeholder path does not exist and must not be replaced until the device is approved:

```bash
CINDER_DEVICE="/dev/disk/by-id/REPLACE_WITH_VERIFIED_EMPTY_DEVICE"
sudo pvcreate "$CINDER_DEVICE"
sudo vgcreate cinder-volumes "$CINDER_DEVICE"
```

Then follow the Kolla-Ansible 2026.2 Cinder guide to enable Cinder, the LVM backend, and the release-matched inventory groups. Do not copy an old inventory-group example from another Kolla release. Re-run `prechecks`, then `deploy` or `reconfigure` as directed by that guide, and test volume create/attach/detach with a disposable instance.

Completion: the selected backend, its failure limits, and the restore procedure are documented; a disposable volume can be created and attached if Cinder was enabled.

## Step 12 — Add Terraform after the manual cloud test

Install Terraform using [HashiCorp’s official installation instructions](https://developer.hashicorp.com/terraform/install). Use the OpenStack provider from the [Terraform Registry](https://registry.terraform.io/providers/terraform-provider-openstack/openstack/latest). Do not use Terraform until the manual network and instance test in Step 10 succeeds.

Use an application credential with only the permissions required for a sandbox project. Keep the credential in a protected local `clouds.yaml` or secret manager, and configure the provider to use the named cloud rather than embedding a password in `.tf` files. Start with:

1. `terraform init` in a separate working directory.
2. Write a minimal network/subnet plan for the sandbox project.
3. Run `terraform fmt` and `terraform validate`.
4. Review `terraform plan` before any `apply`.
5. Verify the resulting OpenStack resources, then test `terraform destroy` only on the disposable resources.

Never commit `.terraform/`, `*.tfstate`, saved plans, application credentials, or secret-bearing `clouds.yaml` files.

## Step 13 — Enable Prometheus and Grafana

Kolla-Ansible can deploy Prometheus and Grafana as part of the cloud. After the core deployment is stable, first add one or more real host aliases to `[monitoring]` in `/etc/kolla/multinode`, preserving the upstream child-group mappings. The copied sample’s `monitoring01` is not a real host; replace it with a chosen host. If no monitoring host is selected, keep Prometheus and Grafana disabled and do not run this step’s deployment commands.

Then add these settings to `/etc/kolla/globals.yml`:

```yaml
enable_prometheus: true
enable_grafana: true
```

Then apply the configuration through Kolla-Ansible:

```bash
kolla-ansible prechecks -i /etc/kolla/multinode
kolla-ansible deploy -i /etc/kolla/multinode
```

Keep the dashboards and endpoints on the management network unless a separate, secured access path is deliberately configured. Confirm that Prometheus has live targets before relying on Grafana dashboards or alerts. Add host and OpenStack service metrics gradually; a dashboard without verified data is not monitoring.

Completion: Grafana and Prometheus are reachable through the intended management path, targets are up, and the dashboards show current host/service data.

## Final completion checklist

- [ ] Ubuntu Server 24.04 LTS is installed on the management VM and all three nodes.
- [ ] OpenSSH and key-based access were installed/configured from the clean baseline.
- [ ] Kolla-Ansible and its Ansible dependencies run from the pinned virtual environment.
- [ ] All three nodes are in the `control`, `network`, and `compute` groups.
- [ ] Hostnames, management addresses, provider NICs, and the reserved VIP match the written network plan.
- [ ] Kolla bootstrap, prechecks, deploy, and configuration validation succeed.
- [ ] The OpenStack CLI authenticates through the VIP and a sandbox instance boots.
- [ ] Optional Cinder, Terraform, and Grafana work is documented and tested only after the base cloud is stable.
- [ ] Secrets, local evidence, and Terraform state remain outside Git.
