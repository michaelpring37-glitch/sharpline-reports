#!/usr/bin/env python3
"""
Sharpline — Automated Wed/Sun Briefing v2
- Deep multi-search research via Claude
- Configurable sections via SECTIONS dict
- Monthly prospect report (auto on first Wednesday)
- Reads custom notes from Google Sheet 'notes' tab
- Sends formatted HTML email via SendGrid
"""

import os
import re
import time
import datetime
import requests
from zoneinfo import ZoneInfo

# ── ─────────────────────────────────────────────────────────────────────────
#    REPORT CONFIG — flip True/False to include/exclude sections
#    Edit this file in GitHub to customize. No other changes needed.
# ── ─────────────────────────────────────────────────────────────────────────
SECTIONS = {
    "futures":        True,   # MLB futures portfolio analysis + value bets
    "daily_recs":     True,   # Today's specific bet recommendations
    "waiver":         True,   # Closer situations, K/9 leaders, hot bats
    "outlook":        True,   # 5-bullet weekly outlook
    "prospects":      True,   # MLB prospect report (schedule controlled below)
    "nfl_update":     False,  # NFL futures + fantasy — flip True in September
    "div_winners":    False,  # Division winner tracker — flip True in August
    "hedge_alerts":   False,  # Flags positions where hedging is now profitable
    "closer_deep":    False,  # Full closer situation deep dive
}

# Prospect schedule: "monthly_first_wed" | "always" | "never"
PROSPECT_SCHEDULE = "monthly_first_wed"

# Boost day — change "Wednesday" if your boost is on a different day
BOOST_DAY_OF_WEEK = "Wednesday"

# ── Env / secrets ─────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SENDGRID_API_KEY  = os.environ["SENDGRID_API_KEY"]
TO_EMAIL          = os.environ["TO_EMAIL"]
FROM_EMAIL        = os.environ["FROM_EMAIL"]
GOOGLE_API_KEY    = os.environ.get("GOOGLE_API_KEY", "")
SHEET_ID          = os.environ.get("SHEET_ID", "1FYbXLRjsnE00xLGUMbw2lXYLa6vYsdAWPCs0O6rfwB0")
LEAGUE_1_ID       = os.environ.get("LEAGUE_1_ID", "123644")
LEAGUE_2_ID       = os.environ.get("LEAGUE_2_ID", "1624981735")

NOW_ET = datetime.datetime.now(ZoneInfo("America/New_York"))
TODAY  = NOW_ET.strftime("%A, %B %-d, %Y")
DOW    = NOW_ET.strftime("%A")
BOOST_DAY = DOW == BOOST_DAY_OF_WEEK

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
SENDGRID_URL  = "https://api.sendgrid.com/v3/mail/send"

def is_first_wednesday() -> bool:
    return DOW == "Wednesday" and NOW_ET.day <= 7

def should_run_prospects() -> bool:
    if not SECTIONS.get("prospects", False): return False
    if PROSPECT_SCHEDULE == "always": return True
    if PROSPECT_SCHEDULE == "never": return False
    return is_first_wednesday()

# ── Claude API ────────────────────────────────────────────────────────────────
def call_claude(prompt: str, max_tokens: int = 2000) -> str:
    headers = {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
    }
    body = {
       "model": "claude-sonnet-4-6",
        "max_tokens": max_tokens,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": prompt}],
    }
    for attempt in range(2):
        try:
            r = requests.post(ANTHROPIC_URL, headers=headers, json=body, timeout=120)
            r.raise_for_status()
            data = r.json()
            return "".join(b["text"] for b in data["content"] if b["type"] == "text")
        except Exception as e:
            if attempt == 0:
                print(f"  Claude retry: {e}")
                print(f"  Key prefix: {ANTHROPIC_API_KEY[:12]}...")
                print(f"  Key length: {len(ANTHROPIC_API_KEY)}")
                time.sleep(5)
            else:
                raise

