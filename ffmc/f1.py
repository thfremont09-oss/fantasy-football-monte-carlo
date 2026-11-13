"""F1 Fantasy (the official game in the F1 app): pick 5 drivers and 2 constructors under
a budget, with a DRS Boost that doubles one driver's points.

Data
* Official F1 Fantasy feeds: every driver's and constructor's price, team and
  F1 Fantasy points in each past round.
* Jolpica (the open F1 results database): every 2026 race, with grid, finish,
  retirements and teams, for each driver's recent form.
* Kalshi (when the race is listed): market odds for the winner, podium, top 5,
  top 10, pole, fastest lap and fastest pit stop.

Monte Carlo
Each simulated weekend draws a qualifying order and a race result (with
retirements) from each driver's expected position plus random luck, then scores
it with F1 Fantasy's rules: qualifying and race positions, places gained or lost,
overtakes, fastest lap, Driver of the Day, -20 for a DNF, and for constructors
both cars plus the Q2/Q3 bonus and pit-stop points.
"""

from __future__ import annotations

import datetime as dt
import itertools
import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np

from .http import APIError, CachedJSON
from .stream import Progress, Tally, batches

FEEDS = "https://fantasy.formula1.com/feeds"
JOLPICA = "https://api.jolpi.ca/ergast/f1/{season}"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2/markets"
UA = {"User-Agent": "Mozilla/5.0 (monte-carlo-sports-lab)"}

N_DRIVERS, N_CONSTRUCTORS = 5, 2
DEFAULT_BUDGET = 100.0                 # $m, what every F1 Fantasy team starts with
RACE_POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
SPRINT_POINTS = [8, 7, 6, 5, 4, 3, 2, 1]
QUALI_POINTS = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
DNF_POINTS = -20
FASTEST_LAP, SPRINT_FASTEST_LAP, DRIVER_OF_THE_DAY = 10, 5, 10
PIT_BANDS = np.array([20, 10, 5, 2, 0])                 # pit stop under 2.0s, 2.0-2.19, 2.2-2.49, 2.5-2.99, slower
PIT_BAND_P = np.array([0.03, 0.22, 0.40, 0.28, 0.07])
FASTEST_PIT = 5
RACE_SD, QUALI_SD = 3.2, 2.6            # luck, in grid places
FORM_RACES = 6                          # recent races used for form
BASE_DNF = 0.08                         # typical retirement rate, used to steady small samples


@dataclass
class Asset:
    id: str
    name: str
    kind: str                           # "driver" or "constructor"
    team: str
    price: float
    code: str = ""                      # three-letter code, e.g. VER
    season_points: float = 0.0
    recent: list[float] = field(default_factory=list)   # F1 Fantasy points in recent rounds, oldest first
    selected: float = 0.0               # % of F1 Fantasy teams that own them
    # model inputs (drivers)
    exp_finish: float = 15.0
    exp_grid: float = 15.0
    dnf: float = BASE_DNF
    form_finish: float | None = None
    market_finish: float | None = None
    win: float | None = None            # Kalshi race-winner chance
    fastlap: float | None = None


@dataclass
class Weekend:
    season: int
    round: int
    name: str
    date: str
    deadline: str
    sprint: bool
    gameday: int
    budget_cap: float
    market: bool = False                # Kalshi odds were found
    races_used: int = 0


