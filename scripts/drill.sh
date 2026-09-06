#!/usr/bin/env bash
# drill.sh <lab> <test> [target-leaf]
#   lab    mlag | evpn-mh
#   test   hostlink | peerlink | leaf | uplinks
#   target leaf01 | leaf02  (for peerlink: the leaf the probe flows are placed on)
# Two 10 pps ping probes run for the whole drill: host02 -> host01 (inbound)
# and host01 -> host02 (outbound). Because the kernel hashes ICMP flows on
# the echo id, every ping process lands on its own leg; the drill restarts
# the probes until BOTH flows ride the target leaf, so each result is the
# worst case: the flow was on the switch that fails. Failure at +10 s,
# mid-failure snapshot at +20 s, restore at +40 s (a rebooted leaf restores
# itself), then loss and outage windows from the ping timestamps.
set -u
cd "$(dirname "$0")/.." || exit 1
source scripts/lib.sh
LAB=$1; TEST=$2; T=${3:-leaf01}
case $T in leaf01) HETH=eth1; N=1 ;; leaf02) HETH=eth2; N=2 ;; esac
RUN=results/$LAB/$TEST-$T
DUR=60; INJECT=10; DURING=20; RESTORE=40
if [ "$TEST" = leaf ]; then DUR=360; DURING=40; RESTORE=0; fi
rm -rf "$RUN"; mkdir -p "$RUN"
TL="$RUN/timeline.txt"
log() { echo "$(now) $*" | tee -a "$TL"; }
H1="clab-$(labname $LAB)-host01"; H2="clab-$(labname $LAB)-host02"

# wait_healthy <seconds>: the drill only means anything if it starts from a
# whole lab, so block until host01's bond has both members aggregating and
# both leaves hold swp1 up. An earlier drill that was interrupted before its
# restore leaves one leg down, and every flow then piles onto the surviving
# leaf, which silently turns the next drill into a measurement of nothing.
# The waits must outlast the MLAG init-delay (180 s by default), which holds
# the secondary's bonds down after a peer link comes back.
wait_healthy() {
  local deadline=$(( $(date +%s) + ${1:-120} )) members l1 l2
  while [ "$(date +%s)" -lt "$deadline" ]; do
    members=$(hx $LAB host01 'grep -A1 "Slave Interface" /proc/net/bonding/bond0 | grep -c "MII Status: up"')
    l1=$(sw $LAB leaf01 "cat /sys/class/net/swp1/operstate"); l2=$(sw $LAB leaf02 "cat /sys/class/net/swp1/operstate")
    [ "${members:-0}" = 2 ] && [ "$l1" = up ] && [ "$l2" = up ] && { echo "healthy: bond 2/2, leaf01 swp1 $l1, leaf02 swp1 $l2"; return 0; }
    sleep 5
  done
  echo "NOT HEALTHY after ${1:-120}s: bond members=${members:-?}, leaf01 swp1=${l1:-?}, leaf02 swp1=${l2:-?}"
  return 1
}

inject() {
  case $TEST in
    hostlink) sw $LAB $T "sudo ip link set swp1 down"; hx $LAB host01 "ip link set $HETH down" ;;
    peerlink) for l in leaf01 leaf02; do sw $LAB $l "sudo ip link set swp4 down; sudo ip link set swp5 down"; done ;;
    leaf)     sw $LAB $T "sudo reboot" ;;
    uplinks)  sw $LAB $T "sudo ip link set swp2 down; sudo ip link set swp3 down"
              sw $LAB spine01 "sudo ip link set swp$N down"; sw $LAB spine02 "sudo ip link set swp$N down" ;;
  esac
}
restore() {
  case $TEST in
    hostlink) sw $LAB $T "sudo ip link set swp1 up"; hx $LAB host01 "ip link set $HETH up" ;;
    peerlink) for l in leaf01 leaf02; do sw $LAB $l "sudo ip link set swp4 up; sudo ip link set swp5 up"; done ;;
    leaf)     : ;;
    uplinks)  sw $LAB $T "sudo ip link set swp2 up; sudo ip link set swp3 up"
              sw $LAB spine01 "sudo ip link set swp$N up"; sw $LAB spine02 "sudo ip link set swp$N up" ;;
  esac
}
# Inbound leg is a deterministic hash of the inner IP pair, so the address
# picks it. Outbound leg is hashed from the ping's ICMP echo id, which is the
# process id, so every restart is a fresh draw. Sixteen addresses and enough
# attempts make the two line up on the leaf under test.
ADDRS=($(seq 12 27 | sed "s/^/172.16.10./"))
SRCS=($(seq 31 35 | sed "s/^/172.16.10./"))
start_probes() {  # $1 = host02 address for both probes, $2 = host01 source for the outbound one
  docker exec $H2 pkill ping 2>/dev/null; docker exec $H1 pkill ping 2>/dev/null; sleep 0.5
  docker exec $H2 sh -c "ping -D -i 0.1 -W 1 -c $((DUR*10)) -I $1 $HOST01_IP > /tmp/probe_in.txt 2>&1" &
  docker exec $H1 sh -c "ping -D -i 0.1 -W 1 -c $((DUR*10)) -I $2 $1 > /tmp/probe_out.txt 2>&1" &
  T0=$(now)
}
# sample 2 s: inbound = which leaf's bond0 transmits the requests toward host01,
# outbound = which host NIC carries the echo requests to host02
sample() {
  a1=$(sw $LAB leaf01 "cat /sys/class/net/bond0/statistics/tx_packets"); a2=$(sw $LAB leaf02 "cat /sys/class/net/bond0/statistics/tx_packets")
  # Match the source the outbound probe is actually using this attempt, not
  # host01's primary address, or the filter sees none of the probe's packets.
  docker exec $H1 sh -c "timeout 2 tcpdump -nni eth1 -l 'icmp[icmptype]=8 and src $S' 2>/dev/null | wc -l" > /tmp/o1.$$ &
  j1=$!
  docker exec $H1 sh -c "timeout 2 tcpdump -nni eth2 -l 'icmp[icmptype]=8 and src $S' 2>/dev/null | wc -l" > /tmp/o2.$$ &
  j2=$!
  wait $j1 $j2 2>/dev/null; sleep 0.2
  b1=$(sw $LAB leaf01 "cat /sys/class/net/bond0/statistics/tx_packets"); b2=$(sw $LAB leaf02 "cat /sys/class/net/bond0/statistics/tx_packets")
  o1=$(cat /tmp/o1.$$); o2=$(cat /tmp/o2.$$); rm -f /tmp/o1.$$ /tmp/o2.$$
  i1=$((b1-a1)); i2=$((b2-a2)); o1=${o1:-0}; o2=${o2:-0}
  # Demand a clear winner (3x the other leg). A tcpdump that returned nothing,
  # or a near-tie, is an unreadable sample, not a placement: calling it either
  # way would let the drill fire at a leaf the traffic is not actually using.
  IN=unclear;   [ $i1 -gt $((i2*3)) ] && IN=leaf01;   [ $i2 -gt $((i1*3)) ] && IN=leaf02
  OUTL=unclear; [ $o1 -gt $((o2*3)) ] && OUTL=leaf01; [ $o2 -gt $((o1*3)) ] && OUTL=leaf02
  echo "host02 address $A, host01 source $S | inbound requests: leaf01 bond0 tx +$i1, leaf02 bond0 tx +$i2 -> $IN | outbound requests from host01: eth1 $o1, eth2 $o2 -> $OUTL"
}