# ── Google Sheets notes ────────────────────────────────────────────────────────
def get_sheet_notes() -> str:
    """
    Reads the 'notes' tab column A from your Google Sheet.
    Requires GOOGLE_API_KEY secret and sheet shared as 'Anyone with link can view'.
    Get a free API key: console.cloud.google.com -> APIs -> Sheets API -> Credentials
    """
    if not GOOGLE_API_KEY:
        return ""
    try:
        url = (f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
               f"/values/notes!A:A?key={GOOGLE_API_KEY}")
        r = requests.get(url, timeout=15)
        if not r.ok:
            print(f"  Notes tab error: {r.status_code}"); return ""
        lines = [row[0].strip() for row in r.json().get("values", []) if row and row[0].strip()]
        return "\n".join(lines)
    except Exception as e:
        print(f"  Notes read failed: {e}"); return ""

# ── Sections ──────────────────────────────────────────────────────────────────
def get_futures_analysis() -> str:
    print("  Futures analysis...")
    return call_claude(f"""Sharp sports futures analyst. Today is {TODAY}.

Search multiple times:
1. Current MLB World Series futures odds across major books
2. AL/NL Pennant odds — which teams are moving
3. AL MVP and NL MVP current odds + leaders
4. AL Cy Young and NL Cy Young current odds
5. MLB standings — teams surging or fading from playoff contention
6. Significant injury news affecting futures value this week

My portfolio:
- WS: Yankees, Mariners, Orioles, Tigers, Braves, Phillies, Brewers, Cubs, Rangers
- Pennant: Mariners (AL), Braves/Phillies (NL)
- AL MVP: Judge, Witt Jr., Rodriguez | NL MVP: UNCOVERED
- Cy Young: Yamamoto, Skenes, Crochet, Skubal, Burnes
- NL ROY: Wederholt | AL ROY: UNCOVERED
- Goal: even coverage/returns across ALL playoff contenders + award nominees

Write detailed FUTURES ANALYSIS with bold headers:
**Portfolio Health** — which positions gained/lost value
**Coverage Gaps** — playoff-caliber teams and award candidates not yet covered
**Award Markets** — best value in MVP and Cy Young right now
**Top Value Bets** — 3 specific picks under $25 with exact odds
**Hedge Watch** — any position where current odds make hedging worth considering""", max_tokens=2000)


def get_daily_recs() -> str:
    print("  Daily recs...")
    boost_note = ("A 20% PAYOUT BOOST IS AVAILABLE TODAY (profit x 1.2). Show BOTH base and boosted payout at $20 stake for each rec."
                  if BOOST_DAY else "No boost today. Show base payout at $20 stake.")
    return call_claude(f"""Sharp MLB futures analyst. Today is {TODAY}. {boost_note}

Search: best value MLB futures today, MVP/Cy Young/ROY odds, any news shifting value.

Existing positions — flag duplicates, prioritize gaps:
- WS covered: Yankees, Mariners, Orioles, Tigers, Braves, Phillies, Brewers, Cubs, Rangers
- AL MVP: Judge, Witt Jr., Rodriguez | NL MVP: UNCOVERED (priority)
- Cy Young: Yamamoto, Skenes, Crochet, Skubal, Burnes
- AL ROY: UNCOVERED (priority) | NL ROY: Wederholt

DAILY BET RECOMMENDATIONS:
- 2-3 team futures (prioritize uncovered playoff teams)
- 1 NL MVP pick (uncovered — high priority)
- 1 Cy Young pick
- 1 AL ROY pick (uncovered — high priority)
- Label each: fills gap / duplicate / new category
- Rank by urgency/value. Be specific with odds and dollar amounts.""", max_tokens=1500)


