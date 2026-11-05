# Target installation architecture

This page describes the target deployment built by the [Full Installation Guide](FULL-INSTALLATION-GUIDE.md). It is a design reference, not a second installation procedure.

## Target hosts and Kolla-Ansible roles

| Host | Management address | Kolla-Ansible groups |
|:--|:--|:--|
| Management VM (`manager`) | Unique address on the management LAN | Deployment host; not an OpenStack node |
| Node 1 | `NODE1_MGMT_IP` | `control`, `network`, `compute` |
| Node 2 | `NODE2_MGMT_IP` | `control`, `network`, `compute` |
| Node 3 | `NODE3_MGMT_IP` | `control`, `network`, `compute` |

The three physical nodes are intentionally multi-role. Kolla-Ansible uses the three-node control group for the control plane and the network group for the HA API load-balancer/VIP path. Keep all three nodes in all three groups in the Kolla inventory.

## High-level diagram

```text
                         Management VM (unique IP)
                  Git + Kolla-Ansible + OpenStack CLI
                               |
                   SSH / API / management LAN
                               |
          +--------------------+--------------------+
          |                    |                    |
  +-------+-------+    +-------+-------+    +-------+-------+
  | Node 1        |    | Node 2        |    | Node 3        |
  | NODE1_MGMT_IP |    | NODE2_MGMT_IP |    | NODE3_MGMT_IP |
  | control       |    | control       |    | control       |
  | network       |    | network       |    | network       |
  | compute       |    | compute       |    | compute       |
  +-------+-------+    +-------+-------+    +-------+-------+
          |                    |                    |
          +========== Provider NIC / shared L2 ==========+
                       Neutron provider network

Management LAN carries SSH, APIs, service traffic, and (in the two-NIC
baseline) Neutron tunnel traffic. The provider NIC has no configured
provider-subnet address or default route; an automatic IPv6 link-local
address may still appear. Reserve a free internal VIP on the management subnet
before deployment.
```

## Network design

The baseline assumes two interfaces per physical node:

1. Management interface: stable node address, SSH, Ansible, service/API traffic, and the default overlay tunnel path.
2. Provider interface: connected to the shared lab switch, no configured provider-subnet address/default route, reserved for Neutron provider networking. An automatic IPv6 link-local address may appear.

A provider network on an isolated switch is still isolated; it does not create Internet access or floating-IP reachability without an upstream router and an explicit address plan. If management, overlay tunnels, and provider traffic must be isolated from one another, use three physical interfaces per node and update the design before deployment.

Reserve node addresses outside DHCP. Reserve a free management-subnet VIP for Kolla and record it in the local deployment plan. Do not copy an example or select an address without confirming it is unused.

## Service flow for a test instance

```text
Operator authenticates through the Kolla API VIP
        |
Keystone -> Nova API -> scheduler -> Placement
        |                         |
        |                         +-> Nova compute on one of three nodes
        |                                  |
        +-> Glance supplies image          +-> KVM/libvirt starts guest
        |
Neutron creates the port and tenant-network path
        |
Guest gets an address from the tenant subnet
        |
Optional provider network requires the planned physical L2/uplink
```

## Control-plane and storage boundaries

- Kolla-Ansible installs OpenStack services in containers; do not manually install a second set of OpenStack packages or a separate OVS deployment on the hosts.
- The Kolla inventory must include all three nodes in `control`, `network`, and `compute`. Preserve the release-matched upstream inventory’s child-group definitions.
- Configure Kolla’s internal VIP on the management network and ensure the network group has all three nodes before deployment.
- Cinder is an optional extension, not a prerequisite for the core cloud. Local LVM provides local block volumes, not replicated HA storage. Select a replicated/shared backend before claiming storage HA.
- A working VIP or healthy process list alone does not prove end-to-end HA; test API access and a disposable workload through a planned, reversible procedure.
