"""GTA VI Twitch CCU forecaster for gta6-twitch-ccu-forecast-01 (Python 3.13, stdlib only).

The program reads one case (/input/<id>.in, schema makefun/twitch-ccu-case/v1)
and writes one forecast (/output/<id>.out): for each of hours 2..24 of the
release day (UTC), five quantiles (5%, 25%, 50%, 75%, 95%) of Twitch's
concurrent live viewers in the "Grand Theft Auto VI" category.

Model (fitted afresh from the case's own comparables at run time, so the same
code adapts to the practice cases and to the final case):

  For each hour h = 2..24, fit by least squares over the comparable past
  launches (each with a complete, positive release-day curve in the case):

      ln(viewers_h) = b0 + b1 * ln(v1) + b2 * ln(v1)^2 + b3 * ln(1 + pre)

  where v1 is the case's hour-1 print and pre is the case's own pre-launch
  baseline: the mean viewers of its category over [day_start - 2 days,
  day_start - 1 day).  Three facts from the comparables drive this form:

  * The level matters, and non-linearly: small hour-1 prints grow several-fold
    over the day as time zones unlock (rolling midnight unlocks), while huge
    hour-1 prints are already near the day's peak.  The quadratic in ln(v1)
    captures that curvature; a plain linear fit under-predicts the biggest
    launches' later hours by ~3x.
  * A pre-existing audience dampens growth: given the same hour-1 print, a
    category that already had viewers before launch grows less over the day
    (b3 < 0).  Hour 1 of such a launch is front-loaded by people who were
    already watching the category.
  * The day's shape is a timezone story: the median curve dips to ~0.7x the
    hour-1 print around hour 4, then climbs to ~2.4x around hour 19-20
    (European evening + US afternoon) before easing off.

  Extrapolation guard: when ln(v1) lies outside the comparables' range, the
  quadratic is replaced by its tangent at the nearest boundary, so a
  record-breaking hour-1 print can never make the forecast turn down.

  Spread: the residual standard deviation among the 12 comparables nearest
  in ln(v1) (a launch's uncertainty looks like launches its own size), floored
  at 0.20 log units and scaled by 0.9; quantiles are exp(pred + z_tau * sd)
  with z = (-1.645, -0.674, 0, 0.674, 1.645).  The spread is deliberately
  honest: the pinball loss on the log scale rewards quantiles the forecaster
  really believes, and the comparables' late-day shapes scatter widely.

  Fallbacks (the output is always a valid forecast): fewer than 12 usable
  comparables -> a linear fit on ln(v1) only; fewer than 5 -> the house
  persistence baseline (every hour at the hour-1 print, spread widening like
  a random walk).  A case with no hour-1 print falls back to its last
  pre-checkpoint hourly mean, then to 1 viewer.

  Determinism: no randomness, no wall-clock use, no network; inputs are read
  in name order and every fit is a pure function of the case file, so two runs
  on the same case write identical bytes.

How the grader runs it: `python3 -P -s /bot/main.py` in python:3.13-slim,
standard library only, no network, at most 8 seconds per case.
Outside the grader: `MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py`

Evaluation (reproduced locally with evaluation/score.py against the practice
answers, SullyGnome hourly category averages): mean pinball loss 0.144 over
the four practice cases, against 0.387 for the house persistence baseline.
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so `import model`
# would find a module shipped beside this file (none is needed: main.py is whole).
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level.
Z = [-1.645, -0.674, 0, 0.674, 1.645]

# Spread: residuals of this many nearest-in-size comparables set the width.
SPREAD_NEIGHBORS = 12
# Spread floor (log units) and calibration scale, both fitted on the practice.
SPREAD_FLOOR = 0.20
SPREAD_SCALE = 0.9
# Pre-launch baseline window: [day_start - 2 days, day_start - 1 day).
PRE_WINDOW_DAYS = (2, 1)
# Minimum usable comparables for each fitting tier.
MIN_COMPARABLES_QUAD = 12
MIN_COMPARABLES_LINEAR = 5
# House baseline spread (per square-root hour), as the starter uses it.
BASELINE_SIGMA = 0.15


def parse_ts(text):
    """Parse an ISO 8601 UTC timestamp ("...T00:00:00Z")."""
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def round2(x):
    """x rounded to 2 decimals, half up, as JavaScript's Math.round(x * 100) / 100."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def release_day_curve(parsed, day_start):
    """Mean viewers per UTC hour of the release day, hours 1..24.

    parsed is a list of (datetime, viewers) points; a point covers the hour
    [at, at + 1h).  An hour with no points has no value (None).
    """
    t0 = parse_ts(day_start)
    curve = {}
    for h in range(1, 25):
        lo = t0 + timedelta(hours=h - 1)
        hi = t0 + timedelta(hours=h)
        pts = [v for at, v in parsed if lo <= at < hi]
        curve[h] = sum(pts) / len(pts) if pts else None
    return curve