def get_waiver_wire() -> str:
    print("  Waiver wire...")
    return call_claude(f"""Fantasy baseball expert. Today is {TODAY}.

Search thoroughly:
1. Every MLB closer situation — who's closing, injuries, handoffs
2. Highest K/9 rates among fantasy-available pitchers
3. Hot hitters on waivers with favorable upcoming matchups
4. SP injuries creating streaming opportunities

Context: Two ESPN H2H categories leagues (#{LEAGUE_1_ID} 8-keeper, #{LEAGUE_2_ID}).
Keepers: Bobby Witt Jr., Bryce Harper, Kyle Tucker, Jarren Duran, Corbin Burnes.
PRIORITY 1 — Closers (saves premium) | PRIORITY 2 — K/9 (10.0+ preferred) | PRIORITY 3 — hot bats

Write WAIVER WIRE with bold headers:
**Closer Report** — every shaky save situation, next man up
**K/9 Streamers** — 3-4 pitchers with elite K rates, include actual K/9 stat and matchup
**Hot Bats** — 2-3 hitters worth adding
**Both Leagues** — flag which adds help both vs just one
**Keeper Flag** — any adds with 8-keeper league value""", max_tokens=1800)


def get_weekly_outlook() -> str:
    print("  Weekly outlook...")
    return call_claude(f"""Sharp sports analyst. Today is {TODAY}.

Search: this week's MLB schedule and pitching matchups, any injuries, SP streaming options by K/9, recent futures odds movement, standings changes.

Write exactly 5 WEEKLY OUTLOOK bullets — each 2-3 sentences, punchy:
• **SCHEDULE EDGE:** Best pitching matchup or team spot this week
• **SP STREAMER:** Best K/9 streaming option with stat and matchup
• **INJURY WATCH:** Any injury news affecting fantasy or futures
• **LINE MOVE:** Notable futures odds shift worth acting on
• **STANDINGS WATCH:** Team gaining/losing playoff odds significantly""", max_tokens=800)


def get_prospect_report() -> str:
    print("  Monthly prospect report...")
    month_name = NOW_ET.strftime("%B %Y")
    return call_claude(f"""MLB prospect and fantasy analyst. Today is {TODAY}. Monthly prospect report for {month_name}.

Search thoroughly:
1. Top 10-15 MLB prospects by ranking (Baseball America, FanGraphs, MLB Pipeline)
2. Prospects with call-up potential in next 30-60 days
3. Recently called-up prospects performing well at MLB level
4. Prospects on my futures teams: Yankees, Mariners, Orioles, Tigers, Braves, Phillies, Brewers, Cubs, Rangers
5. Top dynasty/keeper fantasy value prospects

Write MONTHLY PROSPECT REPORT with bold headers:
**Call-Up Watch** — imminent call-ups with current level and stats
**Recent Debuts** — prospects who debuted recently worth rostering
**Keeper League Targets** — top stash candidates for 8-keeper league with ETA
**Futures Connection** — prospects on my covered teams affecting franchise trajectory
**Deep Sleepers** — 1-2 under-the-radar names worth knowing

Include rankings, minor league stats, and ETA where available.""", max_tokens=2000)


def get_nfl_update() -> str:
    print("  NFL update...")
    return call_claude(f"""Sharp NFL analyst. Today is {TODAY}.
Search: Super Bowl futures, NFL MVP odds, significant NFL news.
My positions: Chiefs (SB), Lions (SB/NFC), Ravens (AFC).
Write brief NFL UPDATE: futures health, value plays, top waiver adds.""", max_tokens=1000)


def get_div_winners() -> str:
    print("  Division tracker...")
    return call_claude(f"""MLB analyst. Today is {TODAY}.
Search current division standings and division winner futures odds.
My covered teams: Yankees (AL East), Mariners (AL West), Orioles (AL East), Tigers (AL Central), Braves (NL East), Phillies (NL East), Brewers (NL Central), Cubs (NL Central), Rangers (AL West).
Write concise DIVISION TRACKER — one paragraph per division, note my team's position.""", max_tokens=800)


