"""Shared look and feel: site-wide CSS, sport colors and page banners."""

from __future__ import annotations

import streamlit as st

APP_VERSION = "2026-11-14a"  # bump on each release so you can tell which version is live

NAVY = "#0c1a2b"
INK = "#14202e"
BORDER = "#dfe3e8"

# One color per sport, plus a subtle texture for its banner.
SPORTS = {
    "nfl": {"label": "NFL", "color": "#2e7d3a", "dark": "#164a20",
            # yard lines
            "texture": "repeating-linear-gradient(90deg, rgba(255,255,255,.10) 0 2px, transparent 2px 72px)"},
    "ncaa": {"label": "NCAA Basketball", "color": "#c75a1c", "dark": "#7a320c",
             # hardwood planks
             "texture": "repeating-linear-gradient(90deg, rgba(255,255,255,.06) 0 22px, rgba(0,0,0,.06) 22px 44px)"},
    "epl": {"label": "Premier League", "color": "#0f7a86", "dark": "#06464f",
            # mown pitch stripes
            "texture": "repeating-linear-gradient(90deg, rgba(255,255,255,.07) 0 56px, transparent 56px 112px)"},
    "f1": {"label": "Formula 1", "color": "#d0021b", "dark": "#5c000b",
           # chequered flag
           "texture": "repeating-conic-gradient(rgba(255,255,255,.07) 0 25%, transparent 0 50%) 0 0 / 26px 26px"},
    "bets": {"label": "DraftKings + Kalshi", "color": "#5b3cc4", "dark": "#24165f",
             # ticker-tape diagonals
             "texture": "repeating-linear-gradient(135deg, rgba(255,255,255,.07) 0 2px, transparent 2px 26px)"},
    "live": {"label": "Live scores + odds", "color": "#1f6feb", "dark": "#0b2a5e",
             # broadcast scanlines
             "texture": "repeating-linear-gradient(0deg, rgba(255,255,255,.05) 0 1px, transparent 1px 6px)"},
    "niche": {"label": "Off the beaten path", "color": "#a3243f", "dark": "#4a0b1b",
              # map-grid dots
              "texture": "radial-gradient(rgba(255,255,255,.12) 1.4px, transparent 1.6px) 0 0 / 18px 18px"},
}