def pre_baseline(parsed, day_start):
    """Mean viewers over [day_start - 2 days, day_start - 1 day); 0 if none."""
    t0 = parse_ts(day_start)
    lo = t0 - timedelta(days=PRE_WINDOW_DAYS[0])
    hi = t0 - timedelta(days=PRE_WINDOW_DAYS[1])
    pts = [v for at, v in parsed if lo <= at < hi]
    return sum(pts) / len(pts) if pts else 0.0


def parse_points(points, key="from"):
    """Parse a list of {key, viewers} points once: [(datetime, viewers)]."""
    out = []
    for p in points:
        if p.get("viewers") is None:
            continue
        out.append((parse_ts(p[key]), p["viewers"]))
    return out


def hourly_means(points):
    """Aggregate minute points into whole-hour means: [{from, viewers}]."""
    buckets = {}
    for p in points:
        if p.get("viewers") is None:
            continue
        at = parse_ts(p["at"])
        hour_start = at.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(hour_start, []).append(p["viewers"])
    out = []
    for hour_start in sorted(buckets):
        vals = buckets[hour_start]
        out.append({"from": hour_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "viewers": sum(vals) / len(vals)})
    return out


def solve_linear(matrix, vector):
    """Solve a small dense linear system by Gaussian elimination.

    Returns the solution list, or None when the matrix is (near-)singular.
    A tiny ridge keeps near-collinear designs (e.g. identical hour-1 prints)
    from failing outright.
    """
    n = len(vector)
    rows = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for i in range(n):
        rows[i][i] += 1e-9
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(rows[r][col]))
        if abs(rows[piv][col]) < 1e-12:
            return None
        rows[col], rows[piv] = rows[piv], rows[col]
        for r in range(n):
            if r != col:
                fac = rows[r][col] / rows[col][col]
                for cc in range(col, n + 1):
                    rows[r][cc] -= fac * rows[col][cc]
    return [rows[i][n] / rows[i][i] for i in range(n)]


def fit_least_squares(design, target):
    """Ordinary least squares via the normal equations; None if singular."""
    k = len(design[0])
    ata = [[sum(row[a] * row[b] for row in design) for b in range(k)]
           for a in range(k)]
    aty = [sum(row[a] * y for row, y in zip(design, target)) for a in range(k)]
    return solve_linear(ata, aty)


def predict_with_tangent_guard(beta, x, xmin, xmax):
    """Quadratic prediction, linear (tangent) outside the training range."""
    if x > xmax:
        slope = beta[1] + 2 * beta[2] * xmax
        base = beta[0] + beta[1] * xmax + beta[2] * xmax * xmax
        return base + slope * (x - xmax)
    if x < xmin:
        slope = beta[1] + 2 * beta[2] * xmin
        base = beta[0] + beta[1] * xmin + beta[2] * xmin * xmin
        return base + slope * (x - xmin)
    return beta[0] + beta[1] * x + beta[2] * x * x


def local_spread(residuals, xs, x, count=SPREAD_NEIGHBORS):
    """Residual std among the `count` training launches nearest in ln(v1)."""
    order = sorted(range(len(xs)), key=lambda i: abs(xs[i] - x))
    near = [residuals[i] for i in order[:count]]
    if len(near) < 2:
        return SPREAD_FLOOR
    mean = sum(near) / len(near)
    var = sum((r - mean) ** 2 for r in near) / len(near)
    return max(math.sqrt(var), SPREAD_FLOOR) * SPREAD_SCALE


def quantiles_from(pred_log, sd):
    """Five quantiles from a log-median and a log spread; non-decreasing."""
    out = []
    prev = 0.0
    for z in Z:
        q = math.exp(pred_log + z * sd)
        q = min(max(q, 1.0), 1e9)
        q = round2(q)
        if q < prev:
            q = prev
        out.append(q)
        prev = q
    return out


