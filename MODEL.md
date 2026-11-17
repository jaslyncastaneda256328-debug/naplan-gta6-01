# Model

## The problem, in one paragraph

GTA VI releases 2026-11-19 on PS5 and Xbox Series X|S, single-player, no PC
until 2027, and no console maker publishes a player count — so the count this
contest forecasts is Twitch's own concurrent viewers in the "Grand Theft Auto
VI" category. The program sees everything up to the end of hour 1 (00:00–
01:00 UTC) and must forecast hours 2–24 as five quantiles each, scored by
mean pinball loss on the log scale. The unlock rolls at local midnight,
country by country: New Zealand first (11:00Z on 18 Nov), central Europe
23:00Z, the UK 00:00Z, US Eastern 05:00Z, US Pacific 08:00Z. So hour 1 is
mostly Europe + Oceania + Asia; the Americas arrive during hours 5–9; the
peak lands in the European evening / US afternoon. Any forecaster that just
says "hour 1, all day" (the house baseline) misses that whole shape.

## What the data says

The kit ships 38–42 past big launches with hourly Twitch category averages
(SullyGnome), each covering 14 days before to 3 days after its release day.
Across the 41 launches with complete release-day curves:

- The median curve dips to 0.72x the hour-1 print around hour 4, then climbs
  to 2.4x around hour 19–20, then eases off. The shape is the timezone story
  above, and it is stable across launches.
- The level is everything, and it is non-linear: the correlation between
  ln(hour-1 print) and the log-ratio at hour 20 is −0.94. Launches with a
  small hour-1 print (a few thousand) grow 5–10x over the day; launches with
  a huge hour-1 print (~850k, e.g. ELDEN RING, Cyberpunk 2077 — both with a
  PC unlock just before the UTC day) stay flat or decline. A linear fit in
  ln(v1) under-predicts the biggest launches' late hours by ~3x.
- The cross-launch scatter is wide late in the day (std of the log-ratio
  ~2.0 at hours 15–24 in the raw ratios), so the quantiles must be wide —
  but most of that scatter is the level effect above, not noise: once the
  level is conditioned on, the residual std is ~0.7–1.0.
- Hour-1 channels add nothing once viewers are known (tested: no gain).
  Early-access-contaminated and "weak" tier launches are still informative;
  excluding them made the score worse, so nothing is excluded.

## The model

For each hour h = 2..24, least squares over the case's comparables with a
complete, positive release-day curve:

```
ln(viewers_h) = b0 + b1 * ln(v1) + b2 * ln(v1)^2 + b3 * ln(1 + pre)
```

- `v1`: the case's hour-1 print (floor 1).
- `pre`: the case's own pre-launch baseline — mean viewers of its category
  over [day_start − 2 days, day_start − 1 day), from `history_hourly`
  (falling back to `history` minute points aggregated to hours, then to 0).
  The fitted b3 is negative (~−0.07): given the same hour-1 print, a
  category that already had viewers before launch grows less — its hour 1
  was front-loaded by people already watching the category.
- The window [−2d, −1d) is deliberate: the final case's history only starts
  2026-11-17, so a 7-day window would be mostly unobservable at final time;
  the 2-day window exists in both practice and final cases, and it scored
  best of the windows tried (7-day 0.1540, 3-day 0.1527, 2-day 0.1496,
  1-day 0.1938 on the practice, before spread calibration).
- Extrapolation guard: outside the comparables' ln(v1) range, the quadratic
  is replaced by its tangent at the nearest boundary. GTA VI's hour-1 print
  may exceed every comparable's (max ~875k); the guard keeps the forecast
  monotone increasing in v1 instead of letting the parabola turn down.
- Spread: the residual std among the 12 comparables nearest in ln(v1),
  floored at 0.20 log units, scaled by 0.9. A launch's uncertainty looks like
  launches its own size. Quantiles are `exp(pred + z_tau * sd)` with
  z = (−1.645, −0.674, 0, 0.674, 1.645), clamped to [1, 1e9].
