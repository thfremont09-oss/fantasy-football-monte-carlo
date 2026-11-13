# Monte Carlo Sports Lab

A website with three simulators that play games out tens of thousands of times
(50,000 NFL weeks, 100,000 brackets, 25,000 FPL gameweeks by default) with
real data and tell you which choice comes out ahead most often:

* **NFL Fantasy Lineups** (`/football`): who to start this week, built for ESPN leagues
  (your league's scoring, lineup slots, roster and opponent; ESPN projections).
* **March Madness** (`/march-madness`): title odds and the best bracket (ESPN data).
* **Fantasy Premier League** (`/fpl`): best XI, bench order and captain for the
  next gameweek (official FPL API). See [Fantasy Premier League](#fantasy-premier-league).

The homepage explains each model in plain English. Each tool keeps its settings
in a panel at the top of its page (there is no sidebar). Pages live in `views/`; the
header, menu and colors are in `app.py` and `ffmc/ui.py`; fonts and base colors
in `.streamlit/config.toml`.

## Run it on a Mac (easiest)

1. Get the code. In Terminal:

   ```bash
   git clone -b claude/affectionate-ptolemy-d4k8cf https://github.com/thfremont09-oss/fantasy-football-monte-carlo.git
   ```

   (or on GitHub: **Code -> Download ZIP**, then unzip it).
2. If you don't have Python 3.10+, install it from
   [python.org](https://www.python.org/downloads/macos/) or with `brew install python`.
3. In Finder, open the folder and **double-click `start.command`**.
   The first run sets everything up (a minute or two), then the app opens in your
   browser at http://localhost:8501. Close the Terminal window to stop it.

   If macOS says it "cannot be opened because it is from an unidentified
   developer", right-click `start.command` -> **Open** -> **Open** (only needed once).

You can also launch it from Terminal inside the folder:

```bash
./start.command
```

## The web app

* **Best possible lineup (any NFL player)**: the top lineup across the whole NFL this week.
* **My ESPN league**: enter your ESPN league ID (the number after `leagueId=` in
  your league's address) and pick your team. It uses your league's exact scoring,
  lineup slots and roster, ESPN's projections, finds this week's opponent, and
  shows your win chance. Private leagues (ESPN's default) also need the `espn_s2`
  and `SWID` cookies from a browser logged in to ESPN; the page explains where to
  find them. They're only used to read your league and are never written to disk.
* **Pick my players**: search and add your players (and optionally your
  opponent's), scored with ESPN PPR, Half-PPR or Standard rules.

Results show who to start, each player's projection, bad-week/great-week range,
how often they were in the best lineup across the simulations, a chart of your
total-points outlook vs. your opponent, and your win probability.
Toggle **Use demo data** to try it without internet.

## Command line

The same engine runs in the terminal (after `start.command` has set up `.venv`):

```bash
source .venv/bin/activate
```

Best possible lineup from every NFL player this week:

```bash
python -m ffmc
```

Start/sit for your Sleeper team (uses your league's scoring and slots, and
maximizes your chance of beating this week's opponent):

```bash
python -m ffmc --league YOUR_SLEEPER_LEAGUE_ID --user YOUR_SLEEPER_USERNAME   # the command line still reads Sleeper leagues
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

See how the simulator would have done in a past week (its pick vs. the actual
best lineup, scored with ESPN's default PPR rules):

```bash
python -m ffmc --backtest --week 9 --scoring espn
```

Useful options (`python -m ffmc --help` for all):

| option | meaning |
| --- | --- |
| `--objective mean\|win\|floor\|ceiling` | maximize expected points, win probability, a safe floor (10th pct) or upside (90th pct). Default: `win` when there's an opponent, otherwise `mean`. |
| `--scoring ppr\|half\|std\|espn` | scoring preset when not using `--league` (`espn` = ESPN default PPR: interceptions -2) |
| `--slots "QB,RB,RB,WR,WR,TE,FLEX,SUPER_FLEX,K,DEF"` | custom lineup slots |
| `--week N --season YYYY` | a different week |
| `--sims N` | number of simulations (default 50,000) |
| `--seed N` | reproducible results |
| `--independent` | turn off teammate/game correlation |
| `--dream` | ignore rosters, use every player |

The UI lives in `app.py` (Streamlit); the engine is in `ffmc/`.

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

## March Madness

`views/march_madness.py` (UI) and `ffmc/madness.py` (model) use the same
Monte Carlo idea as the football side, with data from ESPN's free public
scoreboard (`ffmc/espn.py`):

1. **Team ratings.** Every Division I game this season is fit with least
   squares: `home score - away score = rating_home - rating_away + home edge`.
   A rating of +20 means 20 points better than an average team on a neutral
   court. Early in the season, ratings lean on last season's.
2. **Win chance.** A game's margin swings by about 11 points, so a team rated
   11 points better wins about 84% of the time (the "Upset level" setting).
3. **Simulation.** The 64-team bracket is played out 100,000 times (up to 250,000); each game is
   a weighted coin flip. The tab shows each team's chance of reaching every
   round, title odds, a head-to-head calculator, and the best bracket (each game
   goes to the team that advanced further more often).

Before Selection Sunday the tab shows a projected field (the top 64 teams by
rating). Once ESPN posts the official bracket it switches over automatically.
During the tournament, games already played are locked in. For past seasons it
scores its own bracket with ESPN's points (10/20/40/80/160/320). For 2026 it
picked Michigan as the #2 title favorite and scored about 1000 of 1920 points.

## Fantasy Premier League

`views/fpl.py` (UI) and `ffmc/fpl.py` (model), using the official public FPL API:

1. **Team strength** from this season's results: goals scored and conceded
   compared with the league average, home and away, pulled toward average early
   in the season.
2. **Every fixture is played 25,000 times** (up to 50,000). Each team's goals are drawn from its
   expected goals; each goal and assist goes to a player on the pitch in
   proportion to their xG / xA per 90. Starting chances come from how often each
   player has started and the injury flag.
3. **FPL points** follow from that: appearance, goals (GK 10, DEF 6, MID 5, FWD 4),
   assists, clean sheets, goals conceded, saves, defensive contributions and
   bonus (3/2/1 to the top three in each simulated match).

The page shows the best XI on a pitch, bench order, captain odds (how often each
player topped the XI) and win/draw/loss and clean-sheet odds for every fixture.
For the best XI from every player, pick a budget: **No budget**, **£100.0m** (FPL's
starting budget), **£102.0m**, **£103.5m**, **£105.0m** (typical mid-season team
values) or **Custom**. The budget covers the full 15-player squad: the XI plus the
cheapest legal bench (2 GK, 5 DEF, 5 MID, 3 FWD, max 3 per club).
Enter your FPL team ID to pick from your own squad. FPL only publishes a squad
after a deadline passes, so transfers made since the last deadline aren't seen.
