"""Track record: replay each tool on games that have already happened, using only what was known beforehand,
and grade it against what really happened.

* Best Bets: every finished game of the last few days. Team records are rolled back to before the game,
  Kalshi's price is read from its price history just before kick-off, our simulation is run on those, the
  picks Best Bets would have shown are chosen, and each is graded win/lose with the real payout for $10.
* F1 Fantasy: each recent round with the prices of that round and only earlier races' results, against the
  best team possible in hindsight.
* Fantasy Premier League: each recent gameweek with every player's stats rebuilt to before it (season totals
  minus that gameweek and later), against FPL's average and top manager scores.
* NFL: each recent week (ffmc/backtest.py), against the projections-only lineup and the best possible lineup.
"""

from __future__ import annotations

import copy
import datetime as dt
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from . import bestbets, f1, fpl, live, winprob
from .http import APIError, CachedJSON

ET = live.EASTERN
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
LONG = 86400 * 30          # finished games don't change: cache for a month


# ------------------------------------------------------------------ Best Bets
@dataclass
class GradedPick:
    day: dt.date
    league: str
    pick: str
    opponent: str
    ours: float            # our simulated chance before the game
    kalshi: float          # Kalshi's chance just before kick-off
    ask: float             # what a $1 contract cost then
    won: bool
    profit: float          # on a $10 stake (whole contracts plus fee)
    score: str


@dataclass
class BetsRecord:
    picks: list[GradedPick] = field(default_factory=list)
    games_checked: int = 0
    days: int = 0
    failures: int = 0          # fetches that still failed after retries: the record may be missing games

    @property
    def hits(self) -> int:
        return sum(p.won for p in self.picks)

    @property
    def profit(self) -> float:
        return sum(p.profit for p in self.picks)

    @property
    def staked(self) -> float:
        return 10.0 * len(self.picks)

    @property
    def expected_by_kalshi(self) -> float:
        return sum(p.kalshi for p in self.picks)

    @property
    def expected_by_us(self) -> float:
        return sum(p.ours for p in self.picks)


def _pre_game_record(rec: str, won: bool | None, lost_in_ot: bool, draw: bool, three_way: str) -> str:
    """ESPN shows a finished game's records *including* that game; roll one result back."""
    try:
        parts = [int(x) for x in rec.split("-")]
    except ValueError:
        return rec
    if len(parts) == 2:
        if won is True:
            parts[0] -= 1
        elif won is False:
            parts[1] -= 1
    elif len(parts) == 3:
        if three_way == "soccer":                 # W-D-L
            idx = 1 if draw else (0 if won else 2)
        else:                                     # hockey W-L-OTL
            idx = 0 if won else (2 if lost_in_ot else 1)
        parts[idx] -= 1
    return "-".join(str(max(x, 0)) for x in parts)


_FAILS = {"count": 0}
_FAILS_LOCK = threading.Lock()


def _get(http: CachedJSON, url: str, params, ttl: float, tries: int = 5):
    """GET with retries: ESPN and Kalshi refuse bursts of requests (429) now and then. Without this a
    refused request silently dropped a whole league from the record. A real "not found" isn't retried."""
    for k in range(tries):
        try:
            return http.get(url, params, ttl=ttl)
        except APIError as exc:
            msg = str(exc)
            if "404" in msg or "400" in msg or k == tries - 1:
                if "404" not in msg:
                    with _FAILS_LOCK:
                        _FAILS["count"] += 1
                raise
            time.sleep(0.8 * 2 ** k)


def _finished_games(http: CachedJSON, lg: tuple, day: dt.date, today: dt.date) -> list[live.Game]:
    sport, name, path, _ = lg
    try:
        data = _get(http, live.ESPN.format(path=path), [("dates", day.strftime("%Y%m%d")), ("limit", "300")],
                    ttl=LONG if day < today - dt.timedelta(1) else 1800)
    except APIError:
        return []
    out = []
    for e in data.get("events") or []:
        for comp in e.get("competitions") or []:
            try:
                g = live._game(comp, e, sport, name)
            except (AttributeError, KeyError, TypeError, ValueError, IndexError):
                continue
            if g is None or g.state != "post" or len(g.sides) != 2:
                continue
            g.path, g.event_id = path, str(e.get("id", ""))
            out.append(g)
    return out


