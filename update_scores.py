"""
Daily Hardwood — Auto-Updater
Runs at 5:29 AM Eastern every day via GitHub Actions.
Retries every API call up to 3 times so scores are always fresh.
"""

import requests, re, xml.etree.ElementTree as ET, time
from datetime import datetime, timezone, timedelta
from html import unescape

# ── TIMEZONE ──────────────────────────────────────────────────────────────────
# Detect whether we're in EDT (UTC-4) or EST (UTC-5)
# GitHub Actions runs in UTC — we figure out Eastern from that
utc_now  = datetime.now(timezone.utc)
# EDT runs Mar 2nd Sunday → Nov 1st Sunday (approximate with month check)
month = utc_now.month
is_edt = 3 <= month <= 11
et_offset = -4 if is_edt else -5
ET_OFF   = timezone(timedelta(hours=et_offset))
now_et   = datetime.now(ET_OFF)
today    = now_et.strftime('%Y-%m-%d')
yesterday = (now_et - timedelta(days=1)).strftime('%Y-%m-%d')
label    = now_et.strftime('%A, %B %-d, %Y')
doy      = int(now_et.strftime('%j'))

print(f"\n{'='*60}")
print(f"Daily Hardwood — {label}")
print(f"UTC: {utc_now.strftime('%H:%M')}  Eastern offset: UTC{et_offset}")
print(f"{'='*60}\n")

# ── RESILIENT GET — retries 3 times ──────────────────────────────────────────
def get(url, params=None, timeout=15, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout,
                             headers={'User-Agent': 'Mozilla/5.0 DailyHardwood/1.0'})
            if r.status_code == 200:
                return r
            print(f"  Attempt {attempt+1}: HTTP {r.status_code} — {url[:50]}")
        except Exception as e:
            print(f"  Attempt {attempt+1}: {e} — {url[:50]}")
        if attempt < retries - 1:
            time.sleep(2)  # wait 2 seconds before retry
    return None

def clean(text):
    text = re.sub(r'<[^>]+>', ' ', text or '')
    text = unescape(text)
    return ' '.join(text.split()).strip()

def js_escape(s):
    return (str(s or '')
            .replace('\\', '\\\\')
            .replace("'", "\\'")
            .replace('\n', ' ')
            .replace('\r', ''))

def short_team(n):
    table = {
        'Oklahoma City Thunder': 'OKC Thunder',
        'Golden State Warriors': 'Warriors',
        'Los Angeles Lakers': 'Lakers',
        'Los Angeles Clippers': 'Clippers',
        'Portland Trail Blazers': 'Trail Blazers',
        'New Orleans Pelicans': 'Pelicans',
        'Memphis Grizzlies': 'Grizzlies',
        'Minnesota Timberwolves': 'T-Wolves',
        'San Antonio Spurs': 'Spurs',
        'Philadelphia 76ers': '76ers',
        'Washington Wizards': 'Wizards',
        'Charlotte Hornets': 'Hornets',
        'Cleveland Cavaliers': 'Cavaliers',
        'Toronto Raptors': 'Raptors',
        'Milwaukee Bucks': 'Bucks',
        'Indiana Pacers': 'Pacers',
        'Detroit Pistons': 'Pistons',
        'New York Knicks': 'Knicks',
        'Brooklyn Nets': 'Nets',
        'Boston Celtics': 'Celtics',
        'Miami Heat': 'Heat',
        'Orlando Magic': 'Magic',
        'Atlanta Hawks': 'Hawks',
        'Chicago Bulls': 'Bulls',
        'Denver Nuggets': 'Nuggets',
        'Utah Jazz': 'Jazz',
        'Sacramento Kings': 'Kings',
        'Phoenix Suns': 'Suns',
        'Houston Rockets': 'Rockets',
        'Dallas Mavericks': 'Mavericks',
    }
    return table.get(n, n)


# ════════════════════════════════════════════════════════════════════════════
#  NBA SCORES — fetch today AND yesterday to always have fresh results
# ════════════════════════════════════════════════════════════════════════════
print("🏀 Fetching NBA scores...")
nba_scores = []