SITE_CSS = f"""
<style>
/* ---------- frame ---------- */
.block-container {{ max-width: 1160px; padding-top: 0 !important; }}
[data-testid="stDecoration"] {{ display: none; }}
/* Streamlit's own top bar (and the Share / GitHub icons Streamlit Cloud adds to it) sat
   invisibly on top of our header tabs and swallowed clicks. There's no sidebar to toggle,
   so remove that bar entirely. */
header[data-testid="stHeader"], .stAppHeader, [data-testid="stToolbar"], [data-testid="stToolbarActions"],
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"] {{ display: none !important; pointer-events: none !important; }}
/* No sidebar: every page keeps its settings in a panel at the top, so nothing can be
   closed by accident or cut off by a narrow column. */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] {{ display: none !important; }}
a, button {{ touch-action: manipulation; }}
/* While a page refreshes, Streamlit normally fades the old content ("cloudy"). Keep it
   solid and steady instead; the new numbers simply replace the old ones. */
[data-stale="true"], .stale-element, [data-testid="stElementContainer"][data-stale="true"] *,
[data-testid="stVerticalBlock"][data-stale="true"] {{ opacity: 1 !important; filter: none !important;
  transition: none !important; }}
[data-testid="stSkeleton"] {{ display: none !important; }}

/* ---------- site header (full-width navy band) ---------- */
.st-key-site_header {{ background: {NAVY}; box-shadow: 0 0 0 100vmax {NAVY}; clip-path: inset(-100vmax -100vmax 0 -100vmax);
  padding: 0.85rem 0; margin-bottom: 1.6rem; position: relative; z-index: 1000005; }}   /* in front of everything */
.st-key-site_header [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap; gap: 1rem; align-items: center; }}
.st-key-site_header [data-testid="stColumn"] {{ min-width: 0 !important; }}
.st-key-site_header [data-testid="stColumn"]:last-child {{ flex: 0 0 auto !important; width: auto !important; }}
.st-key-brand a[data-testid="stPageLink-NavLink"] > span:first-child {{ display: none; }}
.st-key-brand a[data-testid="stPageLink-NavLink"] {{ padding-left: 0; background: none !important; }}
.st-key-brand p {{ color: #fff !important; font-family: "Barlow Condensed", sans-serif !important;
  font-size: 1.55rem !important; font-weight: 700 !important; letter-spacing: .02em; text-transform: uppercase; }}
.brand-dot {{ color: #f2b134; }}
/* inline links on desktop */
.st-key-nav_inline {{ gap: 0.25rem !important; justify-content: flex-end; }}
.st-key-nav_inline a[data-testid="stPageLink-NavLink"] {{ background: none !important; border-radius: 0;
  border-bottom: 3px solid transparent; padding: 0.4rem 0.8rem 1.1rem; margin: -0.85rem 0 -0.85rem;
  min-height: 82px; display: flex; align-items: center; }}   /* tap area = the full height of the navy bar */
.st-key-nav_inline a[data-testid="stPageLink-NavLink"] p {{ color: #c9d3df !important; font-weight: 600; font-size: .95rem; }}
.st-key-nav_inline a[data-testid="stPageLink-NavLink"] span {{ color: #c9d3df !important; }}
[class*="st-key-navlink_on"] a[data-testid="stPageLink-NavLink"] {{ border-bottom-color: #f2b134 !important; }}
[class*="st-key-navlink_on"] a[data-testid="stPageLink-NavLink"] p {{ color: #fff !important; }}
@media (hover: hover) {{ .st-key-nav_inline a[data-testid="stPageLink-NavLink"]:hover p {{ color: #fff !important; }} }}
/* menu button (phones) */
.st-key-site_header [data-testid="stPopover"] button {{ min-height: 46px; padding: 0 1rem; background: transparent;
  border: 1px solid rgba(255,255,255,.35); color: #fff; }}
.st-key-site_header [data-testid="stPopover"] button * {{ color: #fff !important; }}
/* light / dark switch */
.st-key-site_header [data-testid="stColumn"]:has(.st-key-theme_col) {{ flex: 0 0 auto !important; width: auto !important; }}
/* small, quiet icon: no border or label, just a dim sun/moon that brightens on hover */
.st-key-theme_col button {{ min-height: 44px; min-width: 44px !important; padding: 0 !important;
  background: transparent !important; border: none !important; box-shadow: none !important; }}
.st-key-theme_col button p {{ display: none; }}
.st-key-theme_col button * {{ color: rgba(201,211,223,.55) !important; font-size: 1.05rem; }}
.st-key-theme_col iframe {{ display: none; }}
@media (hover: hover) {{ .st-key-theme_col button:hover * {{ color: #fff !important; }} }}
@media (min-width: 900px) {{ [data-testid="stColumn"]:has(.st-key-menu_col) {{ display: none !important; }} }}
@media (max-width: 899px) {{ [data-testid="stColumn"]:has(.st-key-nav_col) {{ display: none !important; }}
  [data-testid="stColumn"]:has(.st-key-brand) {{ flex: 1 1 auto !important; width: auto !important; }} }}
.st-key-brand p {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
/* menu panel: whole rows are tap targets */
[data-testid="stPopoverBody"]:has(.st-key-menu_items) {{ min-width: min(330px, 92vw); padding: 0.4rem; }}
.st-key-menu_items {{ gap: 2px; }}
.st-key-menu_items > [data-testid="stElementContainer"] {{ margin: 0 !important; }}
.st-key-menu_items [data-testid="stPageLink"], .st-key-menu_items [data-testid="stPageLink"] > div {{ width: 100%; }}
.st-key-menu_items a[data-testid="stPageLink-NavLink"] {{ display: flex; align-items: center; width: 100%;
  min-height: 50px; padding: 0 0.9rem; border-radius: 6px; -webkit-tap-highlight-color: rgba(12,26,43,.12); }}
.st-key-menu_items a[data-testid="stPageLink-NavLink"]:active {{ background: #e9edf2; }}
@media (hover: hover) {{ .st-key-menu_items a[data-testid="stPageLink-NavLink"]:hover {{ background: #e9edf2; }} }}
.st-key-menu_items a[data-testid="stPageLink-NavLink"] p {{ font-size: 1rem; }}
.st-key-menu_items [data-testid="stCaptionContainer"] {{ padding: 0.4rem 0.9rem 0.2rem; }}

/* ---------- big tap targets for every control (48px is the comfortable thumb size) ---------- */
.stButton button, .stDownloadButton button, .stFormSubmitButton button {{ min-height: 48px; padding: 0 1.4rem;
  font-size: 1rem; font-weight: 600; }}
.stButton button[kind="primary"] {{ min-width: 160px; }}
[data-testid="stPopover"] button {{ min-height: 48px; }}
[data-testid="stBaseButton-headerNoPadding"], [data-testid="stSidebarCollapseButton"] button {{ min-width: 44px; min-height: 44px; }}
[data-testid="stExpandSidebarButton"] {{ min-height: 46px !important; }}
/* tabs */
[data-testid="stTab"] {{ min-height: 48px; padding: 0 1rem !important; display: flex; align-items: center; }}
[data-testid="stTab"] p {{ font-size: 1rem; font-weight: 600; }}
/* expanders */
[data-testid="stExpander"] summary {{ min-height: 48px; display: flex; align-items: center; }}
/* radio buttons and checkboxes: the whole row is tappable */
.stRadio [role="radiogroup"] label, .stCheckbox label {{ min-height: 44px; display: flex; align-items: center;
  width: 100%; padding: 2px 0; cursor: pointer; }}
[data-testid="stToggle"] label {{ min-height: 44px; display: flex; align-items: center; cursor: pointer; }}
/* page links and inputs */
a[data-testid="stPageLink-NavLink"] {{ min-height: 44px; display: flex; align-items: center; }}
[data-testid="stSelectbox"] input, [data-testid="stMultiSelect"] input,
[data-testid="stTextInputField"], [data-testid="stNumberInputField"], .stTextInput input, .stNumberInput input {{ min-height: 44px; }}
[data-testid="stNumberInput"] button {{ min-width: 44px; min-height: 44px; }}
[data-testid="stSegmentedControl"] button, .stPills button {{ min-height: 44px; }}

/* ---------- settings panel ---------- */
.st-key-settings {{ background: #fff; border: 1px solid {BORDER}; border-radius: 10px; padding: 1rem 1.1rem 1.1rem !important;
  margin-bottom: 1.2rem; }}
.st-key-settings label p {{ white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }}
.st-key-settings [data-testid="stPills"] button {{ min-height: 44px; padding: 0 1rem; }}
.st-key-settings [data-testid="stPills"] button p {{ font-size: .98rem; font-weight: 600; }}

/* ---------- type ---------- */
h1, h2, h3, .banner h1 {{ font-family: "Barlow Condensed", sans-serif !important; letter-spacing: .01em; }}
h2 {{ text-transform: uppercase; }}
[data-testid="stMetricValue"] {{ font-family: "Barlow Condensed", sans-serif; font-weight: 600; }}
.eyebrow {{ text-transform: uppercase; letter-spacing: .14em; font-size: .72rem; font-weight: 700;
  color: #4a5a6c; margin: 0 0 .2rem 0; }}
p.lead {{ font-size: 1.1rem; line-height: 1.6; color: #3b4857; max-width: 64ch; }}

/* ---------- banners ---------- */
.banner {{ border-radius: 10px; padding: 1.6rem 1.8rem 1.5rem; color: #fff; margin: 0 0 1.4rem 0;
  position: relative; overflow: hidden; }}
.banner .eyebrow {{ color: rgba(255,255,255,.75); }}
.banner h1 {{ color: #fff; font-size: clamp(1.9rem, 4.6vw, 2.9rem); line-height: 1.05; margin: .1rem 0 .5rem 0;
  padding: 0; font-weight: 700; text-transform: uppercase; }}
.banner p {{ color: rgba(255,255,255,.88); max-width: 64ch; margin: 0; font-size: 1.02rem; line-height: 1.55; }}
.banner .chips {{ margin-top: .9rem; display: flex; gap: .5rem; flex-wrap: wrap; }}
.banner .chip {{ background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.25); border-radius: 999px;
  padding: .2rem .7rem; font-size: .8rem; font-weight: 600; }}

/* ---------- sport cards on the homepage ---------- */
[class*="st-key-card_"] {{ background: #fff; border: 1px solid {BORDER}; border-radius: 10px; overflow: hidden;
  padding: 0 1.1rem 1.1rem !important; height: 100%; }}
.card-text {{ min-height: 6.6em; }}
.card-top {{ height: 92px; margin: 0 -1.1rem .9rem -1.1rem; display: flex; align-items: flex-end;
  padding: 0 1.1rem .7rem; color: #fff; font-weight: 700; letter-spacing: .14em; font-size: .75rem;
  text-transform: uppercase; }}
[class*="st-key-cardlink_"] [data-testid="stPageLink"], [class*="st-key-cardlink_"] [data-testid="stPageLink"] > div {{ width: 100%; }}
[class*="st-key-cardlink_"] a[data-testid="stPageLink-NavLink"] {{ display: flex; align-items: center; width: 100%;
  min-height: 48px; padding: 0 .9rem; border-radius: 6px; background: {NAVY}; }}
[class*="st-key-cardlink_"] a[data-testid="stPageLink-NavLink"] * {{ color: #fff !important; font-weight: 600; }}
/* The whole card is clickable: the link's hit area is stretched over the entire card. */
[class*="st-key-card_"] {{ position: relative; cursor: pointer; transition: box-shadow .15s, transform .15s; }}
[class*="st-key-card_"] [class*="st-key-cardlink_"], [class*="st-key-card_"] [class*="st-key-cardlink_"] * {{ position: static !important; }}
[class*="st-key-cardlink_"] a[data-testid="stPageLink-NavLink"]::after {{ content: ""; position: absolute; inset: 0; z-index: 2; }}
@media (hover: hover) {{
  [class*="st-key-card_"]:hover {{ box-shadow: 0 8px 22px rgba(12,26,43,.14); transform: translateY(-2px); border-color: #c4ccd6; }}
  [class*="st-key-card_"]:hover [class*="st-key-cardlink_"] a[data-testid="stPageLink-NavLink"] {{ background: #1d3a5c; }}
}}

/* step tiles */
.step {{ border-left: 4px solid #f2b134; padding: .2rem 0 .2rem .9rem; }}
.step b {{ font-family: "Barlow Condensed", sans-serif; font-size: 1.25rem; text-transform: uppercase; letter-spacing: .02em; }}
.step p {{ margin: .3rem 0 0 0; color: #3b4857; }}
</style>
"""