def _settled_markets(http: CachedJSON, series: str, since: dt.datetime) -> dict[str, list[dict]]:
    """Kalshi's settled winner markets for a series since a date, grouped by event."""
    events: dict[str, list[dict]] = {}
    cursor = ""
    for _ in range(6):
        params = [("series_ticker", series), ("status", "settled"), ("limit", "1000"),
                  ("min_close_ts", str(int(since.timestamp())))]
        if cursor:
            params.append(("cursor", cursor))
        try:
            data = _get(http, f"{KALSHI_API}/markets", params, ttl=3600)
        except APIError:
            break
        for m in data.get("markets", []):
            events.setdefault(m["event_ticker"], []).append(m)
        cursor = data.get("cursor") or ""
        if not cursor:
            break
    return events


def _price_before(http: CachedJSON, series: str, ticker: str, start: dt.datetime) -> tuple[float, float] | None:
    """(chance, ask) from Kalshi's last hourly candle before ``start``."""
    end = int(start.timestamp())
    try:
        data = _get(http, f"{KALSHI_API}/series/{series}/markets/{ticker}/candlesticks",
                    [("start_ts", str(end - 6 * 3600)), ("end_ts", str(end)), ("period_interval", "60")], ttl=LONG)
    except APIError:
        return None
    for c in reversed(data.get("candlesticks") or []):
        bid = float((c.get("yes_bid") or {}).get("close_dollars") or 0)
        ask = float((c.get("yes_ask") or {}).get("close_dollars") or 0)
        if 0 < ask < 1:
            mid = (bid + ask) / 2 if 0 < bid < ask else ask
            return mid, ask
    return None


def bets_record(days: int = 5, per_day: int = 12, cache_dir=".ffmc_cache", now: dt.datetime | None = None,
                sims: int = 200_000) -> BetsRecord:
    """Replay Best Bets on the last ``days`` days of finished games and grade every pick."""
    now = now or dt.datetime.now(dt.timezone.utc)
    http = CachedJSON(cache_dir)
    today = now.astimezone(ET).date()
    span = [today - dt.timedelta(k) for k in range(1, days + 1)]
    leagues = [l for l in live.LEAGUES if l[0] not in ("Tennis", "MMA")]
    jobs = [(lg, d) for lg in leagues for d in span]
    with _FAILS_LOCK:
        failed_before = _FAILS["count"]
    with ThreadPoolExecutor(4) as pool:
        found = list(pool.map(lambda j: (j[0], _finished_games(http, j[0], j[1], today)), jobs))
    by_league: dict[str, list[live.Game]] = {}
    for lg, gs in found:
        by_league.setdefault(lg[1], []).extend(gs)

    record = BetsRecord(days=days)
    since = now - dt.timedelta(days=days + 2)
    candidates = []
    for lg in leagues:
        games = list({g.key: g for g in by_league.get(lg[1], [])}.values())
        if not games:
            continue
        attached = [copy.deepcopy(g) for g in games]
        live.attach_kalshi(attached, _settled_markets(http, lg[3], since), lg[3])
        for g in attached:
            if not any(s.kalshi_ticker for s in g.sides):
                continue
            record.games_checked += 1
            three = "soccer" if g.sport == "Soccer" else ""
            draw = g.sport == "Soccer" and not any(s.winner for s in g.sides)
            ot = any(x in (g.detail or "") for x in ("OT", "SO"))
            pre = copy.deepcopy(g)
            pre.state, pre.period, pre.clock = "pre", 0, 0.0
            for s in pre.sides:
                won = None if draw else bool(s.winner)
                s.record = _pre_game_record(s.record, won, ot and not s.winner, draw, three)
                s.score = "0"
            if min((winprob._share(s.record) or (0, 0))[1] for s in pre.sides) < bestbets.MIN_GAMES:
                continue
            mine = winprob.own_odds(pre, sims)
            if not mine:
                continue
            fair = g.dk_fair()
            for i, (s, p) in enumerate(((g.sides[0], mine.away), (g.sides[1], mine.home))):
                if not s.kalshi_ticker:
                    continue
                # Saves price lookups: skip sides our model clearly rates below the pre-game DraftKings line.
                if fair and len(fair) >= 2 and p < fair[i] - 0.03:
                    continue
                candidates.append((g, i, s, p))

    def price(c):
        g, i, s, p = c
        return c, _price_before(http, g.kalshi_series, s.kalshi_ticker, g.start)

    with ThreadPoolExecutor(3) as pool:
        priced = list(pool.map(price, candidates))

    edges_by_day: dict[dt.date, list] = {}
    for (g, i, s, p), got in priced:
        if not got:
            continue
        mid, ask = got
        if not 0.05 <= mid <= 0.95 or p - ask <= 0 or bestbets.too_far(g, i, p, mid):
            continue
        edges_by_day.setdefault(g.start.astimezone(ET).date(), []).append((p - ask, g, i, s, p, mid, ask))
    for day, edges in sorted(edges_by_day.items()):
        for gap, g, i, s, p, mid, ask in sorted(edges, key=lambda e: -e[0])[:per_day]:
            other = g.sides[1 - i]
            t = bestbets.ticket(bestbets.Bet(g, s.name, "Kalshi", "", 1 / ask, ask, p, ask=ask), 10.0)
            won = bool(s.winner)
            record.picks.append(GradedPick(
                day=day, league=g.league, pick=s.name, opponent=other.name, ours=p, kalshi=mid, ask=ask, won=won,
                profit=(t.profit if won else -t.spent) if t.contracts else 0.0,
                score=f"{g.sides[0].short} {g.sides[0].score}, {g.sides[1].short} {g.sides[1].score}"))
    with _FAILS_LOCK:
        record.failures = _FAILS["count"] - failed_before
    return record