for date_str in [today, yesterday]:
    r = get('https://www.balldontlie.io/api/v1/games',
            params={'dates[]': date_str, 'per_page': 15})
    if not r:
        continue
    for g in r.json().get('data', []):
        away   = short_team(g['visitor_team']['full_name'])
        home   = short_team(g['home_team']['full_name'])
        status = g.get('status', '')
        aS     = g.get('visitor_team_score')
        hS     = g.get('home_team_score')

        if status == 'Final':
            st, live = 'Final', False
        elif any(x in status for x in ['Qtr', 'Half', 'OT', "'"]):
            st, live = status, True
        else:
            try:
                dt = datetime.fromisoformat(g['date'].replace('Z', '+00:00'))
                st = dt.astimezone(ET_OFF).strftime('%-I:%M %p ET')
            except Exception:
                st = 'Tonight'
            live = False
            aS = hS = None

        nba_scores.append({
            'away': away, 'home': home,
            'aS': aS, 'hS': hS,
            'st': st, 'live': live
        })

# Deduplicate (same game from both dates), prefer Final over scheduled
seen = {}
for g in nba_scores:
    key = f"{g['away']}-{g['home']}"
    if key not in seen or g['st'] == 'Final':
        seen[key] = g
nba_scores = list(seen.values())[:8]

print(f"  ✓ {len(nba_scores)} NBA games")
for g in nba_scores:
    score = f"{g['aS']}-{g['hS']}" if g['aS'] is not None else 'scheduled'
    print(f"    {g['away']} @ {g['home']}: {score} ({g['st']})")


# ════════════════════════════════════════════════════════════════════════════
#  EPL SCORES — today and yesterday
# ════════════════════════════════════════════════════════════════════════════
print("\n⚽ Fetching EPL scores...")
epl_scores = []

for date_str in [today, yesterday]:
    r = get('https://www.thesportsdb.com/api/v1/json/3/eventsday.php',
            params={'d': date_str, 'l': 'English%20Premier%20League'})
    if not r:
        continue
    for e in (r.json().get('events') or []):
        home   = e.get('strHomeTeam', '').replace(' FC', '').replace(' AFC', '')
        away   = e.get('strAwayTeam', '').replace(' FC', '').replace(' AFC', '')
        status = e.get('strStatus', '')
        hS_raw = e.get('intHomeScore')
        aS_raw = e.get('intAwayScore')

        if status in ('Match Finished', 'FT'):
            st, live = 'Final', False
            hS = int(hS_raw) if hS_raw is not None else None
            aS = int(aS_raw) if aS_raw is not None else None
        elif status in ('In Progress', 'HT') or "'" in status:
            st, live = status, True
            hS = int(hS_raw) if hS_raw is not None else None
            aS = int(aS_raw) if aS_raw is not None else None
        else:
            st   = (e.get('strTime', '') or 'TBD') + ' ET'
            live = False
            hS = aS = None

        if home and away:
            epl_scores.append({
                'away': away, 'home': home,
                'aS': aS, 'hS': hS,
                'st': st, 'live': live, 'lg': 'EPL'
            })

# Deduplicate
seen_epl = {}
for g in epl_scores:
    key = f"{g['away']}-{g['home']}"
    if key not in seen_epl or g['st'] == 'Final':
        seen_epl[key] = g
epl_scores = list(seen_epl.values())[:8]

print(f"  ✓ {len(epl_scores)} EPL games")
for g in epl_scores:
    score = f"{g['aS']}-{g['hS']}" if g['aS'] is not None else 'scheduled'
    print(f"    {g['away']} @ {g['home']}: {score} ({g['st']})")


# ════════════════════════════════════════════════════════════════════════════
#  EPL STANDINGS + SOCCER FOR DUMMIES — live table and recent results
# ════════════════════════════════════════════════════════════════════════════
print("\n⚽ Fetching EPL standings for Soccer For Dummies section...")

epl_table_js    = None
epl_results_js  = None
epl_upcoming_js = None

# ── STANDINGS ──────────────────────────────────────────────────────────────
r_stand = get('https://www.thesportsdb.com/api/v1/json/3/lookuptable.php',
              params={'l': '4328', 's': '2025-2026'})

