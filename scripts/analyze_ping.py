#!/usr/bin/env python3
"""analyze_ping.py <ping -D output> [inject_epoch] [restore_epoch]

Reports what a probe run actually did, without letting a display threshold
decide what counts as loss:

  * missing sequences are derived from the sequence numbers themselves, so a
    single dropped probe is reported even though it leaves no visible gap;
  * each missing sequence is placed against the cut and the restore, so loss
    during the failure is never mixed with loss during recovery;
  * replies that arrive very late are reported separately, because a reply that
    turns up 32 seconds after it was sent still counts toward ping's own
    received total and would otherwise look healthy;
  * reply gaps are reported as gaps, not as convergence times.

An earlier version inferred loss from gaps longer than 0.5 s and called
everything else lossless. Runs that dropped one or two probes at the cut were
reported as clean. The thresholds below only affect grouping and labelling,
never whether a loss is counted.
"""
import re, sys

INTERVAL = 0.1          # probe spacing, seconds
LATE_MS = 1000.0        # a reply slower than this is reported separately
NEAR = 3.0              # a loss within this many seconds of an event belongs to it

f = sys.argv[1]
inj = float(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else None
res = float(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else None

replies, sent_total = [], None
for line in open(f, errors="replace"):
    m = re.match(r"\[(\d+\.\d+)\].*icmp_seq=(\d+).*time=([\d.]+) ms", line)
    if m:
        replies.append((float(m.group(1)), int(m.group(2)), float(m.group(3))))
    m = re.search(r"(\d+) packets transmitted", line)
    if m:
        sent_total = int(m.group(1))

if not replies:
    print(f"{f}: no replies at all (sent={sent_total})")
    sys.exit(0)

by_seq = {s: (t, rtt) for t, s, rtt in replies}
highest = max(by_seq)
sent = sent_total or highest
missing = [s for s in range(1, highest + 1) if s not in by_seq]

# Sequence n left about (n - 1) intervals after sequence 1 did.
first_seq = min(by_seq)
t_first = by_seq[first_seq][0] - by_seq[first_seq][1] / 1000.0 - (first_seq - 1) * INTERVAL
sent_at = lambda s: t_first + (s - 1) * INTERVAL

def bucket(s):
    t = sent_at(s)
    if inj is not None and -0.5 <= t - inj <= NEAR:
        return "at the cut"
    if res is not None and -0.5 <= t - res <= NEAR + 12:
        return "at the restore"
    return "elsewhere"

rel = lambda t: (f"{t - inj:+.1f}s vs cut" if inj is not None else f"{t - t_first:.1f}s")

print(f"{f}: sent {sent}, replies {len(replies)}, never answered {len(missing)}")

if missing:
    groups = {}
    for s in missing:
        groups.setdefault(bucket(s), []).append(s)
    for where in ("at the cut", "at the restore", "elsewhere"):
        if where in groups:
            g = groups[where]
            span = f"seq {g[0]}" if len(g) == 1 else f"seq {g[0]} to {g[-1]}"
            print(f"  {len(g)} lost {where} ({span}, first at {rel(sent_at(g[0]))})")
else:
    print("  no sequence went unanswered")

late = sorted([r for r in replies if r[2] >= LATE_MS], key=lambda r: -r[2])
if late:
    seqs = sorted(s for _, s, _ in late)
    print(f"  {len(late)} replies slower than {LATE_MS/1000:.0f} s "
          f"(seq {seqs[0]} to {seqs[-1]}, slowest {late[0][2]:.0f} ms, "
          f"arriving {rel(late[0][0])})")
    print("  ping counted those as received despite the delay")

# A reply gap is how long the host went without receiving anything, so it is
# computed over arrival order. Diffing by sequence number would be meaningless
# here: the very late replies arrive long after higher sequences already did.
arrivals = sorted(t for t, _, _ in replies)
diffs = [(a, b) for a, b in zip(arrivals, arrivals[1:])]
if diffs:
    a, b = max(diffs, key=lambda d: d[1] - d[0])
    width = b - a
    if width > 0.5:
        print(f"  largest reply gap {width:.1f}s, nothing received from {rel(a)} to {rel(b)}"
              + (f" ({b - res:+.1f}s vs restore)" if res else ""))
    else:
        print(f"  largest reply gap {width:.2f}s")