# ------------------------------------------------------------------ data
def _plain(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\b(jr|sr)\b\.?", "", s).strip()


def _surname(s: str) -> str:
    parts = _plain(s).split()
    return parts[-1] if parts else ""


def _feed(http: CachedJSON, path: str, ttl: float) -> dict:
    return http.get(f"{FEEDS}/{path}", ttl=ttl, headers=UA)["Data"]["Value"]


def load_assets(http: CachedJSON, history: int = 5) -> tuple[Weekend, list[Asset]]:
    limits = _feed(http, "limits/constraints.json", 1800)
    gid = int(limits["GamedayId"])
    players = _feed(http, f"drivers/{gid}_en.json", 1800)
    assets = []
    for p in players:
        if str(p.get("IsActive", "1")) != "1":
            continue
        kind = "driver" if p.get("PositionName") == "DRIVER" else "constructor"
        assets.append(Asset(
            id=str(p["PlayerId"]), kind=kind, team=p.get("TeamName", ""),
            name=(p.get("FUllName") or p.get("DisplayName") or p.get("TeamName", "")).strip(),
            price=float(p.get("Value") or 0), code=p.get("DriverTLA") or "",
            season_points=float(p.get("OverallPpints") or 0), selected=float(p.get("SelectedPercentage") or 0)))
    # Points in each recent round (each round's feed has that round's score).
    by_id = {a.id: a for a in assets}
    for g in range(max(1, gid - history), gid):
        try:
            for p in _feed(http, f"drivers/{g}_en.json", 86400 * 7):
                a = by_id.get(str(p["PlayerId"]))
                if a is not None:
                    a.recent.append(float(p.get("GamedayPoints") or 0))
        except (APIError, KeyError):
            continue
    weekend = Weekend(season=dt.date.today().year, round=gid, name="", date="", sprint=False, gameday=gid,
                      deadline=str(limits.get("DeadlineDate", "")),
                      budget_cap=float(limits.get("MaxTeamValue") or DEFAULT_BUDGET))
    return weekend, assets


def load_results(http: CachedJSON, season: int) -> tuple[list[dict], list[dict]]:
    """(every race result this season, the season calendar) from Jolpica."""
    base = JOLPICA.format(season=season)
    races: dict[str, dict] = {}
    offset, total = 0, 1
    while offset < total:
        data = http.get(f"{base}/results.json", [("limit", "100"), ("offset", str(offset))], ttl=6 * 3600)["MRData"]
        total = int(data["total"])
        for r in data["RaceTable"]["Races"]:
            races.setdefault(r["round"], {**r, "Results": []})["Results"] += r["Results"]
        offset += 100
        if not data["RaceTable"]["Races"]:
            break
    calendar = http.get(f"{base}.json", ttl=86400)["MRData"]["RaceTable"]["Races"]
    return sorted(races.values(), key=lambda r: int(r["round"])), calendar


def apply_form(drivers: list[Asset], races: list[dict]) -> int:
    """Each driver's recent average finish and grid, and their retirement rate."""
    recent = races[-FORM_RACES:]
    weights = np.linspace(0.6, 1.0, len(recent)) if recent else []
    for d in drivers:
        fin, grid, w_sum, dnfs, starts = 0.0, 0.0, 0.0, 0, 0
        for w, race in zip(weights, recent):
            row = next((x for x in race["Results"] if x["Driver"].get("code") == d.code
                        or _surname(x["Driver"].get("familyName", "")) == _surname(d.name)), None)
            if row is None:
                continue
            out = row["status"] not in ("Finished", "Lapped") and not row["status"].startswith("+")
            pos = float(row["position"]) if not out else 18.0     # a retirement counts as a poor result
            g = float(row["grid"]) if row.get("grid") not in (None, "0") else 20.0
            fin, grid, w_sum = fin + w * pos, grid + w * g, w_sum + w
            dnfs, starts = dnfs + out, starts + 1
        if w_sum:
            d.form_finish, d.exp_grid = fin / w_sum, grid / w_sum
        d.dnf = (dnfs + 3 * BASE_DNF) / (starts + 3)
    return len(recent)


def _kalshi(http: CachedJSON, series: str) -> dict[str, float]:
    """Driver/team name -> chance, for the next open event in a Kalshi F1 series."""
    try:
        markets = http.get(KALSHI, [("series_ticker", series), ("status", "open"), ("limit", "200")],
                           ttl=600).get("markets", [])
    except APIError:
        return {}
    if not markets:
        return {}
    event = sorted({m["event_ticker"] for m in markets})[0]
    out = {}
    for m in markets:
        if m["event_ticker"] != event:
            continue
        bid, ask = float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 0)
        p = (bid + ask) / 2 if ask > 0 else float(m.get("last_price_dollars") or 0)
        out[m.get("yes_sub_title") or ""] = max(min(p, 0.99), 0.0)
    return out


def implied_finish(win: float, podium: float, top5: float, top10: float, n: int) -> float:
    """Expected finishing position from the market's chances of finishing 1st, top 3, top 5, top 10."""
    pts = {0: 1.0, 1: win, 3: podium, 5: top5, 10: top10, n: 0.0}
    ks = sorted(pts)
    probs = [pts[k] for k in ks]
    # P(finish within k) is non-decreasing in k; fix any market noise.
    probs = list(np.maximum.accumulate(probs[1:-1])) if len(probs) > 2 else []
    xs, ys = [1, 3, 5, 10, n], probs + [1.0]
    within = np.interp(np.arange(1, n + 1), xs, ys)
    return float(1 + np.sum(1 - within[:-1]))


