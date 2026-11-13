"""Parlay Lab: find the best parlays on DraftKings and Kalshi with Monte Carlo.

Data
  * DraftKings lines (moneyline, spread, total) from ESPN's public scoreboards,
    for every league ESPN carries odds for.
  * Every open Kalshi sports market for the coming days (game winners,
    spreads, totals, player props...) from Kalshi's public market data: tens of
    thousands of markets across hundreds of leagues, from the NFL to college
    hockey, esports, cricket and table tennis. Both sides (Yes / No) are legs.

Model
  1. Each leg's true chance is estimated from the prices with the bookmaker's
     margin removed, averaged across DraftKings and Kalshi when both list it.
  2. That estimate is uncertain, so the simulation runs in two layers: each
     "scenario" draws a plausible true chance for every leg, then plays every
     game many times. A million simulations = 1,000 scenarios x 1,000 slates.
  3. Every candidate parlay is scored on those same simulated slates: how often
     it hits, what it pays, its expected value, and how often it's worth it.
"""

from __future__ import annotations

import datetime as dt
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from .http import APIError, CachedJSON

ESPN = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_FEE = 0.07          # taker fee: 0.07 x price x (1 - price) per contract
MAX_SPREAD = 0.30          # keep Kalshi markets with a bid/ask gap up to 30 cents (pages filter tighter)
SCAN_DAYS = 7              # one shared scan covers the next week; pages filter to fewer days
WINNER_SERIES = re.compile(r"(GAME|MATCH|FIGHT|BOUT)$")

# ESPN leagues that carry DraftKings odds: (sport, league, path)
ESPN_LEAGUES = [
    ("Football", "NFL", "football/nfl"), ("Football", "College Football", "football/college-football"),
    ("Football", "CFL", "football/cfl"), ("Football", "UFL", "football/ufl"),
    ("Basketball", "NBA", "basketball/nba"), ("Basketball", "WNBA", "basketball/wnba"),
    ("Basketball", "Men's College Basketball", "basketball/mens-college-basketball"),
    ("Basketball", "Women's College Basketball", "basketball/womens-college-basketball"),
    ("Hockey", "NHL", "hockey/nhl"), ("Baseball", "MLB", "baseball/mlb"),
    ("Soccer", "Premier League", "soccer/eng.1"), ("Soccer", "EFL Championship", "soccer/eng.2"),
    ("Soccer", "La Liga", "soccer/esp.1"), ("Soccer", "Bundesliga", "soccer/ger.1"),
    ("Soccer", "Serie A", "soccer/ita.1"), ("Soccer", "Ligue 1", "soccer/fra.1"),
    ("Soccer", "MLS", "soccer/usa.1"), ("Soccer", "NWSL", "soccer/usa.nwsl"), ("Soccer", "Liga MX", "soccer/mex.1"),
    ("Soccer", "Champions League", "soccer/uefa.champions"), ("Soccer", "Europa League", "soccer/uefa.europa"),
    ("Soccer", "Eredivisie", "soccer/ned.1"), ("Soccer", "Primeira Liga", "soccer/por.1"),
    ("Soccer", "Scottish Premiership", "soccer/sco.1"),
]
MARKETS = ("Moneyline", "Spread", "Total", "Player props", "Other")

ParlayError = APIError
Progress = "Callable[[str, float, dict], None] | None"


# --------------------------------------------------------------------- legs
@dataclass
class Leg:
    key: str                     # unique id
    game: str                    # legs with the same game id are from the same game
    sport: str
    league: str
    matchup: str
    start: dt.datetime
    market: str                  # one of MARKETS
    pick: str
    p: float                     # best estimate of the chance this leg wins
    kappa: float                 # confidence in p (higher = surer); drives the scenario spread
    dk_odds: int | None = None   # DraftKings American odds
    kalshi_ask: float | None = None
    kalshi_mid: float | None = None
    sources: list[str] = field(default_factory=list)
    spread: float = 0.0          # Kalshi bid/ask gap (0 for DraftKings): wider = thinner market

    @property
    def niche(self) -> int:
        return niche_score(self.sport, self.league)

    @property
    def dk_decimal(self) -> float | None:
        return american_to_decimal(self.dk_odds) if self.dk_odds is not None else None

    @property
    def kalshi_cost(self) -> float | None:
        """Cost per $1 payout when buying this side on Kalshi, including the fee."""
        if self.kalshi_ask is None:
            return None
        a = self.kalshi_ask
        return a + KALSHI_FEE * a * (1 - a)


