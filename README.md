# Fantasy Football Monte Carlo Lineup Optimizer

Finds the best fantasy football lineup for the current NFL week by simulating
the week thousands of times.

It pulls live data from the free [Sleeper API](https://docs.sleeper.com/) (no
API key needed):

* **projections** for every player this week,
* **actual stats from recent weeks** to measure how boom/bust each player is,
* **injury status** (Questionable / Doubtful / Out),
* and, if you play on Sleeper, **your league's scoring, roster slots, your
  roster and this week's opponent**.

## Install

```bash
pip install -r requirements.txt
```

## Usage

Best possible lineup from every NFL player this week:

```bash
python -m ffmc
```

Start/sit for your Sleeper team (uses your league's scoring and slots, and
maximizes your chance of beating this week's opponent):

```bash
python -m ffmc --league YOUR_LEAGUE_ID --user YOUR_SLEEPER_USERNAME
```

Not on Sleeper (ESPN, Yahoo, ...)? List your players by name (defenses by team
abbreviation) and optionally your opponent's:

```bash
python -m ffmc --scoring half --players "Josh Allen, Bijan Robinson, Kyren Williams, Puka Nacua, Nico Collins, Garrett Wilson, Sam LaPorta, Brandon Aubrey, BAL" --opponent "Lamar Jackson, Saquon Barkley, ..."
```

Try it offline with made-up players:

```bash
python -m ffmc --demo
```

Useful options (`python -m ffmc --help` for all):

| option | meaning |
| --- | --- |
| `--objective mean\|win\|floor\|ceiling` | maximize expected points, win probability, a safe floor (10th pct) or upside (90th pct). Default: `win` when there's an opponent, otherwise `mean`. |
| `--scoring ppr\|half\|std` | scoring preset when not using `--league` |
| `--slots "QB,RB,RB,WR,WR,TE,FLEX,SUPER_FLEX,K,DEF"` | custom lineup slots |
| `--week N --season YYYY` | a different week |
| `--sims N` | number of simulations (default 10,000) |
| `--seed N` | reproducible results |
| `--independent` | turn off teammate/game correlation |
| `--dream` | ignore rosters, use every player |

Your league id is the number in the Sleeper web URL:
`sleeper.com/leagues/<LEAGUE_ID>/team`.

## How it works

1. **Expected points.** Each player's mean is 75% this week's Sleeper
   projection and 25% their average over recent games (`ffmc/model.py`).
2. **Volatility.** The standard deviation is the player's observed
   week-to-week spread, shrunk toward a typical value for their position so a
   few games don't dominate.
3. **Simulation** (`ffmc/simulate.py`). Every simulated week draws:
   * a factor per NFL offense (big day / bad day),
   * a factor per game (shootout / slugfest),
   * an individual factor per player.

   A QB and his receivers therefore rise and fall together, and a defense
   does badly when the offense it faces booms. Points follow a right-skewed
   distribution (big games are possible, scores below a small floor aren't).
   Questionable players sit out 20% of simulations, Doubtful 80%, Out always.
4. **Optimization** (`ffmc/lineup.py`). The max-expected-points lineup is
   found exactly; for `win`, `floor`, or `ceiling` it is then improved by
   swapping players and scoring each lineup on the simulated weeks. An
   underdog will often prefer riskier players, a favorite safer ones.
5. **Reporting** (`ffmc/report.py`). Results are re-measured on a fresh set of
   simulations so the numbers aren't flattered by the search. `START` shows how
   often a player was in the best lineup in hindsight; it's a quick read on
   close start/sit calls.

API responses are cached in `.ffmc_cache/` (the player database for a day,
projections for an hour).

## Tests

```bash
pip install pytest
python -m pytest
```

## Limitations

* Projections come from Sleeper only; the simulation is only as good as them.
* Kickers and defenses use Sleeper's pre-computed PPR/half/standard totals
  even in custom-scoring leagues.
* IDP slots aren't supported (they're skipped with a note).