ZONE_LABELS = {
    1:  ('title',  '🏆 Title race',            '#16a34a'),
    2:  ('champ',  '⭐ Champions League',       '#2563eb'),
    3:  ('champ',  '⭐ Champions League',       '#2563eb'),
    4:  ('champ',  '⭐ Champions League',       '#2563eb'),
    5:  ('euro',   '🌍 Europa League (5th)',    '#d97706'),
    6:  ('euro',   '🌍 Europa League (6th)',    '#d97706'),
    18: ('rel',    '🔻 Relegation zone',        '#dc2626'),
    19: ('rel',    '🔻 Relegation zone',        '#dc2626'),
    20: ('rel',    '🔻 Nearly certain to go down', '#dc2626'),
}

SHOW_RANKS = {1, 2, 3, 4, 5, 6, 18, 19, 20}

short_club = {
    'Manchester City': 'Man City', 'Manchester United': 'Man United',
    'Tottenham Hotspur': 'Spurs', 'Wolverhampton Wanderers': 'Wolves',
    'Nottingham Forest': 'Nott\'m Forest', 'Brighton & Hove Albion': 'Brighton',
    'West Ham United': 'West Ham', 'Newcastle United': 'Newcastle',
    'Aston Villa': 'Aston Villa', 'Leicester City': 'Leicester',
    'Crystal Palace': 'Crystal Palace', 'Brentford': 'Brentford',
}

table_rows = []
if r_stand:
    try:
        entries = r_stand.json().get('table') or []
        for e in entries:
            rank = int(e.get('intRank', 0))
            if rank not in SHOW_RANKS:
                continue
            team_full = e.get('strTeam', '')
            team = short_club.get(team_full, team_full.replace(' FC', '').replace(' AFC', ''))
            pts  = int(e.get('intPoints', 0))
            w    = int(e.get('intWin', 0))
            d    = int(e.get('intDraw', 0))
            l    = int(e.get('intLoss', 0))
            zone, zone_lbl, zone_clr = ZONE_LABELS.get(rank, ('mid', '— Mid-table', '#aaa'))
            table_rows.append(
                f"  {{rank:{rank},team:'{js_escape(team)}',pts:{pts},"
                f"w:{w},d:{d},l:{l},zone:'{zone}',"
                f"zoneLabel:'{js_escape(zone_lbl)}',zoneColor:'{zone_clr}'}}"
            )
        print(f"  ✓ {len(table_rows)} EPL table rows")
    except Exception as ex:
        print(f"  ✗ standings parse error: {ex}")

if table_rows:
    epl_table_js = 'const EPL_TABLE = [\n' + ',\n'.join(table_rows) + '\n];'

# ── RECENT RESULTS (last 7 days) ───────────────────────────────────────────
# Importance weights for deciding which games to feature
MATCH_IMPORTANCE = {
    frozenset(['Arsenal', 'Man City']):         10,
    frozenset(['Arsenal', 'Liverpool']):         9,
    frozenset(['Arsenal', 'Man United']):        8,
    frozenset(['Man City', 'Liverpool']):         8,
    frozenset(['Arsenal', 'Chelsea']):           7,
    frozenset(['Man City', 'Chelsea']):          7,
    frozenset(['Liverpool', 'Man United']):      7,
    frozenset(['Man United', 'Aston Villa']):    7,
    frozenset(['Liverpool', 'Aston Villa']):     7,
}

