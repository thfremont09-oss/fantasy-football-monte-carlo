"""Team ratings from results: who you played, and by how much.

A team's record alone can't tell a 9-2 FCS team from a 9-2 SEC team. These ratings can. Every finished
game this season is one equation:

    home margin  =  home rating  -  away rating  +  home advantage  +  luck

Solving all of them together (ridge regression, a "simple rating system") gives each team a number in
points (goals or runs in low-scoring sports) that accounts for the strength of everyone it played. So a
team that beat weak opponents gets less credit than one that beat good ones, and FCS teams, who mostly
play each other, are rated on their own scale against the FBS teams they've faced.

Details that keep the numbers sensible:
* blowouts are capped (running up the score against a weak team doesn't make you better),
* recent games count more (a half-life of about two months),
* every rating is pulled toward average as if the team had also played a couple of average games,
* games at a neutral site get no home advantage.

``as_of`` replays history fairly: only games that finished before that date are used.
"""

from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass

import numpy as np

from . import live
from .http import APIError, CachedJSON
from .mem import heavy

# league: (margin cap, prior games, months of results to use, extra ESPN query params per fetch, home edge)
# Home edge is fixed at the usual value rather than fitted: schedules are lopsided (good college teams host
# weak ones), which would make a fitted home edge soak up strength that belongs to the teams.
SETUP = {
    "NFL": (20, 2.0, 6, [[]], 1.5),
    "College Football": (35, 1.5, 6, [[("groups", "80")], [("groups", "81")]], 2.5),
    "NBA": (20, 3.0, 8, [[]], 2.5),
    "WNBA": (20, 3.0, 8, [[]], 2.0),
    "Men's College Basketball": (25, 4.0, 6, [[("groups", "50")]], 3.0),
    "NHL": (3, 4.0, 8, [[]], 0.15),
    "MLB": (5, 8.0, 8, [[]], 0.15),
}
SOCCER = (3, 4.0, 10, [[]], 0.3)
CFB_WEEKS = 17
HALF_LIFE_DAYS = 60
MIN_GAMES = 4                     # a team needs this many results to be rated

# Tuned by tools/tune_ratings.py (rolling backtest: each week predicted only from the games before it).
# "sd" turns an expected margin into a win chance: P(home wins) = Phi(margin / sd).
# Tuned 2026-11-24 on the last 6 weeks (test games in brackets); WNBA and MLB were in their off-seasons with too
# few games, so they keep the defaults above. Soccer is tuned once across all leagues together.
TUNED: dict[str, dict] = {
    "NFL": {"cap": 40, "prior": 2.0, "home_edge": 0.75, "half_life": 35, "sd": 11.2},                   # (84)
    "College Football": {"cap": 35, "prior": 1.5, "home_edge": 2.5, "half_life": 120, "sd": 17.26},    # (725)
    "NBA": {"cap": 20, "prior": 8.0, "home_edge": 1.875, "half_life": 365, "sd": 12.68},               # (248)
    "Men's College Basketball": {"cap": 40, "prior": 1.0, "home_edge": 4.5, "half_life": 120, "sd": 16.64},  # (218)
    "NHL": {"cap": 4, "prior": 20.0, "home_edge": 0.075, "half_life": 730, "sd": 2.19},                # (291)
    "Soccer": {"cap": 4, "prior": 5.0, "home_edge": 0.225, "half_life": 120},                           # (765)
}


@dataclass
class TeamNote:
    """Plain facts behind a team's rating, for explaining a pick."""
    rank: int                     # by rating, among rated teams in the league (1 = best)
    of: int
    sos: float                    # average rating of the opponents it has played
    sos_rank: int                 # 1 = toughest schedule
    wins: int
    losses: int
    last: list[float]
    draws: int = 0             # margins of its last few games, newest first (its own point of view)


@dataclass
class Ratings:
    league: str
    rating: dict[str, float]      # team name -> points better than average (on a neutral field)
    games: dict[str, int]
    home_edge: float              # points
    resid_sd: float               # typical miss of the fitted margins, in points
    n_games: int
    notes: dict[str, TeamNote] | None = None

    def margin(self, home: str, away: str) -> float | None:
        """Expected home margin, or None if either team hasn't played enough to be rated."""
        if self.games.get(home, 0) < MIN_GAMES or self.games.get(away, 0) < MIN_GAMES:
            return None
        return self.rating[home] - self.rating[away] + self.home_edge


def _league(name: str) -> tuple[str, str, str, str] | None:
    return next((l for l in live.LEAGUES if l[1] == name), None)


def _months(as_of: dt.date, n: int) -> list[str]:
    out, y, m = [], as_of.year, as_of.month
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def _events(http: CachedJSON, path: str, when: str, extra: list, past: bool) -> list[dict]:
    data = http.get(live.ESPN.format(path=path), [("dates", when), ("limit", "1000")] + extra,
                    ttl=30 * 86400 if past else 3600)
    return data.get("events") or []


