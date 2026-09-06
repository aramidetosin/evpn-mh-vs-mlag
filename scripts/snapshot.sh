#!/usr/bin/env bash
# snapshot.sh <lab> <outdir> [--config]
# Records the state that matters for the comparison, one file per view.
set -u
cd "$(dirname "$0")/.." || exit 1
source scripts/lib.sh
LAB=$1; OUT=$2; CFG=${3:-}
mkdir -p "$OUT"
echo "snapshot $LAB -> $OUT at $(stamp)" > "$OUT/_time.txt"
for n in spine01 spine02 leaf01 leaf02 leaf03; do
  vt $LAB $n 'show bgp summary' > "$OUT/bgp_summary_$n.txt" &
done
for n in leaf01 leaf02; do
  { sw $LAB $n 'nv show interface bond0'; echo; sw $LAB $n 'nv show interface bond0 bond member'; echo; sw $LAB $n 'nv show interface swp1 link'; } > "$OUT/bond0_$n.txt" &
  case $LAB in
    mlag)
      { sw $LAB $n 'nv show mlag'; echo; sw $LAB $n 'sudo clagctl'; echo; sw $LAB $n 'nv show interface peerlink bond member'; echo; sw $LAB $n 'nv show nve vxlan mlag'; } > "$OUT/mlag_$n.txt" & ;;
    evpn-mh)
      { sw $LAB $n 'nv show evpn multihoming'; echo; sw $LAB $n 'nv show evpn multihoming esi'; echo; vt $LAB $n 'show evpn es detail'; echo; vt $LAB $n 'show evpn es-evi'; } > "$OUT/mh_$n.txt" & ;;
  esac
done
{ vt $LAB leaf03 'show evpn vni 10100'; echo; vt $LAB leaf03 'show evpn mac vni 10100'; } > "$OUT/evpn_vni_leaf03.txt" &
{ vt $LAB leaf03 'show bgp l2vpn evpn route type ead'; echo; vt $LAB leaf03 'show bgp l2vpn evpn route type es'; echo; vt $LAB leaf03 'show evpn es'; } > "$OUT/evpn_es_leaf03.txt" &
{ sw $LAB leaf03 'sudo bridge fdb show | grep -i vxlan'; echo; sw $LAB leaf03 'sudo ip nexthop show'; } > "$OUT/fdb_leaf03.txt" &
{ hx $LAB host01 'cat /proc/net/bonding/bond0'; } > "$OUT/bond_host01.txt" &
{ hx $LAB host01 'ip -s -br link show'; echo; hx $LAB host01 'ip -br addr'; } > "$OUT/links_host01.txt" &
if [ "$CFG" = "--config" ]; then
  for n in spine01 spine02 leaf01 leaf02 leaf03; do sw $LAB $n 'nv config show -o commands' > "$OUT/running_$n.txt" & done
  hx $LAB host01 'ip -d link show bond0; ip addr show bond0' > "$OUT/running_host01.txt" &
fi
wait
echo "snapshot done: $OUT"