def apply_market(http: CachedJSON, drivers: list[Asset]) -> bool:
    series = {k: _kalshi(http, s) for k, s in (("win", "KXF1RACE"), ("podium", "KXF1RACEPODIUM"),
                                                ("top5", "KXF1TOP5"), ("top10", "KXF1TOP10"),
                                                ("fastlap", "KXF1FASTLAP"))}
    if not series["top10"] and not series["win"]:
        return False
    n = len(drivers)
    for d in drivers:
        def get(k):
            return next((p for name, p in series[k].items() if _surname(name) == _surname(d.name)), None)
        win, pod, t5, t10 = get("win"), get("podium"), get("top5"), get("top10")
        if t10 is None and win is None:
            continue
        win = win or 0.0
        pod = max(pod if pod is not None else win * 2.5, win)
        t5 = max(t5 if t5 is not None else pod * 1.5, pod)
        t10 = max(t10 if t10 is not None else t5 * 1.6, t5)
        d.market_finish = implied_finish(win, pod, min(t5, 1), min(t10, 1), n)
        d.win, d.fastlap = win, get("fastlap")
    return any(d.market_finish is not None for d in drivers)


def finalize(drivers: list[Asset]) -> None:
    """Blend recent form and market odds into one expected finish per driver."""
    for d in drivers:
        parts = [(x, w) for x, w in ((d.form_finish, 0.4), (d.market_finish, 0.6)) if x is not None]
        d.exp_finish = sum(x * w for x, w in parts) / sum(w for _, w in parts) if parts else 16.0
        d.exp_grid = 0.5 * d.exp_grid + 0.5 * d.exp_finish if d.form_finish is not None else d.exp_finish


def load_weekend(cache_dir=".ffmc_cache") -> tuple[Weekend, list[Asset]]:
    http = CachedJSON(cache_dir)
    weekend, assets = load_assets(http)
    drivers = [a for a in assets if a.kind == "driver"]
    try:
        races, calendar = load_results(http, weekend.season)
    except APIError:
        races, calendar = [], []
    weekend.races_used = apply_form(drivers, races)
    done = {r["round"] for r in races}
    nxt = next((r for r in calendar if r["round"] not in done), None)
    if nxt:
        weekend.round, weekend.name, weekend.date = int(nxt["round"]), nxt["raceName"], nxt["date"]
        weekend.sprint = "Sprint" in nxt
    weekend.market = apply_market(http, drivers)
    finalize(drivers)
    return weekend, assets


# -------------------------------------------------------------- simulation
def _order(perf: np.ndarray) -> np.ndarray:
    """Finishing position (1 = best) of each driver from a (sims, drivers) performance array."""
    ranks = np.empty_like(perf, dtype=np.int16)
    idx = np.argsort(-perf, axis=1)
    np.put_along_axis(ranks, idx, np.arange(1, perf.shape[1] + 1, dtype=np.int16)[None, :], axis=1)
    return ranks


def _table(pos: np.ndarray, table: list[int]) -> np.ndarray:
    lut = np.zeros(max(int(pos.max()) if pos.size else 0, len(table)) + 2, dtype=np.float32)
    lut[1:len(table) + 1] = table
    return lut[np.minimum(pos, len(lut) - 1)]


def _pick(rng, logw: np.ndarray, allowed: np.ndarray) -> np.ndarray:
    """One winner per row, chosen with probability proportional to exp(logw), among allowed drivers."""
    g = logw[None, :] + rng.gumbel(size=allowed.shape)
    g[~allowed] = -np.inf
    return np.argmax(g, axis=1)


def _race(rng, n, exp_finish, dnf, grid, weekend_luck, points, fl_points, fl_logw, dotd: bool):
    perf = -exp_finish[None, :] + RACE_SD * (0.6 * weekend_luck + 0.8 * rng.standard_normal((n, len(dnf))))
    out = rng.random((n, len(dnf))) < dnf[None, :]
    perf[out] = -1e9                                       # retirements drop to the back
    pos = _order(perf)
    pts = _table(pos, points)
    gained = (grid - pos).astype(np.float32)
    pts += np.where(out, 0, gained)                        # +1 per place gained, -1 per place lost
    pts += np.where(out, 0, 0.7 * np.maximum(gained, 0) + rng.poisson(0.8, gained.shape))   # overtakes
    finished = ~out
    rows = np.arange(n)
    pts[rows, _pick(rng, fl_logw, finished & (pos <= 10))] += fl_points
    driver_of_day = None
    if dotd:     # fans tend to vote for big movers and winners
        vote = np.where(finished, gained + 3 * rng.standard_normal(gained.shape) - 0.3 * pos, -1e9)
        driver_of_day = np.argmax(vote, axis=1)
        pts[rows, driver_of_day] += DRIVER_OF_THE_DAY
    pts[out] = DNF_POINTS
    return pts, driver_of_day


