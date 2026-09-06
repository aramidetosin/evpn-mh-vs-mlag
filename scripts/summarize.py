#!/usr/bin/env python3
"""summarize.py [results-dir]

Builds the comparison from the probe files directly, reporting four things that
an earlier version collapsed into one misleading word:

  probes that were never answered, split into the failure window and the
  restoration window; replies that arrived very late but were still counted as
  received; and the longest stretch during which the host received nothing.

The previous version printed "no loss" whenever it found no reply gap wider
than half a second. Runs that dropped a probe at the cut, and runs where several
replies turned up 32 seconds late, both came out as clean. Nothing here decides
loss from a gap threshold.
"""
import re, sys, pathlib, collections

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "results")
LABS = ["mlag", "evpn-mh"]
INTERVAL, LATE_MS = 0.1, 1000.0
CUT_W, REC_W = 15.0, 25.0   # seconds after each event that belong to it

DRILLS = [
    ("hostlink-leaf01", "server link cut (leaf01)"),
    ("hostlink-leaf02", "server link cut (leaf02)"),
    ("peerlink-leaf01", "peer link cut, probes on the primary"),
    ("peerlink-leaf02", "peer link cut, probes on the secondary"),
    ("uplinks-leaf01",  "leaf loses both uplinks (leaf01)"),
    ("uplinks-leaf02",  "leaf loses both uplinks (leaf02)"),
    ("leaf-leaf01",     "leaf reboots (leaf01)"),
    ("leaf-leaf02",     "leaf reboots (leaf02)"),
]

Probe = collections.namedtuple(
    "Probe", "sent replies at_cut cut_gap at_rec rec_gap elsewhere late late_max")


def events(run):
    """Injection and recovery epochs from the drill's own timeline. A reboot
    drill has no RESTORE line, because the switch restores itself, so its
    recovery marker is the moment it answered SSH again."""
    inj = rec = None
    tl = run / "timeline.txt"
    if not tl.exists():
        return None, None
    for line in tl.read_text(errors="replace").splitlines():
        p = line.split()
        if len(p) > 1 and p[1] == "INJECT" and inj is None:
            inj = float(p[0])
        if len(p) > 1 and p[1] == "RESTORE" and rec is None:
            rec = float(p[0])
        if rec is None and "ssh back" in line:
            rec = float(p[0])
    return inj, rec


def read(path, inj, res):
    replies, sent_total = [], None
    for line in path.read_text(errors="replace").splitlines():
        m = re.match(r"\[(\d+\.\d+)\].*icmp_seq=(\d+).*time=([\d.]+) ms", line)
        if m:
            replies.append((float(m.group(1)), int(m.group(2)), float(m.group(3))))
        m = re.search(r"(\d+) packets transmitted", line)
        if m:
            sent_total = int(m.group(1))
    if not replies:
        return None
    by_seq = {s: (t, r) for t, s, r in replies}
    hi = max(by_seq)
    first = min(by_seq)
    t0 = by_seq[first][0] - by_seq[first][1] / 1000.0 - (first - 1) * INTERVAL
    # Windows are generous enough to catch a slow convergence but never overlap,
    # so a loss is attributed to the failure or to the recovery, never both.
    in_cut = lambda t: inj is not None and -0.5 <= t - inj <= CUT_W
    in_rec = lambda t: res is not None and -0.5 <= t - res <= REC_W
    at_cut = at_rec = other = 0
    for s in range(1, hi + 1):
        if s in by_seq:
            continue
        t = t0 + (s - 1) * INTERVAL
        if in_cut(t):
            at_cut += 1
        elif in_rec(t):
            at_rec += 1
        else:
            other += 1
    late = [r for r in replies if r[2] >= LATE_MS]
    arrivals = sorted(t for t, _, _ in replies)
    def widest(pred):
        w = 0.0
        for a, b in zip(arrivals, arrivals[1:]):
            if pred(a) or pred(b):
                w = max(w, b - a)
        return w
    return Probe(sent_total or hi, len(replies), at_cut, widest(in_cut),
                 at_rec, widest(in_rec), other,
                 len(late), max((r[2] for r in late), default=0.0))


def load(lab, key):
    run = ROOT / lab / key
    if not (run / "probe_in.txt").exists():
        return None
    inj, res = events(run)
    return {"host02": read(run / "probe_in.txt", inj, res),
            "host01": read(run / "probe_out.txt", inj, res)}


def cell_cut(d):
    if d is None:
        return "not run"
    bits = []
    for who in ("host01", "host02"):
        p = d[who]
        if p is None:
            continue
        bits.append(f"{who} probe: {p.at_cut} lost, {p.cut_gap:.2f} s gap" +
                    (f", {p.late} reply(s) {p.late_max/1000:.0f} s late" if p.late else "") +
                    (f", {p.elsewhere} lost outside either window" if p.elsewhere else ""))
    return "; ".join(bits) if bits else "no data"


def cell_restore(d):
    if d is None:
        return "not run"
    out = []
    for who in ("host01", "host02"):
        p = d[who]
        if p is None:
            continue
        out.append(f"{who} probe: {p.at_rec} lost, {p.rec_gap:.2f} s gap")
    return "; ".join(out) if out else "no data"


def main():
    data = {lab: {k: load(lab, k) for k, _ in DRILLS} for lab in LABS}
    for title, fn in (("At the cut", cell_cut), ("Around the recovery", cell_restore)):
        print(f"\n### {title}\n")
        print("| scenario | MLAG | EVPN multihoming |")
        print("|---|---|---|")
        for key, label in DRILLS:
            row = []
            for lab in LABS:
                d = data[lab][key]
                if d is None and key.startswith("peerlink") and lab == "evpn-mh":
                    row.append("there is no peer link")
                else:
                    row.append(fn(d))
            print(f"| {label} | {row[0]} | {row[1]} |")
    print("\nProbes are named for the host that started them. A ping needs a request "
          "and a reply, so a missing reply may be lost on either leg.")
    print("Max gap is the longest stretch with nothing received, over arrival order.")


if __name__ == "__main__":
    main()
