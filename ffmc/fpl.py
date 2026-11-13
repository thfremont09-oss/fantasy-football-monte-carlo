"""Fantasy Premier League Monte Carlo.

Same idea as the NFL and March Madness models, built around how soccer works:

1. Team strength from this season's results: how many goals each club
   scores and concedes compared with the league average.
2. For each simulated gameweek, every fixture is played: each team's goals
   are drawn from its expected goals, and each goal (and assist) is handed to
   one of the players on the pitch in proportion to their xG (xA) per 90.
3. FPL points follow from that: appearance, goals, assists, clean sheets,
   goals conceded, saves, defensive contributions and bonus points.

Data: the official, public FPL API (no login needed).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .http import APIError, CachedJSON

API = "https://fantasy.premierleague.com/api"
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
GOAL_POINTS = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}
CLEAN_SHEET_POINTS = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}
DEFCON_THRESHOLD = {"DEF": 10, "MID": 12, "FWD": 12}      # tackles/blocks/etc. for +2
XI_LIMITS = {"GK": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}   # (min, max) in a starting XI
MAX_PER_CLUB = 3
PRIOR_GAMES = 4          # pull early-season team ratings toward average
ASSIST_RATE = 0.75       # share of goals that have an assist

FPLError = APIError


@dataclass
class FPLPlayer:
    id: int
    name: str
    position: str
    team: int
    team_short: str
    price: float
    fpl_projection: float     # FPL's own "expected points" for the gameweek
    start_prob: float         # chance of starting (plays 60+ minutes)
    sub_prob: float           # chance of a short appearance off the bench
    xg90: float
    xa90: float
    saves90: float
    defcon90: float
    status: str
    news: str = ""
    photo: str | None = None
    fixtures: list[str] = field(default_factory=list)   # e.g. ["CHE (H)"]


@dataclass
class Gameweek:
    id: int
    name: str
    deadline: str
    players: list[FPLPlayer]
    fixtures: list[dict]              # {"home", "away", "home_xg", "away_xg"}
    teams: dict[int, str]             # id -> short name
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ data
class FPLClient:
    def __init__(self, cache_dir=".ffmc_cache"):
        self.http = CachedJSON(cache_dir)

    def bootstrap(self) -> dict:
        return self.http.get(f"{API}/bootstrap-static/", ttl=1800)

    def fixtures(self) -> list[dict]:
        return self.http.get(f"{API}/fixtures/", ttl=1800)

    def entry(self, team_id: int) -> dict:
        return self.http.get(f"{API}/entry/{team_id}/", ttl=600)

    def picks(self, team_id: int, event: int) -> dict:
        return self.http.get(f"{API}/entry/{team_id}/event/{event}/picks/", ttl=600)


def team_strengths(fixtures: list[dict], team_ids: list[int]) -> tuple[dict, dict, float, float]:
    """Attack and defence ratings (1.0 = league average) from finished matches."""
    done = [f for f in fixtures if f.get("finished") and f.get("team_h_score") is not None]
    home_avg = np.mean([f["team_h_score"] for f in done]) if done else 1.5
    away_avg = np.mean([f["team_a_score"] for f in done]) if done else 1.2
    avg = (home_avg + away_avg) / 2
    scored = {t: 0.0 for t in team_ids}
    conceded = {t: 0.0 for t in team_ids}
    games = {t: 0 for t in team_ids}
    for f in done:
        h, a = f["team_h"], f["team_a"]
        scored[h] += f["team_h_score"]; conceded[h] += f["team_a_score"]; games[h] += 1
        scored[a] += f["team_a_score"]; conceded[a] += f["team_h_score"]; games[a] += 1
    attack = {t: (scored[t] + PRIOR_GAMES * avg) / (games[t] + PRIOR_GAMES) / avg for t in team_ids}
    defence = {t: (conceded[t] + PRIOR_GAMES * avg) / (games[t] + PRIOR_GAMES) / avg for t in team_ids}
    return attack, defence, float(home_avg), float(away_avg)


def load_gameweek(client: FPLClient, event: int | None = None) -> Gameweek:
    boot = client.bootstrap()
    events = boot["events"]
    if event is None:
        nxt = next((e for e in events if e.get("is_next")), None) or next(
            (e for e in events if not e.get("finished")), None)
        if nxt is None:
            raise FPLError("The FPL season is over - no upcoming gameweek.")
        event = nxt["id"]
    ev = next(e for e in events if e["id"] == event)
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}

    all_fixtures = client.fixtures()
    attack, defence, home_avg, away_avg = team_strengths(all_fixtures, list(teams))
    team_games = {t: 0 for t in teams}
    for f in all_fixtures:
        if f.get("finished"):
            team_games[f["team_h"]] += 1
            team_games[f["team_a"]] += 1

    fixtures = []
    playing: dict[int, list[str]] = {}
    for f in all_fixtures:
        if f.get("event") != event:
            continue
        h, a = f["team_h"], f["team_a"]
        fixtures.append({"home": h, "away": a,
                         "home_xg": home_avg * attack[h] * defence[a],
                         "away_xg": away_avg * attack[a] * defence[h]})
        playing.setdefault(h, []).append(f"{teams[a]} (H)")
        playing.setdefault(a, []).append(f"{teams[h]} (A)")

    players = []
    for e in boot["elements"]:
        if e["team"] not in playing or e.get("status") in ("u", "n"):   # left club / not eligible
            continue
        chance = e.get("chance_of_playing_next_round")
        avail = 1.0 if chance is None and e.get("status") == "a" else (chance or 0) / 100
        games = max(team_games.get(e["team"], 0), 1)
        start = min(1.0, (e.get("starts") or 0) / games)
        cameo_minutes = max(0.0, (e.get("minutes") or 0) - 85 * (e.get("starts") or 0))
        sub = min(1.0 - start, cameo_minutes / 25 / games)
        players.append(FPLPlayer(
            id=e["id"], name=e["web_name"], position=POSITIONS[e["element_type"]], team=e["team"],
            team_short=teams[e["team"]], price=e["now_cost"] / 10,
            fpl_projection=float(e.get("ep_next") or 0), start_prob=start * avail, sub_prob=sub * avail,
            xg90=float(e.get("expected_goals_per_90") or 0), xa90=float(e.get("expected_assists_per_90") or 0),
            saves90=float(e.get("saves_per_90") or 0), defcon90=float(e.get("defensive_contribution_per_90") or 0),
            status=e.get("status", "a"), news=e.get("news") or "",
            photo=f"https://resources.premierleague.com/premierleague/photos/players/110x140/p{e['code']}.png",
            fixtures=playing[e["team"]],
        ))
    notes = []
    if not any(f.get("finished") for f in all_fixtures):
        notes.append("No matches played yet this season: every team is rated as league average.")
    blank = [teams[t] for t in teams if t not in playing]
    if blank:
        notes.append("Not playing this gameweek: " + ", ".join(sorted(blank)) + ".")
    double = [teams[t] for t, fx in playing.items() if len(fx) > 1]
    if double:
        notes.append("Playing twice this gameweek: " + ", ".join(sorted(double)) + ".")
    return Gameweek(event, ev["name"], ev["deadline_time"], players, fixtures, teams, notes)


# --------------------------------------------------------------- Monte Carlo
def simulate(gw: Gameweek, players: list[FPLPlayer], n_sims: int = 10_000,
             seed: int | None = None) -> np.ndarray:
    """Return points[sim, player] for ``n_sims`` simulated gameweeks."""
    rng = np.random.default_rng(seed)
    points = np.zeros((n_sims, len(players)), dtype=np.float32)   # float32: half the memory, plenty of precision
    for fx in gw.fixtures:
        goals = {fx["home"]: rng.poisson(fx["home_xg"], n_sims),      # 1. play the match
                 fx["away"]: rng.poisson(fx["away_xg"], n_sims)}
        in_match, base = [], []
        for team, opp in ((fx["home"], fx["away"]), (fx["away"], fx["home"])):
            # Only players with some chance of playing; the rest always score 0.
            idx = [i for i, p in enumerate(players) if p.team == team and p.start_prob + p.sub_prob > 0]
            if not idx:
                continue
            squad = [players[i] for i in idx]
            pts = player_points(rng, squad, goals[team], goals[opp])    # 2. hand out the points
            points[:, idx] += pts
            in_match += idx
            base.append(pts)
        if in_match:                                                     # 3. bonus: top 3 in the match
            points[:, in_match] += bonus_points(np.hstack(base))
    return points


def _at_least(lam: float, k: int) -> float:
    """P(Poisson(lam) >= k)."""
    if k >= 999 or lam <= 0:
        return 0.0
    term, cdf = math.exp(-lam), 0.0
    for i in range(k):
        cdf += term
        term *= lam / (i + 1)
    return max(0.0, 1.0 - cdf)


def player_points(rng, squad: list[FPLPlayer], team_goals: np.ndarray, opp_goals: np.ndarray) -> np.ndarray:
    n, k = len(team_goals), len(squad)
    pos = [p.position for p in squad]
    f32 = np.float32

    # Who plays? A roll of the dice per player per simulation.
    roll = rng.random((n, k), dtype=f32)
    start_p = np.array([p.start_prob for p in squad], f32)
    started = roll < start_p
    cameo = ~started & (roll < start_p + np.array([p.sub_prob for p in squad], f32))
    on_pitch = started.astype(f32) + cameo * f32(0.3)        # share of the match each player is on for

    # Goals and assists go to players on the pitch, weighted by their xG / xA per 90.
    scorers = share_out(rng, team_goals, on_pitch * np.array([p.xg90 for p in squad], f32))
    assisters = share_out(rng, rng.binomial(team_goals, ASSIST_RATE), on_pitch * np.array([p.xa90 for p in squad], f32))

    pts = started * f32(2) + cameo * f32(1)                                                # appearance
    pts += scorers * np.array([GOAL_POINTS[x] for x in pos], f32) + assisters * f32(3)    # goals, assists
    clean = started & (opp_goals == 0)[:, None]
    pts += clean * np.array([CLEAN_SHEET_POINTS[x] for x in pos], f32)                    # clean sheet
    back = [j for j, x in enumerate(pos) if x in ("GK", "DEF")]
    pts[:, back] -= started[:, back] * (opp_goals[:, None] // 2).astype(f32)               # -1 per 2 conceded
    keepers = [j for j, x in enumerate(pos) if x == "GK"]
    if keepers:                                                                            # 1 per 3 saves
        saves = rng.poisson(np.array([squad[j].saves90 for j in keepers]), (n, len(keepers)))
        pts[:, keepers] += started[:, keepers] * (saves // 3).astype(f32)
    p_defcon = np.array([_at_least(p.defcon90, DEFCON_THRESHOLD.get(p.position, 999)) for p in squad], f32)
    hit = rng.random((n, k), dtype=f32) < p_defcon
    pts += (started & hit) * f32(2)                                                        # defensive contribution
    return pts


def share_out(rng, counts: np.ndarray, weights: np.ndarray, other: float = 0.1) -> np.ndarray:
    """Give each of ``counts[s]`` events to a player, chosen in proportion to ``weights[s]``.

    ``other`` is the weight of everyone else (subs not modelled, own goals...).
    """
    n, k = weights.shape
    out = np.zeros(n * k, dtype=np.int32)
    cum = np.cumsum(np.hstack([weights, np.full((n, 1), other, weights.dtype)]), axis=1)
    rows = np.arange(n)
    for g in range(int(counts.max(initial=0))):
        active = np.flatnonzero(counts > g)                  # only simulations with another goal to give
        u = rng.random(len(active), dtype=cum.dtype) * cum[active, -1]
        pick = (cum[active] < u[:, None]).sum(axis=1)
        keep = pick < k
        out += np.bincount(rows[active[keep]] * k + pick[keep], minlength=n * k).astype(np.int32)
    return out.reshape(n, k)


def bonus_points(base: np.ndarray) -> np.ndarray:
    """3, 2 and 1 bonus points to the three best performers in each simulated match."""
    bonus = np.zeros_like(base)
    m = min(3, base.shape[1])
    part = np.argpartition(-base, m - 1, axis=1)[:, :m]                    # top 3, unordered
    rows = np.arange(base.shape[0])[:, None]
    order = np.argsort(-base[rows, part], axis=1)
    top = part[rows, order]
    bonus[rows, top] = np.array([3, 2, 1], base.dtype)[:m] * (base[rows, top] > 1)
    return bonus


# --------------------------------------------------------------- team picking
def pick_xi(values: np.ndarray, players: list[FPLPlayer], allowed: np.ndarray | None = None) -> list[int]:
    """Best starting XI by ``values`` in a valid formation.

    Choosing from every player (``allowed`` is None), at most 3 per club, as in a
    real FPL squad. Choosing from your own squad, that rule was already met.
    """
    club_limit = MAX_PER_CLUB if allowed is None else 11
    count = {p: 0 for p in XI_LIMITS}
    clubs: dict[int, int] = {}
    xi: list[int] = []
    for i in np.argsort(-values):
        if allowed is not None and not allowed[i]:
            continue
        p = players[i]
        lo, hi = XI_LIMITS[p.position]
        if count[p.position] >= hi or clubs.get(p.team, 0) >= club_limit:
            continue
        count[p.position] += 1
        still_needed = sum(max(0, XI_LIMITS[q][0] - count[q]) for q in XI_LIMITS)
        if len(xi) + 1 + still_needed > 11:          # would leave no room for a required position
            count[p.position] -= 1
            continue
        xi.append(int(i))
        clubs[p.team] = clubs.get(p.team, 0) + 1
        if len(xi) == 11:
            break
    return xi


SQUAD_SIZE = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}     # a full FPL squad: 15 players
DEFAULT_BUDGET = 100.0                                      # £m


def _valid_xi(xi: list[int], players: list[FPLPlayer]) -> bool:
    count = {p: 0 for p in XI_LIMITS}
    clubs: dict[int, int] = {}
    for i in xi:
        count[players[i].position] += 1
        clubs[players[i].team] = clubs.get(players[i].team, 0) + 1
    return (len(xi) == 11 and all(lo <= count[p] <= hi for p, (lo, hi) in XI_LIMITS.items())
            and max(clubs.values()) <= MAX_PER_CLUB)


def _cheapest_bench(xi: list[int], players: list[FPLPlayer], by_price: dict[str, list[int]]):
    """The 4 cheapest players that complete a legal 15-man squad around ``xi``."""
    taken = set(xi)
    clubs: dict[int, int] = {}
    for i in xi:
        clubs[players[i].team] = clubs.get(players[i].team, 0) + 1
    bench, cost = [], 0.0
    for pos, size in SQUAD_SIZE.items():
        need = size - sum(players[i].position == pos for i in xi)
        for i in by_price[pos]:
            if need <= 0:
                break
            if i in taken or clubs.get(players[i].team, 0) >= MAX_PER_CLUB:
                continue
            bench.append(i)
            clubs[players[i].team] = clubs.get(players[i].team, 0) + 1
            need -= 1
            cost += players[i].price
        if need > 0:
            return None, float("inf")
    return bench, cost


def pick_squad(values: np.ndarray, players: list[FPLPlayer], budget: float = DEFAULT_BUDGET):
    """Best XI whose full 15-man squad (XI + cheapest legal bench) fits ``budget`` (£m).

    Starts from the best XI with no budget, then makes the swaps that give up the
    fewest points per £ saved until it fits, then spends any money left over on
    upgrades. Returns (xi, bench, squad cost).
    """
    by_price = {pos: sorted((i for i, p in enumerate(players) if p.position == pos),
                            key=lambda i: (players[i].price, -values[i])) for pos in SQUAD_SIZE}
    # Swap candidates: the best players in each position, plus the cheapest ones.
    cands = set()
    for pos in SQUAD_SIZE:
        ranked = sorted((i for i, p in enumerate(players) if p.position == pos), key=lambda i: -values[i])
        cands |= set(ranked[:45]) | set(by_price[pos][:12])

    def total(xi):
        bench, bench_cost = _cheapest_bench(xi, players, by_price)
        return sum(players[i].price for i in xi) + bench_cost, bench

    xi = pick_xi(values, players)
    cost, bench = total(xi)
    while cost > budget + 1e-9:                                   # 1. trim until it fits
        best = None
        for k, i in enumerate(xi):
            for j in cands:
                if j in xi:
                    continue
                new = xi[:k] + [j] + xi[k + 1:]
                if not _valid_xi(new, players):
                    continue
                c, b = total(new)
                saved = cost - c
                if saved <= 0 or b is None:
                    continue
                loss = (values[i] - values[j]) / saved
                if best is None or loss < best[0]:
                    best = (loss, new, c, b)
        if best is None:
            raise FPLError(f"No legal squad fits a £{budget:.1f}m budget.")
        _, xi, cost, bench = best
    while True:                                                   # 2. spend what's left
        best = None
        for k, i in enumerate(xi):
            for j in cands:
                if j in xi or values[j] <= values[i]:
                    continue
                new = xi[:k] + [j] + xi[k + 1:]
                if not _valid_xi(new, players):
                    continue
                c, b = total(new)
                if c <= budget + 1e-9 and b is not None and (best is None or values[j] - values[i] > best[0]):
                    best = (values[j] - values[i], new, c, b)
        if best is None:
            break
        _, xi, cost, bench = best
    return xi, bench, cost


@dataclass
class Result:
    xi: list[int]
    bench: list[int]
    captain: int
    vice: int
    mean: np.ndarray            # simulated average points per player
    p10: np.ndarray
    p90: np.ndarray
    best_captain_pct: np.ndarray    # share of sims in which the player outscored the rest of the XI
    in_best_xi_pct: np.ndarray      # share of sims in which the player made the hindsight-best XI
    totals: np.ndarray          # simulated XI totals, captain doubled
    squad_cost: float | None = None  # £m, when a budget was used


SELECT_SIMS = 50_000    # simulations used to choose the team; the rest only measure it


def run(gw: Gameweek, players: list[FPLPlayer], n_sims: int = 25_000, seed: int | None = None,
        squad: list[int] | None = None, budget: float | None = None, progress=None) -> Result:
    """Simulate the gameweek and pick the XI, bench and captain.

    ``squad``: indices of your 15 players. Without it, the best XI from every
    player is chosen; with ``budget`` (£m) the whole 15-man squad must fit it.

    The team is chosen from up to 50,000 simulated gameweeks, then measured on
    ``n_sims`` fresh ones, run in batches so even a million fit in memory.
    """
    from .stream import Tally, batches

    rng = np.random.default_rng(seed)
    select_seed, measure_seed = (int(x) for x in rng.integers(0, 2**32, size=2))

    # 1. Choose the team.
    sims = simulate(gw, players, min(n_sims, SELECT_SIMS), select_seed)
    mean = sims.mean(axis=0)
    allowed = None
    squad_cost = None
    if squad is None and budget is not None:
        xi, bench_pick, squad_cost = pick_squad(mean, players, budget)
        squad = xi + bench_pick
    if squad is not None:
        allowed = np.zeros(len(players), bool)
        allowed[squad] = True
    xi = pick_xi(mean, players, allowed)
    pool = squad if squad is not None else xi
    bench = sorted((i for i in pool if i not in xi), key=lambda i: (players[i].position != "GK", -mean[i]))
    by_mean = sorted(xi, key=lambda i: -mean[i])
    captain, vice = by_mean[0], by_mean[1]

    in_best = np.zeros(len(players))
    sample = sims[:2000]                              # hindsight XI is slow per row; a sample is plenty
    for row in sample:
        in_best[pick_xi(row, players, allowed)] += 1
    in_best_pct = 100 * in_best / len(sample)
    del sims

    # 2. Measure it on fresh simulations, in batches.
    tally = Tally(len(players), lo=-10, hi=80, step=1)      # FPL points are whole numbers
    top = np.zeros(len(players))
    totals = []
    done = 0
    for size, batch_seed in batches(n_sims, measure_seed, batch=25_000):
        sims = simulate(gw, players, size, batch_seed)
        tally.add(sims)
        xi_sims = sims[:, xi]
        np.add.at(top, np.array(xi)[xi_sims.argmax(axis=1)], 1)
        totals.append(xi_sims.sum(axis=1) + sims[:, captain])
        done += size
        if progress:
            progress(done / n_sims)
    return Result(xi, bench, captain, vice, tally.mean, tally.percentile(10), tally.percentile(90),
                  100 * top / n_sims, in_best_pct, np.concatenate(totals), squad_cost)


def load_squad(client: FPLClient, gw: Gameweek, team_id: int) -> tuple[list[int], str, list[str]]:
    """Your 15 players (as indices into ``gw.players``), team name and notes.

    FPL only makes a team's picks public once a gameweek's deadline has passed,
    so this reads your squad from the most recent gameweek; transfers made since
    then won't show up yet.
    """
    entry = client.entry(team_id)
    last = entry.get("current_event")
    if not last:
        raise FPLError("That team hasn't played a gameweek yet.")
    picks = client.picks(team_id, last)["picks"]
    index = {p.id: i for i, p in enumerate(gw.players)}
    squad = [index[p["element"]] for p in picks if p["element"] in index]
    notes = [f"Squad as of gameweek {last}. Transfers made since then are not included."]
    if len(squad) < len(picks):
        notes.append(f"{len(picks) - len(squad)} of your players aren't playing this gameweek "
                     "(blank fixture, injury or suspension).")
    return squad, entry.get("name", f"Team {team_id}"), notes