def _parse(evs: list[dict], seen: set, out: list) -> None:
    """Add every finished game on one page of results to ``out`` (as small tuples), then the page can go."""
    for e in evs:
        if e.get("id") in seen or (e.get("season") or {}).get("type") == 1:     # preseason games don't count
            continue
        for comp in e.get("competitions") or []:
            if ((comp.get("status") or e.get("status") or {}).get("type") or {}).get("state") != "post":
                continue
            teams = comp.get("competitors") or []
            if len(teams) != 2:
                continue
            when = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(live.EASTERN).date()
            home = next((c for c in teams if c.get("homeAway") == "home"), teams[1])
            away = next(c for c in teams if c is not home)
            try:
                hs, as_ = float(home.get("score")), float(away.get("score"))
            except (TypeError, ValueError):
                continue
            seen.add(e.get("id"))
            out.append((when, (home.get("team") or {}).get("displayName", ""),
                        (away.get("team") or {}).get("displayName", ""), hs, as_, bool(comp.get("neutralSite"))))


def _download(name: str, as_of: dt.date, http: CachedJSON) -> list[tuple]:
    lg = _league(name)
    if not lg:
        return []
    sport, _, path, _ = lg
    cap, prior, months, extras, _ = SETUP.get(name, SOCCER)
    today = dt.date.today()
    seen: set = set()
    out: list[tuple] = []
    if name == "College Football":
        # ESPN's college month queries skip most games: go week by week, FBS and FCS
        season = as_of.year if as_of.month >= 6 else as_of.year - 1
        for week in range(1, CFB_WEEKS + 1):
            for extra in extras:
                try:
                    data = http.get(live.ESPN.format(path=path), [("week", str(week)), ("seasontype", "2"),
                                    ("dates", str(season)), ("limit", "500")] + extra, ttl=6 * 3600)
                except APIError:
                    continue
                _parse(data.get("events") or [], seen, out)
                del data
        return out
    for month in _months(as_of, months):
        y, m = int(month[:4]), int(month[4:])
        month_done = (y, m) < (today.year, today.month)
        for extra in extras:
            try:
                evs = _events(http, path, month, extra, month_done)
                if len(evs) >= 1000:              # ESPN stops at 1,000: fetch that month a day at a time
                    evs = None
                    d = dt.date(y, m, 1)
                    while d.month == m and d <= today:
                        _parse(_events(http, path, d.strftime("%Y%m%d"), extra, d < today - dt.timedelta(2)), seen, out)
                        d += dt.timedelta(1)
                    continue
            except APIError:
                continue
            _parse(evs, seen, out)
            del evs
    return out


_RESULTS: dict[tuple[str, dt.date], list[tuple]] = {}


def results(name: str, as_of: dt.date, http: CachedJSON | None = None) -> list[tuple]:
    """(date, home, away, home score, away score, neutral) for every finished game before ``as_of``.

    The season is downloaded once a day per league; replays of earlier days just use the games before them."""
    today = dt.datetime.now(live.EASTERN).date()
    key = (name, today)
    with _LOCK:
        games = _RESULTS.get(key)
    if games is None:
        games = _download(name, max(as_of, today), http or CachedJSON())
        with _LOCK:
            for k in [k for k in _RESULTS if k[1] != today]:
                del _RESULTS[k]
            _RESULTS[key] = games
    return [g for g in games if g[0] < as_of]


def lower_tier(name: str, games: list[tuple], http: CachedJSON | None = None) -> set[str]:
    """Teams from a lower level that should get their own average: FCS in college football, and non-Division I
    visitors (teams with only a game or two in the data) in college basketball."""
    if name == "College Football":
        http = http or CachedJSON()
        try:
            data = http.get("https://site.api.espn.com/apis/v2/sports/football/college-football/standings",
                            [("group", "80")], ttl=7 * 86400)
        except APIError:
            return set()
        fbs: set[str] = set()

        def walk(o):
            if isinstance(o, dict):
                for e in (o.get("standings") or {}).get("entries") or []:
                    fbs.add((e.get("team") or {}).get("displayName", ""))
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(data)
        if len(fbs) < 100:
            return set()
        return {t for g in games for t in (g[1], g[2]) if t not in fbs}
    if name == "Men's College Basketball":
        played: dict[str, int] = {}
        for g in games:
            for team in (g[1], g[2]):
                played[team] = played.get(team, 0) + 1
        return {team for team, n in played.items() if n <= 2}
    return set()


def params(name: str) -> dict:
    """Settings for a league: tuned values (tools/tune_ratings.py) over the hand-picked defaults."""
    cap, prior, _, _, home_edge = SETUP.get(name, SOCCER)
    base = {"cap": cap, "prior": prior, "home_edge": home_edge, "half_life": HALF_LIFE_DAYS}
    tuned = TUNED.get(name) or (TUNED.get("Soccer") if name not in SETUP else None) or {}
    return {**base, **{k: v for k, v in tuned.items() if k in base}}


