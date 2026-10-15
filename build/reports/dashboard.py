#!/usr/bin/env python3
"""Static dashboard generator for the Launch Economics tracker (v0.4 Part 2).

Reads tracker.db, writes files/launch-econ-dashboard.html — a self-contained
HTML file (inline SVG charts, no CDN, works offline). Regenerated daily by cron.

Views: Regime | Collections | Wallets | Mint timing
"""
import os
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

BUILD = os.path.expanduser("~/workspace/goals/launch-economics-data-tool/build")
DB = os.path.join(BUILD, "tracker.db")
OUT = os.path.expanduser("~/workspace/goals/launch-economics-data-tool/files/dragon-dashboard.html")
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

CSS = """

*{box-sizing:border-box}
body{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;color:#e8eef7;margin:0;
padding:28px 24px;max-width:1220px;
background:
radial-gradient(1100px 550px at 12% -5%, #1c1546 0%, transparent 60%),
radial-gradient(950px 520px at 88% 8%, #3d0f30 0%, transparent 55%),
radial-gradient(900px 620px at 50% 112%, #0b2a3d 0%, transparent 60%),
#070a12;}
h1{font-size:27px;margin:0 0 6px;letter-spacing:1px;font-weight:800;
background:linear-gradient(90deg,#3b82f6,#8b5cf6,#d946ef,#fb923c,#facc15);
-webkit-background-clip:text;background-clip:text;color:transparent;}
.sub{color:#8b98ad;font-size:13px;margin-bottom:20px;font-style:italic}
.tabs{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}
.tabs button{background:#0d1320cc;border:1px solid #26334d;color:#c6d2e4;padding:9px 18px;
border-radius:20px;cursor:pointer;font-size:14px;letter-spacing:.3px;transition:all .2s}
.tabs button:hover{border-color:#8b5cf6;color:#fff}
.tabs button.active{background:linear-gradient(90deg,#3b82f655,#d946ef55);
border:1px solid transparent;color:#fff;font-weight:600;
box-shadow:0 0 18px #8b5cf644}
.tab{display:none}.tab.active{display:block;animation:fade .3s}
@keyframes fade{from{opacity:0}to{opacity:1}}
.card{background:#0c1220e6;border:1px solid #22304a;border-radius:14px;padding:18px;
margin-bottom:18px;box-shadow:0 4px 24px #00000055}
.card h2{font-size:16px;margin:0 0 12px;letter-spacing:.4px}
.card h2 .note{font-weight:400}
.card h3{font-size:13px;margin:16px 0 8px;color:#8b98ad;text-transform:uppercase;
letter-spacing:1.2px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:#8b98ad;font-weight:600;padding:7px 8px;
border-bottom:1px solid #2a3a58;cursor:pointer;white-space:nowrap}
td{padding:7px 8px;border-bottom:1px solid #1a2438;font-variant-numeric:tabular-nums}
tr:hover td{background:#141d33}
.up{color:#ccff00}.down{color:#ff4d6d}.flat{color:#9aa7bd}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600}
.b-sweep{background:#3b82f633;color:#93c5fd}.b-dump{background:#ff4d6d33;color:#ff9eaf}
.b-wash{background:#facc1533;color:#fde68a}.b-spike{background:#ccff0033;color:#e4ff8a}
.b-trojan{background:#fb923c33;color:#fdba74}
.note{color:#8b98ad;font-size:12px;line-height:1.5}.mono{font-family:ui-monospace,monospace;font-size:12px}
svg text{fill:#8b98ad;font-size:10px}
.grad-text{background:linear-gradient(90deg,#8b5cf6,#d946ef,#fb923c);
-webkit-background-clip:text;background-clip:text;color:transparent;font-weight:700}
"""