def american_to_decimal(odds: int | float) -> float:
    return 1 + (odds / 100 if odds > 0 else 100 / -odds)


def decimal_to_american(dec: float) -> str:
    if dec >= 2:
        return f"+{round((dec - 1) * 100):,}"
    return f"{round(-100 / (dec - 1)):,}"


def _odds(x) -> int | None:
    try:
        s = str(x).strip().upper()
        if s in ("EVEN", "EV"):
            return 100
        v = int(float(s.replace("+", "")))
        return v if abs(v) >= 100 else None
    except (TypeError, ValueError):
        return None


def _devig(odds: list[int | None]) -> list[float] | None:
    """Remove the bookmaker's margin: implied probabilities scaled to add up to 1."""
    if any(o is None for o in odds):
        return None
    imp = [1 / american_to_decimal(o) for o in odds]
    s = sum(imp)
    return [x / s for x in imp]


# ---------------------------------------------------------------- how niche
# How far off the beaten path each sport is (for a US audience), 0 = mainstream.
SPORT_OBSCURITY = {"Football": 0, "Basketball": 1, "Baseball": 1, "Hockey": 1, "Soccer": 1, "Golf": 2,
                   "Motorsport": 2, "MMA": 2, "UFC": 2, "Boxing": 2, "Tennis": 2, "Olympics": 2, "Cricket": 3,
                   "Esports": 3, "Rugby": 3, "Aussie Rules": 3, "Lacrosse": 3, "Video games": 3, "Volleyball": 4,
                   "Table Tennis": 4, "Darts": 4, "Handball": 4, "Cycling": 4, "Wrestling": 4, "Squash": 5,
                   "Chess": 5, "Rowing": 5}
MAINSTREAM = re.compile(r"\b(NFL|Pro Football|NBA|NHL|MLB|College Football|Men's College Basketball|Premier League|"
                        r"EPL|La Liga|Bundesliga|Serie A|Ligue 1|Champions League|UFC|Super Bowl|World Series|"
                        r"Stanley Cup|Heisman)\b", re.I)
WOMEN = re.compile(r"(Women|\(W\)|WTA|NWSL|WNBA|Ladies|Female)", re.I)
LOWER_TIER = re.compile(r"(\b2\b|\bII\b|\bIII\b|\b[AB]2\b|\b2nd\b|Second|Division|Liga Pro|League One|League Two|Serie [BC]\b|Segunda|\b[234]\. |"
                        r"\bCup\b|\bU-?\d\d\b|Youth|Junior|Winter League|Challenger|\bITF\b|Amateur|Reserve|"
                        r"Exhibition|Friendly|Qualif)", re.I)
COUNTRIES = re.compile(r"\b(Japan|Korea|China|Chinese|Taiwan|Thai|Vietnam|India|Indonesia|Philippine|Malaysia|Australia|"
                       r"New Zealand|Bosnia|Croatia|Serbia|Slovakia|Slovenia|Czech|Poland|Polish|Hungary|Romania|"
                       r"Bulgaria|Greece|Greek|Turkey|Turkish|Cyprus|Israel|Lebanon|Iceland|Norway|Sweden|Swedish|"
                       r"Denmark|Danish|Finland|Finnish|Estonia|Latvia|Lithuania|Ukraine|Russia|Belarus|Georgia|"
                       r"Kazakh|Portugal|Belgium|Belgian|Austria|Swiss|Switzerland|Scotland|Scottish|Wales|Welsh|"
                       r"Ireland|Irish|Peru|Paraguay|Uruguay|Chile|Bolivia|Ecuador|Colombia|Venezuela|Puerto Ric|"
                       r"Dominican|Nicaragua|Cuba|Panama|Costa Rica|Honduras|Guatemala|Egypt|Morocco|Saudi|Qatar|"
                       r"Emirates|Iran|Nigeria|South Africa|Kenya|Argentin|Brazil|Ital|Spain|Spanish|France|French|"
                       r"German|Netherlands|Dutch|England|English|Mexic)", re.I)
