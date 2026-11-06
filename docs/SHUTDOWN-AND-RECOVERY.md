# Shutdown, power-on, and recovery

[Back to the full installation guide](FULL-INSTALLATION-GUIDE.md#operations--shutdown-power-on-and-recovery)

This is the day-to-day procedure for a Kolla-Ansible lab. In VMware terms, the management VM is the administration workstation; the OpenStack nodes are the hosts that run the cloud. Leave the management VM running while you operate on the nodes.

On the management VM, activate the Kolla environment before running commands in this guide:

```bash
source "$HOME/.venvs/kolla-2026.2/bin/activate"
export OS_CLOUD=kolla-admin
```

The generated Kolla cloud is normally named `kolla-admin`; choose your configured cloud name instead if it differs. For commands under `scripts/`, first change into your local clone of this repository. Do not paste secrets from `clouds.yaml` or `/etc/kolla/passwords.yml` into the terminal or chat.

**Scope:** the health checks are read-only. They do not stop or restart services, create or delete VMs, or repair the database. This repository does not yet provide a verified automatic, dependency-ordered shutdown or out-of-band power-on. Do not copy another lab's helper scripts or fixed host order without verifying that its inventory, container engine, service units, and storage match yours.

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
ansible -i /etc/kolla/multinode 'control:compute:network:storage' -b -K \
  -m ansible.builtin.command -a '/sbin/shutdown -h +5'
```

Enter your sudo password at the local terminal prompt. This schedules poweroff in five minutes, allowing time to review the scheduling results; `CHANGED` means a shutdown was requested, **not** that power is already off. Check the Ansible result for every intended host and confirm physical power state via the console or out-of-band controller before removing electricity. Loss of SSH alone does not prove a host is powered off.

If any target fails, is unreachable, or is unexpected, try to cancel immediately with this command from the management VM, using the same target pattern:

```bash
ansible -i /etc/kolla/multinode 'control:compute:network:storage' -b -K \
  -m ansible.builtin.command -a '/sbin/shutdown -c'
```

Enter your sudo password if prompted. Review the cancellation result on every host. The five-minute window is not guaranteed to be enough; cancellation cannot reach an already stopped or disconnected host. If any result is uncertain, do not assume the cluster shut down cleanly.

## 3. Power on and run the automated health check

Power on all physical nodes through their power buttons or your separately configured out-of-band system. Allow them time to boot. A preferred database startup order is not a substitute for Galera recovery, and no order is assumed here without verified shutdown records. Leave the management VM on.

From the **repository root on the management VM**, activate the Kolla environment and run the combined check:

```bash
source "$HOME/.venvs/kolla-2026.2/bin/activate"
bash scripts/lab-health-full.sh
```

Enter the node sudo password at the local terminal prompt for the container checks. The tool does not store or print that password. The first part checks the current inventory, SSH, host resources, management-address service ports, cloud authentication, and available service/agent lists. The second part uses sudo to inspect the MariaDB and RabbitMQ containers and run **local** application diagnostics on their inventory members. It never restarts services, and it does not display tokens, passwords, raw Docker inspection data, or application logs.

For the host/cloud portion only, without sudo, run `python3 scripts/lab-health.py`. For a different inventory or named cloud, use `bash scripts/lab-health-full.sh --inventory PATH --cloud NAME`. A nonzero exit means at least one result needs attention or could not be checked; it is not itself a diagnosis.

By default, the host dashboard checks the `control`, `compute`, and `network` inventory groups; it does not include a host that is **only** in `storage`. If you have a separate storage group, additionally run `python3 scripts/lab-health.py --group control --group compute --group network --group storage` after confirming all four groups exist and are populated. The MariaDB and RabbitMQ TCP probes use each target's inventory management address. If the service binds to a different API address, a blocked TCP probe does not establish that the service is down.

| Result | Meaning |
|---|---|
| `PASS` | The named check succeeded. Read the check's scope; a reachable TCP port is not proof of a healthy cluster. |
| `FAIL` | A named check detected a problem. |
| `BLOCKED` | The check could not establish a result. This is not proof that the service is down. |
| `REVIEW` | The reported state needs an operator decision, for example a disabled scheduling service. |

The dashboard is not a workload test and cannot by itself prove Galera quorum, RabbitMQ membership, successful guest boot, storage integrity, or that the lab is ready to power off. The service heartbeat summaries cover rows returned by the API; they do not verify that every expected host has registered a service. A service can be running while its cluster or OpenStack heartbeat is unhealthy. Do not repeatedly restart components merely because a single check is blocked.

## 4. If the database is unavailable

A failed MariaDB port or HTTP `502` is a symptom, not enough evidence to choose a database recovery. First identify the configured MariaDB members, then inspect the MariaDB containers on all of them from the management VM:

```bash
ansible-inventory -i /etc/kolla/multinode --graph mariadb
ansible -i /etc/kolla/multinode mariadb -b -K \
  -m ansible.builtin.command -a 'docker ps -a --filter name=mariadb'
```

Enter your sudo password locally. Look for the exact `mariadb` container and its status on **every** configured member; the filter may also show temporary recovery containers. An Ansible `CHANGED` label here is the command module's default—it is a read-only listing. If any member is unreachable, its result is missing, a MariaDB container is running, or the stop state is abnormal or unclear, stop and investigate; do not infer a complete stopped cluster from a failed port. Inspect redacted logs and the underlying storage/backup state before deciding on recovery.

For this fallback, proceed only when all intended members are reachable and their `mariadb` containers are confirmed stopped with clean exit status, with no surviving Primary. A surviving Primary member, an unreachable node, a split cluster, unclean exit, or unclear data state needs separate review. Do not manually select a bootstrap node, edit `grastate.dat`, delete a database volume, or start all MariaDB containers independently.

Only after confirming a **complete MariaDB cluster outage** and reviewing backups and the Kolla recovery impact, run the installed Kolla recovery once from the management VM:

```bash
ANSIBLE_BECOME_ASK_PASS=true ANSIBLE_DISPLAY_SKIPPED_HOSTS=false \
  kolla-ansible mariadb-recovery -i /etc/kolla/multinode
```

This is a **change**, not a check: Kolla stops MariaDB containers, runs WSREP recovery, selects a recovered sequence position, modifies bootstrap state and configuration, and coordinates cluster startup. Enter your sudo password at the local prompt. Stop if it reports a failure; do not repeatedly run recovery without diagnosing it. Do not share passwords, tokens, configuration files, or unredacted logs.

After a successful recap with no failures or unreachable hosts, run the combined health dashboard again. Then verify actual Galera status on **every** database member. This example uses the Kolla healthcheck client configuration for an Ubuntu/Debian MariaDB image; it does not display that configuration:

```bash
ansible -i /etc/kolla/multinode mariadb -b -K -m ansible.builtin.command \
  -a "docker exec mariadb mariadb --defaults-file=/etc/mysql/healthcheck.cnf --batch --skip-column-names -e \"SHOW GLOBAL STATUS WHERE Variable_name IN ('wsrep_cluster_status','wsrep_cluster_size','wsrep_local_state_comment','wsrep_ready','wsrep_connected','wsrep_cluster_state_uuid')\""
```

Each member should report `Primary`, `Synced`, `wsrep_ready=ON`, `wsrep_connected=ON`, the same cluster UUID, and a cluster size equal to the number of configured MariaDB members. If the command is unavailable, permission is denied, a member is missing, or any result differs, status is **unknown or unhealthy**: stop and review, not automatic success. The local healthcheck alone does not prove the expected membership.

Check RabbitMQ's reported running members, alarms and partitions too:

```bash
ansible -i /etc/kolla/multinode rabbitmq -b -K -m ansible.builtin.command \
  -a 'docker exec rabbitmq rabbitmq-diagnostics -q cluster_status'
```

Compare the running members with the configured `rabbitmq` inventory group and check that there are no alarms or network partitions. A failure or missing member requires investigation. After that, check API responses and the compute and network service heartbeats using the dashboard, and then restore only the workloads previously recorded. A passing HTTP or port check does not establish guest or storage health.

## 5. Diagnose other failures

- **RabbitMQ:** a listening port does not prove all members joined, that there are no alarms, or that clients authenticate. Inspect the cluster and only then consider a targeted repair.
- **An API returns 502:** inspect its proxy/backend and required dependencies, especially the database; 502 alone does not identify the failed component.
- **A compute or network service reports down:** check its heartbeat, admin state, container and dependencies separately. A disabled service may be intentionally in maintenance; do not automatically enable it.
- **A VM remains in BUILD or ERROR:** inspect the existing VM and its redacted error first. Do not issue a duplicate create command or delete it without reviewing its contents.

## References

This procedure was informed by the separate [shutdown and recovery reference](https://github.com/DinosaurKeys/openstack-from-zero/blob/main/docs/reboot-and-recovery.md); that reference describes a different deployment and its own scripts, host order and service layout, so none are assumed to apply unchanged here. Kolla's [2026.2 troubleshooting documentation](https://docs.openstack.org/kolla-ansible/2026.2/user/troubleshooting.html) describes its logs and operational troubleshooting.