JS = """
function show(id){document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
document.querySelectorAll('.tabs button').forEach(b=>b.classList.remove('active'));
document.getElementById('tab-'+id).classList.add('active');
document.getElementById('btn-'+id).classList.add('active');}
function sortTable(th){const t=th.closest('table'),tb=t.tBodies[0],ci=[...th.parentNode.children].indexOf(th);
const rows=[...tb.rows],num=th.dataset.num==='1';const asc=th.dataset.asc!=='1';th.dataset.asc=asc?'1':'0';
rows.sort((a,b)=>{let x=a.cells[ci].textContent.trim(),y=b.cells[ci].textContent.trim();
if(num){x=parseFloat(x)||0;y=parseFloat(y)||0}return asc?(x>y?1:-1):(x<y?1:-1)});
rows.forEach(r=>tb.appendChild(r));}
function tierOf(s){if(!s||s<=0)return "unknown";if(s<1000)return "sub-1k";
if(s<2000)return "1k-2k";if(s<3000)return "2k-3k";if(s<5000)return "3k-5k";
if(s<10000)return "5k-10k";return "10k+";}
function checkLaunch(){const v=parseInt(document.getElementById('launch-supply').value,10);
const t=tierOf(v),el=document.getElementById('launch-result');
const d=(typeof TIER_DATA!=='undefined'&&TIER_DATA[t])||null;
if(!v||v<=0){el.innerHTML="<p class='note'>Enter a supply size first.</p>";return;}
if(!d||!d.n){el.innerHTML="<p class='note'>No collections in the "+t+" tier yet.</p>";return;}
const deadPct=Math.round(d.dead/d.n*100);
let verdict;
if(d.med7===null||d.med7===undefined){verdict="Not enough floor history yet to call this tier.";}
else if(deadPct>=50){verdict="Most of this tier is dead (no live floor). High-risk tier.";}
else if(d.med7>=5){verdict="Strong tier: floors climbing on balance.";}
else if(d.med7<=-5){verdict="Soft tier: floors sliding on balance. Launch here needs a reason to be different.";}
else{verdict="Flat tier: floors holding roughly level.";}
const f=(x)=>x===null||x===undefined?"n/a":(x>0?"+":"")+x+"%";
const ex=(e)=>e?e.name+" ("+(e.chg>0?"+":"")+e.chg+"%)":"n/a";
el.innerHTML="<table><tbody>"+
"<tr><td>Tier</td><td><b>"+t+"</b> ("+v.toLocaleString()+" supply)</td></tr>"+
"<tr><td>Collections tracked</td><td>"+d.n+" ("+d.dead+" with no live floor)</td></tr>"+
"<tr><td>Median floor, 7d</td><td>"+f(d.med7)+"</td></tr>"+
"<tr><td>Median floor, 30d</td><td>"+f(d.med30)+"</td></tr>"+
"<tr><td>Best 7d mover</td><td>"+ex(d.best7)+"</td></tr>"+
"<tr><td>Worst 7d mover</td><td>"+ex(d.worst7)+"</td></tr>"+
"</tbody></table><p class='note' style='margin-top:10px'><b>Dragon's read:</b> "+verdict+"</p>";}
function setWindow(w){['1d','7d','30d'].forEach(function(x){const b=document.getElementById('win-'+x);
if(x===w){b.style.borderColor='#8b5cf6';b.style.color='#fff';}
else{b.style.borderColor='#26334d';b.style.color='#c6d2e4';}});
const order=(typeof WINDOW_DATA!=='undefined'&&WINDOW_DATA[w])||[];
const wrap=document.getElementById('collection-cards');if(!wrap)return;
const cards={};wrap.querySelectorAll('.collection-card').forEach(function(c){cards[c.dataset.slug]=c;});
const seen={};
order.forEach(function(slug,i){const c=cards[slug];if(!c)return;
wrap.appendChild(c);seen[slug]=1;
const badge=c.querySelector('.rank-badge');if(badge)badge.textContent='#'+(i+1);});
Object.keys(cards).forEach(function(slug){if(!seen[slug]){wrap.appendChild(cards[slug]);
const badge=cards[slug].querySelector('.rank-badge');if(badge)badge.textContent='-';}});}
"""


GRAD_DEF = """<defs><linearGradient id="chromanova" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#3b82f6"/><stop offset=".28" stop-color="#8b5cf6"/>
<stop offset=".55" stop-color="#d946ef"/><stop offset=".8" stop-color="#fb923c"/>
<stop offset="1" stop-color="#facc15"/></linearGradient></defs>"""


