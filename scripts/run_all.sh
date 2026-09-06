#!/usr/bin/env bash
# run_all.sh [lab ...]: baseline snapshots (with running configs), then every
# drill on both labs, flows placed on the failing leaf. Logs to results/run_all.log.
set -u
cd "$(dirname "$0")/.." || exit 1
LABS=${*:-"mlag evpn-mh"}
{
for LAB in $LABS; do
  echo "##### $LAB baseline $(date -u +%FT%TZ)"
  scripts/post-deploy.sh $LAB
  scripts/green.sh $LAB
  scripts/snapshot.sh $LAB results/$LAB/baseline --config
  for T in leaf01 leaf02; do scripts/drill.sh $LAB hostlink $T; scripts/green.sh $LAB; done
  if [ $LAB = mlag ]; then for T in leaf01 leaf02; do scripts/drill.sh $LAB peerlink $T; scripts/green.sh $LAB; done; fi
  for T in leaf01 leaf02; do scripts/drill.sh $LAB uplinks $T; scripts/green.sh $LAB; done
  for T in leaf01 leaf02; do scripts/drill.sh $LAB leaf $T; scripts/green.sh $LAB; done
done
echo "##### all done $(date -u +%FT%TZ)"
} 2>&1 | tee -a results/run_all.log
