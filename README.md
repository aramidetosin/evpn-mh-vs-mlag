# EVPN multihoming vs MLAG

Two containerlab labs with the same wiring, the same addressing and the same
hosts. The only difference is how the leaf pair presents one LACP partner to a
dual homed server: MLAG in `mlag/`, an EVPN Ethernet Segment in `evpn-mh/`.
The drills in `scripts/` break the same things in both and measure what the
traffic did.

## Requirements

- containerlab, Docker, and `sshpass` on the host
- A Cumulus Linux 5.15.0 image tagged `vrnetlab/nvidia_cumulus-vx:5.15.0`,
  built so that `startup-config` (the NVUE `nv set` lines under each lab's
  `bootstrap/`) is applied at first boot
- `ghcr.io/srl-labs/network-multitool` for the two hosts

Switch login is `cumulus` / `Clab123!`, overridable with `PASS=` on any make
target or `CL_PASS=` in the environment.

## Run it

```
make up            # both labs, about 5 minutes
make green         # convergence check on both
make drills        # every failure drill, both labs, about 55 minutes
make results       # the comparison table
make down
```

`make up` ends with `scripts/post-deploy.sh`, which sets
`net.ipv4.fib_multipath_hash_policy=1` on every switch and gives both hosts the
spare addresses the drills use to steer a probe onto a chosen leaf.

## The topology

Two spines, three leaves, two hosts. eBGP unnumbered underlay, EVPN overlay,
VLAN 100 mapped to VNI 10100. host01 is dual homed to leaf01 and leaf02 with an
802.3ad bond running fast LACP. host02 hangs off leaf03.

|  | `mlag/` | `evpn-mh/` |
|---|---|---|
| spine01, spine02 | AS 65100, eBGP unnumbered, EVPN address family | same |
| leaf01, leaf02 | AS 65101 / 65102, MLAG pair, anycast VTEP 10.0.0.12, peer link swp4 and swp5, backup IP over the fabric | AS 65101 / 65102, one Ethernet Segment (ESI `03:44:38:39:be:ef:aa:00:00:01`), VTEPs 10.0.0.1 and 10.0.0.2, uplink tracking, no link between them |
| leaf03 | AS 65103, VTEP 10.0.0.3, host02 on swp1 | same |
| overlay | VLAN 100 to VNI 10100, layer 2 between the hosts | same |

`gen.py` writes both topologies and all ten bootstrap configs from one
description, so `diff mlag/bootstrap/leaf01.cfg evpn-mh/bootstrap/leaf01.cfg`
is the whole difference between the designs.

## The drills

`scripts/drill.sh <lab> <test> <leaf>`:

| test | what is cut | restore |
|---|---|---|
| `hostlink` | the leaf's swp1 and host01's matching NIC, both ends | both up at +40 s |
| `peerlink` | swp4 and swp5 on both leaves (MLAG only) | up at +40 s |
| `uplinks` | the leaf's swp2 and swp3, and the matching spine ports | up at +40 s |
| `leaf` | `reboot` on the leaf | it comes back on its own |

Two ping probes run for the whole drill at 100 ms intervals, one started from
each host, and the drill restarts them until both are riding the leaf under
test. A probe on the surviving leaf does not exercise the affected path, so a
run that cannot place both is recorded as `worst case: no` rather than reported
as one.

Placement needs two controls. Which leaf delivers toward host01 is a hash of the
inner IP pair in the fabric, so host02's source address moves it. Which cable
host01 sends on is its bond's `layer3+4` hash, which for ICMP can fold in the
echo identifier as well as the addresses, so the drill also varies host01's
source address. Both hosts carry spare addresses for this.

## Reading the numbers

`scripts/analyze_ping.py` reports one probe file, `scripts/summarize.py` builds
the comparison, and `scripts/compare_passes.py` combines several passes into
ranges and flags any scenario where the passes disagree about whether there was
loss at all.

Three things are reported separately, because collapsing them misleads:

- probes never answered, split into the failure window and the recovery window
- replies that arrived more than a second late, which `ping` still counts as
  received: under uplink isolation some arrive around 32 seconds late
- the longest stretch with nothing arriving, computed over arrival order rather
  than sequence order, since late replies arrive out of order

Run the matrix more than once. The scenarios do not all reproduce: across three
passes, MLAG under uplink isolation consistently lost at most one probe while
holding one to three replies about 32 seconds, but the peer link cut with probes
on the primary was lossless in one pass and lost 26 probes on one of its two
probes in another.

## Platform notes

- A link set down inside one node does not drop carrier at the far end, so the
  drills shut both ends of a link administratively, in sequence. Those commands
  span roughly 180 to 420 ms, which is inside every measurement.
- The EVPN multihoming leaves need one reboot after the first `nv config apply`
  before the segment bonds get carrier. `evpn mh redirect-off` is not applied in
  this build and does not appear in either leaf's running config.