NICHE_LEVELS = {
    1: ("Off the beaten path", 1, "Anything outside the big US leagues and Europe's top soccer"),
    2: ("Obscure", 3, "Smaller sports, women's leagues and foreign leagues"),
    3: ("Deep cuts", 4, "Lower divisions abroad, esports, cricket, table tennis"),
    4: ("Truly obscure", 5, "Women's and second-tier leagues in far-flung places"),
    5: ("Japanese women's tennis", 6, "The deepest end of the board"),
}


def niche_score(sport: str, league: str) -> int:
    """0 = mainstream (NFL, NBA, Premier League...), higher = more niche."""
    women = bool(WOMEN.search(league))
    if MAINSTREAM.search(league) and not women:
        return 0
    score = 1 + SPORT_OBSCURITY.get(sport, 3)
    score += women + bool(LOWER_TIER.search(league)) + bool(COUNTRIES.search(league))
    return score


def kalshi_market_type(series: str) -> str:
    s = series.upper()
    if WINNER_SERIES.search(s):
        return "Moneyline"
    if "SPREAD" in s or "WINMARGIN" in s:
        return "Spread"
    if "TOTAL" in s:
        return "Total"
    if re.search(r"(REC|RSH|RUSH|PASS|PTS|REB|AST|TD|YDS|GOAL|SOG|SAVES|HR|HITS|STRIKE|KS|3PT|BLK|STL|SCORER)", s):
        return "Player props"
    return "Other"


# ------------------------------------------------------------------ fetching
class OddsClient:
    def __init__(self, cache_dir=".ffmc_cache"):
        self.http = CachedJSON(cache_dir)

    def espn_day(self, path: str, day: dt.date) -> list[dict]:
        try:
            data = self.http.get(ESPN.format(path=path), [("dates", day.strftime("%Y%m%d")), ("limit", "300")], ttl=600)
        except APIError:
            return []
        return data.get("events", [])

    def kalshi(self, path: str, params: list[tuple[str, str]], ttl: float = 600) -> dict:
        for attempt in range(8):                      # Kalshi rate-limits bursts: back off and retry
            try:
                return self.http.get(KALSHI + path, params, ttl=ttl)
            except APIError as exc:
                if "429" not in str(exc):
                    raise
                time.sleep(1.0 + attempt)
        raise ParlayError("Kalshi is busy right now (too many requests). Try again in a minute.")

    def kalshi_sports_series(self) -> dict[str, dict]:
        return {s["ticker"]: s for s in self.kalshi("/series", [("category", "Sports")], ttl=86400).get("series", [])}

    def kalshi_all_markets(self, max_close: int, progress=None, time_limit: float = 100) -> tuple[list[dict], bool]:
        """Every open single (non-combo) Kalshi market closing before ``max_close``, page by page."""
        markets, cursor, start = [], "", time.time()
        while True:
            params = [("status", "open"), ("limit", "1000"), ("max_close_ts", str(max_close)), ("mve_filter", "exclude")]
            if cursor:
                params.append(("cursor", cursor))
            page = self.kalshi("/markets", params, ttl=600)
            markets += page.get("markets", [])
            cursor = page.get("cursor")
            if progress:
                progress(len(markets))
            if not cursor:
                return markets, True
            if time.time() - start > time_limit:          # stay inside the time budget
                return markets, False


def _team(c: dict) -> str:
    t = c.get("team") or c.get("athlete") or {}
    return t.get("shortDisplayName") or t.get("displayName") or t.get("name") or "?"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower().replace("&", "and")).strip()


