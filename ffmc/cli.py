"""Command-line entry point: ``python -m ffmc --help``."""

from __future__ import annotations

import argparse
import sys

from . import engine, report
from .sleeper import SleeperClient, SleeperError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ffmc",
        description="Monte Carlo fantasy football lineup optimizer (data from the free Sleeper API).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  python -m ffmc                                   # best possible lineup from every NFL player
  python -m ffmc --league 1234567890 --user myname # start/sit for your Sleeper team vs your opponent
  python -m ffmc --players "Josh Allen, Bijan Robinson, ..." --scoring half
  python -m ffmc --demo                            # offline demo with fake players
  python -m ffmc --backtest --week 9 --scoring espn  # predicted vs. actual best lineup for week 9
""")
    src = p.add_argument_group("whose team")
    src.add_argument("--league", help="Sleeper league id (uses league scoring, roster slots and matchup)")
    src.add_argument("--user", help="your Sleeper username (required with --league)")
    src.add_argument("--players", help="comma-separated list of your players (defenses: team abbr, e.g. 'KC')")
    src.add_argument("--opponent", help="comma-separated list of your opponent's players")
    src.add_argument("--dream", action="store_true", help="ignore rosters and build the best lineup from all players")

    opts = p.add_argument_group("settings")
    opts.add_argument("--season", type=int, help="NFL season (default: current)")
    opts.add_argument("--week", type=int, help="NFL week (default: current)")
    opts.add_argument("--scoring", choices=["ppr", "half", "std", "espn"], default="ppr",
                      help="scoring preset when not using --league (default: ppr)")
    opts.add_argument("--slots", help="starting slots, e.g. 'QB,RB,RB,WR,WR,TE,FLEX,K,DEF' (default)")
    opts.add_argument("--objective", choices=["auto", "mean", "win", "floor", "ceiling"], default="auto",
                      help="what to optimize; auto = win probability if there is an opponent, else expected points")
    opts.add_argument("--sims", type=int, default=50_000, help="number of simulations (default: 50000)")
    opts.add_argument("--seed", type=int, help="random seed for reproducible results")
    opts.add_argument("--history-weeks", type=int, default=6,
                      help="recent weeks of actual stats used to estimate each player's volatility (default: 6)")
    opts.add_argument("--independent", action="store_true",
                      help="turn off teammate/game correlation in the simulation")
    opts.add_argument("--cache-dir", default=".ffmc_cache", help="where API responses are cached")
    opts.add_argument("--demo", action="store_true", help="use synthetic data (no network needed)")
    opts.add_argument("--backtest", action="store_true",
                      help="for a past week: compare the simulator's pick with the actual best lineup "
                           "(default week: the last completed one)")
    return p


def _split(text: str | None) -> list[str] | None:
    return [t.strip() for t in text.split(",") if t.strip()] if text else None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.backtest:
        return _backtest(args)
    try:
        if args.demo:
            from .demo import demo_slate
            slate = demo_slate(scoring=args.scoring, with_roster=not args.dream)
        else:
            from .data import load_live
            slate = load_live(
                SleeperClient(args.cache_dir), season=args.season, week=args.week, scoring=args.scoring,
                slots=_split(args.slots), league_id=args.league, username=args.user,
                roster_names=None if args.dream else _split(args.players),
                opponent_names=None if args.dream else _split(args.opponent),
                history_weeks=args.history_weeks)
        result = engine.run(slate, n_sims=args.sims, objective=args.objective, seed=args.seed,
                            correlated=not args.independent, dream=args.dream)
    except (SleeperError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(report.render(result, dream=args.dream))
    return 0


def _backtest(args) -> int:
    from .backtest import render_backtest, run_backtest

    client = SleeperClient(args.cache_dir)
    try:
        state = client.state()
        season = args.season or int(state.get("league_season") or state["season"])
        week = args.week or int(state.get("week") or 2) - 1
        if week < 1:
            raise ValueError("no completed week to backtest yet")
        bt = run_backtest(client, season, week, scoring=args.scoring, slots=_split(args.slots),
                          n_sims=args.sims, seed=args.seed, history_weeks=args.history_weeks)
    except (SleeperError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(render_backtest(bt))
    return 0
