"""Home page: what the simulators do, in plain English, with the core code."""

from __future__ import annotations

import inspect

import streamlit as st

from ffmc import fpl, madness, parlay, simulate
from ffmc.ui import APP_VERSION, NAVY, SPORTS, card_top

FOOTBALL, MADNESS, FPL = "views/football.py", "views/march_madness.py", "views/fpl.py"
PARLAYS, NICHE, LIVE = "views/parlays.py", "views/niche.py", "views/live.py"


def eyebrow(text: str) -> None:
    st.markdown(f'<p class="eyebrow">{text}</p>', unsafe_allow_html=True)


def real_code(*fns) -> None:
    with st.expander("See the actual code"):
        for fn in fns:
            st.code(inspect.getsource(fn).rstrip(), language="python")


# --------------------------------------------------------------------- hero
stripes = "".join(f'<span style="background:{s["color"]}"></span>' for s in SPORTS.values())
st.markdown(f"""
<style>
.hero {{ background: repeating-linear-gradient(90deg, rgba(255,255,255,.04) 0 1px, transparent 1px 80px),
  linear-gradient(135deg, {NAVY} 0%, #17324f 100%); border-radius: 12px; padding: 2.4rem 2rem 2rem; color: #fff;
  margin-bottom: 1.6rem; }}
.hero .eyebrow {{ color: #f2b134; }}
.hero h1 {{ color: #fff; font-size: clamp(2.2rem, 6vw, 3.6rem); line-height: 1; margin: .3rem 0 .9rem; padding: 0;
  text-transform: uppercase; font-weight: 700; max-width: 16ch; }}
.hero p {{ color: #c9d3df; font-size: 1.1rem; line-height: 1.6; max-width: 60ch; margin: 0; }}
.hero .bar {{ display: flex; gap: 6px; margin-top: 1.4rem; }}
.hero .bar span {{ height: 6px; width: 64px; border-radius: 3px; }}
.hero .facts {{ display: flex; gap: 2.2rem; flex-wrap: wrap; margin-top: 1.4rem; }}
.hero .facts b {{ display: block; font-family: "Barlow Condensed", sans-serif; font-size: 1.9rem; color: #fff; line-height: 1; }}
.hero .facts small {{ color: #9fb0c3; text-transform: uppercase; letter-spacing: .1em; font-size: .7rem; font-weight: 600; }}
</style>
<div class="hero">
  <p class="eyebrow">Simulation-based sports analytics</p>
  <h1>Every game, played 1,000,000 times.</h1>
  <p>Projections give you one number. These tools play the week, the gameweek or the whole tournament
  out a million times with real data, then tell you which choice comes out ahead most often.</p>
  <div class="facts">
    <div><b>6</b><small>Tools</small></div>
    <div><b>80,000+</b><small>Markets scanned</small></div>
    <div><b>1,000,000</b><small>Simulations per run</small></div>
    <div><b>Live</b><small>Data, refreshed hourly</small></div>
  </div>
  <div class="bar">{stripes}</div>
</div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------- tools
cards = [
    ("live", "Every league · Right now", "Live Odds", LIVE, "Open Live Odds",
     "Scores for the top leagues worldwide with DraftKings and Kalshi odds side by side, live win chances, "
     "search, and a page for every game with stats and a live odds chart, updated every 15 seconds."),
    ("nfl", "NFL · Every week", "Fantasy Football Lineups", FOOTBALL, "Open lineup optimizer",
     "Who to start this week. Connect your ESPN league or enter your roster, and see "
     "your chance of beating this week's opponent."),
    ("ncaa", "NCAA · March", "March Madness Bracket", MADNESS, "Open bracket simulator",
     "Title odds for every team and a complete bracket to fill out. Shows a projected field until "
     "Selection Sunday, then the real bracket."),
    ("epl", "Premier League · Every gameweek", "Fantasy Premier League", FPL, "Open FPL team picker",
     "Your best XI, bench order and captain, on any budget from £100m up or none at all. Or enter your "
     "FPL team ID."),
    ("bets", "DraftKings + Kalshi · Every day", "Parlay Lab", PARLAYS, "Open Parlay Lab",
     "The best parlays for your risk and payout, from 80,000+ DraftKings and Kalshi markets, niche sports "
     "included, each tested on a million simulated slates."),
    ("niche", "Off the beaten path · Every day", "Niche Sports", NICHE, "Open Niche Sports",
     "Russian table tennis, Bosnian basketball, Valorant, women's cricket: every obscure market on the board, "
     "ranked by a Niche-o-meter, with the best bets for your risk and payout."),
]
for row in (cards[:3], cards[3:]):
    for col, (sport, label, title, path, cta, text) in zip(st.columns(len(row), gap="medium"), row):
        with col, st.container(key=f"card_{sport}"):
            st.markdown(card_top(sport, label), unsafe_allow_html=True)
            st.subheader(title)
            st.markdown(f'<p class="card-text">{text}</p>', unsafe_allow_html=True)
            with st.container(key=f"cardlink_{sport}"):
                st.page_link(path, label=cta, icon=":material/arrow_forward:", width="stretch")

# ------------------------------------------------------------ how it works
st.write("")
eyebrow("How it works")
st.header("Three steps, every sport")
steps = [
    ("1. Build a picture", "Start from real data: projections, recent games, injuries, team strength. Turn it "
                           "into a realistic range for each player or team, not just one number."),
    ("2. Play it out", "Let the computer play the games a million times. Some runs a star has a huge day, "
                       "some runs they're quiet, and some runs the underdog wins. Like real life."),
    ("3. Count the wins", "Look at all those results and count. The lineup, bracket or captain that comes "
                          "out on top most often is your best bet, and you see the odds behind it."),
]
for col, (title, text) in zip(st.columns(3, gap="medium"), steps):
    col.markdown(f'<div class="step"><b>{title}</b><p>{text}</p></div>', unsafe_allow_html=True)

# ------------------------------------------------------ how many simulations
st.write("")
eyebrow("Simulations")
st.header("How many simulations?")
st.write("Each run is random, so the odds wobble a little from one run to the next. The more times the "
         "games are played, the less they wobble. Every tool now plays the games a million times, which makes "
         "the odds rock-steady. A million games would fill gigabytes of memory, so they're played in batches "
         "and only the running totals are kept.")


def wobble(n: int) -> str:
    return f"±{196 * (0.25 / n) ** 0.5:.1f}"      # 95% margin on a 50% chance, in percentage points


sims = [("nfl", "NFL lineups", "weeks", "a few seconds"), ("ncaa", "March Madness", "tournaments", "about a second"),
        ("epl", "Fantasy Premier League", "gameweeks", "a minute or two"),
        ("bets", "Parlay Lab", "slates", "under a minute")]
for col, (sport, name, unit, speed) in zip(st.columns(4, gap="medium"), sims):
    c = SPORTS[sport]["color"]
    col.markdown(f"""
<div style="background:#fff;border:1px solid #dfe3e8;border-top:4px solid {c};border-radius:8px;padding:.9rem 1rem">
  <p class="eyebrow" style="color:{c}">{name}</p>
  <div style="font-family:'Barlow Condensed',sans-serif;font-size:2.1rem;font-weight:700;line-height:1">1,000,000</div>
  <p style="margin:.15rem 0 .6rem;color:#3b4857">{unit} per run · takes {speed}</p>
  <p style="margin:0;color:#3b4857;font-size:.92rem">A 50% chance comes out within <b>{wobble(1_000_000)} points</b>.</p>
</div>""", unsafe_allow_html=True)
st.caption("Want a faster answer? Pick fewer simulations under Simulation settings on each tool.")

# -------------------------------------------------------------- what's used
st.write("")
eyebrow("The inputs")
st.header("What each simulator looks at")
inputs = {
    "nfl": ["ESPN's projection for every player this week", "Points scored in each of the last 6 games",
            "Injury report (questionable players sit out about 1 week in 5)", "Who plays who, so teammates and "
            "opponents rise and fall together", "Your ESPN league's scoring and lineup rules (or ESPN's defaults)"],
    "ncaa": ["The final score of every Division I game this season", "Whether each game was home, away or "
             "neutral", "Last season's ratings, early in the year", "The official bracket and results once "
             "the tournament starts"],
    "epl": ["Every club's goals scored and conceded this season", "Each player's expected goals (xG) and "
            "expected assists (xA) per 90 minutes", "How often each player starts, and their injury status",
            "Saves, defensive actions and FPL's scoring rules", "Player prices and your budget (or none)",
            "This gameweek's fixtures, including doubles and blanks"],
    "bets": ["DraftKings moneylines, spreads and totals for 24 leagues", "Every open Kalshi sports market: "
             "winners, spreads, totals and player props", "Each price with the bookmaker's cut removed",
             "Your risk, payout, number of legs, sports and bet types"],
}
for col, (sport, items) in zip(st.columns(4, gap="medium"), inputs.items()):
    s = SPORTS[sport]
    col.markdown(f'<p class="eyebrow" style="color:{s["color"]}">{s["label"]}</p>' +
                 "".join(f"<p style='margin:.35rem 0;border-left:3px solid {s['color']};padding-left:.6rem'>{i}</p>"
                         for i in items), unsafe_allow_html=True)

# --------------------------------------------------------------- the code
st.write("")
eyebrow("Under the hood")
st.header("The idea, in a few lines of code")
st.write("Simplified versions of what each simulator does, written to be read by anyone. "
         "The real code is one click away under each one.")
t_nfl, t_ncaa, t_epl, t_bets = st.tabs(["NFL lineups", "March Madness", "Premier League", "Parlay Lab"])

with t_nfl:
    st.code('''# Play this week 1,000,000 times
for week in range(1_000_000):
    for player in your_players:
        # Start from the projection, then roll the dice:
        # most weeks land near it, some are huge, some are duds.
        points[player] = player.projection * random_good_or_bad_day()

        # Teammates share luck: when a QB has a big day,
        # their receivers usually do too.
        points[player] *= team_luck[player.team]

        # Listed as questionable? Some weeks they don't play.
        if player.questionable and chance(20%):
            points[player] = 0

    # Which lineup would have scored the most this time?
    remember(best_lineup(points))

# Start the lineup that came out on top most often.''', language="python")
    real_code(simulate.simulate, simulate.luck_to_points)

with t_ncaa:
    st.code('''# Step 1: rate every team from this season's scores.
# "A beat B by 12" -> A is about 12 points better than B
# (after allowing for home court). Repeat for thousands of games.
ratings = rate_teams(every_score_this_season)

# Step 2: play the whole tournament 1,000,000 times.
for tournament in range(1_000_000):
    teams_left = the_64_teams
    while more_than_one(teams_left):
        for team_a, team_b in this_rounds_games(teams_left):
            # a team 11 points better wins about 84% of the time
            chance_a_wins = win_chance(ratings[team_a] - ratings[team_b])
            winner = team_a if random() < chance_a_wins else team_b
        teams_left = this_rounds_winners
    remember(champion = teams_left[0])

# Title odds = how often each team ended up as champion.''', language="python")
    real_code(madness.fit_ratings, madness.simulate_bracket)

with t_epl:
    st.code('''# Play this gameweek 1,000,000 times
for gameweek in range(1_000_000):
    for match in this_gameweeks_fixtures:
        # How many goals? Depends on one side's attack vs. the other's defence.
        home_goals = random_goals(expected = home_attack * away_defence)
        away_goals = random_goals(expected = away_attack * home_defence)

        # Who scored? Players with higher xG get more of the goals,
        # but only if they're on the pitch that day.
        for goal in home_goals:
            scorer = pick_a_player(more_likely_if = high_xG)
            points[scorer] += goal_points[scorer.position]   # 4, 5, 6 or 10

        # Defenders and keepers get a clean sheet if the other side scored 0.
        # Then: assists, saves, defensive actions, bonus for the top 3.

    remember(best_xi(points), top_scorer(points))

# Captain = the player who topped the XI most often.''', language="python")
    real_code(fpl.simulate, fpl.player_points)

with t_bets:
    st.code('''# Step 1: every leg's real chance, with the bookmaker's cut taken out.
# DraftKings -150 / +130 -> 58% / 42% after removing the cut.
# If Kalshi lists the same game too, average the two.
chances = fair_chance(every_draftkings_line + every_kalshi_market)

# Step 2: play every game 1,000,000 times.
for scenario in range(1_000):
    # Our chances are estimates, so nudge each one a little per scenario.
    nudged = wiggle(chances)
    for slate in range(1_000):
        won[leg] = random() < nudged[leg]        # for every leg at once

# Step 3: score every parlay that fits your risk, payout and legs.
for parlay in candidates(your_settings):
    hit_rate = share_of_slates_where(all legs in parlay won)
    value = hit_rate * parlay.payout - 1      # profit per $1, on average

# Show the parlays with the best value (or best odds, or biggest payout).''', language="python")
    real_code(parlay.simulate)

# ------------------------------------------------------------ track record
st.write("")
eyebrow("Track record")
st.header("How it has done")
st.write("Each tool can be rerun on past weeks and tournaments using only what was known beforehand.")
m1, m2, m3 = st.columns(3, gap="medium")
m1.metric("NFL 2026, week 9: optimizer's lineup", "186.7 pts", "+8.2 vs. its own projection")
m2.metric("Best lineup possible in hindsight", "260.9 pts")
m2.caption("The optimizer's lineup captured 72% of it.")
m3.metric("2026 March Madness bracket (ESPN scoring)", "≈1,000 / 1,920")
m3.caption("Champion Michigan was its #2 title pick before the tournament.")
st.caption("Single results, not long-run averages.")

# ------------------------------------------------------------------- footer
st.divider()
st.caption("Data: ESPN Fantasy (NFL), ESPN public scoreboards (college basketball and DraftKings odds), the official "
           "Fantasy Premier League API and Kalshi's public market data. Not affiliated with ESPN, DraftKings, Kalshi, "
           "the NFL, the NCAA or the Premier League. For entertainment; no outcome is guaranteed. Betting is 21+; "
           f"if gambling stops being fun, call 1-800-GAMBLER. Version {APP_VERSION}.")