def espn_legs(client: OddsClient, days: int = 3, now: dt.datetime | None = None) -> list[Leg]:
    """DraftKings moneyline, spread and total legs for games in the next ``days`` days."""
    now = now or dt.datetime.now(dt.timezone.utc)
    jobs = [(sport, league, path, (now + dt.timedelta(d)).date()) for sport, league, path in ESPN_LEAGUES
            for d in range(-1, days + 1)]
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda j: (j, client.espn_day(j[2], j[3])), jobs))

    legs, seen = [], set()
    for (sport, league, _, _), events in results:
        for e in events:
            if e["id"] in seen:
                continue
            comp = e["competitions"][0]
            start = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
            state = comp.get("status", {}).get("type", {}).get("state", "pre")
            if state != "pre" or start < now or start > now + dt.timedelta(days):
                continue
            odds = next((o for o in comp.get("odds", []) if "draftkings" in o.get("provider", {}).get("name", "").lower()), None)
            sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            if not odds or "home" not in sides or "away" not in sides:
                continue
            seen.add(e["id"])
            home, away = _team(sides["home"]), _team(sides["away"])
            game = f"espn:{e['id']}"
            base = dict(game=game, sport=sport, league=league, matchup=f"{away} @ {home}", start=start)

            ml = odds.get("moneyline") or {}
            ml_odds = [_odds((ml.get(s) or {}).get("close", {}).get("odds")) for s in ("home", "away")]
            names = [home, away]
            draw = _odds((ml.get("draw") or {}).get("close", {}).get("odds"))
            if draw is not None:
                ml_odds.append(draw)
                names.append("Draw")
            probs = _devig(ml_odds)
            if probs:
                for side, name, o, p in zip(("home", "away", "draw"), names, ml_odds, probs):
                    legs.append(Leg(key=f"{game}:ml:{side}", market="Moneyline",
                                    pick=f"{name} win" if name != "Draw" else "Draw", p=p, kappa=150,
                                    dk_odds=o, sources=["DraftKings"], **base))

            ps = odds.get("pointSpread") or {}
            sp = [((ps.get(s) or {}).get("close") or {}) for s in ("home", "away")]
            probs = _devig([_odds(x.get("odds")) for x in sp])
            if probs and all(x.get("line") for x in sp):
                for side, name, x, p in zip(("home", "away"), (home, away), sp, probs):
                    legs.append(Leg(key=f"{game}:spread:{side}", market="Spread", pick=f"{name} {x['line']}",
                                    p=p, kappa=150, dk_odds=_odds(x["odds"]), sources=["DraftKings"], **base))

            tot = odds.get("total") or {}
            tt = [((tot.get(s) or {}).get("close") or {}) for s in ("over", "under")]
            probs = _devig([_odds(x.get("odds")) for x in tt])
            if probs and all(x.get("line") for x in tt):
                for side, x, p in zip(("Over", "Under"), tt, probs):
                    line = str(x["line"]).lstrip("ou")
                    legs.append(Leg(key=f"{game}:total:{side.lower()}", market="Total",
                                    pick=f"{side} {line} ({away} @ {home})", p=p, kappa=150,
                                    dk_odds=_odds(x["odds"]), sources=["DraftKings"], **base))
    return legs


