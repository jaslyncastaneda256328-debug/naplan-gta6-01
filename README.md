# GTA VI Twitch CCU forecaster

Entry for [gta6-twitch-ccu-forecast-01](https://make.fun/c/gta6-twitch-ccu-forecast-01)
on make.fun: forecast, hour by hour, how many people watch Grand Theft Auto VI
live on Twitch over the 24 UTC hours of its release day, 2026-11-19, from
everything recorded up to the end of its first hour — as five quantiles an
hour (5%, 25%, 50%, 75%, 95%).

## The program

`main.py` (Python 3.13, standard library only) reads one case
(`/input/<id>.in`) and writes one forecast (`/output/<id>.out`). It fits its
model afresh from the case's own comparables at run time — 38 past big
launches in a practice case, 42 in the final — so the same code adapts to
practice and final without any hard-coded numbers:

```
ln(viewers_h) = b0 + b1 * ln(v1) + b2 * ln(v1)^2 + b3 * ln(1 + pre)
```

- `v1` is the case's hour-1 print. The level matters, and non-linearly:
  small hour-1 prints grow several-fold over the day as time zones unlock,
  while huge hour-1 prints are already near the day's peak.
- `pre` is the category's pre-launch baseline (mean viewers over
  [day_start − 2 days, day_start − 1 day)). Given the same hour-1 print, a
  category that already had viewers before launch grows less over the day.
- The spread comes from the residuals of the 12 comparables nearest in size;
  quantiles are `exp(pred + z * sd)`. A tangent guard keeps a record-breaking
  hour-1 print from ever making the forecast turn down.

See [MODEL.md](MODEL.md) for the full reasoning, the evidence for each
choice, and the evaluation. See [dashboard.html](dashboard.html) for the
practice results and an illustrative scenario forecast.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

The grader runs `python3 -P -s /bot/main.py`, one case at a time, no network,
at most 8 seconds a case. Locally the four practice cases take ~1.2 s total
and are byte-identical across runs.

## Check the score locally

```sh
python3 evaluation/score.py --kit <path to the unpacked kit>
```

It runs `main.py` over the practice inputs and scores the forecasts against
the practice answers (`evaluation/practice_answers.json`, SullyGnome hourly
category averages, the same public source the kit's `input/NOTICE.txt`
names) with the competition's own pinball loss on the log scale.

| case | loss | typical miss | 90% coverage |
| --- | --- | --- | --- |
| Marvel's Wolverine | 0.1311 | 19.6% | 1.000 |
| Red Dead Redemption 2 | 0.1430 | 26.8% | 1.000 |
| God of War Ragnarök | 0.1241 | 21.2% | 1.000 |
| Marvel's Spider-Man 2 | 0.1793 | 31.0% | 0.783 |
| **mean** | **0.1444** | | |
| house persistence baseline | 0.3871 | 82.8% | 0.783 |

Mean practice loss **0.1444 vs 0.3871 for the house baseline — 63% lower**.
A prize also needs beating the house model forecast on the final; the
practice says nothing about that, and the final is one launch, so the margin
above is a lead, not a guarantee.

## Layout

- `main.py` — the entry (the only file the grader runs)
- `MODEL.md` — model documentation and evaluation
- `dashboard.html` — practice results, chart, and an illustrative scenario
- `evaluation/score.py` — the local practice scorer
- `evaluation/practice_answers.json` — the four practice answers (SullyGnome)
- `LICENSE` — MIT
