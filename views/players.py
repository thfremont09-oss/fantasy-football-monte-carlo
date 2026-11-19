"""Player Stats page: search any player for this season, career, last game, a game in progress and fun facts."""

from __future__ import annotations

import html
import re

import pandas as pd
import streamlit as st

from ffmc import players
from ffmc.ui import banner

esc = html.escape

CSS = """<style>
.ps-head { display: flex; gap: 1rem; align-items: center; padding: 1rem 1.1rem; border: 1px solid var(--line);
  border-radius: 10px; background: var(--card); border-left: 6px solid var(--tc, #16324f); }
.ps-head .ini { width: 92px; height: 92px; border-radius: 50%; object-fit: cover; object-position: 50% 20%;
  background: var(--soft); flex: 0 0 auto; }
.ps-head .ini { display: flex; align-items: center; justify-content: center; font: 800 1.8rem Archivo, sans-serif;
  color: var(--muted); position: relative; overflow: hidden; }
.ps-head .ini img { position: absolute; inset: 0; width: 100%; height: 100%; border-radius: 0; background: var(--soft); }
.ps-head h2 { margin: 0; padding: 0; font: 800 1.9rem/1.1 Archivo, sans-serif; color: var(--ink); }
.ps-head .sub { color: var(--sub); font-weight: 600; margin-top: .2rem; }
.ps-head .chips { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .55rem; }
.ps-head .chips span { font-size: .82rem; border: 1px solid var(--line); border-radius: 999px; padding: .12rem .6rem;
  color: var(--sub); background: var(--soft); }
.ps-news { margin-top: .7rem; padding: .7rem .9rem; border-radius: 8px; background: var(--soft); color: var(--sub);
  font-size: .93rem; border: 1px solid var(--line); }
.ps-news b { color: var(--ink); }
.ps-live { margin: 1rem 0 .2rem; padding: .8rem 1rem; border-radius: 10px; border: 2px solid var(--accent); }
.ps-live .top { display: flex; justify-content: space-between; gap: 1rem; font-weight: 700; color: var(--ink); }
.ps-live .dot { color: var(--accent); }
.ps-live .row { display: flex; flex-wrap: wrap; gap: .5rem 1.4rem; margin-top: .5rem; }
.ps-live .row div { min-width: 3.6rem; }
.ps-live .row small { display: block; color: var(--muted); font-size: .75rem; font-weight: 600; }
.ps-live .row b { font: 700 1.25rem "Barlow Condensed", Archivo, sans-serif; color: var(--ink); }
.ps-keys { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: .8rem; margin: 1rem 0; }
.ps-key { border: 1px solid var(--line); border-radius: 10px; padding: .8rem .95rem; background: var(--card); }
.ps-key h4 { margin: 0 0 .45rem; padding: 0; font: 700 .8rem Archivo, sans-serif; letter-spacing: .06em;
  text-transform: uppercase; color: var(--muted); }
.ps-key .big { font: 800 2.2rem/1 Archivo, sans-serif; color: var(--ink); }
.ps-key .big small { font: 600 .8rem "IBM Plex Sans", sans-serif; color: var(--muted); margin-left: .35rem; }
.ps-key .pg { color: var(--sub); font-size: .85rem; margin-top: .2rem; }
.ps-key .trio { display: grid; grid-template-columns: 1fr 1fr; gap: .4rem; margin-top: .7rem; padding-top: .6rem;
  border-top: 1px solid var(--line); }
.ps-key .trio small { display: block; color: var(--muted); font-size: .75rem; font-weight: 600; }
.ps-key .trio b { font-size: 1.05rem; color: var(--ink); }
.ps-facts { border: 1px solid var(--line); border-radius: 10px; padding: .9rem 1.1rem .5rem; background: var(--card); }
.ps-facts h3 { margin: 0 0 .3rem; padding: 0; font: 800 1.15rem Archivo, sans-serif; color: var(--ink); }
.ps-facts ul { margin: 0; padding-left: 1.1rem; } .ps-facts li { margin: .35rem 0; color: var(--sub); }
.ps-facts li strong { color: var(--ink); }
.ps-last { color: var(--sub); margin: .2rem 0 .6rem; }
.ps-last b.W { color: #1a8f3c; } .ps-last b.L { color: #d6232a; }
@media (max-width: 520px) { .ps-keys { grid-template-columns: 1fr 1fr; gap: .5rem; }
  .ps-key { padding: .65rem .7rem; } .ps-key .big { font-size: 1.6rem; } .ps-key .big small { display: block; margin: .2rem 0 0; }
  .ps-head { align-items: flex-start; }
  .ps-head .ini { width: 68px; height: 68px; } .ps-head h2 { font-size: 1.45rem; } }
</style>"""