recent_epl = []
for days_back in range(5):
    check_date = (now_et - timedelta(days=days_back)).strftime('%Y-%m-%d')
    r2 = get('https://www.thesportsdb.com/api/v1/json/3/eventsday.php',
             params={'d': check_date, 'l': 'English%20Premier%20League'})
    if not r2:
        continue
    for e in (r2.json().get('events') or []):
        status = e.get('strStatus', '')
        if status not in ('Match Finished', 'FT'):
            continue
        home_full = e.get('strHomeTeam', '')
        away_full = e.get('strAwayTeam', '')
        home = short_club.get(home_full, home_full.replace(' FC','').replace(' AFC',''))
        away = short_club.get(away_full, away_full.replace(' FC','').replace(' AFC',''))
        hS_raw = e.get('intHomeScore')
        aS_raw = e.get('intAwayScore')
        if hS_raw is None or aS_raw is None:
            continue
        hS, aS = int(hS_raw), int(aS_raw)
        # Result label
        if hS > aS:   result_str = f"{home} win"
        elif aS > hS: result_str = f"{away} win"
        else:         result_str = "Draw"
        importance = MATCH_IMPORTANCE.get(frozenset([home, away]), 1)
        recent_epl.append({
            'home': home, 'away': away, 'hS': hS, 'aS': aS,
            'result': result_str, 'importance': importance,
            'date_str': (now_et - timedelta(days=days_back)).strftime('%a %b %-d'),
        })

# Sort by importance, deduplicate, take top 4
seen_matches = set()
filtered = []
for m in sorted(recent_epl, key=lambda x: -x['importance']):
    key = f"{m['home']}-{m['away']}"
    if key not in seen_matches:
        seen_matches.add(key)
        filtered.append(m)
    if len(filtered) == 4:
        break

print(f"  ✓ {len(filtered)} featured EPL results")

RESULT_CONTEXT = {
    'Arsenal win':      ("Arsenal keep building their lead. Clinical and controlled.",
                         "Every Arsenal win makes the title more certain — they're 9 pts clear. A win here adds pressure on Man City."),
    'Man City win':     ("Man City respond with a big result.",
                         "City are 9 points behind Arsenal. Wins keep them mathematically alive, but they need Arsenal to drop points too."),
    'Liverpool win':    ("Liverpool get a much-needed 3 points.",
                         "Liverpool have slipped from defending champions to 5th. They're fighting to hold onto a Champions League spot, not a title."),
    'Man United win':   ("Man United continue their unlikely resurgence.",
                         "United were expected to struggle. They're now in the top-4 conversation — a major financial swing worth tens of millions in Champions League money."),
    'Aston Villa win':  ("Aston Villa hold their Champions League spot.",
                         "Villa are clinging to 4th place. Winning is mandatory — one bad run and Liverpool or Chelsea could leapfrog them."),
    'Chelsea win':      ("Chelsea keep the pressure on the top 4.",
                         "Chelsea are 6th, just outside Champions League spots. Every win matters enormously — that qualification is worth £50-100M."),
    'Draw':             ("Two teams cancel each other out.",
                         "In soccer a draw gives both teams 1 point. Neither team is happy — the team that was supposed to win dropped 2 points, which can swing the title or relegation battle."),
}

def get_context(m):
    key = m['result']
    ctx = RESULT_CONTEXT.get(key, ('A notable result.', 'This result affects the table standings.'))
    return ctx[0], ctx[1]

result_rows = []
for m in filtered:
    takeaway_base, why = get_context(m)
    takeaway = f"{m['home']} {m['hS']}–{m['aS']} {m['away']} ({m['date_str']}): {takeaway_base}"
    result_rows.append(
        f"  {{home:'{js_escape(m['home'])}',hS:{m['hS']},away:'{js_escape(m['away'])}',aS:{m['aS']},"
        f"date:'{js_escape(m['date_str'])}',"
        f"takeaway:'{js_escape(takeaway)}',"
        f"why:'{js_escape(why)}'}}"
    )

if result_rows:
    epl_results_js = 'const EPL_RESULTS = [\n' + ',\n'.join(result_rows) + '\n];'
    print(f"  ✓ EPL_RESULTS built ({len(result_rows)} games)")

