"""Fantasy scoring rules.

Sleeper league ``scoring_settings`` use the same keys as Sleeper's stat
payloads, so points are simply ``sum(stat * weight)``.
"""

from __future__ import annotations

STANDARD: dict[str, float] = {
    # passing
    "pass_yd": 0.04, "pass_td": 4, "pass_int": -1, "pass_2pt": 2,
    # rushing / receiving
    "rush_yd": 0.1, "rush_td": 6, "rush_2pt": 2,
    "rec": 0.0, "rec_yd": 0.1, "rec_td": 6, "rec_2pt": 2,
    "fum_lost": -2,
    # kicking
    "fgm_0_19": 3, "fgm_20_29": 3, "fgm_30_39": 3, "fgm_40_49": 4, "fgm_50p": 5,
    "xpm": 1, "fgmiss": -1, "xpmiss": -1,
    # team defense
    "def_td": 6, "def_st_td": 6, "sack": 1, "int": 2, "fum_rec": 2, "safe": 2, "blk_kick": 2,
    "pts_allow_0": 10, "pts_allow_1_6": 7, "pts_allow_7_13": 4, "pts_allow_14_20": 1,
    "pts_allow_21_27": 0, "pts_allow_28_34": -1, "pts_allow_35p": -4,
}

PRESETS: dict[str, dict[str, float]] = {
    "std": STANDARD,
    "half": {**STANDARD, "rec": 0.5},
    "ppr": {**STANDARD, "rec": 1.0},
    # ESPN's default PPR league: same as PPR but interceptions cost 2.
    "espn": {**STANDARD, "rec": 1.0, "pass_int": -2},
}

# Sleeper pre-computes these totals in every projection/stat row.
PRESET_POINTS_KEY = {"std": "pts_std", "half": "pts_half_ppr", "ppr": "pts_ppr"}


def closest_preset(scoring: dict[str, float]) -> str:
    rec = float(scoring.get("rec", 0.0))
    return min(PRESET_POINTS_KEY, key=lambda k: abs(PRESETS[k]["rec"] - rec))


def fantasy_points(stats: dict, scoring: dict[str, float], position: str | None = None,
                   preset: str | None = None) -> float:
    """Fantasy points for a stat line.

    * If ``preset`` is given and Sleeper's pre-computed total is present, use it.
    * Kickers and defenses use the closest preset total when available, because
      projections give expected points-allowed / FG distance as single numbers
      that don't map cleanly onto bucketed scoring keys.
    * Otherwise compute ``sum(stat * weight)`` with the league's settings.
    """
    if preset in PRESET_POINTS_KEY:
        key = PRESET_POINTS_KEY[preset]
        if key in stats:
            return float(stats[key])
    if position in ("K", "DEF"):
        key = PRESET_POINTS_KEY[closest_preset(scoring)]
        if key in stats:
            return float(stats[key])
    total = 0.0
    for stat, weight in scoring.items():
        val = stats.get(stat)
        if isinstance(val, (int, float)):
            total += val * weight
    if total == 0.0:
        key = PRESET_POINTS_KEY[closest_preset(scoring)]
        if key in stats:
            return float(stats[key])
    return float(total)