def svg_line(series, w=640, h=190, color="url(#chromanova)", fmt="{:.4f}"):
    """series: list of (label, value). Returns SVG string."""
    if len(series) < 2:
        return '<p class="note">not enough data</p>'
    ys = [y for _, y in series]
    mn, mx = min(ys), max(ys)
    rng = (mx - mn) or 1e-9
    n = len(series)
    pts = []
    for i, (lbl, y) in enumerate(series):
        x = 46 + i * (w - 56) / (n - 1)
        yy = h - 18 - (y - mn) / rng * (h - 34)
        pts.append((x, yy, lbl, y))
    path = "M" + " L".join(f"{x:.1f},{yy:.1f}" for x, yy, _, _ in pts)
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="3.2" fill="{color}">'
        f"<title>{lbl}: {fmt.format(y)}</title></circle>"
        for x, yy, lbl, y in pts
    )
    step = max(1, n // 8)
    labels = "".join(
        f'<text x="{x:.1f}" y="{h - 4}" text-anchor="middle">{lbl[5:]}</text>'
        for x, _, lbl, _ in pts[::step]
    )
    return (
        f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:auto">{GRAD_DEF}'
        f'<text x="4" y="12">{fmt.format(mx)}</text>'
        f'<text x="4" y="{h - 18}">{fmt.format(mn)}</text>'
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5"/>'
        f"{dots}{labels}</svg>"
    )


def svg_bars(series, w=640, h=190, color="url(#chromanova)", fmt="{:.2f}"):
    """series: list of (label, value). Returns SVG bar chart."""
    if not series:
        return '<p class="note">not enough data</p>'
    mx = max(y for _, y in series) or 1e-9
    n = len(series)
    bw = (w - 46) / n
    bars = []
    for i, (lbl, y) in enumerate(series):
        bh = max(1, (y / mx) * (h - 34))
        x = 46 + i * bw + 1
        yy = h - 18 - bh
        bars.append(
            f'<rect x="{x:.1f}" y="{yy:.1f}" width="{bw - 2:.1f}" height="{bh:.1f}" '
            f'fill="{color}" rx="2"><title>{lbl}: {fmt.format(y)}</title></rect>'
        )
    step = max(1, n // 10)
    labels = "".join(
        f'<text x="{46 + i * bw + bw / 2:.1f}" y="{h - 4}" text-anchor="middle">'
        f"{lbl[5:] if len(lbl) > 5 else lbl}</text>"
        for i, (lbl, _) in enumerate(series) if i % step == 0
    )
    return (
        f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:auto">{GRAD_DEF}'
        f'<text x="4" y="12">{fmt.format(mx)}</text>' + "".join(bars) + labels + "</svg>"
    )


def arrow(new, old):
    if new > old * 1.05:
        return '<span class="up">▲ UP</span>'
    if new < old * 0.95:
        return '<span class="down">▼ DOWN</span>'
    return '<span class="flat">■ FLAT</span>'


def view_regime(con):
    daily = defaultdict(lambda: [0, 0.0])
    for r in con.execute("SELECT date(timestamp) d, price_eth FROM sales"):
        daily[r["d"]][0] += 1
        if r["price_eth"] is not None:
            daily[r["d"]][1] += r["price_eth"]
    days = sorted(daily)[-30:]
    vol = [(d, daily[d][1]) for d in days]
    cnt = [(d, daily[d][0]) for d in days]
    half = len(days) // 2
    pv = sum(v for _, v in vol[:half]) or 1e-9
    lv = sum(v for _, v in vol[half:])
    chg = (lv - pv) / pv * 100

    rows = ""
    for r in con.execute("SELECT id, slug, name FROM collections"):
        sales = con.execute(
            "SELECT price_eth FROM sales WHERE collection_id=? AND price_eth IS NOT NULL ORDER BY timestamp",
            (r["id"],),
        ).fetchall()
        if len(sales) < 10:
            continue
        vol_eth = sum(s["price_eth"] for s in sales)
        if vol_eth < 0.1:
            continue  # dust: transaction count without economic weight
        q = len(sales) // 4
        old = sorted(s["price_eth"] for s in sales[:q])[q // 2]
        new = sorted(s["price_eth"] for s in sales[-q:])[q // 2]
        rows += (
            f"<tr><td>{r['name']}</td><td>{arrow(new, old)}</td>"
            f"<td data-num='1'>{old:.5f}</td><td data-num='1'>{new:.5f}</td>"
            f"<td data-num='1'>{len(sales)}</td><td data-num='1'>{vol_eth:.2f}</td></tr>"
        )
    return f"""
<div class="card"><h2>Market regime — last 30 days</h2>
<p>Volume trend (second half vs first half): <b class="{'up' if chg > 0 else 'down'}">
{'UP' if chg > 0 else 'DOWN'} {abs(chg):.1f}%</b></p>
<h3>Daily volume (ETH)</h3>{svg_bars(vol, fmt='{:.3f}')}
<h3>Daily sales count</h3>{svg_bars(cnt, color='#8957e5', fmt='{:.0f}')}
</div>
<div class="card"><h2>Price direction by collection</h2>
<p class="note">Newest-quartile median vs oldest-quartile median. Minimum 10 sales and
0.1 ETH total volume, so dust doesn't masquerade as activity. Click headers to sort.</p>
<table><thead><tr><th>Collection</th><th>Trend</th><th data-num="1">Old med</th>
<th data-num="1">New med</th><th data-num="1">Sales</th><th data-num="1">Vol (ETH)</th></tr></thead>
<tbody>{rows}</tbody></table></div>
"""


def _window_rankings():
    """Load top-30 window rankings. Returns {window: [slugs]}."""
    p = os.path.expanduser(
        "~/workspace/goals/launch-economics-data-tool/hidden_files/top30.json")
    try:
        return json.load(open(p)).get("windows", {})
    except Exception:
        return {}


def _is_dead_7d(slug):
    """True if the collection measurably had zero volume over the trailing 7d.
    Dead = snapshots span 7+ days AND (trailing volume diff is 0 OR volume has
    never been recorded). Insufficient history returns False (unknown)."""
    edb = os.path.join(BUILD, "econ.db")
    try:
        econ = sqlite3.connect(edb)
        econ.row_factory = sqlite3.Row
    except Exception:
        return False
    rows = econ.execute(
        "SELECT ts, volume, vol_sym FROM snapshots WHERE slug=? ORDER BY ts",
        (slug,)).fetchall()
    econ.close()
    if len(rows) < 2:
        return False
    first, latest = rows[0], rows[-1]
    # Need history spanning ~7 days to call it.
    try:
        span_days = (datetime.fromisoformat(latest["ts"].replace("Z", "+00:00")) -
                     datetime.fromisoformat(first["ts"].replace("Z", "+00:00"))).days
    except Exception:
        return False
    if span_days < 6:
        return False
    vols = [r["volume"] for r in rows if r["volume"] is not None]
    if not vols:
        return True  # never any volume recorded over 7d+ of tracking
    if (rows[0]["vol_sym"] or "ETH") != (latest["vol_sym"] or "ETH"):
        return False
    # Trailing-7d diff: latest vs the snapshot nearest 7d ago.
    old = None
    for r in reversed(rows[:-1]):
        old = r
        try:
            ago = (datetime.fromisoformat(latest["ts"].replace("Z", "+00:00")) -
                   datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))).days
        except Exception:
            continue
        if ago >= 6:
            break
    if old is None or old["volume"] is None or latest["volume"] is None:
        return False
    return (latest["volume"] - old["volume"]) == 0


def dragon_section(con, top7):
    """Claimed by Dragonfire: tracked collections with zero tape sales in the
    trailing 7 days, excluding the current top 30. The sales tape is the most
    direct measure of 'no volume'."""
    top7set = set(top7)
    claimed = []
    for r in con.execute("SELECT slug, name FROM collections"):
        slug = r["slug"]
        if slug in top7set:
            continue
        n = con.execute(
            "SELECT COUNT(*) c FROM sales s JOIN collections c ON s.collection_id=c.id "
            "WHERE c.slug=? AND s.timestamp >= datetime('now', '-7 days')",
            (slug,)).fetchone()["c"]
        if n == 0:
            claimed.append((r["name"], slug))
    if not claimed:
        return ""
    rows = "".join(
        f"<tr><td>{n}</td><td class='mono'>{s}</td>"
        f"<td>no sales in 7d</td></tr>" for n, s in sorted(claimed))
    return f"""
<div class="card" style="margin-top:24px;border-color:#7f1d1d">
<h2><span class="grad-text">Claimed by Dragonfire</span></h2>
<p class="note">Zero sales on our tape in the trailing 7 days. Data retained for base rates,
off the main board.</p>
<table><thead><tr><th>Collection</th><th>Slug</th><th>Status</th></tr></thead>
<tbody>{rows}</tbody></table></div>"""


def view_collections(con):
    windows = _window_rankings()
    rank7 = windows.get("7d", [])
    # Union of all windows, 7d order first.
    union = []
    for w in ["7d", "1d", "30d"]:
        for s in windows.get(w, []):
            if s not in union:
                union.append(s)
    if not union:
        union = [r["slug"] for r in
                 con.execute("SELECT slug FROM collections ORDER BY name")]
        rank7 = union
    # Ensure tracker rows exist for rendering, using verified names where known.
    try:
        _resolved = json.load(open(os.path.join(BUILD, "resolved.json")))
        _names = {}
        for _n, _m in _resolved.items():
            if isinstance(_m, dict) and _m.get("slug"):
                _names[_m["slug"]] = _m.get("verified_name") or _n
    except Exception:
        _names = {}
    for slug in union:
        if not con.execute("SELECT id FROM collections WHERE slug=?",
                           (slug,)).fetchone():
            con.execute(
                "INSERT INTO collections(slug, name, chain, launch_type) VALUES(?,?,?,?)",
                (slug, _names.get(slug) or slug.replace("-", " ").title(),
                 "robinhood", "unknown"))
    con.commit()
    rank_of = {s: i + 1 for i, s in enumerate(rank7)}

    def card(r, slug):
        cid = r["id"]
        daily = defaultdict(list)
        for s in con.execute(
            "SELECT date(timestamp) d, price_eth FROM sales WHERE collection_id=? AND price_eth IS NOT NULL",
            (cid,),
        ):
            daily[s["d"]].append(s["price_eth"])
        series = sorted((d, sum(v) / len(v)) for d, v in daily.items())
        n = con.execute("SELECT COUNT(*) c FROM sales WHERE collection_id=?",
                        (cid,)).fetchone()["c"]
        evs = con.execute(
            "SELECT type, timestamp, confidence, details FROM events "
            "WHERE collection_id=? "
            "ORDER BY CASE WHEN type='trojan_horse' THEN 0 ELSE 1 END, "
            "timestamp DESC LIMIT 15",
            (cid,),
        ).fetchall()
        ev_rows = ""
        for e in evs:
            cls = {"sweep": "b-sweep", "whale_dump": "b-dump",
                   "wash_flag": "b-wash", "volume_spike": "b-spike",
                   "trojan_horse": "b-trojan"}.get(e["type"], "")
            label = "♘ trojan horse" if e["type"] == "trojan_horse" else e["type"]
            ev_rows += (
                f"<tr><td><span class='badge {cls}'>{label}</span></td>"
                f"<td class='mono'>{e['timestamp'][:16]}</td>"
                f"<td data-num='1'>{e['confidence']:.2f}</td>"
                f"<td class='mono'>{e['details'][:110]}</td></tr>"
            )
        rank = rank_of.get(slug)
        rank_badge = f" <span class='badge b-spike rank-badge'>#{rank}</span>" if rank else ""
        mp = r["mint_price_eth"]
        mint_str = "Free" if mp == 0 else (f"{mp:.4f} ETH" if mp is not None else "mint n/a")
        return f"""
<div class="card collection-card" data-slug="{slug}">
<h2>{r['name']}{rank_badge} <span class="note">{r['chain']} · {n} sales · mint {mint_str}</span></h2>
<h3>Daily median sale (ETH)</h3>
{svg_line([(d, v) for d, v in series]) if len(series) >= 2 else '<p class="note">no tape yet</p>'}
<h3>Recent events</h3>
{f"<table><thead><tr><th>Type</th><th>Time</th><th data-num='1'>Conf</th><th>Details</th></tr></thead><tbody>{ev_rows}</tbody></table>" if ev_rows else '<p class="note">no events detected</p>'}
</div>"""

    out = """<div class="card"><h2><span class="grad-text">Top 30 by volume</span></h2>
<p class="note">Ranked by trading volume in ETH, OpenSea trending methodology.
Toggle the window:</p>
<div style="display:flex;gap:8px;margin-top:8px">
<button onclick="setWindow('1d')" id="win-1d" style="background:#0d1320cc;border:1px solid #26334d;color:#c6d2e4;padding:7px 14px;border-radius:8px;cursor:pointer">1D</button>
<button onclick="setWindow('7d')" id="win-7d" class="active" style="background:#0d1320cc;border:1px solid #8b5cf6;color:#fff;padding:7px 14px;border-radius:8px;cursor:pointer">7D</button>
<button onclick="setWindow('30d')" id="win-30d" style="background:#0d1320cc;border:1px solid #26334d;color:#c6d2e4;padding:7px 14px;border-radius:8px;cursor:pointer">30D</button>
</div></div>
<div id="collection-cards">"""
    # 7d rank order first.
    ordered = sorted(union, key=lambda s: rank_of.get(s, 999))
    for slug in ordered:
        r = con.execute("SELECT id, slug, name, chain, mint_price_eth FROM collections WHERE slug=?",
                        (slug,)).fetchone()
        out += card(r, slug)
    out += "</div>"
    out += dragon_section(con, rank7)
    return out


def view_wallets(con):
    rows = ""
    for r in con.execute(
        """SELECT wallet, dives, dive_wins, win_rate, realized_pnl_eth, dumps
           FROM wallet_scores WHERE dives > 0 OR dumps > 0
           ORDER BY dives DESC, win_rate DESC LIMIT 60"""
    ):
        w = r["wallet"]
        wr = f"{r['win_rate']:.0%}" if r["win_rate"] is not None else "—"
        pnl_cls = "up" if (r["realized_pnl_eth"] or 0) > 0 else (
            "down" if (r["realized_pnl_eth"] or 0) < 0 else "flat")
        rows += (
            f"<tr><td class='mono'>{w[:10]}…{w[-4:]}</td>"
            f"<td data-num='1'>{r['dives']}</td><td data-num='1'>{r['dive_wins']}</td>"
            f"<td>{wr}</td>"
            f"<td data-num='1' class='{pnl_cls}'>{r['realized_pnl_eth']:.4f}</td>"
            f"<td data-num='1'>{r['dumps']}</td></tr>"
        )
    return f"""
<div class="card"><h2>Wallet leaderboard</h2>
<p class="note">Dive = buy within 7 days of first observed sale. Win = later sold same
collection above avg buy. Wallet ≠ person — sybil/bot noise is real; treat scores as
signals, not identities. Click headers to sort.</p>
<table><thead><tr><th>Wallet</th><th data-num="1">Dives</th><th data-num="1">Wins</th>
<th>Dive rate</th><th data-num="1">Realized PnL (ETH)</th><th data-num="1">Dumps</th></tr></thead>
<tbody>{rows}</tbody></table></div>
"""


def view_timing(con):
    rows = ""
    for cohort, n_coll, n_sales in con.execute(
        """SELECT c.cohort, COUNT(DISTINCT c.id), COUNT(s.id)
           FROM collections c LEFT JOIN sales s ON s.collection_id = c.id
           GROUP BY c.cohort"""
    ):
        rows += f"<tr><td>{cohort}</td><td data-num='1'>{n_coll}</td><td data-num='1'>{n_sales}</td></tr>"
    return f"""
<div class="card"><h2>Cohorts</h2>
<table><thead><tr><th>Cohort</th><th data-num="1">Collections</th><th data-num="1">Sales</th></tr></thead>
<tbody>{rows}</tbody></table>
<p class="note" style="margin-top:10px"><b>mint-comps</b> = free-mint comparables for your
launch (Cartoonals Classics, City of Stonks). <b>broad</b> = everything else, feeds wallet
intel and regime reads.</p></div>
<div class="card"><h2>Mint-timing briefing</h2>
<p><span class="grad-text">Regime:</span> broad-cohort medians are down across most
collections — the Robinhood NFT market is cooling, not heating. No urgency from market
momentum; the space between launches is quiet right now.</p>
<p><span class="grad-text">What actually matters for your date:</span> the Bugz mint and
its aftermath (partner collections expected to dump), plus holiday dead zones
(late December). Day-of-week effects are unreliable at current data depth.</p>
<p class="note"><b>Honest gaps:</b> mint-comps has no tape yet — Cartoonals Classics and
City of Stonks trade off Hood Market and off OpenSea. Their history must come from their
actual venues or Blockscout transfers. Hood Market timestamps are approximate
(relative labels). Wash flags are investigative, never accusations.</p></div>
"""


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    n_sales = con.execute("SELECT COUNT(*) c FROM sales").fetchone()["c"]
    n_w = con.execute("SELECT COUNT(*) c FROM wallets").fetchone()["c"]
    tier_data = json.dumps(tier_brief())
    win_data = json.dumps(_window_rankings())
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Water Dragon Dashboard</title><style>{CSS}</style></head><body>
<h1>Water Dragon Dashboard</h1>
<div class="sub">v0.4 Part 2 · {n_sales} sales · {n_w} wallets · charting the hidden worlds of Robinhood NFTs · generated {stamp}</div>
<div class="tabs">
<button id="btn-regime" class="active" onclick="show('regime')">Regime</button>
<button id="btn-collections" onclick="show('collections')">Collections</button>
<button id="btn-wallets" onclick="show('wallets')">Wallets</button>
<button id="btn-timing" onclick="show('timing')">Mint timing</button>
<button id="btn-intel" onclick="show('intel')">Intel</button>
<button id="btn-launch" onclick="show('launch')">Launch</button>
<button id="btn-defs" onclick="show('defs')">Definitions</button>
</div>
<div id="tab-regime" class="tab active">{view_regime(con)}</div>
<div id="tab-collections" class="tab">{view_collections(con)}</div>
<div id="tab-wallets" class="tab">{view_wallets(con)}</div>
<div id="tab-timing" class="tab">{view_timing(con)}</div>
<div id="tab-intel" class="tab">{view_intel()}</div>
<div id="tab-launch" class="tab">{view_launch()}</div>
<div id="tab-defs" class="tab">{view_definitions()}</div>
<script>const TIER_DATA = {tier_data};</script>
<script>const WINDOW_DATA = {win_data};</script>
<script>{JS}</script></body></html>"""
    con.close()
    with open(OUT, "w") as f:
        f.write(html)
    print(f"dashboard written: {OUT} ({len(html)//1024} KB)")


def view_intel():
    """Ecosystem intel from the external CCFF00 chain-forensics audit.
    Static, clearly sourced — not derived from our tape. Integrated 2026-10-04."""
    spinoffs = [
        ("stacc's homecoming", "15 Sep", "8,002", "9,450",
         "none — airdropped 1 per CCFF00 held"),
        ("CCFF00 Cuboids", "19 Sep", "1,919", "1,981", "none"),
        ("CCFF00 CAT", "19 Sep", "600", "539", "none"),
        ("CCFF00 Pyramids", "20 Sep", "500", "432", "none"),
        ("NeonVerse", "21 Sep", "2,000", "988", "none"),
        ("CCFF00 #DOTS", "21 Sep", "999", "882", "none"),
        ("CCFF00 Bugs", "22 Sep", "465", "384", "none"),
        ("CCFF00 Cubes (Cluster A)", "17 Sep", "—", "2,146",
         "none — name copying only"),
    ]
    rows = "".join(
        f"<tr><td>{n}</td><td>{d}</td><td data-num='1'>{s}</td>"
        f"<td data-num='1'>{h}</td><td class='mono'>{m}</td></tr>"
        for n, d, s, h, m in spinoffs
    )
    return f"""
<div class="card"><h2>Ecosystem intel — CCFF00 audit</h2>
<p class="note">External chain-forensics audit, checked 4 Oct 2026. User-generated and
unverified: treat every figure as a lead, not gospel. Integrated into the dashboard
2026-10-04; our own tape now tracks CCFF00 and Stacc's Homecoming directly.</p>
<h3>The sale</h3>
<p class="note">9,750 public mints at 0.003 ETH = <b>29.25 ETH</b>, paid through an
on-chain 3-way splitter: 50% to one wallet, 25% each to two others. The creator
(hoodstreet.eth) kept <b>0 ETH</b> directly — deployed, ran the 250-NFT reserve,
triggered payouts, then went quiet after 16 Sep. A test collection ("HoodStreet Step 6C")
was deployed in August and never released.</p>
<h3>Distribution</h3>
<p class="note">No farm behind the top 40 holders (first-funder trace; only shared
funders were public bridge solvers). Top 20 hold 14.7%. The declared project reserve
(230 NFTs) is the #1 holder and has <b>never sold</b>. Real owners are roughly half the
explorer holder count — the rest are each NFT's own token-bound wallet.</p>
<h3>Where the money went</h3>
<p class="note">The 50% payee swapped to USDC and cashed <b>9,528 USDC</b> out to an
exchange (test transfers of $1–10 before each large send — careful operator). Both 25%
payees are dormant, sitting on ~6 ETH each. <b>No payee has ever held an NFT.</b>
One 25% payee sent <b>2.75 ETH</b> to the wallet that launched SKNOTS twelve days later:
payment proven, reason unknown (partner share, loan, or purchase). Attribution weight
65/100 — a money link, not a team tie.</p>
<h3>Token structure</h3>
<p class="note">90% of the 1B CCFF00 ERC-20 sits in 3 wallets that have never
transacted. Each NFT carries <b>10,000 tokens</b> in its own ERC-6551 token-bound wallet —
the NFT and its tokens travel together.</p>
<h3>Cluster A (Cube Twist / 00CCFF)</h3>
<p class="note">Name-copying and trading only — <b>no money link</b> to the CCFF00 team.
Their MAIN wallet gifted 21 Hood Crayons (~$880 at floor) to CCFF00's project reserve on
24 Sep: a gift to a big holder, not a payment.</p>
</div>
<div class="card"><h2>Spin-off watch — CCFF00 copycats</h2>
<p class="note">Every deployer was checked for transfers with the CCFF00 team. None found:
independent devs building on the name.</p>
<table><thead><tr><th>Collection</th><th>Launched</th><th data-num="1">Supply</th>
<th data-num="1">Holders</th><th>Money link</th></tr></thead>
<tbody>{rows}</tbody></table>
<p class="note" style="margin-top:10px"><b>Base rate so far: 8 copycats, 0 with money
links to the original team.</b> Copying the name is cheap; copying the distribution
is not. Watch whether any spin-off converts attention into its own holder base —
that's the survival signal.</p></div>
<div class="card"><h2>Stacc's burn mechanism — Fireball Wizards</h2>
<p class="note">User-reported 2026-10-06, corroborated on OpenSea. Stacc's Homecoming
introduced a burn mechanism with two effects: (1) Stacc's NFTs get burned, shrinking
that collection's supply; (2) burners receive into a new collection, <b>Fireball
Wizards</b> (0xf0545da454…, Robinhood Chain). OpenSea shows 255 supply, 111 owners,
created 2026-10-04, floor 53.0 USDG. Our tape now tracks Fireball Wizards directly
(its sales are USDG-denominated, tagged separately from ETH volume).
Why it matters: Stacc's is the dashboard's positive price-direction outlier — a
shrinking supply is a real fundamental change, not just tape noise. Watch whether
the burn sustains the premium or just front-runs it.</p></div>
"""


def source_heartbeat_html():
    """Data-sources freshness: last-pulled time per source, shown in ET."""
    import json
    hp = os.path.expanduser("~/workspace/goals/launch-economics-data-tool/hidden_files/source_pulls.json")
    try:
        data = json.load(open(hp))
    except Exception:
        data = {}
    try:
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
    except ImportError:
        et = timezone.utc

    def fmt(key):
        ts = data.get(key)
        if not ts:
            return "<i>not yet recorded</i>"
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(et)
            return dt.strftime("%b %-d, %Y, %-I:%M %p %Z")
        except Exception:
            return ts

    rows = [
        ("OpenSea", "collection snapshots (floors, owners, volume)", fmt("opensea_snapshots")),
        ("OpenSea", "sales tape", fmt("opensea_sales")),
        ("OpenSea", "top-30 universe refresh", fmt("universe")),
    ]
    lis = "".join(
        f"<li><b>{src}</b>, {what}: last pulled {when}</li>" for src, what, when in rows
    )
    return (
        "<div class='card' style='margin-bottom:12px'>"
        "<h2><span class='grad-text'>Data sources</span></h2>"
        f"<ul class='note' style='font-size:13px;line-height:1.7'>{lis}</ul>"
        "<p class='note' style='font-size:12px'>Timestamps show when each pull last ran, "
        "not when the last sale happened. A quiet tape still gets pulled on schedule.</p></div>"
    )


def tier_brief():
    """Per-tier launch base rates from econ.db snapshots.

    For each supply tier: collection count, share with no live floor (dead),
    median floor change over trailing 7d/30d (ETH-denominated only), and the
    best/worst 7d movers as concrete examples. Returned as JSON-ready dict.
    """
    edb = os.path.join(BUILD, "econ.db")
    try:
        econ = sqlite3.connect(edb)
        econ.row_factory = sqlite3.Row
    except Exception:
        return {}
    latest = econ.execute("SELECT MAX(ts) FROM snapshots").fetchone()[0]
    if not latest:
        econ.close()
        return {}
    cols = {}
    for r in econ.execute(
            "SELECT slug, name, tier, total_supply, floor, floor_sym FROM snapshots WHERE ts=?",
            (latest,)):
        cols[r["slug"]] = dict(r)

    def med(pairs):
        s = sorted(v for _, v in pairs)
        return round(s[len(s) // 2], 1) if s else None

    out = {}
    for t in ["sub-1k", "1k-2k", "2k-3k", "3k-5k", "5k-10k", "10k+"]:
        members = [c for c in cols.values() if c["tier"] == t]
        n = len(members)
        if n == 0:
            out[t] = {"n": 0}
            continue
        dead = sum(1 for c in members if not c["floor"])
        ch7, ch30 = [], []
        for c in members:
            if not c["floor"] or (c["floor_sym"] or "ETH") != "ETH":
                continue
            old7 = econ.execute(
                "SELECT floor FROM snapshots WHERE slug=? AND ts <= datetime(?, '-7 days') "
                "AND floor IS NOT NULL ORDER BY ts DESC LIMIT 1",
                (c["slug"], latest)).fetchone()
            old30 = econ.execute(
                "SELECT floor FROM snapshots WHERE slug=? AND ts <= datetime(?, '-30 days') "
                "AND floor IS NOT NULL ORDER BY ts DESC LIMIT 1",
                (c["slug"], latest)).fetchone()
            if old7 and old7["floor"]:
                ch7.append((c["name"], (c["floor"] - old7["floor"]) / old7["floor"] * 100))
            if old30 and old30["floor"]:
                ch30.append((c["name"], (c["floor"] - old30["floor"]) / old30["floor"] * 100))
        ch7s = sorted(ch7, key=lambda x: x[1])
        out[t] = {
            "n": n,
            "dead": dead,
            "n_eth": len(ch7),
            "med7": med(ch7),
            "med30": med(ch30),
            "best7": {"name": ch7s[-1][0], "chg": round(ch7s[-1][1], 1)} if ch7s else None,
            "worst7": {"name": ch7s[0][0], "chg": round(ch7s[0][1], 1)} if ch7s else None,
        }
    econ.close()
    return out


def view_launch():
    """Interactive launch-size checker. Tier stats are precomputed at build time
    and embedded as JSON; the lookup itself runs client-side, offline."""
    return """
<div class="card"><h2><span class="grad-text">Should I launch at this size?</span></h2>
<p class="note">Type a supply size. The Dragon looks up its tier and shows how that tier
has actually performed: median floor movement, share with no live floor, best and worst movers.</p>
<div style="display:flex;gap:10px;align-items:center;margin:12px 0;flex-wrap:wrap">
<input id="launch-supply" type="number" min="1" placeholder="e.g. 5552"
 style="background:#0d1320cc;border:1px solid #26334d;color:#e8eef7;padding:9px 12px;border-radius:8px;width:160px;font-size:15px">
<button onclick="checkLaunch()" style="background:#0d1320cc;border:1px solid #8b5cf6;color:#e8eef7;padding:9px 18px;border-radius:8px;cursor:pointer;font-size:15px">Check tier</button>
</div>
<div id="launch-result"><p class="note">Results appear here.</p></div></div>
<div class="card"><h2>How to read this</h2>
<p class="note" style="font-size:13px">Tiers mirror the v0.4 spec: sub-1k, 1k-2k, 2k-3k, 3k-5k, 5k-10k, 10k+.
Floor changes are ETH-denominated collections only. A collection with no live floor counts as dead for this read.
Small n means wide uncertainty, treat thin tiers as hints, not verdicts.</p></div>
"""


def view_definitions():
    defs = [
        ("Tape",
         "Every individual sale — price, buyer, seller, timestamp, tx hash. "
         "The source of truth. Every detector, score, and chart derives from the tape, "
         "never from floor snapshots alone.",
         None),
        ("Floor",
         "The lowest currently listed price. A lagging snapshot: useful context, "
         "but a flat floor can hide real movement on the tape.",
         None),
        ("Price unit",
         "Sale prices are recorded as ETH only when the trade was denominated in "
         "ETH or WETH. Trades in other tokens (e.g. USDG) are tagged with their "
         "symbol and excluded from ETH volume and price aggregates — never silently "
         "converted.",
         None),
        ("Dive",
         "A buy within 7 days of a collection's first observed sale. "
         "Measures early conviction — not necessarily smart conviction.",
         "≤ 7 days from first sale"),
        ("Dive win",
         "An dive where the wallet later sold the same collection above its average buy price.",
         None),
        ("Dive rate",
         "Dive wins ÷ dives. Wallets need at least 2 dives to appear on the leaderboard — "
         "one lucky buy is not a track record.",
         "min 2 dives"),
        ("Realized PnL",
         "Total sell revenue minus total buy cost (ETH), counting only trades visible on "
         "the tape. Understates true PnL — off-tape and cross-chain trades are invisible.",
         None),
        ("Sweep",
         "5 or more sales to a single buyer within 6 hours. Flags buyer concentration. "
         "Sweeps are often followed by dumps — the pattern, not the buyer, is the signal.",
         "≥ 5 buys / 6h"),
        ("Whale",
         "We don't score wallet size — we detect whale <i>behavior</i>. "
         "A wallet moving size, not a wallet holding size. See Whale dump.",
         None),
        ("Whale dump",
         "One wallet selling 3 or more tokens of a single collection within 24 hours. "
         "Possible distribution, panic exit, or rotation — the tape shows the what, not the why.",
         "≥ 3 sells / 24h"),
        ("Wash flag",
         "Wallets A and B trading with each other in both directions on one collection. "
         "Confidence 0.60. Investigative only — a flag is never an accusation.",
         "confidence 0.60"),
        ("Volume spike",
         "24-hour sales at or above 3× the trailing-7-day daily average. Momentum, "
         "for better or worse.",
         "≥ 3× 7d avg"),
        ("♘ Trojan horse",
         "A sweep (apparent demand) followed by a dump from the same wallet, 1–72 hours "
         "later. The gift that was an exit — buying pressure as camouflage for distribution. "
         "The Wood Horse watches the gates for these.",
         "1–72h gap"),
        ("Mint-out",
         "Time from mint open to sellout. Defined in the v0.4 spec — detector not yet built.",
         "planned"),
        ("Attribution methods",
         "How wallets get tied to teams — the playbook from the CCFF00 ecosystem audit "
         "(Oct 2026), the standard we hold manual investigations to. Strongest first: "
         "constructor arguments and payment-splitter releases (named on-chain); first-funder "
         "tracing with public bridge solvers filtered out; shared exchange deposit addresses; "
         "SeaDrop drop-settings comparison (payout wallet, fee recipient, signer); metadata "
         "hosts; repeat OpenSea counterparties; bridge-origin decoding; behavior fingerprints "
         "(gas settings, nonce patterns, time-of-day). "
         "On-chain patterns show what happened, not intent — a money link is not a team tie.",
         "manual"),
        ("Cohort: mint-comps",
         "Free-mint comparables for your launch: Cartoonals Classics, City of Stonks. "
         "The lens for your mint-date decision.",
         None),
        ("Cohort: broad",
         "Everything else. Feeds wallet intelligence (breadth is the feature) and regime reads.",
         None),
        ("Regime",
         "Market-wide direction from aggregate tape: volume trend plus per-collection "
         "price direction. Answers 'is the water rising or falling', not 'should I buy'.",
         None),
        ("Survival curve",
         "Probability a collection's floor sits at or above mint price at day 30 / 60 / 90 / 180. "
         "Spec'd in v0.4 — the dataset is still accruing toward it.",
         "accruing"),
    ]
    cards = ""
    for term, body, chip in defs:
        chip_html = f" <span class='badge b-spike'>{chip}</span>" if chip else ""
        cards += (
            f"<div class='card' style='margin-bottom:12px'>"
            f"<h2><span class='grad-text'>{term}</span>{chip_html}</h2>"
            f"<p class='note' style='font-size:13px'>{body}</p></div>"
        )
    return f"""
<div class="card"><h2>What the Dragon means</h2>
<p class="note">Every label the dashboard uses, defined exactly as the code computes it.
Thresholds come from the v0.4 config, if a number changes there, this page follows.</p></div>
{source_heartbeat_html()}
{cards}
"""


if __name__ == "__main__":
    main()