# ── UPCOMING FIXTURES ──────────────────────────────────────────────────────
upcoming_epl = []
for days_ahead in range(1, 10):
    check_date = (now_et + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    r3 = get('https://www.thesportsdb.com/api/v1/json/3/eventsday.php',
             params={'d': check_date, 'l': 'English%20Premier%20League'})
    if not r3:
        continue
    for e in (r3.json().get('events') or []):
        status = e.get('strStatus', '')
        if status in ('Match Finished', 'FT'):
            continue
        home_full = e.get('strHomeTeam', '')
        away_full = e.get('strAwayTeam', '')
        home = short_club.get(home_full, home_full.replace(' FC','').replace(' AFC',''))
        away = short_club.get(away_full, away_full.replace(' FC','').replace(' AFC',''))
        raw_time = e.get('strTime', '') or 'TBD'
        importance = MATCH_IMPORTANCE.get(frozenset([home, away]), 1)
        date_disp = (now_et + timedelta(days=days_ahead)).strftime('%a %b %-d')
        upcoming_epl.append({
            'game': f"{home} vs {away}",
            'time': f"{date_disp} · {raw_time} ET",
            'importance': importance,
            'home': home, 'away': away,
        })
    if len(upcoming_epl) >= 12:
        break

# Sort by importance, take top 3
upcoming_epl.sort(key=lambda x: -x['importance'])
top_upcoming = upcoming_epl[:3]

UPCOMING_WHY = {
    frozenset(['Arsenal', 'Man City']):   ("The title decider. If Arsenal still lead, a win seals it. If City have cut the gap, this is the Super Bowl of the season.", "Arsenal win: 52%"),
    frozenset(['Arsenal', 'Liverpool']):  ("Both teams need points for very different reasons — Arsenal for the title, Liverpool to stay in the top 4.", "Arsenal win: 55%"),
    frozenset(['Arsenal', 'Chelsea']):    ("Arsenal protect their lead. Chelsea chase Champions League.", "Arsenal win: 58%"),
    frozenset(['Man City', 'Liverpool']): ("Two giants, both with big stakes — City chasing Arsenal, Liverpool fighting for a Champions League spot.", "Man City win: 50%"),
    frozenset(['Liverpool', 'Man United']):("The old rivalry. Liverpool need points for top 4. United want to cement 3rd.", "Liverpool win: 42%"),
    frozenset(['Man United', 'Aston Villa']):("Both fighting for top-4 spots. The loser falls further behind.", "Man United win: 44%"),
    frozenset(['Liverpool', 'Aston Villa']):("Direct top-4 rivals. Three points here could decide who makes the Champions League.", "Liverpool win: 48%"),
    frozenset(['Arsenal', 'Man United']):  ("Arsenal protect top spot. Man United prove the resurgence is real.", "Arsenal win: 56%"),
    frozenset(['Man City', 'Chelsea']):    ("City stay in the title race. Chelsea chase 4th.", "Man City win: 54%"),
}

upcoming_rows = []
for g in top_upcoming:
    pair = frozenset([g['home'], g['away']])
    why_text, prob = UPCOMING_WHY.get(pair, (
        f"A fixture with table implications — both teams need points.",
        "Check odds closer to kickoff"
    ))
    upcoming_rows.append(
        f"  {{game:'{js_escape(g['game'])}',time:'{js_escape(g['time'])}',"
        f"why:'{js_escape(why_text)}',prob:'{js_escape(prob)}'}}"
    )

if not upcoming_rows:
    upcoming_rows = [
        "  {game:'No fixtures this week',time:'Check Premier League schedule',why:'The Premier League is on an international break — club games resume soon.',prob:''}",
    ]

epl_upcoming_js = 'const EPL_UPCOMING = [\n' + ',\n'.join(upcoming_rows) + '\n];'
print(f"  ✓ EPL_UPCOMING built ({len(upcoming_rows)} fixtures)")


# ════════════════════════════════════════════════════════════════════════════
print("\n📰 Fetching real headlines...")

RSS_FEEDS = {
    'ESPN NBA':    'https://www.espn.com/espn/rss/nba/news',
    'ESPN NFL':    'https://www.espn.com/espn/rss/nfl/news',
    'ESPN Soccer': 'https://www.espn.com/espn/rss/soccer/news',
    'ESPN F1':     'https://www.espn.com/espn/rss/rpm/news',
    'ESPN NCAAB':  'https://www.espn.com/espn/rss/ncb/news',
    'BBC Sport':   'https://feeds.bbci.co.uk/sport/rss.xml',
    'CBS Sports':  'https://www.cbssports.com/rss/headlines/',
}

all_stories = []

for source, url in RSS_FEEDS.items():
    r = get(url)
    if not r:
        print(f"  ✗ {source}: unavailable")
        continue
    try:
        root = ET.fromstring(r.content)
        count = 0
        for item in root.findall('.//item')[:5]:
            title = clean(item.findtext('title', ''))
            desc  = clean(item.findtext('description', ''))
            if not title or len(title) < 15:
                continue
            t = (title + ' ' + desc).lower()
            if any(x in t for x in ['nba','lakers','celtics','warriors','thunder',
                'knicks','bucks','spurs','cavaliers','mavericks','nuggets','76ers',
                'heat','suns','nets','bulls','pacers','pistons','grizzlies','rockets',
                'clippers','hawks','hornets','magic','raptors','wizards','jazz',
                'kings','blazers','pelicans','timberwolves','lebron','curry',
                'giannis','wembanyama','flagg','sga','gilgeous']):
                cat = 'NBA'
            elif any(x in t for x in ['premier league','arsenal','liverpool',
                'chelsea','man united','manchester united','man city','manchester city',
                'tottenham','newcastle','everton','aston villa','brighton','fulham',
                'west ham','wolves','leeds','crystal palace','brentford','burnley',
                'sunderland','bournemouth','nottm','forest']):
                cat = 'EPL'
            elif any(x in t for x in ['formula 1','f1','grand prix','verstappen',
                'hamilton','leclerc','russell','norris','alonso','ferrari',
                'mercedes','red bull','mclaren','williams','haas','race','circuit']):
                cat = 'F1'
            elif any(x in t for x in ['ncaa','march madness','college basketball',
                'duke','kansas','arizona','michigan','florida','uconn','gonzaga',
                'houston','purdue','byu','kentucky','tournament bracket']):
                cat = 'NCAA'
            elif any(x in t for x in ['nfl','quarterback','touchdown','super bowl',
                'mahomes','chiefs','eagles','cowboys','patriots','49ers','ravens',
                'bills','bengals','browns','packers','bears','lions','vikings',
                'rams','chargers','raiders','broncos','seahawks','draft']):
                cat = 'NFL'
            else:
                cat = 'Sports'

            all_stories.append({
                'source': source,
                'cat':    cat,
                'title':  title,
                'desc':   desc[:300] if desc else title,
            })
            count += 1
        print(f"  ✓ {source}: {count} stories")
    except Exception as e:
        print(f"  ✗ {source}: parse error — {e}")

print(f"  Total: {len(all_stories)} stories across all sources")

# Pick top story per category
by_cat = {}
for s in all_stories:
    by_cat.setdefault(s['cat'], []).append(s)

priority      = ['NBA', 'F1', 'EPL', 'NCAA', 'NFL', 'Soccer', 'Sports']
picked_leads  = [by_cat[c][0] for c in priority if by_cat.get(c)][:5]
picked_recaps = []
for c in priority:
    for s in by_cat.get(c, [])[1:3]:
        if len(picked_recaps) < 8:
            picked_recaps.append(s)

print(f"\n  Leads:  {len(picked_leads)}")
for s in picked_leads:
    print(f"    [{s['cat']}] {s['title'][:65]}")
print(f"  Recaps: {len(picked_recaps)}")


# ════════════════════════════════════════════════════════════════════════════
#  BUILD JS + INJECT INTO index.html
# ════════════════════════════════════════════════════════════════════════════
def score_line(g, include_lg=False):
    aS   = 'null' if g['aS'] is None else str(g['aS'])
    hS   = 'null' if g['hS'] is None else str(g['hS'])
    live = 'true' if g.get('live') else 'false'
    lg   = f",lg:'{g['lg']}'" if include_lg and g.get('lg') else ''
    return (f"  {{away:'{js_escape(g['away'])}',home:'{js_escape(g['home'])}',"
            f"aS:{aS},hS:{hS},st:'{js_escape(g['st'])}',live:{live}{lg}}}")

IMG = {
    'NBA':    'basketball nba arena game action',
    'EPL':    'soccer football stadium crowd match',
    'F1':     'formula 1 racing car track speed',
    'NCAA':   'basketball college arena crowd',
    'NFL':    'american football stadium crowd field',
    'Sports': 'sports arena crowd cheering',
}

def make_lead(s, i):
    t   = js_escape(s['title'])
    d   = js_escape(s['desc'][:280])
    src = js_escape(s['source'])
    q   = IMG.get(s['cat'], 'sports arena crowd')
    return (f"  {{id:'live_{i}',tag:'{s['cat']} \u00b7 Today',date:'{label}',"
            f"query:'{q}',seed:{i + doy},"
            f"headline:'{t}',"
            f"deck:'{js_escape(s['desc'][:140])}...',"
            f"body:['{d}','Source: {src}.'],"
            f"sources:[{{o:'{src}',d:'Live RSS feed'}}]}}")

def make_recap(s, i):
    t   = js_escape(s['title'])
    d   = js_escape(s['desc'][:280])
    src = js_escape(s['source'])
    q   = IMG.get(s['cat'], 'sports game action')
    return (f"  {{id:'recap_{i}',tag:'{s['cat']} \u00b7 Recap',date:'{label}',"
            f"query:'{q}',seed:{i + doy + 50},"
            f"headline:'{t}',teams:'',body:['{d}'],km:'',"
            f"sources:[{{o:'{src}',d:'Live RSS feed'}}]}}")

print("\n💉 Injecting into index.html...")
with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# NBA scores
if nba_scores:
    new_js = 'const NBA_SCORES = [\n' + ',\n'.join(score_line(g) for g in nba_scores) + '\n];'
    html = re.sub(r'const NBA_SCORES = \[[\s\S]*?\];', new_js, html)
    print("  ✓ NBA scores")

# EPL scores
if epl_scores:
    new_js = 'const SOC_SCORES = [\n' + ',\n'.join(score_line(g, True) for g in epl_scores) + '\n];'
    html = re.sub(r'const SOC_SCORES = \[[\s\S]*?\];', new_js, html)
    print("  ✓ EPL scores")

# Lead stories
if len(picked_leads) >= 2:
    new_js = 'const ALL_LEADS = [\n' + ',\n'.join(make_lead(s, i) for i, s in enumerate(picked_leads)) + '\n];'
    html = re.sub(r'const ALL_LEADS = \[[\s\S]*?\];', new_js, html)
    print(f"  ✓ {len(picked_leads)} lead stories")

# Recap stories
if len(picked_recaps) >= 2:
    new_js = 'const ALL_RECAPS = [\n' + ',\n'.join(make_recap(s, i) for i, s in enumerate(picked_recaps)) + '\n];'
    html = re.sub(r'const ALL_RECAPS = \[[\s\S]*?\];', new_js, html)
    print(f"  ✓ {len(picked_recaps)} recap stories")

# EPL Soccer For Dummies — table, results, upcoming
if epl_table_js:
    html = re.sub(r'const EPL_TABLE = \[[\s\S]*?\];', epl_table_js, html)
    print("  ✓ EPL table (Soccer For Dummies)")
if epl_results_js:
    html = re.sub(r'const EPL_RESULTS = \[[\s\S]*?\];', epl_results_js, html)
    print("  ✓ EPL results (Soccer For Dummies)")
if epl_upcoming_js:
    html = re.sub(r'const EPL_UPCOMING = \[[\s\S]*?\];', epl_upcoming_js, html)
    print("  ✓ EPL upcoming (Soccer For Dummies)")

# Update date seed so images rotate
html = re.sub(
    r"const DATE_ISO\s*=\s*(?:new Date\(\)\.toISOString\(\)\.slice\(0,\s*10\)|'[0-9-]+');(?:\s*//.*)?",
    f"const DATE_ISO = '{today}'; // auto-updated {today}",
    html
)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"\n{'='*60}")
print(f"✅ Done — {label}")
print(f"   NBA: {len(nba_scores)} games | EPL scores: {len(epl_scores)} | EPL table rows: {len(table_rows)} | Headlines: {len(all_stories)}")
print(f"{'='*60}\n")