def fit(name: str, games: list[tuple], as_of: dt.date, tier: set[str] | None = None, **override) -> Ratings | None:
    s = {**params(name), **override}
    cap, prior, home_edge, half_life = s["cap"], s["prior"], s["home_edge"], s["half_life"]
    if len(games) < 10:
        return None
    teams = sorted({g[1] for g in games} | {g[2] for g in games})
    idx = {t: i for i, t in enumerate(teams)}
    n, k = len(games), len(teams)
    tier = tier or set()
    X = np.zeros((n, k + 1))                 # last column: "lower tier" (FCS...), which gets its own average
    y = np.zeros(n)
    w = np.zeros(n)
    for r, (when, home, away, hs, as_, neutral) in enumerate(games):
        X[r, idx[home]], X[r, idx[away]] = 1.0, -1.0
        X[r, k] = (home in tier) - (away in tier)
        # take the home edge off first, then cap the blowout, except between levels (FBS vs FCS): there the
        # size of the blowout is exactly what tells us how far apart the levels are
        m = hs - as_ - (0.0 if neutral else home_edge)
        y[r] = m if (home in tier) != (away in tier) else np.clip(m, -cap, cap)
        w[r] = 0.5 ** ((as_of - when).days / half_life)
    # ridge: like every team also playing `prior` games against an average team
    reg = np.full(k + 1, prior * float(w.mean()))
    reg[k] = 1e-6
    A = X.T @ (X * w[:, None]) + np.diag(reg)
    b = X.T @ (w * y)
    sol = np.linalg.solve(A, b)
    resid = y - X @ sol
    played: dict[str, int] = {}
    for g in games:
        played[g[1]] = played.get(g[1], 0) + 1
        played[g[2]] = played.get(g[2], 0) + 1
    rating = {t: float(sol[idx[t]] + (sol[k] if t in tier else 0.0)) for t in teams}
    return Ratings(name, rating, played, home_edge, float(np.sqrt(np.average(resid ** 2, weights=w))), n,
                   team_notes(games, rating, played))


def team_notes(games: list[tuple], rating: dict[str, float], played: dict[str, int]) -> dict[str, TeamNote]:
    """Rank, schedule strength, record and recent margins for every rated team."""
    # Records and recent form count this season only: it starts after the last long break in the schedule.
    days = sorted({g[0] for g in games})
    season_start = days[0] if days else dt.date.min
    for a_, b_ in zip(days, days[1:]):
        if (b_ - a_).days > 70:          # an off-season, not a mid-season break (e.g. a World Cup pause)
            season_start = b_
    opp: dict[str, list[float]] = {}
    hist: dict[str, list[tuple]] = {}
    for when, home, away, hs, as_, _ in games:
        for team, other, margin in ((home, away, hs - as_), (away, home, as_ - hs)):
            opp.setdefault(team, []).append(rating.get(other, 0.0))
            if when >= season_start:
                hist.setdefault(team, []).append((when, margin))
    # ranks among teams playing this season (relegated or finished teams keep a rating but aren't ranked)
    rated = sorted((t for t in rating if played.get(t, 0) >= MIN_GAMES and len(hist.get(t, [])) >= 3),
                   key=lambda t: -rating[t])
    rank = {t: i + 1 for i, t in enumerate(rated)}
    sos = {t: float(np.mean(v)) for t, v in opp.items()}
    sos_rank = {t: i + 1 for i, t in enumerate(sorted((t for t in rated), key=lambda t: -sos[t]))}
    out = {}
    for t in rated:
        h = sorted(hist.get(t, []), key=lambda x: x[0], reverse=True)
        out[t] = TeamNote(rank[t], len(rated), sos[t], sos_rank[t], sum(m > 0 for _, m in h), sum(m < 0 for _, m in h),
                          [m for _, m in h[:5]], sum(m == 0 for _, m in h))
    return out


_CACHE: dict[tuple[str, dt.date], Ratings | None] = {}
_LOCK = threading.Lock()


def get(name: str, as_of: dt.date | None = None) -> Ratings | None:
    """Ratings for a league using games before ``as_of`` (default: today), cached per day."""
    as_of = as_of or dt.datetime.now(live.EASTERN).date()
    key = (name, as_of)
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
    try:
        with heavy():                                # one big download/fit at a time (512 MB server)
            with _LOCK:
                if key in _CACHE:                    # fitted by someone else while we waited
                    return _CACHE[key]
            games = results(name, as_of)
            r = fit(name, games, as_of, lower_tier(name, games))
    except Exception:                                # ratings are an extra: never break a page over them
        r = None
    with _LOCK:
        _CACHE[key] = r
        if len(_CACHE) > 400:
            _CACHE.pop(next(iter(_CACHE)))
    return r