def kalshi_legs(client: OddsClient, days: int = 3, now: dt.datetime | None = None,
                progress=None) -> tuple[list[Leg], dict]:
    """Both sides of every open, priced Kalshi sports market for the next ``days`` days."""
    now = now or dt.datetime.now(dt.timezone.utc)
    series = client.kalshi_sports_series()
    max_close = int((now + dt.timedelta(days + 4)).timestamp())    # markets close a while after the game
    markets, complete = client.kalshi_all_markets(max_close, progress)
    stats = {"scanned": len(markets), "complete": complete}

    by_event: dict[str, list[dict]] = {}
    for m in markets:
        if m["event_ticker"].split("-")[0] in series:
            by_event.setdefault(m["event_ticker"], []).append(m)
    stats["sports_markets"] = sum(len(v) for v in by_event.values())

    legs, leagues = [], set()
    for event, ms in by_event.items():
        prefix = event.split("-")[0]
        info = series.get(prefix, {})
        when = ms[0].get("occurrence_datetime") or ms[0].get("expected_expiration_time")
        try:
            start = dt.datetime.fromisoformat(str(when).replace("Z", "+00:00"))
        except ValueError:
            continue
        # Kalshi's time here is roughly when the game ends; keep games still to be decided.
        if start < now or start > now + dt.timedelta(days, hours=6):
            continue
        quotes = []
        for m in ms:
            bid, ask = float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 0)
            if 0 < bid < ask < 1 and ask - bid <= MAX_SPREAD:
                quotes.append((m, bid, ask))
        if not quotes:
            continue
        kind = kalshi_market_type(prefix)
        tags = info.get("tags") or []
        league = re.sub(r"\s+(Game|Match|Fight|Bout)( Winner)?$", "", info.get("title", prefix))
        leagues.add(league)
        game = "kalshi:" + (event.split("-", 1)[1] if "-" in event else event)   # same game across series
        winner = kind == "Moneyline"
        total_mid = sum((b + a) / 2 for _, b, a in quotes)
        names = [m.get("yes_sub_title") or m.get("title", "?") for m, _, _ in quotes]
        teams = [n for n in names if n.lower() not in ("tie", "draw")]
        matchup = " vs ".join(teams) if winner and len(teams) <= 2 else re.sub(r"\?$", "", info.get("title", prefix))
        for (m, bid, ask), name in zip(quotes, names):
            mid = (bid + ask) / 2
            spread = ask - bid
            kappa = max(25.0, 150 - 800 * spread)
            base = dict(game=game, sport=tags[0] if tags else "Other", league=league, matchup=matchup, start=start,
                        market=kind, sources=["Kalshi"], spread=spread)
            if winner:
                p = mid / total_mid if len(quotes) == len(ms) and len(quotes) >= 2 else mid
                label = f"{name} win" if name.lower() not in ("tie", "draw") else "Draw"
                legs.append(Leg(key=f"kalshi:{m['ticker']}", pick=label, p=p, kappa=kappa,
                                kalshi_ask=ask, kalshi_mid=mid, **base))
                continue
            title = re.sub(r"\?$", "", m.get("title") or name)
            if m.get("yes_sub_title") and m["yes_sub_title"] not in title:
                title = f"{title}: {m['yes_sub_title']}"
            legs.append(Leg(key=f"kalshi:{m['ticker']}:yes", pick=title, p=mid, kappa=kappa,
                            kalshi_ask=ask, kalshi_mid=mid, **base))
            legs.append(Leg(key=f"kalshi:{m['ticker']}:no", pick=f"NOT {title}", p=1 - mid, kappa=kappa,
                            kalshi_ask=1 - bid, kalshi_mid=1 - mid, **base))
    stats["leagues"] = len(leagues)
    return legs, stats


def merge(dk: list[Leg], kalshi: list[Leg]) -> list[Leg]:
    """Attach Kalshi prices to matching DraftKings moneylines; keep every other Kalshi leg.

    Kalshi legs from a matched game take the DraftKings game id, so "one leg per
    game" treats them as the same game.
    """
    by_game: dict[str, list[Leg]] = {}
    for l in dk:
        if l.market == "Moneyline":
            by_game.setdefault(l.game, []).append(l)
    k_events: dict[str, list[Leg]] = {}
    for l in kalshi:
        if l.market == "Moneyline":
            k_events.setdefault(l.key.rsplit("-", 1)[0], []).append(l)

    def team_of(leg: Leg) -> str:
        return _norm(leg.pick.removesuffix(" win"))

    used, game_alias = set(), {}
    for klegs in k_events.values():
        k_teams = {team_of(l) for l in klegs if l.pick != "Draw"}
        for game, glegs in by_game.items():
            if abs((glegs[0].start - klegs[0].start).total_seconds()) > 36 * 3600:
                continue
            d_teams = {team_of(l) for l in glegs if l.pick != "Draw"}
            pairs = {}
            for kt in k_teams:
                match = [x for x in d_teams if kt and x and (kt == x or kt in x or x in kt)]
                if len(match) == 1:
                    pairs[kt] = match[0]
            if not (len(pairs) == len(k_teams) == len(d_teams) and len(set(pairs.values())) == len(pairs)):
                continue
            # Same game found. Only combine prices if both are clearly the same bet: a 3-way
            # (draw possible) line can't be combined with a 2-way "who advances" market, and
            # prices that disagree a lot usually mean different rules (e.g. overtime counted).
            matched = []
            for kl in klegs:
                target = "draw" if kl.pick == "Draw" else pairs.get(team_of(kl))
                dl = next((g for g in glegs if (g.pick == "Draw" if target == "draw" else team_of(g) == target)), None)
                if dl is not None:
                    matched.append((kl, dl))
            same_shape = any(g.pick == "Draw" for g in glegs) == any(k.pick == "Draw" for k in klegs)
            if same_shape and matched and all(abs(dl.p - kl.p) <= 0.08 for kl, dl in matched):
                for kl, dl in matched:
                    dl.kalshi_ask, dl.kalshi_mid = kl.kalshi_ask, kl.kalshi_mid
                    agree = abs(dl.p - kl.p)
                    dl.p = (dl.p + kl.p) / 2
                    dl.kappa = 300 if agree < 0.03 else 120      # two sources that agree = more confidence
                    dl.sources = ["DraftKings", "Kalshi"]
                    used.add(kl.key)
            game_alias[klegs[0].game] = game                     # either way, it's the same game
            break
    out = list(dk)
    for l in kalshi:
        if l.key in used:
            continue
        if l.game in game_alias:
            l.game = game_alias[l.game]
        out.append(l)
    return out