# ════════════════════════════════════════════════════════════════════════════
#  NCAA TOURNAMENT BRACKET — fetch live results from TheSportsDB
# ════════════════════════════════════════════════════════════════════════════
print("\n🏀 Fetching NCAA Tournament results...")
ncaa_results = {}

# Fetch last 7 days of NCAA tournament games
for days_back in range(7):
    check_date = (now_et - timedelta(days=days_back)).strftime('%Y-%m-%d')
    r = get('https://www.thesportsdb.com/api/v1/json/3/eventsday.php',
            params={'d': check_date, 's': 'Basketball'})
    if not r:
        continue
    try:
        events = r.json().get('events') or []
        for e in events:
            league = e.get('strLeague', '')
            if 'NCAA' not in league and 'March Madness' not in league and 'College Basketball' not in league:
                continue
            home = e.get('strHomeTeam', '')
            away = e.get('strAwayTeam', '')
            hS = e.get('intHomeScore')
            aS = e.get('intAwayScore')
            status = e.get('strStatus', '')
            if status in ('Match Finished', 'FT') and hS is not None and aS is not None:
                hS, aS = int(hS), int(aS)
                winner = home if hS > aS else away
                loser  = away if hS > aS else home
                ws = hS if hS > aS else aS
                ls = aS if hS > aS else hS
                key = tuple(sorted([home.lower(), away.lower()]))
                if key not in ncaa_results:
                    ncaa_results[key] = f"{winner} {ws}-{ls}"
                    print(f"  {winner} def. {loser} {ws}-{ls}")
    except Exception as ex:
        pass