echo "=== $LAB / $TEST / $T  (probe ${DUR}s, cut at +${INJECT}s, restore at +${RESTORE}s)" | tee "$RUN/summary.txt"
HEALTH=$(wait_healthy 300); echo "$HEALTH" | tee -a "$RUN/summary.txt"
case $HEALTH in "NOT HEALTHY"*) echo "ABORTED: lab was not whole at the start of this drill" | tee -a "$RUN/summary.txt"; exit 1 ;; esac
scripts/snapshot.sh $LAB "$RUN/before" >/dev/null
PLACED=no
# 16 destinations and 5 sources step at different rates, so each attempt is a
# distinct pair rather than a repeat of the same losing draw.
for attempt in $(seq 1 40); do
  A=${ADDRS[$(( (attempt-1) % 16 ))]}; S=${SRCS[$(( (attempt-1) % 5 ))]}
  start_probes $A $S; sleep 3
  sample > "$RUN/placement.tmp"; P=$(cat "$RUN/placement.tmp"); rm -f "$RUN/placement.tmp"; echo "attempt $attempt: $P"
  if [ "$IN" = "$T" ] && [ "$OUTL" = "$T" ]; then PLACED=yes; break; fi
done
# Inbound is a deterministic hash of the inner IP pair, outbound is a hash of
# the ping's echo id, so a fresh pair of probes is a fresh draw. If 40 draws
# never put both flows on the leaf under test, say so loudly: the numbers below
# then describe a flow that survived on the other leaf, not a worst case.
{ echo "$P"; echo "placement on $T achieved: $PLACED (attempt $attempt of 40)"; } | tee "$RUN/placement.txt"
[ "$PLACED" = no ] && echo "WARNING: flows were NOT both on $T; this run is not the worst case" | tee -a "$RUN/summary.txt"
log "probes started (placed=$PLACED, accepted attempt $attempt, T0=$T0)"
SL=$(python3 -c "import time;print(max(0,$T0+$INJECT-time.time()))"); sleep $SL
log "INJECT $TEST on $T"; TI=$(now); inject; log "injected"
sleep $((DURING-INJECT))
scripts/snapshot.sh $LAB "$RUN/during" >/dev/null; log "mid-failure snapshot taken"
if [ "$TEST" = leaf ]; then
  for i in $(seq 1 60); do sw $LAB $T true && break; sleep 5; done; log "$T ssh back"
  TR=$(now)
  for i in $(seq 1 60); do
    st=$(sw $LAB $T "cat /sys/class/net/bond0/operstate" 2>/dev/null); [ "$st" = up ] && break; sleep 5
  done; log "$T bond0 operstate=$st"
else
  sleep $((RESTORE-DURING)); log "RESTORE"; TR=$(now); restore; log "restored"
fi
wait
log "probes finished"
docker cp "$H2:/tmp/probe_in.txt" "$RUN/probe_in.txt"
docker cp "$H1:/tmp/probe_out.txt" "$RUN/probe_out.txt"
scripts/snapshot.sh $LAB "$RUN/after" >/dev/null
{
  echo "flows: $P"
  echo "worst case (both flows on $T): $PLACED"
  echo "--- inbound  host02 -> host01"; python3 scripts/analyze_ping.py "$RUN/probe_in.txt" "$TI" "$TR"
  echo "--- outbound host01 -> host02"; python3 scripts/analyze_ping.py "$RUN/probe_out.txt" "$TI" "$TR"
} | tee -a "$RUN/summary.txt"
# Leave the lab whole for whatever runs next. A bond that has not finished
# re-aggregating is the exact condition that invalidated the earlier run.
log "waiting for the lab to come back: $(wait_healthy 300)"