def within(legs: list[Leg], days: float, max_spread: float = 1.0, now: dt.datetime | None = None) -> list[Leg]:
    """Legs whose game is within ``days`` and whose Kalshi bid/ask gap is at most ``max_spread``."""
    now = now or dt.datetime.now(dt.timezone.utc)
    end = now + dt.timedelta(days=days, hours=6)
    return [l for l in legs if now <= l.start <= end and l.spread <= max_spread]


def load_legs(days: int = SCAN_DAYS, cache_dir=".ffmc_cache", progress=None) -> tuple[list[Leg], dict]:
    """Every leg on offer: DraftKings (via ESPN) and Kalshi. ``progress(stage, fraction, stats)``."""
    client = OddsClient(cache_dir)
    stats: dict = {"notes": []}

    def say(stage, frac):
        if progress:
            progress(stage, frac, stats)

    say("Pulling DraftKings lines and scanning every open Kalshi sports market", 0.02)
    # DraftKings (via ESPN) loads in the background while Kalshi is scanned.
    pool = ThreadPoolExecutor(1)
    dk_job = pool.submit(espn_legs, client, days)
    try:
        def page(n):
            stats["scanned"] = n
            if dk_job.done() and "dk_legs" not in stats:
                stats["dk_legs"] = len(dk_job.result())
            say("Scanning every open Kalshi sports market", min(0.85, 0.05 + 0.8 * n / 90_000))
        ks, kstats = kalshi_legs(client, days, progress=page)
        stats.update(kstats)
        if not kstats["complete"]:
            stats["notes"].append("Kalshi has more markets than fit in the time limit; scanned the first "
                                  f"{kstats['scanned']:,}.")
    except APIError as exc:
        ks = []
        stats["notes"].append(f"Kalshi prices unavailable right now ({exc}); showing DraftKings only.")
    stats["kalshi_legs"] = len(ks)
    dk = dk_job.result()
    pool.shutdown()
    stats["dk_legs"] = len(dk)
    say("Matching DraftKings and Kalshi games", 0.9)
    legs = [l for l in merge(dk, ks) if 0.01 < l.p < 0.99]
    stats["legs"] = len(legs)
    stats["games"] = len({l.game for l in legs})
    stats["both"] = sum(1 for l in legs if len(l.sources) == 2)
    say("Ready", 1.0)
    return legs, stats


# --------------------------------------------------------------------- search
@dataclass
class Settings:
    app: str = "DraftKings"            # DraftKings, Kalshi, Either (best price)
    risk: int = 5                      # 1 (safest) .. 10 (longest shots)
    payout_range: tuple[float, float] = (3.0, 50.0)   # total payout multiple of the stake
    legs_range: tuple[int, int] = (2, 4)
    leg_prob_range: tuple[float, float] = (0.15, 0.92)
    markets: tuple[str, ...] = MARKETS
    sports: tuple[str, ...] | None = None
    one_per_game: bool = True
    rank_by: str = "value"             # value, likely, payout
    stake: float = 10.0
    n_show: int = 10


def min_hit_chance(risk: int) -> float:
    """Risk 1 -> parlays must hit at least 45% of the time; risk 10 -> 0.5%."""
    return 0.45 * (0.005 / 0.45) ** ((risk - 1) / 9)


