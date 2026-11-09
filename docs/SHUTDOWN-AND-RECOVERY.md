# Shutdown, power-on, and recovery

[Back to the full installation guide](FULL-INSTALLATION-GUIDE.md#operations--shutdown-power-on-and-recovery)

This is the day-to-day procedure for a Kolla-Ansible lab. In VMware terms, the management VM is the administration workstation; the OpenStack nodes are the hosts that run the cloud. Leave the management VM running while you operate on the nodes.

On R2D2, this repository is at `$HOME/fishbone`. From any R2D2 terminal, enter it and activate the Kolla environment:

```bash
cd "$HOME/fishbone" && source "$HOME/.venvs/kolla-2026.2/bin/activate"
```

Do not continue if that command fails. For a clone in another location, use its actual path instead. The helper commands below use absolute paths for this R2D2 clone, so they also work from another directory once the Kolla environment is active. The direct `openstack` CLI examples use the `kolla-admin` cloud:

```bash
export OS_CLOUD=kolla-admin
```

The helpers have their own `kolla-admin` default; if using a different configured cloud, pass their `--cloud NAME` option as well as selecting the cloud for direct CLI commands. Do not paste secrets from `clouds.yaml` or `/etc/kolla/passwords.yml` into the terminal or chat.

These examples assume passwordless become has been verified on the intended nodes. For Ansible ad-hoc commands, add `-K` if sudo needs an interactive password and enter it only at the local prompt. A harmless privilege check on the reviewed target group is:

```bash
ansible -i /etc/kolla/multinode 'control:compute:network:storage' -b -m ansible.builtin.command -a 'id -u'
```

Every intended node must return `0`; Ansible may label this read-only command `CHANGED`. A failure does not prove the account lacks sudo: it may require a password. For Kolla itself, which does not accept `-K`, use `ANSIBLE_BECOME_ASK_PASS=true` if a secure local prompt is required.

**Scope:** the health checks and the default `lab-recover.sh` view are read-only. They do not stop or restart services, create or delete VMs, or repair the database. Its separate `--restart` action is an explicit, confirmed change to one selected service on one selected node; see [manual service restart](#6-manual-service-restart). This repository does not yet provide a verified automatic, dependency-ordered shutdown or out-of-band power-on. Do not copy another lab's helper scripts or fixed host order without verifying that its inventory, container engine, service units, and storage match yours.

### Quick path after a full shutdown

1. Power on the physical nodes and leave the management VM running. If the previous shutdown was the simultaneous fallback below, **there is no verified last database member**; do not assume a particular boot order prevents recovery.
2. From R2D2, run `bash "$HOME/fishbone/scripts/lab-recover.sh" --check`. This is an observation, not a repair. Then use `bash "$HOME/fishbone/scripts/lab-recover.sh" --full` for the sampled Galera and local RabbitMQ checks. The full check defaults to noninteractive sudo; add `--ask-become-pass` if a local password prompt is required. Check RabbitMQ membership separately as described below.
3. If the database is healthy, **leave it alone**. If it is unavailable, use [the MariaDB decision table](#4-if-the-database-is-unavailable) before deciding whether coordinated recovery is appropriate.
4. Once Galera and RabbitMQ are healthy, check the affected API backends and service/agent heartbeats. Repair only a named, confirmed failure; a successful MariaDB recovery does not guarantee its dependent applications recovered.
5. Run the dashboard again and separately verify guest networking, data, and storage. No dashboard result replaces a workload test.

### How the previous lab's shutdown differs

The previous lab's `lab-shutdown.py --apply` implements a two-stage design: it checks readiness and stops cloud clients and agents first, then proxies and RabbitMQ, then MariaDB members one at a time, checking clean exits and database positions. A separate `lab-poweroff.sh --apply` checks a saved shutdown record before scheduling host poweroff. That is a more deliberate approach than simultaneous OS shutdown.

**Those scripts are not implemented or validated in this repository.** They depend on the previous lab's helper modules, paths, inventory, supported Kolla source, and container allowlist. For example, a deployment with Heat services needs those services accounted for. Do not run the other lab's command here or treat its `READY_FOR_MANUAL_POWEROFF` result as available. An adapted workflow must be tested against this deployment, including interrupted shutdown and recovery, before it can replace the fallback below. Ordered shutdown reduces uncertainty but does not guarantee automatic Galera recovery after the next power-on.

## 1. Before shutting down

1. Finish OpenStack operations and stop or cleanly shut down every guest and any other workload. From the management VM, after activating the Kolla environment, list VMs across projects:

   ```bash
   openstack server list --all-projects -c ID -c Name -c Status
   ```

   Record which guests and attached storage must be restored later. Use the cloud's normal guest shutdown process, then check the list again. A VM in `SHUTOFF` is not proof that its guest filesystems or storage were cleanly quiesced; verify those separately. If Cinder is enabled, review outstanding volume operations and attachments as well.
2. Confirm you have console or out-of-band access to the physical machines, a current backup, and a plan to start them again. A host powered off cannot ordinarily be powered on over SSH. Do not assume Wake-on-LAN, IPMI, or a smart switch is configured.
3. Run the read-only health check below and address failures first. If the API is unavailable, an empty or failed VM list is **not** proof that all VMs are stopped. Verify workload and storage state through an appropriate independent method before proceeding.
4. Review the exact targets. From the management VM, with the Kolla virtual environment active:

   ```bash
   ansible -i /etc/kolla/multinode 'control:compute:network:storage' --list-hosts
   ```

   Proceed only if every displayed target is a node you intend to power off and all intended nodes are present. In particular, make sure the management VM is not in the target set. Inventory aliases can represent the same physical host; review that mapping as well.

## 2. Power off the nodes: higher-risk fallback

The preferred path is a verified, deployment-specific, dependency-ordered shutdown that records which Galera member stopped last. This repository does not yet supply or verify such a procedure. In particular, do not assume that `kolla-ansible stop` or a helper from a different deployment guarantees the required order.

**Fallback only: this schedules a whole-cloud outage, not a coordinated service shutdown.** The command below schedules normal operating-system shutdown on every host shown in the inventory preview. It does not first coordinate a Galera shutdown or guarantee which database member stops last. A complete database outage may therefore require coordinated Kolla MariaDB recovery at the next start. Do not use it until the workload, storage, backup, console, and target checks above are complete and you explicitly accept that risk and potential recovery. Keep workloads stopped and do not start new operations during the countdown.

On the **management VM**, run once:

```bash
ansible -i /etc/kolla/multinode 'control:compute:network:storage' -b \
  -m ansible.builtin.command -a '/sbin/shutdown -h +5'
```

This schedules poweroff in five minutes, allowing time to review the scheduling results; `CHANGED` means a shutdown was requested, **not** that power is already off. Check the Ansible result for every intended host and confirm physical power state via the console or out-of-band controller before removing electricity. Loss of SSH alone does not prove a host is powered off.

If any target fails, is unreachable, or is unexpected, try to cancel immediately with this command from the management VM, using the same target pattern:

```bash
ansible -i /etc/kolla/multinode 'control:compute:network:storage' -b \
  -m ansible.builtin.command -a '/sbin/shutdown -c'
```

Enter your sudo password if prompted. Review the cancellation result on every host. **The countdown may disable new SSH logins immediately**, including while the machines still answer on port 22. In that case the Ansible cancellation cannot connect; use an already-open privileged console or other verified console access instead. The five-minute window is not guaranteed to be enough; cancellation cannot reach an already stopped or disconnected host. If any result is uncertain, do not assume the cluster shut down cleanly. After the scheduled time, SSH unreachability alone does not prove physical power-off.

## 3. Power on and run the automated health check

Power on all physical nodes through their power buttons or your separately configured out-of-band system. Allow them time to boot. A preferred database startup order is not a substitute for Galera recovery, and no order is assumed here without verified shutdown records. Leave the management VM on.

For a compact, table-form overview first, run the following from the repository root on the management VM:

```bash
source "$HOME/.venvs/kolla-2026.2/bin/activate"
bash "$HOME/fishbone/scripts/lab-recover.sh"
```

This is read-only and does not ask for sudo. It shows each selected node's Kolla systemd unit state, reported Compute service and Network agent heartbeats, and VM statuses. An `ACTIVE` systemd unit does **not** prove its container, API, or cluster is healthy. `ABSENT` means the unit was not found on that node; verify whether it is expected there. `MISSING` means a core unit is absent on a host in its corresponding inventory group. Compute heartbeat coverage is compared with `compute` inventory aliases; if service hostnames differ from aliases, investigate the resulting `BLOCKED` status. Other service and agent rows are API-reported only, and missing expected rows are not fully detected. VM status does not prove guest connectivity or storage health. A VM in `ERROR`, a failed or unreachable check, a stopped or expected-but-missing unit, or an unavailable API makes the command return nonzero; `(none returned)` means the API successfully returned an empty VM list, not proof of workload quiescence.

For both the table and the more detailed check below, use `bash "$HOME/fishbone/scripts/lab-recover.sh" --full`. This runs the table first and then invokes the existing full audit with noninteractive sudo. Add `--ask-become-pass` if the nodes require a local sudo password prompt. The checks are independent: the full audit still runs if the table identifies an issue. Neither mode restarts anything.

Alternatively, from the **repository root on the management VM**, activate the Kolla environment and run the original combined check directly:

```bash
source "$HOME/.venvs/kolla-2026.2/bin/activate"
bash "$HOME/fishbone/scripts/lab-health-full.sh"
```

If passwordless sudo is unavailable, add `--ask-become-pass` and enter the node sudo password at the local terminal prompt. The tool does not store or print that password. The first part checks the current inventory, SSH, host resources, management-address service ports, cloud authentication, and available service/agent lists. The second part uses sudo to inspect the MariaDB and RabbitMQ containers, run local application diagnostics, and compare reported Galera state across the expected members of a single inventory shard. It never restarts services, and it does not display tokens, passwords, raw Docker inspection data, cluster UUIDs, or application logs.

For the host/cloud portion only, without sudo, run `python3 "$HOME/fishbone/scripts/lab-health.py"`. For a different inventory or named cloud, use `bash "$HOME/fishbone/scripts/lab-health-full.sh" --inventory PATH --cloud NAME`. A nonzero exit means at least one result needs attention or could not be checked; it is not itself a diagnosis.

By default, the host dashboard checks the `control`, `compute`, and `network` inventory groups; it does not include a host that is **only** in `storage`. If you have a separate storage group, additionally run `python3 "$HOME/fishbone/scripts/lab-health.py" --group control --group compute --group network --group storage` after confirming all four groups exist and are populated. The MariaDB and RabbitMQ TCP probes use each target's inventory management address. If the service binds to a different API address, a blocked TCP probe does not establish that the service is down.

| Result | Meaning |
|---|---|
| `PASS` | The named check succeeded. Read the check's scope; a reachable TCP port is not proof of a healthy cluster. |
| `FAIL` | A named check detected a problem. |
| `BLOCKED` | The check could not establish a result. This is not proof that the service is down. |
| `REVIEW` | The reported state needs an operator decision, for example a disabled scheduling service. |

The Galera aggregate check is designed for a **single shard** represented by the `mariadb` inventory group. It requires each expected member to report `Primary`, `Synced`, connected and ready, the expected member count, and the same nonzero cluster UUID. A missing status, unavailable healthcheck credentials, unrecognized result, or detected multiple-shard layout is `BLOCKED`. Not every custom multi-shard layout can be detected automatically; if you use multiple shards, do not rely on this aggregate and verify each shard separately.

The dashboard is not a workload test and cannot by itself prove exact Galera member identities, a single atomic cluster view, RabbitMQ membership, successful guest boot, storage integrity, or that the lab is ready to power off. It samples members sequentially and compares the reported counts and UUIDs; an unexpected member could replace an expected one without changing the count. A Galera PASS does not prove backup or storage integrity. The service heartbeat summaries cover rows returned by the API; they do not verify that every expected host has registered a service. A service can be running while its cluster or OpenStack heartbeat is unhealthy. Do not repeatedly restart components merely because a single check is blocked.

**A recurring cold-start pattern:** hosts and RabbitMQ can be up while MariaDB containers remain `starting` and the cloud API is blocked. One possible cause is a Galera cluster with all members in `NON_PRIM`. Follow the database decision table below to establish whether that is actually the current state. A reboot does not automatically require recovery, and an unconditional recovery at every boot could disrupt a healthy or partially available cluster.

Galera needs a Primary Component, not just running containers. After a complete shutdown, ordinary simultaneous container starts do not always re-establish one. MariaDB documents that `gvwstate.dat` is deleted on graceful shutdown, so its absence alone is not evidence of corruption. When `pc.recovery` is enabled and a suitable saved view exists, a cluster may recover automatically after a full crash once the saved members reconnect; that mechanism is not guaranteed for every shutdown. See the [MariaDB Primary Component recovery documentation](https://mariadb.com/docs/galera-cluster/high-availability/recovering-a-primary-component).

## 4. If the database is unavailable

A failed MariaDB port or HTTP `502` is a symptom, not enough evidence to choose a database recovery. First identify the configured MariaDB members, then inspect the MariaDB containers on all of them from the management VM:

```bash
ansible-inventory -i /etc/kolla/multinode --graph mariadb
ansible -i /etc/kolla/multinode mariadb -b \
  -m ansible.builtin.command -a 'docker ps -a --filter name=mariadb'
```

Look for the exact `mariadb` container and its status on **every** configured member; the filter may also show temporary recovery containers. An Ansible `CHANGED` label here is the command module's default—it is a read-only listing. Container state alone does not establish whether Galera has a Primary component: containers can be running while the database cluster is non-primary.

If containers are running but the database is not ready, inspect the actual MariaDB application log on each member (the wrapper output from `docker logs` can omit it). If SQL is responding, also run the read-only [Galera status check](#verify-galera-and-rabbitmq); a failed SQL query means **unknown**, not automatically “no Primary.”

```bash
ansible -i /etc/kolla/multinode mariadb -b -m ansible.builtin.command \
  -a 'docker exec mariadb tail -n 40 /var/log/kolla/mariadb/mariadb.log'
```

Check the newest timestamps, not old entries. These logs may contain private information; redact them before sharing. If a container is restarting and `docker exec` fails, its state is **unknown**, not proof of a complete outage. `gvwstate.dat` missing alone does not prove the database is corrupt; do not create or edit it by hand.

| Observed state | Decision |
|---|---|
| A Primary component survives, or its presence is uncertain | Do not run complete-cluster recovery; inspect that member and the rest of the cluster first. |
| Every configured member is reachable and the database containers are cleanly stopped after a full shutdown, with no surviving Primary | Review backups and proceed with coordinated Kolla recovery if the complete outage is confirmed. |
| Containers are **running**, but all members show a recent, consistent `NON_PRIM` view with no surviving Primary | This can also be a complete cluster outage. Verify the view covers every configured member, review backups, and use coordinated Kolla recovery; Kolla will stop the containers itself. |
| Any member is unreachable, logs are stale/incomplete, the views disagree, there are additional unexamined shards, or data state is unclear | Stop for investigation; a failed port or `starting` healthcheck is not enough evidence to recover. |

Do not manually select a bootstrap node, edit `grastate.dat`, delete a database volume, or restart all MariaDB containers independently. Full-cluster loss after a power cycle may require Kolla recovery; it is **not** an instruction to recover on every reboot or proof that hardware is defective.

Only after confirming a **complete MariaDB cluster outage** and reviewing backups and the Kolla recovery impact should you consider recovery. Immediately before running it, recheck that all intended members are still reachable and inspect their current container states:

```bash
ansible -i /etc/kolla/multinode mariadb -e '{"ansible_become": false}' -m ansible.builtin.ping
ansible -i /etc/kolla/multinode mariadb -b \
  -m ansible.builtin.command -a 'docker ps -a --filter name=mariadb'
```

If any MariaDB container is running, repeat the current SQL and log checks above for every member, and verify no Primary or independently writable partition survives. Recent logs are evidence, not an atomic proof: a member can change state between checks and recovery. Keep other operators and workloads from changing the cluster during review; if a host is missing, a Primary may exist, a result is stale, or the state is uncertain, **do not run recovery**. A privileged, coordinated assessment or backup review is then needed.

Once those checks and the outage decision are complete, run the installed Kolla recovery once from the management VM:

```bash
ANSIBLE_DISPLAY_SKIPPED_HOSTS=false \
  kolla-ansible mariadb-recovery -i /etc/kolla/multinode --become
```

This is a **change**, not a check: Kolla stops MariaDB containers, runs WSREP recovery, normally compares recovered positions and chooses a member to bootstrap, modifies bootstrap state and configuration, and coordinates cluster startup. A preselected recovery-host override bypasses the normal selection; do not set one without a separate, verified recovery plan. The example uses verified passwordless sudo. If the nodes require a sudo password, prefix the same command with `ANSIBLE_BECOME_ASK_PASS=true` and enter it at the local prompt; never enter the password in the command or chat. Stop if recovery reports a failure; do not repeatedly run it without diagnosing the cause. Do not share tokens, configuration files, or unredacted logs.

### Verify Galera and RabbitMQ

After a successful recap with no failures or unreachable hosts, run the combined health dashboard again. Then verify actual Galera status on **every** database member. This example uses the Kolla healthcheck client configuration for an Ubuntu/Debian MariaDB image; it does not display that configuration:

```bash
ansible -i /etc/kolla/multinode mariadb -b -m ansible.builtin.command \
  -a "docker exec mariadb mariadb --defaults-file=/etc/mysql/healthcheck.cnf --batch --skip-column-names -e \"SHOW GLOBAL STATUS WHERE Variable_name IN ('wsrep_cluster_status','wsrep_cluster_size','wsrep_local_state_comment','wsrep_ready','wsrep_connected','wsrep_cluster_state_uuid','wsrep_incoming_addresses')\""
```

Each member of the **same Galera shard** should report `Primary`, `Synced`, `wsrep_ready=ON`, `wsrep_connected=ON`, the same cluster UUID, and a cluster size equal to that shard's configured MariaDB member count. For a single-shard deployment, that is the number of MariaDB members. Where `wsrep_incoming_addresses` reports identifiable addresses, compare them with the expected members; if those addresses cannot be reliably mapped, exact identities remain unknown. These are sequential samples, not an atomic view. Keep node addresses and cluster identifiers private when sharing results. If you use multiple shards, check each shard and its inventory membership separately rather than expecting one UUID across all shards. If the command is unavailable, permission is denied, a member is missing, or any result differs, status is **unknown or unhealthy**: stop and review, not automatic success. The local healthcheck alone does not prove the expected membership.

Check RabbitMQ's reported running members, alarms and partitions too:

```bash
ansible -i /etc/kolla/multinode rabbitmq -b -m ansible.builtin.command \
  -a 'docker exec rabbitmq rabbitmq-diagnostics -q cluster_status'
```

Compare the running members with the configured `rabbitmq` inventory group and check that there are no alarms or network partitions. A failure or missing member requires investigation. After that, check API responses and the compute and network service heartbeats using the dashboard, and then restore only the workloads previously recorded. A passing HTTP or port check does not establish guest or storage health.

## 5. Diagnose other failures

- **RabbitMQ:** a listening port does not prove all members joined, that there are no alarms, or that clients authenticate. Inspect the cluster and only then consider a targeted repair.
- **An API returns 502 or 503:** a proxy may be unable to use its backend, but the HTTP status alone does not identify why. Check the database, RabbitMQ, and the affected API's local health first. If those dependencies are healthy, inspect the affected API's logs on its inventory members; do not keep repeating MariaDB recovery. For example, to inspect Neutron server logs on the nodes in `neutron-server`:

  ```bash
  ansible -i /etc/kolla/multinode neutron-server -b -m ansible.builtin.command \
    -a 'docker exec neutron_server tail -n 40 /var/log/kolla/neutron/neutron-server.log'
  ```

  These logs may include private information or service credentials. Redact them before sharing. If the container is stopped or restarting, `docker exec` may fail; inspect that container's state and find the persistent Kolla log volume instead of inferring the cause. Restart only a reviewed affected service after checking its dependencies; do not restart the entire cloud blindly.

  **Check the affected backend, not just the shared VIP.** For example, when Neutron is configured to listen on the node management address and port 9696, replace `NODE_MGMT_IP` with the affected node's actual address and run this from the management VM:

  ```bash
  curl --noproxy '*' -s -o /dev/null --max-time 5 -w '%{http_code}\n' http://NODE_MGMT_IP:9696/
  ```

  HTTP `200` verifies only that this unauthenticated root request received a response. HTTP `500` indicates that backend returned an error; it does not by itself identify the cause. `000` or a failed command means the probe could not establish a response, including when this deployment binds elsewhere. Check Galera, RabbitMQ, Neutron RPC services, and the affected backend's application and uWSGI logs; if those dependencies are healthy and the selected backend requires a restart, use the Neutron server row in the Ansible quick reference below. Verify the backend and agents again before touching another node.
- **A compute or network service reports down:** check its heartbeat, admin state, container and dependencies separately. A disabled service may be intentionally in maintenance; do not automatically enable it.
- **A VM remains in BUILD or ERROR:** inspect the existing VM and its redacted error first. Do not issue a duplicate create command or delete it without reviewing its contents.

## 6. Manual service restart

A restart is an **intentional service interruption**, not a health check. First identify the exact affected node and service, inspect its recent errors, and check its dependencies, workloads, and remaining replicas. Restarting a compute service or network agent can affect workloads or networking; do not assume another replica can carry the load. A running process or HTTP error alone does not identify the cause. Do not repeatedly restart a service when the cause or outcome is unclear.

### Open vSwitch agent: identify and recover one affected node

Run these commands on the **management VM**, with the Kolla environment active. The service's systemd name is case-sensitive: use `kolla-neutron_openvswitch_agent-container.service`, not the human-readable agent name. `kolla-Neutron-Open-vSwitch-agent.service` is not the Kolla unit name.

1. Find the affected host and check its heartbeat:

   ```bash
   openstack network agent list --agent-type open-vswitch
   ```

   A DOWN heartbeat is separate from systemd state: a unit and container can be running while the agent is not reporting to Neutron. If this command fails because the network API is unavailable, **do not infer agent health**; diagnose the API and its dependencies first.
2. Review the selected host's workloads and network impact, Galera and RabbitMQ health, Neutron server/RPC health, and the remaining agents. Check the actual unit exists and is loaded. In the next command, replace `NODE_ALIAS` with the affected host's inventory alias; do not type `NODE_ALIAS` literally:

   ```bash
   ansible -i /etc/kolla/multinode NODE_ALIAS -b -m ansible.builtin.command -a 'systemctl show kolla-neutron_openvswitch_agent-container.service -p LoadState -p ActiveState -p SubState'
   ```

   The Ansible command module may report `CHANGED` for this read-only query. A missing unit or an unavailable dependency is a stop condition, not an instruction to create a unit. Review sanitized agent logs when the cause is unclear; never paste credentials or unredacted logs into chat.
3. **Only after reviewing the impact and approving the restart**, target that same one host:

   ```bash
   ansible -i /etc/kolla/multinode NODE_ALIAS -b -m ansible.builtin.command -a 'systemctl restart kolla-neutron_openvswitch_agent-container.service'
   ```

   Add `-K` if the node requires an interactive sudo password. This restarts the agent; it does not intentionally restart the Open vSwitch database or switch processes. Systemd dependencies and workloads can still be affected. A successful command means the request completed, not that the agent heartbeat recovered.
4. Run `openstack network agent list --agent-type open-vswitch` again. Confirm the **same host** reports alive and enabled. Also verify its container health and the affected network workloads. If the heartbeat stays down, the API is unavailable, or the restart outcome is unclear, stop and investigate; do not repeatedly restart it or move to another node.

### From the management VM

From the repository root with the Kolla environment active, choose **one** inventory alias shown in the table and **one** approved service name from the reference below. This example selects `nova_compute`; replace `NODE_ALIAS` with the actual affected inventory alias:

```bash
bash "$HOME/fishbone/scripts/lab-recover.sh" --restart --node NODE_ALIAS --service nova_compute
```

The tool shows the selected node, literal inventory IP, and service and requires the exact confirmation phrase displayed. It uses noninteractive sudo by default; add `--ask-become-pass` for a local password prompt when needed. It requires an SSH target with a literal inventory IP and refuses local, loopback, or management-interface addresses; if your inventory uses only a DNS name, configure and review its literal `ansible_host` first. The tool rechecks the inventory after confirmation and pins the chosen address, but it cannot eliminate all concurrent-change races. Do not put the password in chat or in the command. If confirmation is declined, no restart is sent. The playbook validates the one-node target and allowlist, checks the unit and existing container, requests one restart of the selected unit, and checks its resulting state. Systemd dependencies can affect other units. It does **not** establish healthy dependencies, sufficient capacity, application-level health, or quorum on your behalf; those require separate review. A stopped existing unit may be started by `restart`. If a check fails or the outcome is unclear, stop and inspect the result; do not blindly repeat the action. The confirmation is an operator safeguard, not an access-control boundary; an administrator can still invoke systemd directly.

The tool deliberately excludes MariaDB and RabbitMQ from its generic restart action. Do not use individual systemd restarts as a substitute for Galera or RabbitMQ cluster recovery. Follow the database section above or a broker-specific procedure.

### Ansible quick reference: run on the management VM

These are **alternative commands, not a batch**. Select one affected component and one host after the checks above. Replace `NODE_ALIAS` with the affected inventory alias; do not type it literally. Add `-K` when sudo needs a password. Verify the same service's container health and OpenStack heartbeat afterward. Do not restart an agent solely because its unit is ACTIVE or because a different node reports DOWN.

| Component | Ansible command on the management VM |
|---|---|
| Nova compute | `ansible -i /etc/kolla/multinode NODE_ALIAS -b -m ansible.builtin.command -a 'systemctl restart kolla-nova_compute-container.service'` |
| Nova conductor | `ansible -i /etc/kolla/multinode NODE_ALIAS -b -m ansible.builtin.command -a 'systemctl restart kolla-nova_conductor-container.service'` |
| Nova scheduler | `ansible -i /etc/kolla/multinode NODE_ALIAS -b -m ansible.builtin.command -a 'systemctl restart kolla-nova_scheduler-container.service'` |
| Nova API | `ansible -i /etc/kolla/multinode NODE_ALIAS -b -m ansible.builtin.command -a 'systemctl restart kolla-nova_api-container.service'` |
| Placement API | `ansible -i /etc/kolla/multinode NODE_ALIAS -b -m ansible.builtin.command -a 'systemctl restart kolla-placement_api-container.service'` |
| Neutron server API | `ansible -i /etc/kolla/multinode NODE_ALIAS -b -m ansible.builtin.command -a 'systemctl restart kolla-neutron_server-container.service'` |
| Neutron Open vSwitch agent | `ansible -i /etc/kolla/multinode NODE_ALIAS -b -m ansible.builtin.command -a 'systemctl restart kolla-neutron_openvswitch_agent-container.service'` |
| Neutron router / L3 agent | `ansible -i /etc/kolla/multinode NODE_ALIAS -b -m ansible.builtin.command -a 'systemctl restart kolla-neutron_l3_agent-container.service'` |
| Neutron DHCP agent | `ansible -i /etc/kolla/multinode NODE_ALIAS -b -m ansible.builtin.command -a 'systemctl restart kolla-neutron_dhcp_agent-container.service'` |
| Neutron metadata agent | `ansible -i /etc/kolla/multinode NODE_ALIAS -b -m ansible.builtin.command -a 'systemctl restart kolla-neutron_metadata_agent-container.service'` |
| Cinder scheduler | `ansible -i /etc/kolla/multinode NODE_ALIAS -b -m ansible.builtin.command -a 'systemctl restart kolla-cinder_scheduler-container.service'` |

### Direct quick reference: on the affected node only

These are alternatives to the management-VM tool, **not** commands to run together. Select only the one service whose restart you have reviewed. The unit names apply to Kolla deployments that actually have these systemd units; verify the selected unit and container on the affected node first. A service that is not deployed, such as an optional Cinder scheduler, cannot be restarted this way. `systemctl restart` also starts a stopped unit; do not run a separate stop first. A successful command is normally silent.

| Component | Command on the affected node |
|---|---|
| Nova compute | `sudo systemctl restart kolla-nova_compute-container.service` |
| Nova conductor | `sudo systemctl restart kolla-nova_conductor-container.service` |
| Nova scheduler | `sudo systemctl restart kolla-nova_scheduler-container.service` |
| Nova API | `sudo systemctl restart kolla-nova_api-container.service` |
| Placement API | `sudo systemctl restart kolla-placement_api-container.service` |
| Neutron server API | `sudo systemctl restart kolla-neutron_server-container.service` |
| Neutron Open vSwitch agent | `sudo systemctl restart kolla-neutron_openvswitch_agent-container.service` |
| Neutron router / L3 agent | `sudo systemctl restart kolla-neutron_l3_agent-container.service` |
| Neutron DHCP agent | `sudo systemctl restart kolla-neutron_dhcp_agent-container.service` |
| Neutron metadata agent | `sudo systemctl restart kolla-neutron_metadata_agent-container.service` |
| Cinder scheduler | `sudo systemctl restart kolla-cinder_scheduler-container.service` |

For example, after selecting Nova compute, verify the **same affected node and service**:

```bash
systemctl status kolla-nova_compute-container.service --no-pager
sudo docker inspect --format 'status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}not-configured{{end}}' nova_compute
```

A running unit or container without a configured healthcheck is **not** a health pass. In that case, the management-VM action reports `UNKNOWN` and exits nonzero **after the restart was sent**; verify the application and workload rather than repeating the restart. Where health is configured, wait for `healthy` and separately verify the relevant API or OpenStack service heartbeat and the affected workload. If it fails or remains `starting`, stop and review the service's sanitized logs. The tool accepts standard Kolla Docker systemd units; a unit that changes between checks, a drop-in, unsupported dependency, unloaded systemd change, or other nonstandard configuration blocks the action. This local quick reference assumes Docker; check your configured container engine and unit implementation before applying it to another deployment.

## References

This procedure was informed by the separate [shutdown and recovery reference](https://github.com/DinosaurKeys/openstack-from-zero/blob/main/docs/reboot-and-recovery.md); that reference describes a different deployment and its own scripts, host order and service layout, so none are assumed to apply unchanged here. Kolla's [2026.2 troubleshooting documentation](https://docs.openstack.org/kolla-ansible/2026.2/user/troubleshooting.html) describes its logs and operational troubleshooting.
