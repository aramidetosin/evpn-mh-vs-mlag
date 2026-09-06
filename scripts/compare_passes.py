#!/usr/bin/env python3
"""compare_passes.py <results-dir> [<results-dir> ...]

Combines independent passes of the same matrix into the ranges that get
published, so no figure depends on someone picking a representative run by eye.

For each scenario and design it reports, across every pass and both probes of
each run: probes never answered in the failure window, the longest stretch with
nothing arriving, and replies that came back later than a second. A value that
is identical everywhere prints once; anything else prints as a range, and a row
whose passes disagree about whether there was loss at all is called out, because
that is a different claim from a wide range.
"""
import sys, pathlib, importlib.util

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("summarize", HERE / "summarize.py")
S = importlib.util.module_from_spec(spec)
sys.modules["summarize"] = S
spec.loader.exec_module(S)

DIRS = [pathlib.Path(d) for d in sys.argv[1:]] or [pathlib.Path("results")]


def span(values, fmt="{:g}"):
    vals = sorted(set(values))
    if not vals:
        return "no data"
    if len(vals) == 1:
        return fmt.format(vals[0])
    return f"{fmt.format(vals[0])} to {fmt.format(vals[-1])}"


def collect(lab, key):
    """Every probe of every pass for one scenario, as (lost, gap, late) tuples."""
    out = []
    for root in DIRS:
        S.ROOT = root
        d = S.load(lab, key)
        if not d:
            continue
        for who in ("host01", "host02"):
            p = d.get(who)
            if p:
                out.append((p.at_cut, p.cut_gap, p.late))
    return out


def main():
    print(f"Passes compared: {', '.join(str(d) for d in DIRS)}\n")
    print("| scenario | design | probes lost at the cut | longest gap | late replies | agrees? |")
    print("|---|---|---|---|---|---|")
    for key, label in S.DRILLS:
        for lab in S.LABS:
            rows = collect(lab, key)
            if not rows:
                if key.startswith("peerlink") and lab == "evpn-mh":
                    print(f"| {label} | {lab} | there is no peer link | | | |")
                continue
            lost = [r[0] for r in rows]
            gaps = [r[1] for r in rows]
            late = [r[2] for r in rows]
            # A row where some probes lost nothing and others lost a lot is not a
            # range, it is a contradiction, and gets said so out loud. A spread of
            # a probe or two either side of zero is measurement noise, not that.
            MATERIAL = 5
            agrees = "no, passes conflict" if min(lost) == 0 and max(lost) >= MATERIAL else "yes"
            print(f"| {label} | {lab} | {span(lost)} | {span(gaps, '{:.2f} s')} | "
                  f"{span(late)} | {agrees} |")
    print(f"\n{len(DIRS)} pass(es), two probes per run. Ranges span every probe of every pass.")


if __name__ == "__main__":
    main()