# Dark mode: Streamlit recolors its own widgets from .streamlit/config.toml ([theme.dark]);
# these rules recolor the site's own cards, panels and text to match.
DARK_RULES = """
.st-key-settings, [class*="st-key-card_"], .lv-card, .gd-head { background: #151f2b !important; border-color: #2a3644 !important; }
div[style*="background:#fff"] { background: #151f2b !important; border-color: #2a3644 !important; }
[style*="color:#3b4857"], [style*="color:#4a5a6c"], [style*="color:#6b7889"], p.lead, .step p { color: #b8c4d2 !important; }
.eyebrow, .lv-league, .lv-final { color: #9fb0c3 !important; }
.banner .eyebrow, .hero .eyebrow { color: rgba(255,255,255,.75) !important; }
.hero .eyebrow { color: #f2b134 !important; }
.st-key-menu_items a[data-testid="stPageLink-NavLink"]:active { background: #1c2836 !important; }
@media (hover: hover) { .st-key-menu_items a[data-testid="stPageLink-NavLink"]:hover { background: #1c2836 !important; }
  [class*="st-key-card_"]:hover { border-color: #3c4b5d !important; box-shadow: 0 8px 22px rgba(0,0,0,.45) !important; } }
.lv-card.is-live { border-color: #7a2f35 !important; }
.lv-card td { color: #dbe3ec !important; border-top-color: #222e3c !important; }
.lv-card th, .lv-team small, .lv-foot, .gd-team small { color: #8d9cad !important; }
tr.lv-win td.lv-team span, tr.lv-win .lv-score, .lv-count, .gd-score, .gd-team b { color: #f3f6f9 !important; }
.lv-pre { color: #a9c7ee !important; } .lv-live { color: #ff6b6b !important; }
.lv-bar { background: #263241 !important; }
.gd-box { background: #1c2836 !important; color: #dbe3ec; }
div[style*="background:#e3e7ee"] { background: #263241 !important; }
.ffmc-wl-row { color: #dbe3ec; }
"""