def simulate_batch(rng, drivers: list[Asset], teams: list[str], team_of: np.ndarray, n: int,
                   sprint: bool, pit_logw: np.ndarray) -> np.ndarray:
    """(n, drivers + constructors) F1 Fantasy points for one batch of simulated weekends."""
    k = len(drivers)
    exp_finish = np.array([d.exp_finish for d in drivers])
    exp_grid = np.array([d.exp_grid for d in drivers])
    dnf = np.array([d.dnf for d in drivers])
    fl = np.array([d.fastlap if d.fastlap else 0.0 for d in drivers])
    fl_logw = np.log(fl + 0.005) if fl.any() else -0.25 * exp_finish
    luck = rng.standard_normal((n, k))                      # a driver's weekend: good or bad all round
    qperf = -exp_grid[None, :] + QUALI_SD * (0.6 * luck + 0.8 * rng.standard_normal((n, k)))
    grid = _order(qperf)
    quali = _table(grid, QUALI_POINTS)
    race, dotd = _race(rng, n, exp_finish, dnf, grid, luck, RACE_POINTS, FASTEST_LAP, fl_logw, dotd=True)
    total = quali + race
    cons_driver = quali + race
    rows = np.arange(n)
    cons_driver[rows, dotd] -= DRIVER_OF_THE_DAY            # constructors don't get Driver of the Day
    if sprint:
        sgrid = _order(-exp_grid[None, :] + QUALI_SD * (0.6 * luck + 0.8 * rng.standard_normal((n, k))))
        sp, _ = _race(rng, n, exp_finish, dnf * 0.5, sgrid, luck, SPRINT_POINTS, SPRINT_FASTEST_LAP, fl_logw,
                      dotd=False)
        total += sp
        cons_driver += sp
    nt = len(teams)
    cons = np.zeros((n, nt), dtype=np.float32)
    for t in range(nt):
        cars = np.where(team_of == t)[0]
        if not len(cars):
            continue
        cons[:, t] = cons_driver[:, cars].sum(axis=1)
        q2 = (grid[:, cars] <= 15).sum(axis=1)
        q3 = (grid[:, cars] <= 10).sum(axis=1)
        bonus = np.select([q3 == 2, q3 == 1, q2 == 2, q2 == 1], [10, 5, 3, 1], default=-1)
        cons[:, t] += bonus
        cons[:, t] += PIT_BANDS[rng.choice(len(PIT_BANDS), size=n, p=PIT_BAND_P)]
    cons[rows, _pick(rng, pit_logw, np.ones((n, nt), bool))] += FASTEST_PIT
    return np.concatenate([total, cons], axis=1)


@dataclass
class Team:
    drivers: list[int]          # indexes into the asset list
    constructors: list[int]
    boost: int                  # the DRS Boost driver
    cost: float
    mean: float


FORM_WEIGHT = 0.4      # how far each average is pulled toward the asset's real F1 Fantasy points lately


def form_shift(sim_mean: np.ndarray, assets: list[Asset]) -> np.ndarray:
    """Per-asset nudge toward recent real F1 Fantasy scores (catches what the race model misses,
    like overtakes and pit stops), trusted more with more rounds of history."""
    out = np.zeros(len(assets))
    for i, a in enumerate(assets):
        if a.recent:
            n = len(a.recent)
            out[i] = FORM_WEIGHT * n / (n + 2) * (float(np.mean(a.recent)) - sim_mean[i])
    return out


@dataclass
class Result:
    weekend: Weekend
    assets: list[Asset]
    tally: Tally                # per asset, before the form nudge
    shift: np.ndarray           # form nudge per asset (add to means and percentiles)
    team: Team
    team_tally: Tally           # the chosen team's total, one column
    alternatives: list[Team]
    n_sims: int
    budget: float | None
    boost_mult: int


def _setup(assets: list[Asset]):
    drivers = [a for a in assets if a.kind == "driver"]
    cons = [a for a in assets if a.kind == "constructor"]
    teams = [c.team or c.name for c in cons]
    team_of = np.array([teams.index(d.team) if d.team in teams else -1 for d in drivers])
    return drivers, cons, teams, team_of


