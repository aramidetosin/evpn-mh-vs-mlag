# Shared helpers for the two labs. Source this; do not run it.
#   sw <lab> <node> <cmd>   run a shell command on a Cumulus switch (ssh, cumulus user)
#   vt <lab> <node> <cmd>   run a vtysh command on a switch
#   hx <lab> <node> <cmd>   run a shell command inside a host container
PASS=${CL_PASS:-Clab123!}
labname() { case "$1" in mlag) echo vs-mlag ;; evpn-mh|mh) echo vs-evpnmh ;; *) echo "bad lab $1" >&2; exit 2 ;; esac; }
sw() { sshpass -p "$PASS" ssh -n -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=5 "cumulus@clab-$(labname "$1")-$2" "$3" 2>/dev/null; }
vt() { sw "$1" "$2" "sudo vtysh -c '$3'"; }
hx() { docker exec "clab-$(labname "$1")-$2" sh -c "$3" 2>/dev/null; }
now() { date +%s.%N; }
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
HOST01_IP=172.16.10.11; HOST02_IP=172.16.10.12