def is_dark() -> bool | None:
    """True/False once the browser has told us its theme; None on the very first run."""
    try:
        t = st.context.theme.type
    except Exception:
        return None
    return None if t is None else t == "dark"


def apply_site_css() -> None:
    dark = is_dark()
    if dark:
        extra = DARK_RULES
    elif dark is None:   # not known yet: follow the device setting until the browser reports it
        extra = f"@media (prefers-color-scheme: dark) {{ {DARK_RULES} }}"
    else:
        extra = ""
    st.markdown(SITE_CSS + (f"<style>{extra}</style>" if extra else ""), unsafe_allow_html=True)


THEME_JS = """
<script>
// Remember the chosen theme the way Streamlit does (per page path), then reload to apply it.
const w = window.parent, pages = %s, cur = %s, mode = %s;
let path = w.location.pathname.replace(/\\/$/, "");
let base = cur && path.endsWith("/" + cur) ? path.slice(0, -cur.length - 1) : path;
for (const p of pages) {
  for (const k of [base + "/" + p, (base + "/" + p).replace(/\\/$/, "")]) {
    w.localStorage.setItem("stActiveTheme-" + (k || "/") + "-v2", JSON.stringify(mode));
  }
}
w.location.reload();
</script>
"""


def theme_button(pages: list[str], current: str) -> None:
    """Light / Dark switch for the header."""
    import json

    import streamlit.components.v1 as components

    dark = bool(is_dark())
    if st.button("Light" if dark else "Dark", icon=":material/light_mode:" if dark else ":material/dark_mode:",
                 key="theme_toggle", help="Switch to light mode" if dark else "Switch to dark mode"):
        components.html(THEME_JS % (json.dumps(pages), json.dumps(current), json.dumps("Light" if dark else "Dark")),
                        height=0)