def get_hedge_alerts() -> str:
    print("  Hedge alerts...")
    return call_claude(f"""Sharp futures analyst. Today is {TODAY}.
Search current odds for all my WS positions: Yankees, Mariners, Orioles, Tigers, Braves, Phillies, Brewers, Cubs, Rangers.
Original stakes all under $25. Calculate if hedging any position now locks meaningful profit.
Write HEDGE ALERTS — only include positions where hedging is genuinely worth considering. Skip if none qualify.""", max_tokens=800)


def get_closer_deep_dive() -> str:
    print("  Closer deep dive...")
    return call_claude(f"""Fantasy baseball closer expert. Today is {TODAY}.
Search every MLB team's current closer situation in detail.
Write CLOSER DEEP DIVE organized by AL and NL. For each team: current closer, handoff candidate, recent save opps, blown saves, injury status. Flag high-upside handoff situations.""", max_tokens=1500)


# ── HTML email ────────────────────────────────────────────────────────────────
def md_to_html(text: str) -> str:
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    parts = []
    for p in paragraphs:
        p = p.replace('\n', '<br>')
        parts.append(f'<p style="margin:8px 0;line-height:1.75;">{p}</p>')
    return ''.join(parts)


def email_section(title: str, emoji: str, content: str, accent: str) -> str:
    return f"""
    <div style="margin-bottom:36px;">
      <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px;">
        <tr><td style="border-bottom:2px solid {accent};padding-bottom:8px;">
          <span style="font-size:18px;margin-right:8px;">{emoji}</span>
          <span style="font-family:'Space Mono',monospace;font-size:17px;font-weight:700;color:#111;letter-spacing:-0.5px;">{title}</span>
        </td></tr>
      </table>
      <div style="font-size:15px;color:#374151;">{md_to_html(content)}</div>
    </div>"""


def format_email(sections_content: dict, notes: str, run_prospects: bool) -> str:
    dow_label = "Wednesday" if DOW == "Wednesday" else "Sunday"
    prospect_badge = (' <span style="background:#ede9fe;color:#5b21b6;font-size:11px;'
                      'font-weight:700;padding:2px 8px;border-radius:20px;">🌱 PROSPECT MONTH</span>'
                      if run_prospects else "")
    boost_banner = ("""<div style="background:#fef9c3;border:1px solid #fde047;border-radius:8px;padding:12px 16px;margin-bottom:28px;">
      <strong style="color:#854d0e;font-size:15px;">⚡ BOOST DAY — 20% Payout Boost Available</strong>
      <div style="color:#854d0e;font-size:13px;margin-top:4px;">All recs below show base and boosted payouts at $20 stake.</div>
    </div>""" if BOOST_DAY else "")

    section_order = [
        ("futures",      "📊", "Futures Portfolio & Analysis",                    "#1D9E75"),
        ("daily_recs",   "🎯", "Today's Bet Recommendations",                     "#2563eb"),
        ("prospects",    "🌱", f"Monthly Prospect Report — {NOW_ET.strftime('%B %Y')}", "#7c3aed"),
        ("waiver",       "⚾", "Waiver Wire",                                      "#7c3aed"),
        ("nfl_update",   "🏈", "NFL Update",                                       "#dc2626"),
        ("div_winners",  "🗺️",  "Division Tracker",                                "#0891b2"),
        ("hedge_alerts", "🔒", "Hedge Alerts",                                    "#d97706"),
        ("closer_deep",  "💾", "Closer Deep Dive",                                "#059669"),
        ("outlook",      "📅", "Weekly Outlook",                                  "#dc2626"),
    ]

    body = ""
    for key, emoji, title, color in section_order:
        if key in sections_content:
            body += email_section(title, emoji, sections_content[key], color)

    notes_html = ""
    if notes:
        notes_html = f"""
        <div style="margin-top:36px;padding:20px 24px;background:#f8fafc;border-radius:10px;border:1px solid #e5e7eb;">
          <div style="font-family:'Space Mono',monospace;font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">📝 Notes & Reminders</div>
          <div style="font-size:14px;color:#374151;line-height:1.75;white-space:pre-wrap;">{notes}</div>
          <div style="font-size:11px;color:#9ca3af;margin-top:8px;">Edit in Google Sheet → "notes" tab, column A</div>
        </div>"""

    return f"""<!DOCTYPE html><html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#f1f5f9;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:24px 0;"><tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="background:white;border-radius:14px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
  <tr><td style="background:#0f172a;padding:26px 32px;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td><div style="font-family:'Space Mono',monospace;font-size:24px;font-weight:700;color:white;letter-spacing:-1px;">SHARP<span style="color:#1D9E75;">LINE</span></div>
        <div style="color:#64748b;font-size:13px;margin-top:4px;">{dow_label} Morning Report{prospect_badge}</div></td>
      <td align="right" style="vertical-align:top;">
        <div style="color:#64748b;font-size:13px;">{TODAY}</div>
        {'<div style="background:#fde047;color:#854d0e;font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;margin-top:6px;display:inline-block;">⚡ BOOST DAY</div>' if BOOST_DAY else ''}
      </td>
    </tr></table>
  </td></tr>
  <tr><td style="padding:30px 32px;">{boost_banner}{body}{notes_html}</td></tr>
  <tr><td style="background:#f8fafc;padding:18px 32px;border-top:1px solid #e2e8f0;">
    <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center;">
      Sharpline Automated Report · {NOW_ET.strftime("%-I:%M %p ET")} · Edit sections in generate_briefing.py SECTIONS dict
    </p>
  </td></tr>
</table></td></tr></table>
</body></html>"""


