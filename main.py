#!/usr/bin/env python3
"""GTA VI launch-day Twitch CCU forecaster (make.fun gta6-twitch-ccu-forecast-01).

Reads /input/<id>.in, writes /output/<id>.out: hour-2..24 quantiles of the
Twitch category viewer count, from weighted empirical log-ratio quantiles of
past big launches' release days, weighted by hour-1 scale similarity.
Offline, stdlib only, deterministic.
"""
import json
import math
import os
from datetime import datetime

LEVELS = [0.05, 0.25, 0.50, 0.75, 0.95]
T = 0.65          # scale-similarity temperature
SPREAD = 0.9      # spread multiplier around median
W_FLOOR = 0.05    # keep some diversity even when the target is off-scale

def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

def tier_of(c):
    u = (c.get("unlock") or "").lower()
    if "not a launch" in u or "target-history" in u:
        return "target"
    if "contaminated" in u:
        return "ea"
    if "weak" in u:
        return "weak"
    return "ok"

def day_hourly(c):
    ds = parse(c["day_start"])
    out = {}
    for row in c["hourly"]:
        t = parse(row["from"])
        h = int((t - ds).total_seconds() // 3600)
        if 0 <= h < 24 and row.get("viewers") is not None:
            out.setdefault(h, []).append(row["viewers"])
    return {h: sum(v) / len(v) for h, v in out.items()}

def ratios_for(c, tiers):
    if tier_of(c) not in tiers:
        return None
    dh = day_hourly(c)
    if 1 not in dh or dh[1] <= 0:
        return None
    v1 = dh[1]
    r = {}
    for h in range(2, 25):
        if h in dh and dh[h] > 0:
            r[h] = math.log(dh[h] / v1)
    if len(r) < 10:
        return None
    return {"v1": v1, "logratios": r}

def wquantile(pairs, q):
    pairs = sorted(pairs)
    tot = sum(w for _, w in pairs)
    acc = 0.0
    for x, w in pairs:
        acc += w
        if acc / tot >= q:
            return x
    return pairs[-1][0]

def forecast(v1, others):
    logv1 = math.log(v1)
    sims = [max(math.exp(-abs(math.log(o["v1"]) - logv1) / T), W_FLOOR) for o in others]
    preds = {}
    for h in range(2, 25):
        pairs = []
        for o, s in zip(others, sims):
            lr = o["logratios"].get(h)
            if lr is not None:
                pairs.append((lr, s))
        if not pairs:
            preds[h] = preds.get(h - 1, [v1] * 5)
            continue
        qs = [wquantile(pairs, q) for q in LEVELS]
        med = qs[2]
        qs = [med + (x - med) * SPREAD for x in qs]
        for i in range(1, 5):
            if qs[i] < qs[i - 1]:
                qs[i] = qs[i - 1]
        preds[h] = [v1 * math.exp(x) for x in qs]
    return preds

def main():
    case = None
    for name in sorted(os.listdir("/input")):
        if name.endswith(".in"):
            with open(os.path.join("/input", name), encoding="utf-8") as f:
                case = json.load(f)
    if case is None:
        raise SystemExit("no case in /input")
    v1 = float(case["known"][0]["viewers"])
    if v1 <= 0:
        v1 = 1.0
    others = []
    for c in case.get("comparables", []):
        r = ratios_for(c, ("ok", "ea"))
        if r:
            others.append(r)
    preds = forecast(v1, others)
    hours = []
    for row in case["forecast"]:
        h = row["hour"]
        q = preds.get(h, [v1] * 5)
        q = [min(max(float(x), 0.01), 1e9) for x in q]
        for i in range(1, 5):
            if q[i] < q[i - 1]:
                q[i] = q[i - 1]
        hours.append({"hour": h, "q": q})
    os.makedirs("/output", exist_ok=True)
    out_path = os.path.join("/output", case["id"] + ".out")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"hours": hours}, f)

if __name__ == "__main__":
    main()
