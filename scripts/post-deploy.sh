#!/usr/bin/env bash
# post-deploy.sh <lab>: two lab-side settings that make the VX kernel dataplane
# behave like a switch ASIC for these drills. Idempotent.
#  1. ECMP hashing on the outer L4 header (the VXLAN UDP source port carries the
#     inner flow entropy); the kernel default hashes on L3 only, so every flow
#     between two VTEPs would ride one path.
#  2. host02 gets sixteen addresses so a probe can choose the inner IP pair that
#     hashes onto the leaf under test.
set -u
cd "$(dirname "$0")/.." || exit 1
source scripts/lib.sh
LAB=$1
for n in spine01 spine02 leaf01 leaf02 leaf03; do
  echo -n "$n: "; sw $LAB $n "sudo sysctl -w net.ipv4.fib_multipath_hash_policy=1"
done
for a in $(seq 13 27); do hx $LAB host02 "ip addr add 172.16.10.$a/24 dev eth1 2>/dev/null"; done
#  3. host01 gets spare addresses too. The outbound leg is chosen by the bond's
#     hash over the IP pair and the ICMP echo id, and the echo id is the ping's
#     pid, which is not ours to choose. A source address we can choose turns
#     that lottery into a knob, so a drill can put the outbound flow on the leaf
#     it is about to break instead of hoping.
for a in $(seq 31 35); do hx $LAB host01 "ip addr add 172.16.10.$a/24 dev bond0 2>/dev/null"; done
echo "host01 addresses: $(hx $LAB host01 'ip -br addr show bond0' | tr -s ' ')"
echo "host02 addresses: $(hx $LAB host02 'ip -br addr show eth1' | tr -s ' ')"