# ── Send ──────────────────────────────────────────────────────────────────────
def send_email(html: str):
    dow_label = "Wednesday" if DOW == "Wednesday" else "Sunday"
    subject = f"Sharpline {dow_label} — {NOW_ET.strftime('%b %-d')}{'  ⚡' if BOOST_DAY else ''}{'  🌱' if should_run_prospects() else ''}"
    r = requests.post(SENDGRID_URL,
        headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
        json={"personalizations": [{"to": [{"email": TO_EMAIL}]}],
              "from": {"email": FROM_EMAIL, "name": "Sharpline"},
              "subject": subject,
              "content": [{"type": "text/html", "value": html}]},
        timeout=30)
    if r.status_code not in (200, 202):
        raise RuntimeError(f"SendGrid {r.status_code}: {r.text}")
    print(f"  Email sent → {TO_EMAIL}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\nSharpline — {TODAY}")
    print(f"Boost: {BOOST_DAY} | Prospects: {should_run_prospects()} | First Wed: {is_first_wednesday()}\n")

    run_prospects = should_run_prospects()
    sections_content = {}

    generators = {
        "futures":      get_futures_analysis,
        "daily_recs":   get_daily_recs,
        "waiver":       get_waiver_wire,
        "outlook":      get_weekly_outlook,
        "nfl_update":   get_nfl_update,
        "div_winners":  get_div_winners,
        "hedge_alerts": get_hedge_alerts,
        "closer_deep":  get_closer_deep_dive,
    }

    for key, fn in generators.items():
        if SECTIONS.get(key, False):
            try:
                sections_content[key] = fn()
                time.sleep(15)
            except Exception as e:
                print(f"  Section '{key}' failed: {e}")
                sections_content[key] = f"Could not generate this section: {e}"

    if run_prospects:
        try:
            sections_content["prospects"] = get_prospect_report()
        except Exception as e:
            sections_content["prospects"] = f"Could not generate prospect report: {e}"

    print("\n  Reading notes from Google Sheet...")
    notes = get_sheet_notes()
    print(f"  Notes: {len(notes)} chars" if notes else "  No notes")

    print("\n  Formatting + sending email...")
    send_email(format_email(sections_content, notes, run_prospects))
    print("\nDone. ✓\n")


if __name__ == "__main__":
    main()
