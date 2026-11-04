# Automation and troubleshooting approach

This project borrows the useful organization and reporting ideas from the scripts in [DinosaurKeys/openstack-from-zero](https://github.com/DinosaurKeys/openstack-from-zero/tree/main/scripts), but does not copy its interactive TTY or password-prompt workflow. The goal here is to make routine checks and troubleshooting executable by the operator/agent from the management VM without stopping for an interactive terminal prompt or asking the user to paste a password into chat.

## Useful patterns from the reference scripts

The reviewed scripts demonstrate several patterns worth adapting:

- Separate a small per-node collector from an orchestrator that runs it across the cluster.
- Make inspection the default; make changes explicit and separately gated.
- Collect structured observations, then validate specific invariants rather than trusting a command's exit code alone.
- Continue collecting from other nodes if one node's check fails; report each node's result independently.
- Distinguish `PASS`, `REVIEW`, and `UNKNOWN`: a timeout or inaccessible node is unknown, not automatically down or healthy.
- Bound remote commands with timeouts, report incomplete collection honestly, and avoid hanging workflows.
- Save concise, private reports that exclude passwords, tokens, private keys, and raw sensitive command output.
- Treat snapshots, repair actions, reboot actions, and failover exercises as different operations.

These are design principles, not a claim that every reference script is safe to run here. Review a script's actual effects, inputs, and target scope before adapting it.

## Authentication and independent operation

The intended control point is the separate management VM. Use the configured SSH key and Ansible inventory to identify the three nodes. Scripts should never ask for passwords through `input()`, `getpass`, a TTY requirement, `sshpass`, or `sudo -S`; they must not put credentials in argv, logs, reports, environment dumps, or Git.

For unattended privileged checks, configure a deliberate, least-privilege access method on the nodes and verify it before relying on automation. Do not silently add broad passwordless sudo. If access is not ready, stop with a clear prerequisite/error and ask the user to complete the secure access setup locally; never request the password in chat.

A check should name its target hosts and operations. It must not infer that a node is safe to reboot, that a database member can be reset, or that a disk can be erased merely because a check failed.

## Script contract

Every operational script should state:

1. Purpose and exact target scope.
2. Whether it is read-only or changes state.
3. Required tools and authorization, checked before remote actions.
4. Per-node results, including timeouts and partial failures.
5. A bounded timeout and safe handling of interruption.
6. What was actually verified and what remains unknown.
7. Where any report is stored and how sensitive data is excluded.

Use read-only checks by default. If a mutating command is later justified, place it behind an explicit action mode, validate its inputs and target, preserve a recovery path, and verify the resulting state with a separate read-back check. High-impact operations—network changes, disk/LVM changes, service restarts that affect HA, reboot, database recovery, failover—need a reviewed plan and explicit user approval before execution.

## Operational sequence

Keep the learning order in the guide's 13 steps. In particular, Step 11 is verification and controlled testing of the existing HA/VIP design: the lab owner reports all three nodes already have controller, network, and compute roles and are configured for HA. It is not an instruction to create a new cluster or add an unplanned VIP.

When troubleshooting, first collect independent, read-only facts from all three nodes and the relevant OpenStack APIs. Correlate symptoms before choosing a change. Never equate “SSH failed” with “node is down,” “one service is up” with “HA works,” or “API says ACTIVE” with proven guest traffic/data integrity.
