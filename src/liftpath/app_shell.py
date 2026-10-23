"""The app frame: the top bar with the logo, the tab bar, the loading screen and the global
styles of the dark theme. Streamlit code only, no logic."""

import html

import streamlit as st

from liftpath.style import (
    DARK_BG,
    DARK_BLUE,
    DARK_BORDER,
    DARK_MUTED,
    DARK_SURFACE,
    DARK_SURFACE_2,
    DARK_TEXT,
    DARK_TEXT_SECONDARY,
)

# Served by Streamlit from app/static (server.enableStaticServing in .streamlit/config.toml).
LOGO_URL = "app/static/logo_white.png"

GLOBAL_CSS = f"""
<style>
@keyframes lp-fade {{from {{opacity:0; transform:translateY(4px);}}
  to {{opacity:1; transform:none;}}}}
@keyframes lp-pulse {{0%,100% {{transform:scale(1); opacity:.92;}}
  50% {{transform:scale(1.05); opacity:1;}}}}
@keyframes lp-bar {{0% {{left:-40%;}} 100% {{left:100%;}}}}

.stApp {{background:radial-gradient(1200px 500px at 85% -10%, #16233a 0%, {DARK_BG} 60%);}}
header[data-testid="stHeader"] {{background:transparent;}}
[data-testid="stMainBlockContainer"] {{padding-top:2.2rem; max-width:1400px;}}

.lp-top {{display:flex; align-items:center; gap:16px; padding:14px 20px; margin-bottom:14px;
  background:linear-gradient(135deg, {DARK_SURFACE} 0%, #1a2943 100%);
  border:1px solid {DARK_BORDER}; border-radius:16px; animation:lp-fade .35s ease-out;}}
.lp-top img {{width:52px; height:52px; flex:0 0 52px;}}
.lp-top .txt {{flex:1 1 auto; min-width:0;}}
.lp-top .name {{font-size:1.55rem; font-weight:800; letter-spacing:.2px; color:{DARK_TEXT};
  line-height:1.1;}}
.lp-top .pitch {{color:{DARK_TEXT_SECONDARY}; font-size:.95rem; margin-top:2px;}}
.lp-top .tag {{margin-left:auto; padding:4px 12px; border-radius:999px; font-size:.8rem;
  color:{DARK_TEXT_SECONDARY}; border:1px solid {DARK_BORDER}; background:{DARK_SURFACE_2};
  white-space:nowrap;}}

/* The tab bar: a pill bar that stays at the top of the window (Streamlit 1.66 markup). */
.stTabs [role="tablist"] {{gap:4px; padding:6px; background:{DARK_SURFACE};
  border:1px solid {DARK_BORDER}; border-radius:14px; position:sticky; top:0.4rem;
  z-index:50; box-shadow:0 6px 18px rgba(0,0,0,.25); overflow-x:auto;}}
.stTabs [role="tablist"]::before, .stTabs [role="tablist"]::after {{display:none;}}
.stTabs [role="tab"] {{height:auto; padding:8px 16px; border-radius:10px; border:none;
  color:{DARK_TEXT_SECONDARY}; background:transparent; transition:background .15s, color .15s;}}
.stTabs [role="tab"] p {{font-size:.95rem; font-weight:600;}}
.stTabs [role="tab"]:hover {{background:{DARK_SURFACE_2}; color:{DARK_TEXT};}}
.stTabs [role="tab"][aria-selected="true"] {{background:{DARK_BLUE}; color:#fff;}}
.stTabs [data-testid="stTabPanel"] {{padding-top:18px; animation:lp-fade .3s ease-out;}}

[data-testid="stExpander"] details {{background:{DARK_SURFACE}; border-color:{DARK_BORDER};
  border-radius:12px;}}
[data-testid="stImage"] img {{border-radius:12px;}}
[data-testid="stCaptionContainer"] {{color:{DARK_MUTED};}}

/* Phone width. */
@media (max-width: 640px) {{
  [data-testid="stMainBlockContainer"] {{padding-left:1rem; padding-right:1rem;
    padding-top:1.4rem;}}
  .lp-top {{flex-wrap:wrap; gap:10px 12px; padding:12px 14px;}}
  .lp-top img {{width:40px; height:40px; flex-basis:40px;}}
  .lp-top .name {{font-size:1.3rem;}}
  .lp-top .pitch {{font-size:.86rem;}}
  .lp-top .txt {{flex:1 1 0;}}
  .lp-top .tag {{margin-left:52px; flex:0 0 auto; max-width:calc(100% - 52px);
    white-space:normal; font-size:.75rem; order:3;}}
  .lp-top::after {{content:""; order:2; flex-basis:100%; height:0;}}
  .stTabs [role="tablist"] {{flex-wrap:wrap; overflow:visible; position:static;}}
  .stTabs [role="tab"] {{padding:7px 12px;}}
  [data-testid="stTable"] {{overflow-x:auto;}}
  [data-testid="stTable"] table {{min-width:600px;}}
  /* Dense charts keep a readable width and scroll sideways in their own box. */
  .st-key-rescue_chart, .st-key-sim_pass_chart {{overflow-x:auto;}}
  .st-key-rescue_chart > div, .st-key-sim_pass_chart > div {{min-width:640px;}}
}}

.lp-splash {{position:fixed; inset:0; z-index:9999; display:flex; flex-direction:column;
  align-items:center; justify-content:center; gap:18px; background:{DARK_BG};}}
.lp-splash img {{width:120px; height:120px; animation:lp-pulse 1.6s ease-in-out infinite;}}
.lp-splash .name {{font-size:2rem; font-weight:800; color:{DARK_TEXT};}}
.lp-splash .msg {{color:{DARK_TEXT_SECONDARY};}}
.lp-splash .track {{position:relative; width:220px; height:4px; border-radius:4px;
  background:{DARK_SURFACE_2}; overflow:hidden;}}
.lp-splash .track span {{position:absolute; top:0; width:40%; height:100%; border-radius:4px;
  background:{DARK_BLUE}; animation:lp-bar 1.1s ease-in-out infinite;}}
</style>
"""


def global_styles() -> None:
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def top_bar(pitch: str, tag: str) -> None:
    st.markdown(
        f'<div class="lp-top"><img src="{LOGO_URL}" alt="LiftPath logo"><div class="txt">'
        f'<div class="name">LiftPath</div><div class="pitch">{html.escape(pitch)}</div></div>'
        f'<div class="tag">{html.escape(tag)}</div></div>', unsafe_allow_html=True)


def splash(message: str):
    """A full-window loading screen. Returns its placeholder. Call .empty() to remove it."""
    holder = st.empty()
    holder.markdown(
        f'<div class="lp-splash"><img src="{LOGO_URL}" alt=""><div class="name">LiftPath</div>'
        f'<div class="track"><span></span></div><div class="msg">{html.escape(message)}</div>'
        '</div>', unsafe_allow_html=True)
    return holder
