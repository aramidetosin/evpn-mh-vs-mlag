#!/usr/bin/env python3
"""Generate the two labs (mlag/ and evpn-mh/): containerlab topologies and
Cumulus Linux 5.15 NVUE bootstrap configs. Same wiring, same addressing,
same hosts; only the leaf pair's redundancy mechanism differs.
Run: python3 gen.py
"""
import os

IMAGE = "vrnetlab/nvidia_cumulus-vx:5.15.0"
HOST_IMAGE = "ghcr.io/srl-labs/network-multitool:latest"
SEG_MAC = "44:38:39:be:ef:aa"      # LACP system ID the host sees, in both designs
ANYCAST_VTEP = "10.0.0.12"         # MLAG only: the pair's shared VTEP address
VLAN, VNI = 100, 10100
HOST01_IP, HOST02_IP = "172.16.10.11", "172.16.10.12"

SW = {  # name: (loopback, asn)
    "spine01": ("10.0.0.101", 65100),
    "spine02": ("10.0.0.102", 65100),
    "leaf01": ("10.0.0.1", 65101),
    "leaf02": ("10.0.0.2", 65102),
    "leaf03": ("10.0.0.3", 65103),
}
UPLINKS = ["swp2", "swp3"]           # every leaf: swp2 -> spine01, swp3 -> spine02
SPINE_PORTS = ["swp1", "swp2", "swp3"]  # spineNN: swp1 -> leaf01, swp2 -> leaf02, swp3 -> leaf03
PEERLINK = ["swp4", "swp5"]          # MLAG only


def base(name, ports, neighbors):
    lo, asn = SW[name]
    L = [
        f"nv set system hostname {name}",
        f"nv set interface lo ip address {lo}/32",
        "nv set interface lo type loopback",
        f"nv set interface {ports} type swp",
        f"nv set router bgp autonomous-system {asn}",
        f"nv set router bgp router-id {lo}",
        "nv set router bgp state enabled",
        "nv set vrf default router bgp state enabled",
        "nv set vrf default router bgp address-family ipv4-unicast state enabled",
        "nv set vrf default router bgp address-family ipv4-unicast redistribute connected state enabled",
        "nv set vrf default router bgp address-family l2vpn-evpn state enabled",
        "nv set vrf default router bgp path-selection multipath aspath-ignore enabled",
    ]
    for n in neighbors:
        L += [
            f"nv set vrf default router bgp neighbor {n} remote-as external",
            f"nv set vrf default router bgp neighbor {n} type unnumbered",
            f"nv set vrf default router bgp neighbor {n} address-family l2vpn-evpn state enabled",
        ]
    L += ["nv set evpn state enabled", "nv set system ssh-server state enabled"]
    return L


def vtep(name):
    lo, _ = SW[name]
    return [
        "nv set nve vxlan state enabled",
        f"nv set nve vxlan source address {lo}",
        f"nv set bridge domain br_default vlan {VLAN} vni {VNI}",
    ]


def host_bond():
    return [
        "nv set interface bond0 bond member swp1",
        "nv set interface bond0 bond lacp-rate fast",
        f"nv set interface bond0 bridge domain br_default access {VLAN}",
    ]


def spine(name):
    return base(name, "swp1-3", SPINE_PORTS)


def leaf03():
    return base("leaf03", "swp1-3", UPLINKS) + vtep("leaf03") + [
        f"nv set interface swp1 bridge domain br_default access {VLAN}",
    ]


def mlag_leaf(name, peer, priority):
    L = base(name, "swp1-5", UPLINKS + ["peerlink.4094"]) + vtep(name) + host_bond()
    L += [
        "nv set interface bond0 bond mlag id 1",
        f"nv set interface peerlink bond member {PEERLINK[0]}-{PEERLINK[1][-1]}",
        "nv set interface peerlink bridge domain br_default",
        f"nv set mlag mac-address {SEG_MAC}",
        f"nv set mlag backup {SW[peer][0]}",
        "nv set mlag peer-ip linklocal",
        f"nv set mlag priority {priority}",
        f"nv set nve vxlan mlag shared-address {ANYCAST_VTEP}",
    ]
    return L


