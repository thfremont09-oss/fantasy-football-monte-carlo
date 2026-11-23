"""Shared look and feel: site-wide CSS, sport colors and page banners."""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

APP_VERSION = "2026-11-23b"  # bump on each release so you can tell which version is live

NAVY = "#0c1a2b"
SHADOW = "none"
INK = "#14202e"
BORDER = "#dfe3e8"

# One color per sport, plus a subtle texture for its banner.
SPORTS = {
    "nfl": {"label": "NFL", "color": "#2e7d3a", "dark": "#164a20",
            # yard lines
            "texture": "repeating-linear-gradient(90deg, rgba(255,255,255,.10) 0 2px, transparent 2px 72px)"},
    "nba": {"label": "NBA Fantasy", "color": "#1d428a", "dark": "#0d2250", "texture": "none"},
    "nhl": {"label": "NHL Fantasy", "color": "#0b5b7a", "dark": "#05334a", "texture": "none"},
    "ncaa": {"label": "NCAA Basketball", "color": "#c75a1c", "dark": "#7a320c",
             # hardwood planks
             "texture": "repeating-linear-gradient(90deg, rgba(255,255,255,.06) 0 22px, rgba(0,0,0,.06) 22px 44px)"},
    "epl": {"label": "Premier League", "color": "#0f7a86", "dark": "#06464f",
            # mown pitch stripes
            "texture": "repeating-linear-gradient(90deg, rgba(255,255,255,.07) 0 56px, transparent 56px 112px)"},
    "f1": {"label": "Formula 1", "color": "#d0021b", "dark": "#5c000b",
           # chequered flag
           "texture": "repeating-conic-gradient(rgba(255,255,255,.07) 0 25%, transparent 0 50%) 0 0 / 26px 26px"},
    "stats": {"label": "Player stats", "color": "#0b6e4f", "dark": "#053a2a", "texture": "none"},
    "edge": {"label": "Our sims vs Kalshi", "color": "#5b3cc4", "dark": "#24165f", "texture": "none"},
    "lab": {"label": "The Lab", "color": "#c0392b", "dark": "#7a1f16", "texture": "none"},
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

# The logo mark (a bell curve of bars: a million simulated games) from static/brand/mark.svg, inlined.
_MARK = Path(__file__).resolve().parent.parent / "static" / "brand" / "mark.svg"
MARK_URI = "data:image/svg+xml;base64," + base64.b64encode(_MARK.read_bytes()).decode() if _MARK.exists() else ""
BRAND_TEXT_X = "calc(5px + 2.1rem + .6rem)"           # where "Monte Sports Lab" starts, after the mark
BRAND_TEXT_W = f"calc(100% - {BRAND_TEXT_X} - 1.55rem)"   # its width (minus the mark before it and the home icon after)

SITE_CSS = f"""
<style>
@import url("https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800;900&family=Source+Serif+4:opsz,wght@8..60,600;8..60,700&display=swap");
/* ---------- colours shared by custom pieces (switched for dark mode below) ---------- */
:root {{ --ink: #111827; --sub: #374151; --muted: #6b7280; --line: #e5e7eb; --card: #ffffff; --soft: #f5f6f8;
  --accent: #d6232a; }}
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
.st-key-site_header {{ background: {NAVY}; padding: 0 !important; height: 76px !important; min-height: 76px !important;
  justify-content: center; box-sizing: border-box; overflow: visible;
  margin-bottom: 1.8rem; position: relative;
  z-index: 1000005;                                  /* in front of everything */
  clip-path: inset(-200px -100vmax 0 -100vmax); }}   /* nothing pokes out below the band */
/* the navy band runs edge to edge (and up to the top of the window): one solid layer, no seams */
.st-key-site_header::before {{ content: ""; position: absolute; top: -200px; bottom: 0; left: 50%; width: 100vw;
  transform: translateX(-50%); background: {NAVY}; z-index: -1; }}
[data-testid="stMain"], [data-testid="stAppViewContainer"] {{ overflow-x: hidden; }}
.st-key-site_header [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap; gap: 1rem; align-items: center; }}
.st-key-site_header [data-testid="stColumn"] {{ min-width: 0 !important; }}
.st-key-site_header [data-testid="stColumn"]:last-child {{ flex: 0 0 auto !important; width: auto !important; }}
.st-key-brand a[data-testid="stPageLink-NavLink"] > span:first-child {{ display: none; }}
.st-key-brand a[data-testid="stPageLink-NavLink"] {{ padding-left: 0; background: none !important; }}
/* wordmark: the bell-curve mark, then "Monte Sports Lab" */
.st-key-brand p {{ color: #fff !important; font-family: "Archivo", sans-serif !important;
  font-size: 1.4rem !important; font-weight: 800 !important; letter-spacing: -.02em; display: flex !important;
  align-items: center; gap: .6rem; }}
.st-key-brand p::before {{ content: ""; flex: 0 0 auto; width: 2.1rem; height: 2.1rem; border-radius: 8px;
  background: url("{MARK_URI}") center / cover no-repeat; box-shadow: 0 0 0 1px rgba(255,255,255,.08);
  transition: transform .18s ease, box-shadow .18s ease; }}
/* a little room on the left, so the mark's edge and focus ring aren't clipped */
.st-key-brand p {{ padding-left: 5px !important; margin-left: -5px !important; }}
/* the wordmark is the home button: a small house icon after it says so at all times; the hairline underline
   slides in only while you hover */
.st-key-brand a[data-testid="stPageLink-NavLink"] {{ cursor: pointer; }}
.st-key-brand p::after {{ content: "home"; font-family: "Material Symbols Rounded"; font-weight: 400;
  font-style: normal; font-size: 1.15rem; line-height: 1; letter-spacing: 0; color: rgba(255,255,255,.42);
  margin-left: -.1rem; transition: color .2s ease; font-feature-settings: "liga"; }}
.st-key-brand p {{ background-image: linear-gradient(rgba(255,255,255,.55), rgba(255,255,255,.55));
  background-repeat: no-repeat; background-size: 0 1px; background-position: {BRAND_TEXT_X} 92%;
  transition: background-size .25s ease; }}
@media (hover: hover) {{
  .st-key-brand a:hover p {{ background-size: {BRAND_TEXT_W} 1px; }}
  .st-key-brand a:hover p::after {{ color: #fff; }}
  .st-key-brand a:hover p::before {{ transform: translateY(-1px) rotate(-3deg); box-shadow: 0 4px 12px rgba(242,177,52,.35); }}
}}
/* header tabs get the same hairline underline on hover */
.st-key-nav_inline a[data-testid="stPageLink-NavLink"] p {{
  background-image: linear-gradient(rgba(255,255,255,.55), rgba(255,255,255,.55)); background-repeat: no-repeat;
  background-size: 0 1px; background-position: 0 100%; transition: background-size .25s ease, color .15s ease;
  padding-bottom: 2px; }}
@media (hover: hover) {{
  .st-key-nav_inline a[data-testid="stPageLink-NavLink"]:hover p {{ background-size: 100% 1px; }} }}
.st-key-brand a:focus-visible {{ outline: 2px solid rgba(255,255,255,.6); outline-offset: 4px; border-radius: 4px; }}
.brand-dot {{ color: #f2b134; }}
/* inline links on desktop */
.st-key-nav_inline {{ gap: 0.25rem !important; justify-content: flex-end; }}
.st-key-nav_inline a[data-testid="stPageLink-NavLink"] {{ background: none !important; border-radius: 0;
  border-bottom: 3px solid transparent; border-top: 3px solid transparent; padding: 0 .5rem;
  height: 76px; min-height: 76px; display: flex; align-items: center; }}   /* tap area = the full height of the navy bar */
.st-key-nav_inline a[data-testid="stPageLink-NavLink"] p {{ color: #c9d3df !important; font-weight: 600; font-size: .95rem; }}
/* text-only links, like a news site's section nav (and room for every section) */
.st-key-nav_inline a[data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"],
.st-key-nav_inline a[data-testid="stPageLink-NavLink"] > span:first-child:not(:only-child) {{ display: none !important; }}
@media (max-width: 1250px) {{ .st-key-nav_inline a[data-testid="stPageLink-NavLink"] {{ padding: 0 .4rem; }} }}
@media (min-width: 1081px) {{
  [data-testid="stColumn"]:has(.st-key-brand) {{ flex: 0 0 auto !important; width: auto !important; }}
  [data-testid="stColumn"]:has(.st-key-nav_col) {{ flex: 1 1 0 !important; width: auto !important; min-width: 0 !important; }}
  .st-key-nav_inline {{ flex-wrap: nowrap !important; }} }}
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
/* the tabs need about 1080px; narrower than that, the Menu button takes over */
@media (min-width: 1081px) {{ [data-testid="stColumn"]:has(.st-key-menu_col) {{ display: none !important; }} }}
@media (max-width: 1080px) {{ [data-testid="stColumn"]:has(.st-key-nav_col) {{ display: none !important; }}
  [data-testid="stColumn"]:has(.st-key-brand) {{ flex: 1 1 auto !important; width: auto !important; }} }}
.st-key-brand p {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
@media (max-width: 520px) {{ .st-key-brand p {{ font-size: 1.18rem !important; letter-spacing: -.01em; gap: .5rem; }}
  .st-key-brand p::before {{ width: 1.9rem; height: 1.9rem; }}
  /* phones: the menu button is just its icon, so the whole name fits */
  .st-key-menu_col [data-testid="stPopover"] button [data-testid="stMarkdownContainer"],
  .st-key-menu_col [data-testid="stPopover"] button [data-testid="stIconMaterial"]:last-child:not(:first-child) {{ display: none !important; }}
  .st-key-menu_col [data-testid="stPopover"] button {{ padding: 0 .75rem !important; }}
  .block-container {{ padding-left: 1rem !important; padding-right: 1rem !important; }} }}
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
  font-size: 1rem; font-weight: 600; border-radius: 6px; }}
.stButton button[kind="primary"] {{ min-width: 160px; }}
[data-testid="stPopover"] button {{ min-height: 48px; }}
[data-testid="stBaseButton-headerNoPadding"], [data-testid="stSidebarCollapseButton"] button {{ min-width: 44px; min-height: 44px; }}
[data-testid="stExpandSidebarButton"] {{ min-height: 46px !important; }}
/* tabs */
[data-testid="stTab"] {{ min-height: 48px; padding: 0 1rem !important; display: flex; align-items: center; }}
[data-testid="stTab"] p {{ font-size: 1rem; font-weight: 600; }}
[data-testid="stTab"][aria-selected="false"] p {{ opacity: .62; }}
[data-testid="stTabs"] {{ margin-top: .2rem; }}
/* expanders */
[data-testid="stExpander"] summary {{ min-height: 48px; display: flex; align-items: center; }}
[data-testid="stExpander"] details {{ border-radius: 6px !important; background: #fff; }}
[data-testid="stExpander"] summary p {{ font-weight: 600; }}
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
.st-key-settings, .st-key-bb_settings {{ background: #f7f8fa; border: 1px solid {BORDER}; border-radius: 8px;
  padding: 1.15rem 1.25rem 1.25rem !important; margin-bottom: 1.4rem; box-shadow: {SHADOW}; }}
/* controls side by side line up along their bottom edge (a toggle next to a dropdown, etc.) */
.st-key-settings [data-testid="stHorizontalBlock"], .st-key-bb_settings [data-testid="stHorizontalBlock"] {{
  align-items: stretch; }}
.st-key-settings [data-testid="stColumn"], .st-key-bb_settings [data-testid="stColumn"] {{
  display: flex; flex-direction: column; justify-content: flex-end; }}
/* a toggle beside a dropdown sits level with the dropdown's box, not its label */
.st-key-settings [data-testid="stColumn"] [data-testid="stCheckbox"] {{ transform: translateY(10px); }}
[data-testid="stMetric"] {{ background: #fff; border: 1px solid {BORDER}; border-top: 3px solid {INK}; border-radius: 6px; padding: .8rem 1rem .85rem;
  box-shadow: {SHADOW}; height: 100%; }}
[data-testid="stMetricLabel"] p {{ font-size: .78rem !important; font-weight: 600; text-transform: uppercase;
  letter-spacing: .06em; color: #5b6878; }}
[data-testid="stMetricValue"] {{ font-size: 2rem !important; line-height: 1.15; }}
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 6px; overflow: hidden; box-shadow: {SHADOW}; }}
[data-testid="stAlert"] > div {{ border-radius: 6px; }}
[data-testid="stVegaLiteChart"] {{ background: #fff; border: 1px solid {BORDER}; border-radius: 6px;
  padding: .6rem .6rem .2rem; box-shadow: {SHADOW}; }}
h2 {{ margin-top: .4rem !important; }}
h3 {{ margin-top: .3rem !important; }}
.st-key-settings label p, .st-key-bb_settings label p {{ white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }}
.st-key-settings [data-testid="stPills"] button {{ min-height: 44px; padding: 0 1rem; }}
.st-key-settings [data-testid="stPills"] button p {{ font-size: .98rem; font-weight: 600; }}

/* ---------- type ---------- */
h1, h2, h3, .banner h1 {{ font-family: "Archivo", sans-serif !important; letter-spacing: -.01em; font-weight: 800 !important; }}
[data-testid="stMetricValue"] {{ font-family: "Barlow Condensed", sans-serif; font-weight: 600; }}
.eyebrow {{ text-transform: uppercase; letter-spacing: .14em; font-size: .72rem; font-weight: 700;
  color: #4a5a6c; margin: 0 0 .2rem 0; }}
p.lead {{ font-size: 1.1rem; line-height: 1.6; color: #3b4857; max-width: 64ch; }}

/* ---------- banners ---------- */
/* page header: flat and editorial */
.phead {{ padding: .2rem 0 1.15rem; margin: 0 0 1.3rem; border-bottom: 1px solid {BORDER}; }}
.ptag {{ display: flex; align-items: center; gap: .5rem; margin: 0 0 .35rem; font-size: .76rem; font-weight: 700;
  letter-spacing: .12em; text-transform: uppercase; color: var(--c); }}
.ptag i {{ width: 10px; height: 3px; background: var(--c); display: inline-block; }}
.phead h1 {{ font-size: clamp(2.1rem, 5vw, 3.2rem) !important; line-height: 1 !important; margin: 0 0 .55rem !important;
  padding: 0 !important; font-weight: 800; color: var(--ink); letter-spacing: -.02em; }}
.phead .dek {{ font-size: 1.06rem; line-height: 1.55; color: var(--sub); max-width: 70ch; margin: 0; }}
.pmeta {{ margin: .6rem 0 0; font-size: .86rem; font-weight: 600; color: var(--muted); }}
.pmeta span {{ color: #b3bcc7; margin: 0 .2rem; }}
.banner {{ border-radius: 6px; padding: 1.7rem 1.9rem 1.6rem; color: #fff; margin: 0 0 1.4rem 0;
  position: relative; overflow: hidden; }}
@media (max-width: 640px) {{ .banner {{ padding: 1.25rem 1.2rem 1.2rem; }} .banner p {{ font-size: .95rem !important; }} }}
.banner .eyebrow {{ color: rgba(255,255,255,.75); }}
.banner h1 {{ color: #fff; font-size: clamp(1.9rem, 4.6vw, 2.9rem); line-height: 1.05; margin: .1rem 0 .5rem 0;
  padding: 0; font-weight: 700; text-transform: uppercase; }}
.banner p {{ color: rgba(255,255,255,.88); max-width: 64ch; margin: 0; font-size: 1.02rem; line-height: 1.55; }}
.banner .chips {{ margin-top: .9rem; display: flex; gap: .5rem; flex-wrap: wrap; }}
.banner .chip {{ background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.25); border-radius: 999px;
  padding: .2rem .7rem; font-size: .8rem; font-weight: 600; }}

/* ---------- sport cards on the homepage ---------- */
[data-testid="stColumn"]:has([class*="st-key-card_"]) > [data-testid="stVerticalBlock"] {{ height: 100%; }}
[data-testid="stLayoutWrapper"]:has(> [class*="st-key-card_"]) {{ flex: 1 1 auto !important; }}
[class*="st-key-card_"] {{ background: #fff; border: 1px solid {BORDER}; border-radius: 6px; overflow: hidden;
  padding: 0 1.15rem 1.15rem !important; height: 100%; display: flex; flex-direction: column; }}
[class*="st-key-card_"] h3 {{ padding-bottom: .2rem !important; }}
[class*="st-key-cardlink_"],
[data-testid="stLayoutWrapper"]:has(> [class*="st-key-cardlink_"]) {{ margin-top: auto !important; }}  /* button at the bottom */
.card-text {{ margin-bottom: .4rem; color: #3b4857; line-height: 1.5; }}
.card-top {{ margin: 0 -1.15rem .2rem -1.15rem; padding: .85rem 1.15rem 0; border-top: 5px solid var(--c);
  color: var(--c); font-weight: 700; letter-spacing: .12em; font-size: .72rem; text-transform: uppercase;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
[class*="st-key-cardlink_"] [data-testid="stPageLink"], [class*="st-key-cardlink_"] [data-testid="stPageLink"] > div {{ width: 100%; }}
[class*="st-key-cardlink_"] a[data-testid="stPageLink-NavLink"] {{ display: flex; align-items: center; width: 100%;
  min-height: 46px; padding: 0 .9rem; border-radius: 6px; background: {NAVY}; }}
[class*="st-key-cardlink_"] a[data-testid="stPageLink-NavLink"] * {{ color: #fff !important; font-weight: 600; }}
/* The whole card is clickable: the link's hit area is stretched over the entire card. */
[class*="st-key-card_"] {{ position: relative; cursor: pointer; transition: box-shadow .15s, transform .15s; }}
[class*="st-key-card_"] [class*="st-key-cardlink_"], [class*="st-key-card_"] [class*="st-key-cardlink_"] * {{ position: static !important; }}
[class*="st-key-cardlink_"] a[data-testid="stPageLink-NavLink"]::after {{ content: ""; position: absolute; inset: 0; z-index: 2; }}
@media (hover: hover) {{
  [class*="st-key-card_"]:hover {{ border-color: #9aa5b1; }}
  [class*="st-key-card_"]:hover [class*="st-key-cardlink_"] a[data-testid="stPageLink-NavLink"] {{ background: #1d3a5c; }}
}}

/* homepage grids: rows of tiles that always line up, and stack on phones */
.grid.g3 {{ grid-template-columns: repeat(3, 1fr); }}
@media (max-width: 900px) {{ .grid.g3 {{ grid-template-columns: repeat(2, 1fr); }} }}
@media (max-width: 560px) {{ .grid.g3 {{ grid-template-columns: 1fr; }} }}
.grid {{ display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); align-items: stretch;
  margin: .3rem 0 .4rem; }}
.tile {{ background: #fff; border: 1px solid {BORDER}; border-radius: 6px; padding: 1rem 1.1rem; box-shadow: {SHADOW};
  height: 100%; }}
.tile .big {{ font-family: "Barlow Condensed", sans-serif; font-size: 2.1rem; font-weight: 700; line-height: 1; margin: .2rem 0; }}
.tile p {{ margin: .25rem 0 0; color: #3b4857; font-size: .93rem; line-height: 1.5; }}
.tile ul {{ margin: .4rem 0 0; padding: 0; list-style: none; }}
.tile li {{ margin: .45rem 0 0; padding-left: .7rem; border-left: 3px solid var(--c, #c4ccd6); font-size: .93rem;
  line-height: 1.45; color: #2b3a4a; }}
/* step tiles */
.step {{ border-left: 4px solid #f2b134; padding: .2rem 0 .2rem .9rem; }}
.tile.step {{ padding: 1rem 1.1rem; border-left: 4px solid #f2b134; }}
.step b {{ font-family: "Barlow Condensed", sans-serif; font-size: 1.25rem; text-transform: uppercase; letter-spacing: .02em; }}
.step p {{ margin: .3rem 0 0 0; color: #3b4857; }}
</style>
"""


# Dark mode: Streamlit recolors its own widgets from .streamlit/config.toml ([theme.dark]);
# these rules recolor the site's own cards, panels and text to match.
DARK_RULES = """
.st-key-settings, .st-key-bb_settings, [class*="st-key-card_"], .lv-card, .gd-head { background: #151f2b !important; border-color: #2a3644 !important; }
div[style*="background:#fff"] { background: #151f2b !important; border-color: #2a3644 !important; }
[style*="color:#3b4857"], [style*="color:#4a5a6c"], [style*="color:#6b7889"], p.lead, .step p { color: #b8c4d2 !important; }
.eyebrow, .lv-league, .lv-final { color: #9fb0c3 !important; }
.banner .eyebrow, .hero .eyebrow { color: rgba(255,255,255,.75) !important; }
.hero .eyebrow { color: #f2b134 !important; }
.st-key-menu_items a[data-testid="stPageLink-NavLink"]:active { background: #1c2836 !important; }
@media (hover: hover) { .st-key-menu_items a[data-testid="stPageLink-NavLink"]:hover { background: #1c2836 !important; }
  [class*="st-key-card_"]:hover { border-color: #3c4b5d !important; box-shadow: 0 8px 22px rgba(0,0,0,.45) !important; } }
[data-testid="stMetric"], [data-testid="stVegaLiteChart"], .tile { background: #151f2b !important; border-color: #2a3644 !important; }
[data-testid="stDataFrame"] { border-color: #2a3644 !important; }
[data-testid="stMetricLabel"] p { color: #9fb0c3 !important; }
.tile p, .card-text { color: #b8c4d2 !important; } .tile li { color: #dbe3ec !important; }
.lv-card.is-live { box-shadow: inset 3px 0 0 #ff5a5a !important; }
.phead { border-color: #2a3644 !important; }
.hero, .hero .facts, .hero .facts div { border-color: #2a3644 !important; } .hero .facts small { color: #9fb0c3 !important; }
.hero h1 { color: #f3f6f9 !important; }
[class*="st-key-cardlink_"] a[data-testid="stPageLink-NavLink"] { background: #24384f !important; } .phead h1, .hero h1 { color: #f3f6f9 !important; }
.phead .dek, .hero .dek { color: #b8c4d2 !important; } .pmeta { color: #9fb0c3 !important; }
.st-key-settings, .st-key-bb_settings { background: #121b26 !important; }
[data-testid="stExpander"] details { background: #151f2b !important; }
[data-testid="stMetric"] { border-top-color: #9fb0c3 !important; }
.lv-card td { color: #dbe3ec !important; border-top-color: #222e3c !important; }
.lv-card th, .lv-team small, .lv-foot, .gd-team small, .bb-game { color: #8d9cad !important; }
tr.lv-win td.lv-team span, tr.lv-win .lv-score, .lv-count, .gd-score, .gd-team b { color: #f3f6f9 !important; }
.lv-pre { color: #a9c7ee !important; } .lv-live { color: #ff6b6b !important; }
.lv-bar { background: #263241 !important; }
.gd-box { background: #1c2836 !important; color: #dbe3ec; }
.bb-pay { background: #17302a !important; } .bb-how { color: #b8c4d2 !important; }
.bb-pos { color: #4cc26f !important; } .bb-neg { color: #ff6b6b !important; }
div[style*="background:#e3e7ee"] { background: #263241 !important; }
.ffmc-wl-row { color: #dbe3ec; }
:root { --ink: #f3f4f6; --sub: #d1d5db; --muted: #9ca3af; --line: #2a3644; --card: #151f2b; --soft: #121b26;
  --accent: #ff4d55; }

.f1-card { background: #151f2b !important; border-color: #2a3644 !important; } .f1-team, .f1-nums small { color: #9fb0c3 !important; }
.f1-card .f1-pic { background-color: #1c2836 !important; }
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
    """Page header: a small colored sport tag, a bold headline, one plain sentence and a line of facts.
    Also tints primary buttons in the sport's color."""
    s = SPORTS[sport]
    meta = " <span>·</span> ".join(chips or [])
    st.markdown(f"""<style>
.stButton button[kind="primary"] {{ background: {s['color']}; border-color: {s['color']}; }}
.stButton button[kind="primary"]:active {{ background: {s['dark']}; border-color: {s['dark']}; }}
@media (hover: hover) {{ .stButton button[kind="primary"]:hover {{ background: {s['dark']}; border-color: {s['dark']}; }} }}
</style>
<div class="phead" style="--c:{s['color']}"><p class="ptag"><i></i>{s['label']}</p><h1>{title}</h1><p class="dek">{text}</p>{f'<p class="pmeta">{meta}</p>' if chips else ''}</div>""",
                unsafe_allow_html=True)


def card_top(sport: str, label: str) -> str:
    """A thin bar in the sport's color across the top of a card, with a small label under it."""
    return f'<div class="card-top" style="--c:{SPORTS[sport]["color"]}">{label}</div>'