def leg_payout(leg: Leg, app: str) -> float | None:
    """Payout multiple for this leg on the chosen app (None if not listed there)."""
    dk = leg.dk_decimal
    k = 1 / leg.kalshi_cost if leg.kalshi_cost else None
    if app == "DraftKings":
        return dk
    if app == "Kalshi":
        return k
    return max(x for x in (dk, k) if x) if (dk or k) else None


@dataclass
class Parlay:
    legs: list[int]
    payout: float            # total payout multiple (stake included) on the chosen app
    app: str                 # where to place it
    dk_payout: float | None
    kalshi_payout: float | None
    hit: float = 0.0         # Monte Carlo chance that every leg wins
    ev: float = 0.0          # expected profit per $1 staked
    worth_it: float = 0.0    # share of scenarios in which the bet has positive expected value
    est_hit: float = 0.0     # chance from multiplying leg chances (before simulation)


def candidates(legs: list[Leg], s: Settings, beam: int = 500, pool_size: int = 700, keep: int = 400) -> list[Parlay]:
    """Search leg combinations that fit the settings (beam search on log odds)."""
    lo_pay, hi_pay = s.payout_range
    min_hit = min_hit_chance(s.risk)
    pool = [i for i, l in enumerate(legs)
            if s.leg_prob_range[0] <= l.p <= s.leg_prob_range[1] and l.market in s.markets
            and (not s.sports or l.sport in s.sports) and leg_payout(l, s.app)]
    if not pool:
        return []
    lp = {i: math.log(legs[i].p) for i in pool}
    lpay = {i: math.log(leg_payout(legs[i], s.app)) for i in pool}

    log_min_hit, log_lo, log_hi = math.log(min_hit), math.log(lo_pay), math.log(hi_pay)

    def score(lp_sum: float, lpay_sum: float) -> float:
        short = max(0.0, log_lo - lpay_sum)            # still below the payout you asked for
        if s.rank_by == "likely":
            return lp_sum - 3 * short
        if s.rank_by == "payout":
            return lpay_sum + 0.25 * lp_sum
        return lp_sum + lpay_sum - short               # log of expected return

    # Tens of thousands of legs: search among a few hundred of the most promising,
    # mixing the best value, the most likely and the best-paying legs.
    by = lambda f, n: sorted(pool, key=f)[:n]
    pool = sorted(set(by(lambda i: -(lp[i] + lpay[i]), pool_size // 2))
                  | set(by(lambda i: -lp[i], pool_size // 4)) | set(by(lambda i: -lpay[i] - 0.5 * lp[i], pool_size // 4)))
    frontier = [((i,), lp[i], lpay[i]) for i in pool]
    found: dict[tuple, tuple[float, float]] = {}
    for size in range(1, s.legs_range[1] + 1):
        if size > 1:
            nxt = {}
            for combo, a, b in frontier:
                games = {legs[j].game for j in combo}
                for i in pool:
                    if i <= combo[-1]:
                        continue
                    if s.one_per_game and legs[i].game in games:
                        continue
                    na, nb = a + lp[i], b + lpay[i]
                    if na < log_min_hit or nb > log_hi:
                        continue
                    nxt[combo + (i,)] = (na, nb)
            frontier = [(c, a, b) for c, (a, b) in sorted(nxt.items(), key=lambda kv: -score(*kv[1]))[:beam]]
        for combo, a, b in frontier:
            if size >= s.legs_range[0] and log_lo <= b and a >= log_min_hit:
                found[combo] = (a, b)
        if not frontier:
            break
    best = sorted(found.items(), key=lambda kv: -score(*kv[1]))[:keep]
    out = []
    for combo, (a, b) in best:
        dk = math.prod(legs[i].dk_decimal for i in combo) if all(legs[i].dk_decimal for i in combo) else None
        kal = 1 / math.prod(legs[i].kalshi_cost for i in combo) if all(legs[i].kalshi_cost for i in combo) else None
        if s.app == "DraftKings":
            app, pay = "DraftKings", dk
        elif s.app == "Kalshi":
            app, pay = "Kalshi", kal
        else:                                             # place it wherever the whole parlay pays most
            options = [(x, n) for x, n in ((dk, "DraftKings"), (kal, "Kalshi")) if x]
            pay, app = max(options) if options else (None, "")
        if pay and lo_pay <= pay <= hi_pay:
            out.append(Parlay(list(combo), pay, app, dk, kal, est_hit=math.exp(a)))
    return out


# ---------------------------------------------------------------- Monte Carlo
@dataclass
class Simulation:
    parlays: list[Parlay]
    n_sims: int
    portfolio_profit: np.ndarray    # total profit per simulated slate if you bet every shown parlay
    legs_used: int
    candidates: int


def simulate(legs: list[Leg], parlays: list[Parlay], s: Settings, n_sims: int = 1_000_000,
             seed: int | None = None, progress=None) -> Simulation:
    """Play every game ``n_sims`` times and score each candidate parlay on the same slates.

    Two layers: ``scenarios`` draw a plausible true chance for every leg (the
    estimate is uncertain), and each scenario is played ``per`` times.
    """
    rng = np.random.default_rng(seed)
    used = sorted({i for p in parlays for i in p.legs})
    col = {leg: c for c, leg in enumerate(used)}
    p = np.array([legs[i].p for i in used])
    kappa = np.array([legs[i].kappa for i in used])
    per = 1000
    scenarios = max(1, n_sims // per)
    n_sims = scenarios * per

    # Layer 1: a plausible true chance for every leg in every scenario.
    true_p = rng.beta(p * kappa, (1 - p) * kappa, size=(scenarios, len(used)))
    log_true = np.log(true_p)
    for par in parlays:            # in how many scenarios is this bet worth making (+EV)?
        par.worth_it = float((log_true[:, [col[i] for i in par.legs]].sum(axis=1) + math.log(par.payout) > 0).mean())

    # Layer 2: play the games. Results are stored as bits (1 = leg won), 8 slates per byte.
    packed = np.zeros((n_sims // 8, len(used)), dtype=np.uint8)
    chunk = 100                                       # scenarios per batch (100,000 slates)
    for start in range(0, scenarios, chunk):
        stop = min(scenarios, start + chunk)
        tp = np.repeat(true_p[start:stop].astype(np.float32), per, axis=0)
        wins = rng.random(tp.shape, dtype=np.float32) < tp
        packed[start * per // 8: stop * per // 8] = np.packbits(wins, axis=0)
        if progress:
            progress(stop / scenarios)

    for par in parlays:
        bits = np.bitwise_and.reduce(packed[:, [col[i] for i in par.legs]], axis=1)
        par.hit = float(np.bitwise_count(bits).sum()) / n_sims
        par.ev = par.hit * par.payout - 1

    key = {"likely": lambda x: (x.hit, x.ev), "payout": lambda x: (x.payout, x.ev), "value": lambda x: (x.ev, x.hit)}[s.rank_by]
    ranked = sorted(parlays, key=key, reverse=True)
    shown, leg_count = [], {}
    for par in ranked:                                     # variety: no leg in more than 3 shown parlays
        if any(leg_count.get(i, 0) >= 3 for i in par.legs):
            continue
        shown.append(par)
        for i in par.legs:
            leg_count[i] = leg_count.get(i, 0) + 1
        if len(shown) == s.n_show:
            break
    for par in ranked:                                     # not enough variety? fill with the next best
        if len(shown) >= s.n_show:
            break
        if par not in shown:
            shown.append(par)
    shown.sort(key=key, reverse=True)

    profit = np.zeros(n_sims, dtype=np.float32)
    for par in shown:
        bits = np.bitwise_and.reduce(packed[:, [col[i] for i in par.legs]], axis=1)
        won = np.unpackbits(bits)[:n_sims].astype(bool)
        profit += np.where(won, s.stake * (par.payout - 1), -s.stake).astype(np.float32)
    return Simulation(shown, n_sims, profit, len(used), len(parlays))


def find_parlays(legs: list[Leg], s: Settings, n_sims: int = 1_000_000, seed: int | None = None,
                 progress=None) -> Simulation:
    cands = candidates(legs, s)
    if not cands:
        raise ParlayError("No parlays fit these settings. Try more legs, a wider payout range, a higher "
                          "risk level, or more sports and bet types.")
    return simulate(legs, cands, s, n_sims, seed, progress)