@st.cache_data(ttl=3600, show_spinner=False)
def search(q: str) -> list[players.Player]:
    return players.search(q)


@st.cache_data(ttl=60, show_spinner=False)
def profile(p: players.Player) -> players.Profile:
    return players.profile(p)


@st.cache_data(ttl=20, show_spinner=False)
def live(p: players.Player) -> players.LiveLine | None:
    from ffmc.http import CachedJSON
    return players.live_line(p, CachedJSON())


def bold(s: str) -> str:
    """**markdown bold** -> <strong>, after escaping."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(s))


def header(pr: players.Profile) -> str:
    p = pr.player
    initials = "".join(w[0] for w in p.name.split()[:2]).upper()
    pic = (f'<div class="ini">{initials}' + (f'<img src="{esc(p.headshot)}" alt="">' if p.headshot else "")
           + "</div>")
    sub = " · ".join(x for x in [p.team or p.label, p.position, f"#{p.jersey}" if p.jersey else ""] if x)
    chips = []
    if pr.next_game:
        chips.append(f"Next: {esc(pr.next_game)}")
    if pr.fantasy.get("percentOwned"):
        chips.append(f"Rostered in {float(pr.fantasy['percentOwned']):.0f}% of ESPN fantasy leagues")
    if pr.fantasy.get("positionRank"):
        chips.append(f"#{esc(pr.fantasy['positionRank'])} {esc(p.position)} in fantasy")
    news = (f'<div class="ps-news"><b>Latest:</b> {esc(pr.news)}</div>' if pr.news else "")
    color = f"#{p.color}" if re.fullmatch(r"[0-9a-fA-F]{6}", p.color or "") else "#16324f"
    return (f'<div class="ps-head" style="--tc:{color}">{pic}<div><h2>{esc(p.name)}</h2><div class="sub">{esc(sub)}'
            f'</div><div class="chips">{"".join(f"<span>{c}</span>" for c in chips)}</div></div></div>{news}')


def live_box(p: players.Player) -> None:
    ln = live(p)
    if not ln:
        return
    title = "Live now" if ln.state == "in" else "Just finished"
    dot = '<span class="dot">●</span> ' if ln.state == "in" else ""
    stats = "".join(f'<div title="{esc(lng)}"><small>{esc(lab)}</small><b>{esc(v)}</b></div>' for lab, lng, v in ln.stats)
    body = f'<div class="row">{stats}</div>' if stats else '<div class="row">No stats in this game yet.</div>'
    st.markdown(f'<div class="ps-live"><div class="top"><span>{dot}{title}: {esc(ln.score)}</span>'
                f'<span>{esc(ln.status)}</span></div>{body}</div>', unsafe_allow_html=True)


def key_cards(pr: players.Profile) -> str:
    cards = []
    season = (re.sub(r"\s*Regular Season\s*", "", pr.season_label) + " season").strip()
    for k in pr.keys:
        last = k.last if k.last is not None else "-"
        career = f"{k.career}{' /game' if k.career_note else ''}" if k.career else "-"
        cards.append(
            f'<div class="ps-key"><h4>{esc(k.label)}</h4>'
            f'<div class="big">{esc(k.season or "-")}<small>{esc(season)}</small></div>'
            f'<div class="pg">{esc(k.per_game or "-")} per game</div>'
            f'<div class="trio"><div><small>Last game</small><b>{esc(str(last))}</b></div>'
            f'<div><small>Career</small><b>{esc(career)}</b></div></div></div>')
    return f'<div class="ps-keys">{"".join(cards)}</div>'


def game_table(pr: players.Profile) -> pd.DataFrame:
    rows = []
    for g in pr.games:
        row = {"Date": g.date.astimezone(players.EASTERN).strftime("%b %-d"), "Game": g.matchup,
               "Result": f"{g.result} {g.score}".strip()}
        for name, lab, _ in pr.game_columns:
            col = lab if lab not in row else f"{lab} "
            row[col] = g.stats.get(name, "")
        rows.append(row)
    return pd.DataFrame(rows)


def table_frame(t: players.Table) -> pd.DataFrame:
    cols = list(dict.fromkeys(t.columns))        # keep columns unique
    out = []
    for label, vals in t.rows:
        row = {"": label}
        for i, c in enumerate(t.columns):
            key = c if c not in row else f"{c} ({i})"
            row[key] = vals[i] if i < len(vals) else ""
        out.append(row)
    return pd.DataFrame(out)


def color_result(v: str) -> str:
    if isinstance(v, str) and v[:1] == "W":
        return "color: #1a8f3c; font-weight: 600"
    if isinstance(v, str) and v[:1] == "L":
        return "color: #d6232a; font-weight: 600"
    return ""


# ------------------------------------------------------------------- page

st.markdown(CSS, unsafe_allow_html=True)
banner("stats", "Player Stats",
       "Search any player for their numbers this season, over their whole career and in their last game, plus a "
       "game they're playing right now and the most interesting things in their numbers.",
       chips=["NFL · NBA · WNBA · NHL · MLB", "College football & basketball", "Soccer"])

qp = st.query_params
q = st.text_input("Search a player", value=qp.get("q", ""), placeholder="Try Drake Maye, LeBron, McDavid, Haaland...",
                  key="ps_q", icon=":material/search:")
q = q.strip()
if not q:
    st.caption("Spelling doesn't have to be perfect: *drak maye* finds Drake Maye.")
    st.stop()

with st.spinner("Looking up players..."):
    found = search(q)
if not found:
    st.info(f"No players found for “{q}”. Try a last name, like *Maye* or *Mahomes*.")
    st.stop()

options = {p.key: p for p in found}
start = qp.get("p") if qp.get("p") in options else found[0].key
pick = start
if len(found) > 1:
    keys = list(options)
    pick = st.selectbox("Not who you meant?", keys, index=keys.index(start), key=f"ps_pick_{q}",
                        format_func=lambda k: f"{options[k].name} · {options[k].short_label}")
st.query_params.update({"q": q, "p": pick})
player = options[pick]

with st.spinner(f"Loading {player.name}..."):
    pr = profile(player)

st.markdown(header(pr), unsafe_allow_html=True)
st.fragment(run_every=30)(live_box)(player)

if not pr.keys and not pr.seasons and not pr.games:
    st.info("ESPN doesn't have stats for this player yet.")
    st.stop()

st.markdown(key_cards(pr), unsafe_allow_html=True)
if pr.facts:
    st.markdown('<div class="ps-facts"><h3>Fun facts</h3><ul>' + "".join(f"<li>{bold(f)}</li>" for f in pr.facts)
                + "</ul></div>", unsafe_allow_html=True)
st.write("")

tabs = st.tabs(["Last game", "This season, game by game", "Career by season", "Splits"])
with tabs[0]:
    g = pr.last_game
    if not g:
        st.caption("No games yet this season.")
    else:
        res = {"W": "Won", "L": "Lost", "D": "Drew", "T": "Tied"}.get(g.result, "")
        st.markdown(f'<p class="ps-last">{g.date.astimezone(players.EASTERN).strftime("%A, %B %-d")} · {esc(g.matchup)}'
                    f' ({esc(g.opponent)}) · <b class="{g.result}">{res} {esc(g.score)}</b></p>', unsafe_allow_html=True)
        line = [{"Stat": lng, "": g.stats.get(name, "")} for name, lab, lng in pr.game_columns]
        st.dataframe(pd.DataFrame(line), hide_index=True, width="stretch")
with tabs[1]:
    if pr.games:
        df = game_table(pr)
        st.dataframe(df.style.map(color_result, subset=["Result"]), hide_index=True, width="stretch")
        st.caption(" · ".join(f"**{lab}** {lng}" for _, lab, lng in pr.game_columns))
    else:
        st.caption("No games yet this season.")
with tabs[2]:
    if pr.seasons:
        names = [t.title for t in pr.seasons]
        which = st.segmented_control("Category", names, default=names[0], key=f"ps_cat_{pick}",
                                     label_visibility="collapsed") or names[0]
        t = next(t for t in pr.seasons if t.title == which)
        st.dataframe(table_frame(t), hide_index=True, width="stretch")
        st.caption(" · ".join(f"**{a}** {b}" for a, b in dict(zip(t.columns, t.tips)).items()))
    else:
        st.caption("ESPN doesn't publish season-by-season totals for this player; the splits tab has this season by "
                   "competition.")
with tabs[3]:
    if pr.splits:
        st.dataframe(table_frame(pr.splits), hide_index=True, width="stretch")
        st.caption(" · ".join(f"**{a}** {b}" for a, b in dict(zip(pr.splits.columns, pr.splits.tips)).items()))
    else:
        st.caption("No splits for this player.")

st.divider()
st.caption("Stats and news from ESPN. Not affiliated with ESPN or any league.")