def banner(sport: str, title: str, text: str, chips: list[str] | None = None) -> None:
    """Colored page banner with the sport's texture. Also tints primary buttons in that color."""
    s = SPORTS[sport]
    chip_html = "".join(f'<span class="chip">{c}</span>' for c in chips or [])
    st.markdown(f"""
<style>
.stButton button[kind="primary"] {{ background: {s['color']}; border-color: {s['color']}; }}
.stButton button[kind="primary"]:active {{ background: {s['dark']}; border-color: {s['dark']}; }}
@media (hover: hover) {{ .stButton button[kind="primary"]:hover {{ background: {s['dark']}; border-color: {s['dark']}; }} }}
</style>
<div class="banner" style="background: {s['texture']}, linear-gradient(120deg, {s['dark']} 0%, {s['color']} 100%);">
  <p class="eyebrow">{s['label']}</p>
  <h1>{title}</h1>
  <p>{text}</p>
  {f'<div class="chips">{chip_html}</div>' if chips else ''}
</div>""", unsafe_allow_html=True)


def card_top(sport: str, label: str) -> str:
    s = SPORTS[sport]
    return (f'<div class="card-top" style="background: {s["texture"]}, '
            f'linear-gradient(120deg, {s["dark"]} 0%, {s["color"]} 100%);">{label}</div>')