print(f"  NCAA results found: {len(ncaa_results)}")

# ── INJECT BRACKET RESULTS INTO HTML ─────────────────────────────────────────
if ncaa_results:
    def update_bracket_result(html_content, t1, t2, result):
        """Find the game row for t1 vs t2 and update the result."""
        # Match patterns like: {s1:1, t1:'Duke', s2:16, t2:'Siena', r:null
        patterns = [
            (f"t1:'{t1}'", f"t2:'{t2}'"),
            (f"t1:'{t2}'", f"t2:'{t1}'"),
        ]
        for p1, p2 in patterns:
            # Find the game object and replace r:null with r:'result'
            pattern = r"(\{[^}]*" + re.escape(p1) + r"[^}]*" + re.escape(p2) + r"[^}]*),r:null"
            replacement = r"\1,r:'" + js_escape(result) + "'"
            new_content = re.sub(pattern, replacement, html_content)
            if new_content != html_content:
                return new_content
            # Try reverse order
            pattern2 = r"(\{[^}]*" + re.escape(p2) + r"[^}]*" + re.escape(p1) + r"[^}]*),r:null"
            new_content = re.sub(pattern2, replacement, html_content)
            if new_content != html_content:
                return new_content
        return html_content

    # Map known team name variations
    TEAM_ALIASES = {
        'north carolina': 'n. carolina',
        'north carolina tar heels': 'n. carolina',
        'michigan wolverines': 'michigan',
        'duke blue devils': 'duke',
        'uconn huskies': 'uconn',
        'michigan state spartans': 'michigan st.',
        'iowa state cyclones': 'iowa state',
        'north dakota state bison': 'n. dakota st.',
        'kennesaw state owls': 'kennesaw st.',
        'saint marys gaels': "saint mary's",
        'saint mary s gaels': "saint mary's",
        'texas a m aggies': 'texas a&m',
        'byu cougars': 'byu',
        'unc wilmington seahawks': 'uncw',
    }

    with open('index.html', 'r', encoding='utf-8') as f:
        html = f.read()

    updated = 0
    for (t1_raw, t2_raw), result in ncaa_results.items():
        t1 = TEAM_ALIASES.get(t1_raw, t1_raw.title())
        t2 = TEAM_ALIASES.get(t2_raw, t2_raw.title())
        new_html = update_bracket_result(html, t1, t2, result)
        if new_html != html:
            html = new_html
            updated += 1

    if updated:
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"  ✓ Updated {updated} bracket game results in index.html")
    else:
        print("  ℹ No bracket results matched (games may not have started yet)")

print(f"\n{'='*60}\nAll done — {label}\n{'='*60}\n")