- Fallbacks, in order: fewer than 12 usable comparables → a linear fit on
  ln(v1) only; fewer than 5 → the house persistence baseline. The output is
  always a valid forecast.

Nothing is hard-coded from the practice answers: every coefficient is fitted
from the case file at run time. The final case's comparables (42, including
the four practice launches) are used the same way.

## How the pieces were chosen (all on the practice, then confirmed)

Each candidate was scored with the competition's own loss on the four
practice cases (answers: SullyGnome hourly averages, verified by reproducing
all four hour-1 prints exactly), plus a leave-one-out run over all 41
complete launches:

| model | practice mean loss | LOO mean loss (41 launches) |
| --- | --- | --- |
| house persistence baseline | 0.3871 | — |
| median shape (no level) | 0.3956 | — |
| linear in ln(v1) | 0.2390 | 0.4175 |
| quadratic in ln(v1) | 0.2234 | 0.3814 |
| quadratic + pre baseline, local spread (k=12) | 0.1496 | 0.3602 |
| **final: quadratic + pre, local spread, scale 0.9** | **0.1444** | — |

Decisions the numbers forced: the quadratic over the linear fit (the big
launches' late hours); the pre-launch baseline (consistent gains on all four
practice cases, 0.191 → 0.150); the local spread over a global one (LOO
0.361 vs 0.384, practice about tied); keeping every tier of comparable
(excluding weak/early-access made LOO worse); no channels feature (no gain);
no blending with the median shape (worse on practice).

## Practice results (the entry as submitted)

| case | hour-1 print | loss | typical miss | 90% coverage |
| --- | --- | --- | --- | --- |
| Marvel's Wolverine | 23,357 | 0.1311 | 19.6% | 1.000 |
| Red Dead Redemption 2 | 116,550 | 0.1430 | 26.8% | 1.000 |
| God of War Ragnarök | 269,517 | 0.1241 | 21.2% | 1.000 |
| Marvel's Spider-Man 2 | 119,087 | 0.1793 | 31.0% | 0.783 |
| **mean** | | **0.1444** | | |
| house baseline | | 0.3871 | 82.8% | 0.783 |

Reproduce with `python3 evaluation/score.py --kit <kit dir>`.

## What could still go wrong on the final

- **One launch, not four.** The practice mean is an average over four
  launches; the final is a single draw. GTA VI is the biggest launch in the
  set by a wide margin, so the forecast leans on the tangent guard and on
  the biggest comparables (ELDEN RING, Cyberpunk 2077, Hogwarts Legacy).
  If GTA VI's hour-1 print is far above the training range, the forecast is
  an extrapolation, and the spread — set by the nearest big launches — is
  the honest admission of that.
- **The pre-launch baseline is a proxy.** It is fitted on sequels and
  franchise games whose categories already existed; GTA VI's category has
  been unusually active since its August premiere (1,240 viewers and 181
  channels on 2026-11-17). The fitted effect is small (b3 ≈ −0.07) and GTA
  VI's pre value sits near the comparables' median, so the adjustment is
  modest either way.
- **The house model forecast is unknown.** A prize needs a loss strictly
  below the best house entry on the final — the persistence baseline and a
  one-shot model forecast. The practice beats the baseline by 63%; the
  model forecast is a different, unknown bar.
- **Practice ≠ final.** The practice answers are SullyGnome hourly averages;
  the final's prints are means of 60 minute reads. Both estimate the same
  underlying hourly mean, but the measures differ slightly.

## Assumptions, stated plainly

1. The launch-day shape of past big console launches transfers to GTA VI
   once the hour-1 level and the pre-launch baseline are conditioned on.
2. The hour-1 print is the single most informative number the program gets;
   the top streams and the category ranking at the checkpoint carry no
   additional signal worth modelling (they are a snapshot, not a curve).
3. Twitch's category count moves with the launch the way a player count
   would — the contest's own premise, not something this entry re-litigates.
4. SullyGnome's hourly averages are an adequate stand-in for the final's
   minute-mean prints when fitting and evaluating.