# --------------------------------------------------------------------- F1
@dataclass
class F1Round:
    round: int
    name: str
    ours: float            # what our team really scored
    best: float            # the best team possible in hindsight (same $100M budget)
    team: list[str]
    boost: str


def f1_record(rounds: int = 6, cache_dir=".ffmc_cache", sims: int = 100_000) -> list[F1Round]:
    http = CachedJSON(cache_dir)
    current = int(f1._feed(http, "limits/constraints.json", 1800)["GamedayId"])
    season = dt.date.today().year
    try:
        races, calendar = f1.load_results(http, season)
    except APIError:
        races, calendar = [], []
    names = {int(r["round"]): r["raceName"] for r in calendar}
    out = []
    for r in range(max(1, current - rounds), current):
        try:
            weekend, assets = f1.load_assets(http, gid=r)
        except (APIError, KeyError):
            continue
        drivers = [a for a in assets if a.kind == "driver"]
        f1.apply_form(drivers, [x for x in races if int(x["round"]) < r])
        f1.finalize(drivers)
        weekend.sprint = False
        res = f1.run(weekend, assets, n_sims=sims, budget=f1.DEFAULT_BUDGET, seed=r)
        # What actually happened that round (F1 Fantasy's own points).
        pts = {str(p["PlayerId"]): float(p.get("GamedayPoints") or 0)
               for p in f1._feed(http, f"drivers/{r}_en.json", LONG)}
        actual = np.array([pts.get(a.id, 0.0) for a in res.assets])
        t = res.team
        ours = actual[t.drivers].sum() + actual[t.constructors].sum() + (res.boost_mult - 1) * actual[t.boost]
        prices = np.array([a.price for a in res.assets])
        n_drivers = sum(a.kind == "driver" for a in res.assets)
        best = f1.best_teams(actual, prices, n_drivers, f1.DEFAULT_BUDGET, res.boost_mult, keep=1)
        out.append(F1Round(r, names.get(r, f"Round {r}"), float(ours), best[0].mean if best else float(ours),
                           [res.assets[i].name for i in t.drivers + t.constructors], res.assets[t.boost].name))
    return out


# ---------------------------------------------------------------------- FPL
@dataclass
class FPLWeek:
    gw: int
    ours: float            # our XI's real points, captain doubled
    average: float         # FPL's average manager score that week
    top: float             # FPL's top score that week
    captain: str
    captain_points: float


