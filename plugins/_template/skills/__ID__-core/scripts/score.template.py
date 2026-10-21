#!/usr/bin/env python3
"""score.py - the deterministic rubric (STUB). Reads the weights from profile/scoring.md (the
`scoring` fence) and the optimizer's block, scores one candidate 0-100, and says why. Replace the
features with this agent's own; keep it deterministic - no model decides a score.

    score.py --json '{...candidate...}'      -> {"score": N, "why": "...", "knockout": ""}
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import profile_dir  # noqa: E402


def weights():
    w = {"weight.fit": 3.0, "weight.signal": 2.0, "weight.warmth": 2.0, "floor": 60.0}
    p = profile_dir() / "scoring.md"
    if p.is_file():
        txt = p.read_text(encoding="utf-8")
        m = re.search(r"```scoring\n(.*?)\n```", txt, re.S)
        for line in (m.group(1) if m else "").splitlines():
            mm = re.match(r"^\s*([\w.]+)\s*:\s*([\d.]+)", line)
            if mm:
                w[mm.group(1)] = float(mm.group(2))
        for mm in re.finditer(r"^- (weight\.[\w.]+): (up|down)$", txt, re.M):
            base = w.get(mm.group(1), 1.0)
            w[mm.group(1)] = base * (1.25 if mm.group(2) == "up" else 0.8)
    return w


def score(c, w=None):
    w = w or weights()
    fit = 1.0 if c.get("kind") == "__ITEM__" else 0.5
    signal = min(1.0, len(c.get("signals") or []) / 3)
    warmth = 1.0 if c.get("warm") else 0.0
    total = w["weight.fit"] * fit + w["weight.signal"] * signal + w["weight.warmth"] * warmth
    denom = w["weight.fit"] + w["weight.signal"] + w["weight.warmth"]
    s = int(round(100 * total / denom)) if denom else 0
    return {"score": s, "why": f"fit {fit:.1f} · signal {signal:.1f} · warmth {warmth:.1f}",
            "knockout": "" if not c.get("excluded") else "excluded by the profile", "floor": int(w["floor"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    a = ap.parse_args()
    print(json.dumps(score(json.loads(a.json)), ensure_ascii=False))


if __name__ == "__main__":
    main()
