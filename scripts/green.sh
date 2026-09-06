#!/usr/bin/env bash
# green.sh <lab>: is the lab converged? BGP up everywhere, host bond has two
# active members with the shared LACP partner, pair state healthy, ping works.
set -u
cd "$(dirname "$0")/.." || exit 1
source scripts/lib.sh
LAB=$1
for n in spine01 spine02; do
  echo "$n: $(vt $LAB $n 'show bgp summary' | awk '/^IPv4 Unicast/,/^Total/' | grep -c FRRouting) ipv4 + $(vt $LAB $n 'show bgp summary' | awk '/^L2VPN EVPN/,/^Total/' | grep -c FRRouting) evpn sessions established (want 3 + 3)"
done
echo "host01 bond: $(hx $LAB host01 'grep -A1 "Slave Interface" /proc/net/bonding/bond0 | grep -c "MII Status: up"') members up, partner $(hx $LAB host01 'grep -m1 "Partner Mac Address" /proc/net/bonding/bond0')"
case $LAB in
  mlag) for n in leaf01 leaf02; do echo "$n: $(sw $LAB $n 'nv show mlag' | grep -E 'peer-alive|backup|role|is-primary|conflict' | tr -s " " | tr "\n" ";")"; done ;;
  evpn-mh) for n in leaf01 leaf02; do echo "$n: $(vt $LAB $n 'show evpn es' | grep -E '^03:' )"; done ;;
esac
echo "leaf03 sees: $(vt $LAB leaf03 'show evpn es' | grep -E '^03:')"
echo "ping host02 -> host01: $(hx $LAB host02 "ping -c 3 -i 0.2 -W 1 $HOST01_IP" | grep -E 'packet loss')"