def mh_leaf(name, df_pref=None):
    L = base(name, "swp1-3", UPLINKS) + vtep(name) + host_bond()
    L += [
        "nv set evpn multihoming state enabled",
        "nv set interface bond0 evpn multihoming segment local-id 1",
        f"nv set interface bond0 evpn multihoming segment mac-address {SEG_MAC}",
        "nv set interface bond0 evpn multihoming segment state enabled",
        f"nv set interface {UPLINKS[0]}-{UPLINKS[1][-1]} evpn multihoming uplink enabled",
    ]
    if df_pref:
        L.insert(-1, f"nv set interface bond0 evpn multihoming segment df-preference {df_pref}")
    return L


def topo(labname, mgmt, with_peerlink):
    links = [
        ("leaf01:swp1", "host01:eth1"),
        ("leaf02:swp1", "host01:eth2"),
        ("leaf03:swp1", "host02:eth1"),
    ]
    for i, leaf in enumerate(["leaf01", "leaf02", "leaf03"], start=1):
        links.append((f"{leaf}:swp2", f"spine01:swp{i}"))
        links.append((f"{leaf}:swp3", f"spine02:swp{i}"))
    if with_peerlink:
        for p in PEERLINK:
            links.append((f"leaf01:{p}", f"leaf02:{p}"))
    y = [f"name: {labname}", "mgmt:", f"  network: {labname}", f"  ipv4-subnet: {mgmt}",
         "topology:", "  defaults:", "    kind: nvidia_cumulusvx", f"    image: {IMAGE}", "  nodes:"]
    for sw in ["spine01", "spine02", "leaf01", "leaf02", "leaf03"]:
        y += [f"    {sw}:", f"      startup-config: bootstrap/{sw}.cfg"]
    y += [
        "    host01:", "      kind: linux", f"      image: {HOST_IMAGE}", "      exec:",
        "      - ip link set eth1 down", "      - ip link set eth2 down",
        "      - ip link add bond0 type bond mode 802.3ad miimon 100 lacp_rate fast xmit_hash_policy layer3+4",
        "      - ip link set eth1 master bond0", "      - ip link set eth2 master bond0",
        "      - ip link set eth1 mtu 9216", "      - ip link set eth2 mtu 9216", "      - ip link set bond0 mtu 9216",
        "      - ip link set eth1 up", "      - ip link set eth2 up", "      - ip link set bond0 up",
        f"      - ip addr add {HOST01_IP}/24 dev bond0",
        "    host02:", "      kind: linux", f"      image: {HOST_IMAGE}", "      exec:",
        "      - ip link set eth1 mtu 9216", f"      - ip addr add {HOST02_IP}/24 dev eth1",
        # extra addresses: the fabric hashes VXLAN flows on the inner IP pair (not the ICMP id),
        # so a probe picks the source address that lands on the leaf under test
        "      - ip addr add 172.16.10.13/24 dev eth1", "      - ip addr add 172.16.10.14/24 dev eth1",
        "      - ip addr add 172.16.10.15/24 dev eth1",
        "  links:",
    ]
    for a, b in links:
        y += ["  - endpoints:", f"    - {a}", f"    - {b}"]
    return "\n".join(y) + "\n"


def write(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(lines if isinstance(lines, str) else "\n".join(lines) + "\n")
    print("wrote", path)


for lab, labname, mgmt, pl in [("mlag", "vs-mlag", "172.20.51.0/24", True),
                               ("evpn-mh", "vs-evpnmh", "172.20.52.0/24", False)]:
    write(f"{lab}/topo.clab.yml", topo(labname, mgmt, pl))
    write(f"{lab}/bootstrap/spine01.cfg", spine("spine01"))
    write(f"{lab}/bootstrap/spine02.cfg", spine("spine02"))
    write(f"{lab}/bootstrap/leaf03.cfg", leaf03())
    if lab == "mlag":
        write(f"{lab}/bootstrap/leaf01.cfg", mlag_leaf("leaf01", "leaf02", 1000))
        write(f"{lab}/bootstrap/leaf02.cfg", mlag_leaf("leaf02", "leaf01", 32768))
    else:
        write(f"{lab}/bootstrap/leaf01.cfg", mh_leaf("leaf01", df_pref=50000))
        write(f"{lab}/bootstrap/leaf02.cfg", mh_leaf("leaf02"))
