# Lab architecture and flow

## Owner-reported lab role model

Per the lab owner, the cluster is configured for HA, and **each of the three nodes is assigned controller, network, and compute roles**. These are reported roles; current service placement and HA mechanisms have not yet been independently verified. Learning-step names are topics to inspect, not exclusive node assignments.

| Node | Management address | Roles |
|---|---|---|
| Node 1 | `192.168.0.200` | Controller + network + compute; HA member |
| Node 2 | `192.168.0.201` | Controller + network + compute; HA member |
| Node 3 | `192.168.0.202` | Controller + network + compute; HA member |
| Management VM | Separate unique address | Git, Ansible, operator tools |

The exact HA mechanisms, service placement, VIPs, database/message-queue topology, and storage replication must be discovered from the live configuration. Do not infer those details from the word “HA.”

Discover every interface, route, bridge, and VLAN on each host before describing or changing network roles. Do not assume the USB NIC is an isolated private network; confirm its cabling and current use from live state.

## High-level diagram

```text
                         Management VM
                    Hermes + Git + Ansible
                              |
                   SSH / API / management LAN
       +----------------------+----------------------+
       |                      |                      |
 Node 1 .200              Node 2 .201              Node 3 .202
 Controller               Controller               Controller
 Network                  Network                  Network
 Compute                  Compute                  Compute
 HA member                HA member                HA member
       |                      |                      |
       +========= internal / tenant networking =========+

Controller, network, and compute roles are present across all three nodes.
The diagram is conceptual; exact service placement and HA mechanisms must
be discovered from the live cluster before operating it.
```

## Low-level traffic picture

```text
Client/admin
    |
    | management LAN: SSH, Ansible, OpenStack APIs
    v
        +------------------------------+
        | 3-node service cluster       |
        |                              |
        | Controller APIs / DB / MQ    |
        | Network agents / bridges     |
        | Compute / hypervisors        |
        |                              |
        | all roles span nodes 1-3     |
        +------------------------------+
             |                  |
       tenant/provider      guest workloads
       network paths       and storage paths

Exact service placement, API VIP path, and network/storage paths are to be
observed; this picture is conceptual, not a deployment configuration.
```

## Ordered learning guide

The ordered 13-step sequence lives only in the [intensive guide](INTENSIVE-GUIDE.md#the-13-learning-steps). This page focuses on topology and traffic flow rather than repeating that sequence.

## The three networks to understand

1. Management/API path: confirm from the actual node interfaces, routes, and API endpoints.
2. Internal/tunnel path: identify the configured overlay/underlay and its interfaces from live state.
3. External/provider path: inspect the existing bridge, NIC, VLAN, and upstream connectivity. Do not assume the USB NIC's purpose from its form factor.

## HA verification boundary

This lab is not at the “add HA later” stage: the owner reports that HA is already configured across all three nodes. Step 11 therefore means inspect and validate the existing design, test only approved failure scenarios, and document recovery—not build a separate VIP on top of a single-controller design. A VIP alone is not proof of end-to-end HA; verify the actual API, database, messaging, network, compute, and storage behavior independently.
