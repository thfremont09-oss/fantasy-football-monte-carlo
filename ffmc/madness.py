"""March Madness Monte Carlo.

1. Rate every team from this season's scores: margin = rating_A - rating_B (+ home edge).
2. Turn two ratings into a win chance (a game's margin varies by about 11 points).
3. Play the 64-team bracket thousands of times and count how far each team gets.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np

from .espn import ROUND_NAMES, ESPNClient, Game

SEED_ORDER = [1, 16, 8, 9, 5, 12, 4, 13, 6, 11, 3, 14, 7, 10, 2, 15]   # top-to-bottom in a region
DEFAULT_REGIONS = ["East", "South", "West", "Midwest"]                 # 0 v 1 and 2 v 3 in the Final Four
ROUND_LABELS = ["Round of 32", "Sweet 16", "Elite 8", "Final Four", "Title game", "Champion"]
ESPN_POINTS = [10, 20, 40, 80, 160, 320]                               # ESPN bracket challenge scoring
GAME_SD = 11.0                                                          # points of randomness per game


# ------------------------------------------------------------------ ratings
def fit_ratings(games: list[Game], prior: dict[str, float] | None = None,
                prior_games: float = 3.0) -> dict[str, float]:
    """Least-squares power ratings: home_score - away_score = r_home - r_away + home_edge.

    Each team is also pulled toward its ``prior`` rating (last season) as if
    it had played ``prior_games`` games at that level; this matters early in
    the season and barely at all by March.
    """
    games = [g for g in games if g.completed and (g.home_score or g.away_score)]
    teams = sorted({g.home_id for g in games} | {g.away_id for g in games} | set(prior or {}))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    X = np.zeros((len(games) + n, n + 1))
    y = np.zeros(len(games) + n)
    for r, g in enumerate(games):
        X[r, idx[g.home_id]], X[r, idx[g.away_id]] = 1, -1
        X[r, n] = 0 if g.neutral else 1                       # home-court edge
        y[r] = g.home_score - g.away_score
    w = math.sqrt(prior_games)
    for t, i in idx.items():                                  # shrink toward prior (or 0)
        X[len(games) + i, i] = w
        y[len(games) + i] = w * (prior or {}).get(t, 0.0)
    solution = np.linalg.lstsq(X, y, rcond=None)[0]
    ratings = solution[:n] - solution[:n].mean()
    return {t: float(ratings[i]) for t, i in idx.items()}


def win_probability(rating_a: float, rating_b: float, game_sd: float = GAME_SD) -> float:
    """Chance A beats B on a neutral court."""
    return 0.5 * (1 + math.erf((rating_a - rating_b) / (game_sd * math.sqrt(2))))


# ------------------------------------------------------------------ bracket
@dataclass
class Team:
    id: str
    name: str
    short: str
    seed: int
    region: str
    rating: float
    logo: str | None = None


@dataclass
class Bracket:
    season: int
    teams: list[Team]                          # 64 teams in bracket order
    regions: list[str]
    official: bool                             # False = projected field
    results: list[list[int]] = field(default_factory=list)   # actual winner (team index) per round/slot
    notes: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return len(self.results) == 6 and all(w >= 0 for w in self.results[-1])


def current_season(today: dt.date | None = None) -> int:
    """The season whose tournament is next (2026-27 season -> 2027)."""
    today = today or dt.date.today()
    return today.year + 1 if today.month >= 8 else today.year


def load_bracket(client: ESPNClient, season: int, today: dt.date | None = None) -> Bracket:
    today = today or dt.date.today()
    notes: list[str] = []

    # Tournament games (only once March of that season has arrived).
    t_start, t_end = dt.date(season, 3, 14), dt.date(season, 4, 9)
    tourney = client.days(t_start, min(t_end, today), tournament_only=True) if today >= t_start else []
    tourney = [g for g in tourney if g.tournament]
    first_day = min((g.date for g in tourney), default=None)

    # Regular season + conference tournaments, up to the day before the NCAA tournament.
    s_start = dt.date(season - 1, 11, 1)
    s_end = min(today - dt.timedelta(1), (first_day or t_end) - dt.timedelta(1), dt.date(season, 3, 16))
    games = client.days(s_start, s_end) if s_end >= s_start else []
    prior = None
    if s_end < dt.date(season, 1, 15):     # early season: lean on last year's ratings
        last = client.days(dt.date(season - 2, 11, 1), dt.date(season - 1, 3, 16))
        prior = {t: 0.7 * r for t, r in fit_ratings(last).items()}
        notes.append("Early season: ratings blend this season's games with last season's.")
    ratings = fit_ratings(games, prior, prior_games=8 if prior else 3)

    def team(tid: str, seed: int, region: str) -> Team:
        info = client.teams.get(tid, {})
        return Team(tid, info.get("name", tid), info.get("short", ""), seed, region,
                    ratings.get(tid, -15.0), info.get("logo"))

    first_round = [g for g in tourney if g.round == "1st Round"]
    if len(first_round) == 32:
        bracket = _official_bracket(season, tourney, first_round, team, notes)
    else:
        bracket = _projected_bracket(season, games, ratings, team, notes)
    return bracket


def _official_bracket(season, tourney, first_round, team, notes) -> Bracket:
    by_region: dict[str, dict[int, str]] = {}
    for g in first_round:
        seeds = by_region.setdefault(g.region, {})
        seeds[g.home_seed] = g.home_id
        seeds[g.away_seed] = g.away_id

    # Final Four pairings: read them from the semifinals if played, else assume.
    regions = [r for r in DEFAULT_REGIONS if r in by_region] + sorted(set(by_region) - set(DEFAULT_REGIONS))
    team_region = {tid: r for r, seeds in by_region.items() for tid in seeds.values()}
    semis = [g for g in tourney if g.round == "Final Four"]
    if len(semis) == 2:
        regions = [team_region.get(t, "?") for g in semis for t in (g.home_id, g.away_id)]
    else:
        notes.append("Final Four pairings not known yet - assumed " + " vs ".join(regions[:2])
                     + " and " + " vs ".join(regions[2:]) + ".")

    teams = [team(by_region[r][s], s, r) for r in regions for s in SEED_ORDER]
    bracket = Bracket(season, teams, regions, official=True, notes=notes)
    bracket.results = _results(bracket, tourney)
    return bracket


def _projected_bracket(season, games, ratings, team, notes) -> Bracket:
    played: dict[str, int] = {}
    for g in games:
        for t in (g.home_id, g.away_id):
            played[t] = played.get(t, 0) + 1
    pool = [t for t in ratings if played.get(t, 0) >= 3] or list(ratings)
    top = sorted(pool, key=lambda t: -ratings[t])[:64]
    seeds: dict[str, dict[int, str]] = {r: {} for r in DEFAULT_REGIONS}
    for i, tid in enumerate(top):                       # S-curve: 1-seeds go 1,2,3,4 then 4,3,2,1...
        line, pos = divmod(i, 4)
        region = DEFAULT_REGIONS[pos if line % 2 == 0 else 3 - pos]
        seeds[region][line + 1] = tid
    teams = [team(seeds[r][s], s, r) for r in DEFAULT_REGIONS for s in SEED_ORDER]
    notes.append("Projected field: the top 64 teams by our ratings. The official bracket "
                 f"(Selection Sunday, mid-March {season}) replaces this automatically.")
    return Bracket(season, teams, list(DEFAULT_REGIONS), official=False, notes=notes)


def _results(bracket: Bracket, tourney: list[Game]) -> list[list[int]]:
    """Actual winner of every bracket slot played so far (-1 = not played yet)."""
    winners = {name: set() for name in ROUND_NAMES}
    for g in tourney:
        if g.completed and g.round in winners:
            winners[g.round].add(g.home_id if g.home_score > g.away_score else g.away_id)
    alive = list(range(64))
    results = []
    for name in ROUND_NAMES:
        nxt = []
        for a, b in zip(alive[0::2], alive[1::2]):
            ids = {bracket.teams[a].id if a >= 0 else None: a, bracket.teams[b].id if b >= 0 else None: b}
            nxt.append(next((i for tid, i in ids.items() if tid in winners[name]), -1))
        results.append(nxt)
        alive = nxt
    return results


# --------------------------------------------------------------- Monte Carlo
def simulate_bracket(win_prob: np.ndarray, n_sims: int = 10_000, seed: int | None = None,
                     locked: list[list[int]] | None = None) -> list[np.ndarray]:
    """Play the 64-team bracket ``n_sims`` times.

    ``win_prob[i, j]`` is the chance team i beats team j. Teams are in bracket
    order, so neighbours play each other. ``locked`` holds results of games
    already played. Returns, for each round, the winners: an (n_sims, games) array.
    """
    rng = np.random.default_rng(seed)
    alive = np.tile(np.arange(64), (n_sims, 1))             # every simulation starts with all 64
    rounds = []
    for r in range(6):
        a, b = alive[:, 0::2], alive[:, 1::2]                # neighbours play each other
        a_wins = rng.random(a.shape) < win_prob[a, b]        # flip a weighted coin per game
        if locked and r < len(locked):                       # games already played keep their result
            known = np.array(locked[r])
            a_wins = np.where(known >= 0, a == known, a_wins)
        alive = np.where(a_wins, a, b)                       # winners move on
        rounds.append(alive)
    return rounds


def advancement(rounds: list[np.ndarray]) -> np.ndarray:
    """odds[team, round] = share of simulations in which the team won that round."""
    return np.column_stack([np.bincount(w.ravel(), minlength=64) / w.shape[0] for w in rounds])


def best_bracket(odds: np.ndarray) -> list[list[int]]:
    """Fill out a bracket: in every game, advance the team more likely to win that round."""
    picks, alive = [], list(range(64))
    for r in range(6):
        alive = [max(a, b, key=lambda t: odds[t, r]) for a, b in zip(alive[0::2], alive[1::2])]
        picks.append(alive)
    return picks


def bracket_score(picks: list[list[int]], results: list[list[int]]) -> tuple[int, int]:
    """ESPN-style points earned by ``picks`` so far, and the maximum possible so far."""
    earned = possible = 0
    for r, (p, actual) in enumerate(zip(picks, results)):
        for pick, winner in zip(p, actual):
            if winner >= 0:
                possible += ESPN_POINTS[r]
                earned += ESPN_POINTS[r] * (pick == winner)
    return earned, possible


def run(bracket: Bracket, n_sims: int = 10_000, seed: int | None = None, game_sd: float = GAME_SD,
        use_results: bool = True):
    """Simulate a bracket; returns (odds[team, round], best-bracket picks)."""
    r = np.array([t.rating for t in bracket.teams])
    win_prob = 0.5 * (1 + np.vectorize(math.erf)((r[:, None] - r[None, :]) / (game_sd * math.sqrt(2))))
    locked = bracket.results if use_results and not bracket.complete else None
    odds = advancement(simulate_bracket(win_prob, n_sims, seed, locked))
    return odds, best_bracket(odds)
