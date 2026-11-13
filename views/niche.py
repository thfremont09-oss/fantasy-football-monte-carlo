"""Niche Sports page: the most obscure markets on the board, with the Parlay Lab Monte Carlo."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ffmc import parlay as pl
from ffmc import parlay_ui as ui
from ffmc.ui import SPORTS, banner

COLOR = SPORTS["niche"]["color"]

banner("niche", "Niche Sports",
       "The deep end of the board: Russian table tennis, Bosnian basketball, Valorant, women's cricket, Japanese "
       "cup soccer, winter-league baseball and whatever else Kalshi lists this week. Every league is scored for how "
       "obscure it is; pick how deep to go and the million-slate simulation finds the best bets.",
       chips=["Ranked by obscurity", "Kalshi + DraftKings", "Singles and parlays"])

all_legs, stats, loaded_at = ui.get_legs(COLOR)

with st.container(key="settings"):
    names = {lvl: name for lvl, (name, _, _) in pl.NICHE_LEVELS.items()}
    level = st.select_slider("Niche-o-meter", list(names), value=3, format_func=lambda l: f"{l} · {names[l]}",
                             key="ni_level", help="How obscure the leagues must be. 1 skips the big US leagues and "
                                                  "Europe's top soccer; 5 is the deepest end, like Japanese women's tennis.")
    st.caption(pl.NICHE_LEVELS[level][2] + ".")
    n1, n2 = st.columns(2, gap="large")
    days = n1.select_slider("Games starting within", [1, 2, 3, 5, 7], value=7, key="ni_days",
                            format_func=lambda d: f"{d} day{'s' if d > 1 else ''}")
    max_gap = n2.select_slider("Market depth", [0.05, 0.10, 0.15, 0.20, 0.30], value=0.20, key="ni_gap",
                               format_func=lambda g: f"bid/ask gap up to {g * 100:.0f}¢",
                               help="Niche markets trade less, so buy and sell prices sit further apart. A wider "
                                    "gap lets in more obscure markets, but their prices are less certain (the "
                                    "simulation accounts for that).")
    bet = ui.bet_controls(app_default="Kalshi", risk_default=6, payout_default=(2, 20), legs_default=(1, 3),
                          min_legs=1, key="ni")
    with st.expander("More options"):
        a1, a2 = st.columns(2, gap="large")
        rank_by = a1.pills("Rank by", ["Best value", "Most likely to hit", "Biggest payout"], default="Best value",
                           required=True, key="ni_rank")
        markets = a1.multiselect("Bet types", list(pl.MARKETS), default=list(pl.MARKETS), key="ni_markets")
        leg_prob = a2.slider("Each leg's chance to win", 0.05, 0.95, (0.10, 0.92), 0.01, format="%.2f", key="ni_prob")
        n_show = a2.slider("Bets to show", 3, 20, 10, key="ni_show")
        n_sims = a2.select_slider("Simulated slates", [100_000, 250_000, 1_000_000], value=1_000_000,
                                  format_func=lambda n: f"{n:,}", key="ni_sims")

min_score = pl.NICHE_LEVELS[level][1]
legs = [l for l in pl.within(all_legs, days, max_spread=max_gap) if l.niche >= min_score]

# ------------------------------------------------------------ what's on
st.subheader("On the board right now")
if not legs:
    st.info(f"Nothing this obscure is open in the next {days} day{'s' if days > 1 else ''}. Try a lower Niche-o-meter "
            "level, more days, or a wider market depth. Kalshi adds niche events all the time (ITF women's tennis, "
            "darts, chess, squash...), and they show up here as soon as they're listed.")
    st.stop()

board = {}
for l in legs:
    b = board.setdefault(l.league, {"Sport": l.sport, "League": l.league, "niche": l.niche, "games": set(), "Bets": 0,
                                    "next": l.start, "example": l.matchup})
    b["games"].add(l.game)
    b["Bets"] += 1
    if l.start < b["next"]:
        b["next"], b["example"] = l.start, l.matchup
rows = sorted(board.values(), key=lambda b: (-b["niche"], b["next"]))
top = rows[0]
st.markdown(f"""
<div style="background:#fff;border:1px solid #dfe3e8;border-left:6px solid {COLOR};border-radius:8px;padding:.9rem 1.1rem;margin-bottom:.8rem">
  <p class="eyebrow" style="color:{COLOR};margin:0">Most obscure thing on the board</p>
  <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.7rem;font-weight:700;line-height:1.1">{top['League']}</div>
  <p style="margin:.2rem 0 0;color:#3b4857">{top['Sport']} · {top['example']} · {ui.fmt_start(top['next'])} ET ·
  {len(top['games'])} game{'s' if len(top['games']) > 1 else ''} open</p>
</div>""", unsafe_allow_html=True)

df = pd.DataFrame([{"Niche": "●" * min(b["niche"], 7), "Sport": b["Sport"], "League": b["League"],
                    "Games": len(b["games"]), "Bets": b["Bets"], "Next game (ET)": ui.fmt_start(b["next"]),
                    "Example": b["example"]} for b in rows])
st.dataframe(df, hide_index=True, width="stretch", height=min(420, (len(df) + 1) * 35 + 3),
             column_config={"Niche": st.column_config.TextColumn(help="More dots = more obscure")})
leagues = [b["League"] for b in rows]
with st.container(key="league_filter"):
    # Keyed on the board's settings, so changing the Niche-o-meter starts again from every league.
    picked = st.multiselect(f"Leagues to bet on ({len(leagues)} available)", leagues, default=leagues,
                            key=f"ni_leagues_{level}_{days}_{max_gap}",
                            help="Remove any you don't want in your bets.")
legs = [l for l in legs if l.league in set(picked)] if picked else legs

st.caption(f"Odds as of {loaded_at.astimezone(ui.ET):%a %b %d, %I:%M %p} ET · {len(legs):,} niche bets from "
           f"{len({l.game for l in legs}):,} games. Niche markets are thin and prices move: check them before betting.")

settings = pl.Settings(app=bet["app"], risk=bet["risk"], payout_range=bet["payout"], legs_range=bet["legs_range"],
                       leg_prob_range=leg_prob, markets=tuple(markets), sports=None, one_per_game=True,
                       rank_by={"Best value": "value", "Most likely to hit": "likely", "Biggest payout": "payout"}[rank_by],
                       stake=bet["stake"], n_show=n_show)
params = (settings, n_sims, days, level, max_gap, tuple(sorted(picked)), int(loaded_at.timestamp()))
sim = ui.run_search(legs, settings, n_sims, params, key="ni", button=f"Find niche bets · simulate {n_sims:,} slates")
ui.render_results(sim, legs, bet["stake"], show_niche=True)

with st.expander("How the Niche-o-meter works"):
    st.markdown("""
Every league gets an obscurity score:

* **The sport**: football scores lowest, then basketball, baseball, hockey and soccer; tennis, golf and MMA a bit
  higher; cricket, esports and rugby higher still; table tennis, volleyball, darts and handball near the top; chess
  and squash at the very top.
* **+1** for a women's league, **+1** for a lower division, cup, youth, winter or ITF/Challenger event, and **+1**
  for a league based outside the US.
* The NFL, NBA, NHL, MLB, big college sports and Europe's top soccer leagues score zero and never appear here.

Higher Niche-o-meter levels only keep leagues with higher scores. ITF women's tennis in Japan, for example, lands
at the top level. Niche markets trade less, so their prices carry more uncertainty: the simulation widens its
range of "true" chances for them, which shows up in the **Worth it** number.
""")

st.divider()
st.caption(ui.GAMBLING_NOTE)