def best_teams(means: np.ndarray, prices: np.ndarray, n_drivers: int, budget: float | None,
               boost_mult: int = 2, keep: int = 30, must: set[int] | None = None,
               banned: set[int] | None = None) -> list[Team]:
    """Highest expected-points teams of 5 drivers + 2 constructors within the budget (exact search)."""
    must, banned = must or set(), banned or set()
    d_idx = [i for i in range(n_drivers) if i not in banned]
    c_idx = [i for i in range(n_drivers, len(means)) if i not in banned]
    combos = np.array(list(itertools.combinations(d_idx, N_DRIVERS)))
    if must:
        ok = np.ones(len(combos), bool)
        for m in must:
            if m < n_drivers:
                ok &= (combos == m).any(axis=1)
        combos = combos[ok]
    d_cost = prices[combos].sum(axis=1)
    d_mean = means[combos].sum(axis=1)
    best_in = means[combos].max(axis=1)
    d_val = d_mean + (boost_mult - 1) * best_in
    boost = combos[np.arange(len(combos)), means[combos].argmax(axis=1)]
    out: list[Team] = []
    for pair in itertools.combinations(c_idx, N_CONSTRUCTORS):
        if any(m >= n_drivers for m in must) and not all(m in pair for m in must if m >= n_drivers):
            continue
        c_cost = prices[list(pair)].sum()
        c_mean = means[list(pair)].sum()
        ok = np.ones(len(combos), bool) if budget is None else (d_cost + c_cost <= budget + 1e-9)
        if not ok.any():
            continue
        vals = np.where(ok, d_val, -np.inf)
        top = np.argpartition(-vals, min(3, len(vals) - 1))[:3]
        for t in top:
            if np.isfinite(vals[t]):
                out.append(Team(list(combos[t]), list(pair), int(boost[t]), float(d_cost[t] + c_cost),
                                float(vals[t] + c_mean)))
    out.sort(key=lambda t: -t.mean)
    return out[:keep]


def team_points(pts: np.ndarray, team: Team, boost_mult: int) -> np.ndarray:
    return (pts[:, team.drivers].sum(axis=1) + pts[:, team.constructors].sum(axis=1)
            + (boost_mult - 1) * pts[:, team.boost])


def run(weekend: Weekend, assets: list[Asset], n_sims: int = 1_000_000, budget: float | None = DEFAULT_BUDGET,
        objective: str = "mean", boost_mult: int = 2, seed: int | None = 7, must: set[str] | None = None,
        banned: set[str] | None = None, progress: Progress = None) -> Result:
    drivers, cons, teams, team_of = _setup(assets)
    ordered = drivers + cons
    pit = np.array([0.0] * len(cons))
    pit_logw = pit
    tally = Tally(len(ordered), lo=-60, hi=160, step=0.5)
    sample: list[np.ndarray] = []
    for i, (size, s) in enumerate(batches(n_sims, seed, 50_000)):
        pts = simulate_batch(np.random.default_rng(s), drivers, teams, team_of, size, weekend.sprint, pit_logw)
        tally.add(pts)
        if i == 0:
            sample.append(pts)                               # 50k weekends kept for floor / ceiling picks
        if progress:
            progress(0.85 * (i + 1) * 50_000 / n_sims)
    ids = [a.id for a in ordered]
    must_i = {ids.index(x) for x in (must or set()) if x in ids}
    banned_i = {ids.index(x) for x in (banned or set()) if x in ids}
    prices = np.array([a.price for a in ordered])
    shift = form_shift(tally.mean, ordered)
    means = tally.mean + shift
    cands = best_teams(means, prices, len(drivers), budget, boost_mult, keep=60, must=must_i, banned=banned_i)
    if not cands:
        raise ValueError("No team fits that budget. Try a bigger budget or fewer locked picks.")
    if objective in ("floor", "ceiling"):
        q = 10 if objective == "floor" else 90
        cands.sort(key=lambda t: -np.percentile(team_points(sample[0] + shift, t, boost_mult), q))
    team = cands[0]
    team_tally = Tally(1, lo=-100, hi=500, step=0.5)
    for size, s in batches(n_sims, seed, 50_000):
        pts = simulate_batch(np.random.default_rng(s), drivers, teams, team_of, size, weekend.sprint, pit_logw)
        team_tally.add(team_points(pts + shift, team, boost_mult)[:, None])
    if progress:
        progress(1.0)
    return Result(weekend, ordered, tally, shift, team, team_tally, cands[1:6], n_sims, budget, boost_mult)
