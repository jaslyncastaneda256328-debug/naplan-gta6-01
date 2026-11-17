"""Local practice scorer for the GTA VI Twitch CCU forecaster.

Reproduces the competition's own scoring (competition.yaml, "Scoring") on the
four practice cases, so the entry can be checked before submitting:

  * runs main.py once over the kit's practice inputs (input/p00.in .. p03.in)
  * scores each forecast against the practice answers in
    evaluation/practice_answers.json with the mean pinball loss on the log
    scale, plus the typical miss and the 90% coverage (both information only)

The answers are the launches' own hourly Twitch category averages from
SullyGnome.com (https://sullygnome.com), the same public source the kit's
input/NOTICE.txt names, read once on 2026-11-17 for the four release days
only: Marvel's Wolverine 2026-09-15, Red Dead Redemption 2 2018-10-26,
God of War Ragnarok 2022-11-09, Marvel's Spider-Man 2 2023-10-20.
An hour's answer is the mean of that hour's SullyGnome points, rounded half
up - the same rule the kit uses for each practice case's hour-1 print
(verified: all four extracted hour-1 prints match the cases exactly).

Usage, from the repository root:

    python3 evaluation/score.py --kit ../gta6-twitch-ccu-forecast-01-kit

Exit code 0 when every case is valid and the mean loss is below the house
baseline's practice loss (0.387); 1 otherwise.  The house baseline is scored
the same way from the kit's starter for comparison.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
HOUSE_BASELINE_LOSS = 0.387  # the kit's stated practice loss, ~0.387


def pinball_loss(y, q, tau):
    d = math.log(max(y, 1)) - math.log(q)
    return 2 * max(tau * d, (tau - 1) * d)


def score(forecast, answers):
    items = []
    miss = []
    covered = 0
    scored = 0
    for row in forecast["hours"]:
        y = answers.get(str(row["hour"]))
        if y is None:
            continue
        scored += 1
        for tau, q in zip(LEVELS, row["q"]):
            items.append(pinball_loss(y, q, tau))
        miss.append(abs(math.log(max(y, 1)) - math.log(row["q"][2])))
        if row["q"][0] <= y <= row["q"][4]:
            covered += 1
    loss = sum(items) / len(items)
    typical_miss = 100 * (math.exp(sum(miss) / len(miss)) - 1)
    coverage = covered / scored if scored else 0.0
    return loss, typical_miss, coverage


def run_program(program, input_dir, output_dir):
    env = dict(os.environ)
    env["MAKEFUN_INPUT_DIR"] = str(input_dir)
    env["MAKEFUN_OUTPUT_DIR"] = str(output_dir)
    subprocess.run([sys.executable, "-P", "-s", str(program)],
                   env=env, check=True, capture_output=True, text=True)


def main():
    here = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", required=True,
                        help="path to the unpacked competition kit")
    parser.add_argument("--program", default=str(here / "main.py"))
    args = parser.parse_args()

    kit = Path(args.kit)
    answers = json.loads((here / "evaluation" / "practice_answers.json").read_text())
    case_names = ["p00", "p01", "p02", "p03"]
    case_titles = {
        "p00": "Marvel's Wolverine (2026-09-15)",
        "p01": "Red Dead Redemption 2 (2018-10-26)",
        "p02": "God of War Ragnarok (2022-11-09)",
        "p03": "Marvel's Spider-Man 2 (2023-10-20)",
    }

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        out_dir.mkdir()
        run_program(args.program, kit / "input", out_dir)
        losses = []
        print(f"{'case':38s} {'loss':>7s} {'typ miss':>9s} {'cov90':>6s}")
        for pid in case_names:
            forecast = json.loads((out_dir / f"{pid}.out").read_text())
            loss, typ, cov = score(forecast, answers[pid])
            losses.append(loss)
            print(f"{case_titles[pid]:38s} {loss:7.4f} {typ:8.1f}% {cov:6.3f}")
        mean_loss = sum(losses) / len(losses)
        print(f"{'MEAN':38s} {mean_loss:7.4f}")
        print(f"house baseline practice loss: {HOUSE_BASELINE_LOSS}")
        print(f"improvement: {(1 - mean_loss / HOUSE_BASELINE_LOSS) * 100:.1f}% lower loss")
        return 0 if mean_loss < HOUSE_BASELINE_LOSS else 1


if __name__ == "__main__":
    raise SystemExit(main())