def _fpl_gameweek_before(boot: dict, fixtures: list[dict], lives: dict[int, dict], g: int) -> fpl.Gameweek:
    """The gameweek ``g`` as it looked before kick-off: fixtures, team strengths and player stats from earlier
    gameweeks only (season totals minus gameweek g and later)."""
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    past = []
    for f in fixtures:
        f2 = dict(f)
        if not (f.get("event") and f["event"] < g and f.get("finished")):
            f2["finished"] = False
        past.append(f2)
    attack, defence, home_avg, away_avg = fpl.team_strengths(past, list(teams))
    team_games = {t: 0 for t in teams}
    for f in past:
        if f.get("finished"):
            team_games[f["team_h"]] += 1
            team_games[f["team_a"]] += 1
    gw_fix, playing = [], {}
    for f in fixtures:
        if f.get("event") != g:
            continue
        h, a = f["team_h"], f["team_a"]
        gw_fix.append({"home": h, "away": a, "home_xg": home_avg * attack[h] * defence[a],
                       "away_xg": away_avg * attack[a] * defence[h]})
        playing.setdefault(h, []).append(f"{teams[a]} (H)")
        playing.setdefault(a, []).append(f"{teams[h]} (A)")
    later: dict[int, dict] = {}
    for gw, data in lives.items():
        if gw >= g:
            for el in data.get("elements", []):
                acc = later.setdefault(el["id"], {})
                for k, v in el["stats"].items():
                    try:
                        acc[k] = acc.get(k, 0.0) + float(v)
                    except (TypeError, ValueError):
                        pass
    players = []
    for e in boot["elements"]:
        if e["team"] not in playing or e.get("status") in ("u", "n"):
            continue
        sub = later.get(e["id"], {})

        def before(key):
            return max(float(e.get(key) or 0) - sub.get(key, 0.0), 0.0)
        mins, starts = before("minutes"), before("starts")
        if mins <= 0:
            continue
        games = max(team_games.get(e["team"], 0), 1)
        start = min(1.0, starts / games)
        cameo = max(0.0, mins - 85 * starts)
        per90 = 90 / max(mins, 90)
        players.append(fpl.FPLPlayer(
            id=e["id"], name=e["web_name"], position=fpl.POSITIONS[e["element_type"]], team=e["team"],
            team_short=teams[e["team"]], price=e["now_cost"] / 10, fpl_projection=0.0, start_prob=start,
            sub_prob=min(1.0 - start, cameo / 25 / games), xg90=before("expected_goals") * per90,
            xa90=before("expected_assists") * per90, saves90=before("saves") * per90,
            defcon90=before("defensive_contribution") * per90, status="a", fixtures=playing[e["team"]]))
    ev = next(x for x in boot["events"] if x["id"] == g)
    return fpl.Gameweek(g, ev["name"], ev["deadline_time"], players, gw_fix, teams)


def fpl_record(weeks: int = 4, cache_dir=".ffmc_cache", sims: int = 50_000) -> list[FPLWeek]:
    client = fpl.FPLClient(cache_dir)
    boot, fixtures = client.bootstrap(), client.fixtures()
    finished = [e for e in boot["events"] if e.get("finished")]
    if not finished:
        return []
    last = finished[-1]["id"]
    lives = {}
    for gw in range(max(1, last - weeks + 1), last + 1):
        try:
            lives[gw] = client.http.get(f"{fpl.API}/event/{gw}/live/", ttl=LONG if gw < last else 3600)
        except APIError:
            pass
    out = []
    for e in finished[-weeks:]:
        g = e["id"]
        if g not in lives:
            continue
        gw = _fpl_gameweek_before(boot, fixtures, lives, g)
        res = fpl.run(gw, gw.players, sims, 7, None, fpl.DEFAULT_BUDGET)
        pts = {el["id"]: float(el["stats"]["total_points"]) for el in lives[g]["elements"]}
        xi = [gw.players[i] for i in res.xi]
        cap = gw.players[res.captain]
        ours = sum(pts.get(p.id, 0.0) for p in xi) + pts.get(cap.id, 0.0)
        out.append(FPLWeek(g, ours, float(e.get("average_entry_score") or 0), float(e.get("highest_score") or 0),
                           cap.name, pts.get(cap.id, 0.0)))
    return out


# ---------------------------------------------------------------------- NFL
@dataclass
class NFLWeek:
    week: int
    ours: float            # the simulator's lineup, real points
    projections: float     # the best lineup by projections alone, real points
    best: float            # the best lineup possible in hindsight


def nfl_record(weeks: int = 3, cache_dir=".ffmc_cache", sims: int = 50_000) -> list[NFLWeek]:
    from .backtest import run_backtest
    from .sleeper import SleeperClient
    client = SleeperClient(cache_dir)
    state = client.state()
    season, current = int(state.get("season") or dt.date.today().year), int(state.get("week") or 1)
    out = []
    for w in range(max(1, current - weeks), current):
        try:
            bt = run_backtest(client, season, w, "ppr", n_sims=sims, seed=w)
        except (APIError, ValueError):
            continue
        out.append(NFLWeek(w, bt.predicted_total, bt.projection_total, bt.best_total))
    return out


def top_calls(rec: BetsRecord, n: int = 10) -> tuple[list[GradedPick], list[dt.date]]:
    """Our ``n`` strongest Best Bets calls (biggest gap over Kalshi, ranked before the games) from the most recent
    day with finished picks, adding earlier days until there are ``n``."""
    pool: list[GradedPick] = []
    used: list[dt.date] = []
    for day in sorted({p.day for p in rec.picks}, reverse=True):
        pool += [p for p in rec.picks if p.day == day]
        used.append(day)
        if len(pool) >= n:
            break
    return sorted(pool, key=lambda p: -(p.ours - p.ask))[:n], sorted(used)