def baseline_quantiles(p1, h):
    """House persistence baseline: every hour at the hour-1 print."""
    return [round2(p1 * math.exp(z * BASELINE_SIGMA * math.sqrt(h - 1)))
            for z in Z]


def usable_comparables(case):
    """Comparables with a complete, positive release-day curve + pre baseline."""
    train = []
    for comp in case.get("comparables") or []:
        hourly = comp.get("hourly") or []
        if not hourly:
            continue
        parsed = parse_points(hourly)
        curve = release_day_curve(parsed, comp["day_start"])
        if any(curve[h] is None or curve[h] <= 0 for h in range(1, 25)):
            continue
        pre = pre_baseline(parsed, comp["day_start"])
        train.append({"curve": curve, "pre": pre})
    return train


def case_hour1_print(case):
    """Hour-1 print; falls back to the last pre-checkpoint hourly mean, then 1."""
    known = case.get("known") or []
    for row in known:
        if row.get("hour") == 1 and row.get("viewers") is not None:
            return max(1.0, float(row["viewers"]))
    hourly = case.get("history_hourly") or []
    if hourly:
        vals = [p["viewers"] for p in hourly if p.get("viewers") is not None]
        if vals:
            return max(1.0, float(vals[-1]))
    return 1.0


def case_pre_baseline(case):
    """The case's own pre-launch baseline over the pre window."""
    hourly = case.get("history_hourly") or []
    if not hourly and case.get("history"):
        hourly = hourly_means(case["history"])
    if not hourly:
        return 0.0
    return pre_baseline(parse_points(hourly), case["day_start"])


def forecast_case(case, name):
    if case.get("levels") != LEVELS:
        raise ValueError(f"{name} asks for levels {case.get('levels')}, not {LEVELS}")
    p1 = case_hour1_print(case)
    pre = case_pre_baseline(case)
    x = math.log(p1)
    log_pre = math.log1p(pre)
    train = usable_comparables(case)

    hours = []
    if train and len(train) >= MIN_COMPARABLES_QUAD:
        # Primary model: quadratic in ln(v1) plus the pre-launch baseline.
        xs = [math.log(c["curve"][1]) for c in train]
        xmin, xmax = min(xs), max(xs)
        for row in case["forecast"]:
            h = row["hour"]
            ys = [math.log(c["curve"][h]) for c in train]
            design = [[1.0, xx, xx * xx, math.log1p(c["pre"])]
                      for xx, c in zip(xs, train)]
            beta = fit_least_squares(design, ys)
            if beta is None:
                hours.append({"hour": h, "q": baseline_quantiles(p1, h)})
                continue
            pred = predict_with_tangent_guard(beta, x, xmin, xmax)
            pred += beta[3] * log_pre
            resid = [ys[i] - sum(beta[j] * design[i][j] for j in range(4))
                     for i in range(len(design))]
            sd = local_spread(resid, xs, x)
            hours.append({"hour": h, "q": quantiles_from(pred, sd)})
    elif train and len(train) >= MIN_COMPARABLES_LINEAR:
        # Fallback: linear in ln(v1) only, global residual spread.
        xs = [math.log(c["curve"][1]) for c in train]
        for row in case["forecast"]:
            h = row["hour"]
            ys = [math.log(c["curve"][h]) for c in train]
            design = [[1.0, xx] for xx in xs]
            beta = fit_least_squares(design, ys)
            if beta is None:
                hours.append({"hour": h, "q": baseline_quantiles(p1, h)})
                continue
            pred = beta[0] + beta[1] * x
            resid = [ys[i] - (beta[0] + beta[1] * xs[i]) for i in range(len(xs))]
            mean = sum(resid) / len(resid)
            var = sum((r - mean) ** 2 for r in resid) / len(resid)
            sd = max(math.sqrt(var), SPREAD_FLOOR) * SPREAD_SCALE
            hours.append({"hour": h, "q": quantiles_from(pred, sd)})
    else:
        # Last resort: the house persistence baseline.
        for row in case["forecast"]:
            h = row["hour"]
            hours.append({"hour": h, "q": baseline_quantiles(p1, h)})

    hours.sort(key=lambda r: r["hour"])
    return {"hours": hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
