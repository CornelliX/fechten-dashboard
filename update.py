#!/usr/bin/env python3
"""Ellas Fecht-Dashboard: holt FIE-Daten, mischt manual.json (Ophardt) ein,
erkennt Änderungen und schreibt docs/data/{state.json, changes.json, history.csv}.
Nur Standardbibliothek. Aufruf: python update.py"""
import csv
import html
import json
import os
import re
import secrets
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "docs" / "data"
FIE = "https://fie.org"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; fencing-dashboard/1.0)"}
TYPE_DE = {"World Cup": "Weltcup", "World Championship": "WM", "World Championships": "WM", "Zone Championships": "EM",
           "Satellite": "Satellite", "Grand Prix": "Grand Prix",
           "Coupe du Monde": "Weltcup", "Tournoi Satellite": "Satellite"}


# ---------- Abruf ----------

def get(url):
    time.sleep(1)  # höflich: ~15 Requests pro Lauf, einer pro Sekunde
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def nuxt_queries(html):
    """FIE ist eine Nuxt-App; die Seitendaten stecken devalue-serialisiert in __NUXT_DATA__.
    Liefert {json(queryKey): body} aller vue-query-Abfragen der Seite."""
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise ValueError("__NUXT_DATA__ fehlt, FIE-Seitenstruktur geändert?")
    arr, memo = json.loads(m.group(1)), {}
    wrappers = {"Reactive", "ShallowReactive", "Ref", "ShallowRef", "EmptyRef", "EmptyShallowRef", "NuxtError"}

    def r(i):
        if i < 0:  # devalue-Sonderwerte (undefined, NaN, ...)
            return None
        if i in memo:
            return memo[i]
        v = arr[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str):  # devalue-Typen: ["Reactive", idx], ["Date", "..."], ["Set", ...]
                t, rest = v[0], v[1:]
                if t in wrappers:
                    memo[i] = r(rest[0]) if rest else None
                elif t == "Set":
                    memo[i] = [r(x) for x in rest]
                elif t in ("Map", "null"):
                    memo[i] = {str(r(k)) if t == "Map" else k: r(x) for k, x in zip(rest[::2], rest[1::2])}
                else:  # Date, RegExp, BigInt, ...: Literalwert
                    memo[i] = rest[0] if rest else None
                return memo[i]
            memo[i] = out = []
            out.extend(r(x) for x in v)
            return out
        if isinstance(v, dict):
            memo[i] = out = {}
            for k, x in v.items():
                out[k] = r(x)
            return out
        memo[i] = v
        return v

    root = r(0)
    return {json.dumps(q["queryKey"]): (q["state"].get("data") or {}).get("body")
            for q in root["state"]["$svue-query"]["queries"]}


def pick(queries, prefix):
    return next((v for k, v in queries.items() if k.startswith(prefix)), None)


def season_of(d):
    """FIE-Saison 2027 = 2026/27, Wechsel im August."""
    return d.year + 1 if d.month >= 8 else d.year


def fetch_ranking(cfg, season):
    q = urllib.parse.urlencode({"season": season, "weapon": cfg["weapon"], "gender": cfg["gender"],
                                "category": cfg["category"], "type": "I"})
    body = pick(nuxt_queries(get(f"{FIE}/athletes/detailed-ranking?{q}")), '["fencers", "detailed-ranking"')
    me = next((f for f in body["fencers"] if f["addrId"] == cfg["fie_id"]), None)
    raw = (me or {}).get("competitionPoints", {})
    comp_points = {k: float(v.strip("()")) for k, v in raw.items()}
    comps = {c["key"]: c for c in body.get("competitions", [])}
    # Welche Turniere mit wie vielen Punkten zählen; "(8.000)" = Streichergebnis
    breakdown = [{"key": k, "label": f"{event_de(comps[k]['name'])} {comps[k]['location']} {comps[k]['beginDate'][:4]}"
                  if k in comps else k, "points": comp_points[k], "counted": not v.startswith("(")}
                 for k, v in raw.items()]
    return {
        "rank": me and me["rank"],
        "points": me and float(me["points"]),
        "comp_points": comp_points,
        "breakdown": breakdown,
        "top_ger": [{"rank": f["rank"], "name": f["name"], "points": float(f["points"]), "id": f["addrId"]}
                    for f in body["fencers"] if f["countryCode"] == "GER"][:12],
    }


def fetch_profile(cfg):
    fid = cfg["fie_id"]
    qs = nuxt_queries(get(f"{FIE}/athletes/{fid}"))
    prof = pick(qs, f'["fencers", {fid}, null]')
    results = (pick(qs, f'["fencers", {fid}, "results"') or {}).get("items", [])
    bouts = pick(qs, f'["fencers", {fid}, "latest-bouts"') or []
    return {
        "rank": prof["rank"], "points": float(prof["points"]), "image": prof.get("image"),
        "seasons": [{"season": s["season"], "rank": s["rank"], "points": float(s["point"])}
                    for s in prof.get("ranking", []) if s.get("category") == cfg["category"]],
        "results": [result_row(x, cfg["category"]) for x in results],
        "bouts": [{"date": b["date"][:10], "event": f"{TYPE_DE.get(b['name'], b['name'])} {b['location']}",
                   "win": b["isWinner"], "score": f"{b['score']['fencer']}:{b['score']['opponent']}",
                   "opponent": " ".join(b["opponent"]["name"].split()), "nat": b["opponent"]["nationality"]}
                  for b in bouts],
    }


def result_row(x, cat):
    """FIE-Ergebnis -> Dashboard-Zeile. Senior-Schlüssel bleiben wie bisher, U20 bekommt ein Suffix."""
    name = f"{TYPE_DE.get(x['competitionType'], x['competitionType'])} {x['city']}" + (" (U20)" if cat == "J" else "")
    return {"key": f"fie-{x['season']}-{x['competitionId']}" + ("-J" if cat == "J" else ""), "date": x["date"],
            "name": name, "city": x["city"], "place": x["place"], "season": x["season"],
            "competition_id": x["competitionId"], "category": cat, "source": "FIE"}


def fetch_results(cfg, season):
    """Ergebnisse dieser und der letzten Saison, Senior und U20 (alte bleiben im State erhalten)."""
    out = []
    for s in (season, season - 1):
        for cat in ("S", "J"):
            q = urllib.parse.urlencode({"category": cat, "season": s})
            items = json.loads(get(f"{FIE}/api/fie/fencer/{cfg['fie_id']}/results?{q}")).get("items", [])
            out += [result_row(x, cat) for x in items]
    return out


def fetch_field(season, competition_id):
    season, competition_id = int(season), int(competition_id)  # nur Zahlen in die URL
    return json.loads(get(f"{FIE}/api/fie/competition/{season}/{competition_id}")).get("fencerCount")


def event_de(name):
    """FIE-Wettkampfnamen (oft französisch) kurz auf Deutsch."""
    n = " ".join(name.split())
    if n.startswith("Championnats"):
        return "EM" if "Europe" in n else "WM" if "Monde" in n else n
    return TYPE_DE.get(n, n)


def parse_opponents(items, fid):
    """Bilanz je Gegnerin aus den Einzelgefechten (FIE-'victories' zählt aus Sicht der Gegnerin)."""
    rows = []
    for o in items:
        bouts = []
        for e in o.get("events", []):
            me, other = (e["fencer1"], e["fencer2"]) if e["fencer1"].get("id") == fid else (e["fencer2"], e["fencer1"])
            bouts.append({"date": e["date"][:10], "win": bool(me.get("isWinner")),
                          "score": f"{me.get('score')}:{other.get('score')}",
                          "event": f"{event_de(e['name'])} {e['location']}" + (" (U20)" if e.get("category") == "J" else "")})
        if not bouts:
            continue
        bouts.sort(key=lambda b: b["date"], reverse=True)
        wins = sum(b["win"] for b in bouts)
        rows.append({"id": o["id"], "name": " ".join(o["name"].split()), "nat": (o.get("flag") or "").upper(),
                     "wins": wins, "losses": len(bouts) - wins, "last": bouts[0]})
    return sorted(rows, key=lambda r: (r["wins"] + r["losses"], r["last"]["date"]), reverse=True)  # häufigste, dann jüngste


def fetch_opponents(cfg):
    items, page = [], 1
    while page <= 10:  # 20 pro Seite
        d = json.loads(get(f"{FIE}/api/fie/fencer/{cfg['fie_id']}/opponents?page={page}"))
        items += d.get("items", [])
        if not d.get("items") or len(items) >= d.get("totalFound", 0):
            break
        page += 1
    return parse_opponents(items, cfg["fie_id"])


DFB_NEWS = "https://www.fechten.org/news/listenansicht"


def parse_dfb_news(page):
    """Neueste Meldung der DFB-Nachrichtenliste (jüngstes Datum; angeheftete Topnews stehen nicht immer oben)."""
    def clean(x):
        return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", x or "")).split())
    items = []
    for chunk in page.split('news-list-item')[1:]:
        head = re.search(r'itemprop="headline">\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', chunk, re.S)
        when = re.search(r'datetime="(\d{4}-\d{2}-\d{2})"', chunk)
        if not head or not when:
            continue
        href = html.unescape(head.group(1))
        url = "https://www.fechten.org" + href if href.startswith("/") else href
        if not url.startswith("https://www.fechten.org/"):  # nur Links auf die DFB-Seite
            continue
        cat = re.search(r'<span class="label[^"]*">(.*?)</span>', chunk, re.S)
        lead = re.search(r'<div class="lead"[^>]*>(.*?)</div>', chunk, re.S)
        items.append({"date": when.group(1), "title": clean(head.group(2)), "url": url,
                      "category": clean(cat.group(1)) if cat else "", "teaser": clean(lead.group(1)) if lead else ""})
    if not items:
        raise ValueError("keine Meldungen gefunden, Seitenstruktur geändert?")
    return max(items, key=lambda i: i["date"])  # bei gleichem Datum gewinnt die erste in der Liste


def fetch_dfb_news(cfg):
    return parse_dfb_news(get(DFB_NEWS))


# ---------- DFB-Fotoarchiv ----------
# Nur Albumtitel + Datum (öffentlich auf fechten.org). Album-/Download-Links werden bewusst NICHT
# übernommen: Die Archiv-Nutzungsbedingungen (§ 4) verbieten ihre Veröffentlichung.
PHOTO_ARCHIVE = "https://www.fechten.org/service/foto-archiv/bilder/"


def parse_photo_albums(page):
    albums = []
    for chunk in page.split('news-list-item')[1:]:
        title = re.search(r'itemprop="headline">\s*<a[^>]*title="([^"]*)"', chunk)
        when = re.search(r'datetime="(\d{4}-\d{2}-\d{2})"', chunk)
        if title and when:
            albums.append({"title": " ".join(html.unescape(title.group(1)).split()), "date": when.group(1)})
    return albums


def fetch_photo_albums(cfg):
    return parse_photo_albums(get(PHOTO_ARCHIVE))


def _fold(s):
    """Kleinbuchstaben ohne Akzente/Umlaute, für robusten Ortsvergleich."""
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def match_album(album, item):
    """Passt ein Fotoalbum zu einem Turnier? Datum im Fenster, Ort im Titel, Waffe Florett oder nicht genannt."""
    try:
        a = date.fromisoformat(album["date"])
        start = date.fromisoformat(str(item["date"])[:10])
        end = date.fromisoformat(str(item.get("end") or item["date"])[:10])
    except (ValueError, KeyError):
        return False
    if not (start - timedelta(days=1) <= a <= end + timedelta(days=7)):
        return False
    title, city = _fold(album["title"]), _fold(item.get("city"))
    if not city or city not in title:
        return False
    weapons = ("degen", "sabel", "florett")
    named = [w for w in weapons if w in title]
    return not named or named == ["florett"]


def fetch_events(cfg):
    data = json.loads(get(f"{FIE}/api/fie/tournaments?upcoming=true&limit=100&sort=dateAsc"))
    events = []
    for t in data["items"]:
        if not (cfg["weapon"] in t["weapons"] and cfg["gender"] in t["genders"] and cfg["category"] in t["categories"]):
            continue
        if t["type"] == "Zone Championships" and "European" not in t["name"]:
            continue  # für GER nur die EM relevant
        q = urllib.parse.urlencode({"page": 1, "pageSize": 24, "search": cfg["fie_search"], "type": "I"})
        entries = json.loads(get(f"{FIE}/api/fie/tournaments/{t['id']}/event-entries?{q}")).get("entries", [])
        start = date.fromisoformat(t["startDate"])
        events.append({"key": f"fie-{t['id']}", "fie_id": t["id"], "date": t["startDate"], "end": t["endDate"],
                       "name": t["name"], "city": t["city"], "country": t["country"], "type": t["type"],
                       "entered": any(e["fencer"]["id"] == cfg["fie_id"] for e in entries),
                       "url": f"{FIE}/tournaments/{season_of(start)}/{t['id']}", "source": "FIE"})
    return events


# ---------- Zusammenbau ----------

def event_status(ev, manual):
    if ev.get("entered"):
        return "Gemeldet (FIE)"
    return manual.get("fie_status", {}).get(str(ev["fie_id"]), "Keine Meldung bekannt")


def build_state(cfg, manual, old, today, fetchers=None):
    f = {"ranking": fetch_ranking, "profile": fetch_profile, "events": fetch_events, "results": fetch_results,
         "field": fetch_field, "opponents": fetch_opponents, "dfb_news": fetch_dfb_news,
         "photo_albums": fetch_photo_albums, **(fetchers or {})}
    season, errors = season_of(today), []

    def attempt(label, fn):
        try:
            return fn()
        except Exception as e:  # Quelle down/geändert: alten Stand behalten, Fehler anzeigen
            errors.append(f"{label}: {e}")
            return None

    rank = attempt("FIE-Rangliste", lambda: f["ranking"](cfg, season))
    prof = attempt("FIE-Profil", lambda: f["profile"](cfg))
    events = attempt("FIE-Kalender", lambda: f["events"](cfg))
    more_results = attempt("FIE-Ergebnisse", lambda: f["results"](cfg, season))
    opponents = attempt("FIE-Gegnerinnen", lambda: f["opponents"](cfg))
    dfb_news = attempt("DFB-News", lambda: f["dfb_news"](cfg))
    new_albums = attempt("DFB-Fotoarchiv", lambda: f["photo_albums"](cfg))

    fie = dict(old.get("fie") or {}, season=season)
    if prof:
        fie.update(rank=prof["rank"], points=prof["points"], image=prof["image"], seasons=prof["seasons"])
    if rank and rank["rank"]:
        fie.update(rank=rank["rank"], points=rank["points"])
    if rank:
        fie["top_ger"] = rank["top_ger"]
        fie["breakdown"] = rank.get("breakdown", [])

    results = {r["key"]: r for r in old.get("results", []) if r.get("source") == "FIE"}
    for r in (prof or {}).get("results", []) + (more_results or []):
        prev = results.get(r["key"], {})
        pts = (rank or {}).get("comp_points", {}).get(f"{r['competition_id']}_{r['season']}") if r.get("category", "S") == "S" else None
        field = prev.get("field")
        if field is None:  # Teilnehmerzahl ändert sich nach dem Turnier nicht: nur einmal abrufen
            try:
                field = f["field"](r["season"], r["competition_id"])
            except Exception:  # Nebeninfo, kein Fehlerbanner; nächster Lauf versucht es erneut
                field = None
        results[r["key"]] = dict(r, points=pts if pts is not None else prev.get("points"), field=field)
    for m in manual.get("results", []):
        results[f"m-{m['date']}-{m['name']}"] = dict(m, key=f"m-{m['date']}-{m['name']}", source="Ophardt (manuell)")

    # Fotoalben sammeln (das Archiv zeigt nur die 12 neuesten) und passenden Ergebnissen zuordnen
    albums = {(a["title"], a["date"]): a for a in (old.get("photo_albums") or []) + (new_albums or [])}
    photo_albums = sorted(albums.values(), key=lambda a: a["date"], reverse=True)
    for k, r in results.items():
        hit = next((a for a in photo_albums if match_album(a, r)), None)
        if hit:
            results[k] = dict(r, photos=hit["title"])
        elif "photos" in r:
            results[k] = {x: v for x, v in r.items() if x != "photos"}

    fie_events = events if events is not None else [e for e in old.get("events", []) if e.get("source") == "FIE"]
    all_events = [dict(e, status=event_status(e, manual)) for e in fie_events]
    all_events += [dict(m, key=f"m-{m['date']}-{m['name']}", source="Ophardt (manuell)") for m in manual.get("events", [])]

    dfb = manual.get("dfb", {})
    # Vorheriger Stand je Rangliste: wird bei jeder Platz-/Punkteänderung durch den alten Stand ersetzt
    old_dfb, old_fie = old.get("dfb") or {}, old.get("fie") or {}
    changed = lambda o, n: o.get("rank") and (o.get("rank"), o.get("points")) != (n.get("rank"), n.get("points"))
    dfb_prev = ({k: old_dfb.get(k) for k in ("rank", "points", "calculated", "top10")}
                if changed(old_dfb, dfb) else old.get("dfb_prev"))
    fie_prev = ({"rank": old_fie.get("rank"), "points": old_fie.get("points"), "breakdown": old_fie.get("breakdown"),
                 "date": str(old.get("updated", ""))[:10]} if changed(old_fie, fie) else old.get("fie_prev"))

    return {
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "name": cfg["name"],
        "fie_id": cfg["fie_id"],
        "errors": errors,
        "fie": fie,
        "dfb": dfb,
        "dfb_prev": dfb_prev,
        "fie_prev": fie_prev,
        "explain": {"dfb": explain_dfb(dfb_prev, dfb), "fie": explain_fie(fie_prev, fie)},
        "results": sorted(results.values(), key=lambda r: str(r["date"]), reverse=True),
        "bouts": prof["bouts"] if prof else old.get("bouts", []),
        "opponents": opponents if opponents is not None else old.get("opponents", []),
        "dfb_news": dfb_news or old.get("dfb_news"),
        "photo_albums": photo_albums,
        "events": sorted(all_events, key=lambda e: e["date"]),
    }


# ---------- Änderungen ----------

def de(x):
    return f"{x:g}".replace(".", ",") if isinstance(x, (int, float)) else str(x)


def dmy(s):
    p = str(s).split("-")
    return ".".join(reversed(p)) if len(p) == 3 else str(s)


# ---------- Erläuterungen zu den Ranglisten (Aufklappmenü in den Karten oben) ----------
# Zeilen mit "– " am Anfang werden als Aufzählung dargestellt.

def _movement(o, n):
    """Kernsatz: Platz- und Punkteänderung, inkl. des scheinbaren Widerspruchs."""
    dr, dp = o["rank"] - n["rank"], round((n.get("points") or 0) - (o.get("points") or 0), 3)
    pts = f"{de(o.get('points'))} → {de(n.get('points'))} Punkte" + (f" ({'+' if dp > 0 else '−'}{de(abs(dp))})" if dp else "")
    head = f"Platz {o['rank']} → {n['rank']}, {pts}."
    if dr > 0 and dp < 0:
        why = "Weniger Punkte und trotzdem besser platziert: Konkurrentinnen vor ihr haben noch mehr Punkte verloren."
    elif dr < 0 and dp > 0:
        why = "Mehr Punkte und trotzdem schlechter platziert: Andere haben noch mehr Punkte hinzugewonnen."
    elif dr and not dp:
        why = "Ihre Punkte sind gleich geblieben; verschoben haben sich die Punkte der anderen."
    elif not dr and dp:
        why = "Der Platz ist gleich geblieben, nur die Punkte haben sich verändert."
    else:
        why = ""
    return [head] + ([why] if why else [])


def explain_dfb(prev, cur):
    if not cur.get("rank"):
        return []
    out = []
    if prev and prev.get("rank"):
        out.append(f"Seit der Berechnung vom {dmy(prev.get('calculated'))}:")
        out += _movement(prev, cur)
        old = {r["name"]: r for r in prev.get("top10") or []}
        new = {r["name"]: r for r in cur.get("top10") or []}
        is_me = lambda name: "gamke" in name.lower()
        for name, r in old.items():  # vorher vor ihr, jetzt hinter ihr
            if not is_me(name) and r["rank"] < prev["rank"] and (name not in new or new[name]["rank"] > cur["rank"]):
                now = f"{de(new[name]['points'])} Punkte" if name in new else "nicht mehr in den Top 10"
                out.append(f"– Überholt: {name} ({de(r['points'])} → {now})")
        for name, r in new.items():  # vorher hinter ihr, jetzt vor ihr
            if not is_me(name) and r["rank"] < cur["rank"] and (name not in old or old[name]["rank"] > prev["rank"]):
                before = f"{de(old[name]['points'])}" if name in old else "außerhalb der Top 10"
                out.append(f"– Vorbeigezogen: {name} ({before} → {de(r['points'])} Punkte)")
    out.append("So rechnet die DFB-Rangliste: Jedes Ergebnis zählt ein Jahr und fällt danach heraus, "
               "schwächere Ergebnisse können als Streichergebnis wegfallen. Punkte ändern sich deshalb "
               "bei jeder Neuberechnung, auch ohne neues Turnier.")
    if cur.get("calculated"):
        out.append(f"Aktueller Stand: berechnet am {dmy(cur['calculated'])} (Ophardt).")
    return out


def explain_fie(prev, cur):
    if not cur.get("rank"):
        return []
    out = []
    if prev and prev.get("rank"):
        out.append(f"Seit {prev['label']}:" if prev.get("label") else f"Seit dem {dmy(prev.get('date'))}:")
        out += _movement(prev, cur)
        ob = {b["key"]: b for b in prev.get("breakdown") or []}
        nb = {b["key"]: b for b in cur.get("breakdown") or []}
        if ob:
            out += [f"– Neu gewertet: {b['label']} (+{de(b['points'])})" for k, b in nb.items() if k not in ob and b["counted"]]
            out += [f"– Weggefallen: {b['label']} (−{de(b['points'])})" for k, b in ob.items() if k not in nb and b["counted"]]
            out += [f"– Jetzt Streichergebnis: {b['label']} ({de(b['points'])})" for k, b in nb.items()
                    if k in ob and ob[k]["counted"] and not b["counted"]]
    counted = [b for b in cur.get("breakdown") or [] if b["counted"]]
    dropped = [b for b in cur.get("breakdown") or [] if not b["counted"]]
    if counted:
        out.append("Aktuell gewertet:")
        out += [f"– {b['label']}: {de(b['points'])}" for b in counted]
    out += [f"– Streichergebnis, zählt nicht: {b['label']} ({de(b['points'])})" for b in dropped]
    out.append("So rechnet die FIE-Weltrangliste: Gewertet werden die Ergebnisse der letzten zwölf Monate. "
               "Die Punkte eines Turniers fallen weg, sobald es im neuen Jahr wieder ausgetragen wird. "
               "Es zählt nur eine begrenzte Zahl bester Ergebnisse, der Rest wird gestrichen.")
    return out


def rank_change(label, o, n):
    if not (o or {}).get("rank") or not (n or {}).get("rank"):
        return None
    if (o["rank"], o.get("points")) == (n["rank"], n.get("points")):
        return None
    arrow = "↑" if n["rank"] < o["rank"] else "↓" if n["rank"] > o["rank"] else "→"
    return (f"{label}: Platz {o['rank']} → {n['rank']} {arrow} "
            f"({de(o.get('points'))} → {de(n.get('points'))} Punkte)")


def diff(old, new):
    out = [c for c in (rank_change("FIE-Weltrangliste", old.get("fie"), new.get("fie")),
                       rank_change("DFB-Rangliste", old.get("dfb"), new.get("dfb"))) if c]

    old_r = {r["key"]: r for r in old.get("results", [])}
    # Ältere Ergebnisse, die erst jetzt mitgeladen werden (z. B. Vorsaison, U20), sind keine Neuigkeit
    cutoff = (date.fromisoformat(new.get("updated", "9999-12-31")[:10]) - timedelta(days=45)).isoformat()
    for r in new.get("results", []):
        o = old_r.get(r["key"])
        if o is None:
            if str(r["date"]) >= cutoff:
                out.append(f"Neues Ergebnis: {r['name']}: Platz {r['place']}")
        elif o.get("place") != r.get("place"):
            out.append(f"Ergebnis geändert: {r['name']}: Platz {o.get('place')} → {r.get('place')}")
        if r.get("photos") and r.get("photos") != (o or {}).get("photos") and str(r["date"]) >= cutoff:
            out.append(f"Neue Fotos im DFB-Fotoarchiv: {r['photos']} ({r['name']})")

    old_e = {e["key"]: e for e in old.get("events", [])}
    for e in new.get("events", []):
        o = old_e.get(e["key"])
        if o is None:
            out.append(f"Neuer Termin: {e['name']} ({dmy(e['date'])}), {e.get('status')}")
            continue
        if o.get("status") != e.get("status"):
            out.append(f"{e['name']}: {o.get('status')} → {e.get('status')}")
        if o.get("date") != e.get("date"):
            out.append(f"{e['name']} verschoben: {dmy(o['date'])} → {dmy(e['date'])}")
    return out


# ---------- Schreiben ----------

def append_history(path, state, today):
    rows = list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []
    last = {r["source"]: r for r in rows}
    new = []
    for src, d in (("FIE", state["fie"]), ("DFB", state["dfb"])):
        if d.get("rank") and (src not in last or (last[src]["rank"], last[src]["points"]) != (str(d["rank"]), str(d["points"]))):
            new.append({"date": today.isoformat(), "source": src, "rank": d["rank"], "points": d["points"]})
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["date", "source", "rank", "points"])
        if not rows:
            w.writeheader()
        w.writerows(new)


def ics(events, name, stamp):
    """Kalender-Abo (RFC 5545): ganztägige Termine, stabile UIDs, Status in der Beschreibung."""
    def esc(s):  # Steuerzeichen/CR raus (sonst ließen sich eigene Kalenderzeilen einschleusen), dann RFC-Escaping
        s = re.sub(r"[\x00-\x09\x0b-\x1f\x7f]", "", str(s or "").replace("\r\n", "\n").replace("\r", "\n"))
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    def fold(line):  # Zeilen > 75 Bytes umbrechen (Folgezeile beginnt mit Leerzeichen), Umlaute = 2 Bytes
        parts, cur = [], ""
        for ch in line:
            if len((cur + ch).encode()) > (75 if not parts else 74):
                parts.append(cur)
                cur = ""
            cur += ch
        return "\r\n ".join(parts + [cur])

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//fechten-dashboard//DE", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{esc(name)} Fechten", "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
             "X-PUBLISHED-TTL:PT12H"]
    for e in events:
        if "Nicht relevant" in str(e.get("status")):
            continue
        try:
            start = date.fromisoformat(str(e["date"]))
            end = date.fromisoformat(str(e.get("end") or e["date"]))
        except ValueError:
            continue
        url = str(e.get("url") or "")
        desc = f"Status: {e.get('status')}" + (f"\n{url}" if re.match(r"^https?://", url) else "")
        uid = re.sub(r"[^A-Za-z0-9-]+", "-", e["key"]).strip("-")
        lines += ["BEGIN:VEVENT", f"UID:{uid}@fechten-dashboard", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{start:%Y%m%d}", f"DTEND;VALUE=DATE:{end + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{esc(e['name'])}", f"LOCATION:{esc(e.get('city'))}", f"DESCRIPTION:{esc(desc)}",
                  "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    manual = json.loads((ROOT / "manual.json").read_text(encoding="utf-8"))
    DATA.mkdir(parents=True, exist_ok=True)
    state_path, changes_path = DATA / "state.json", DATA / "changes.json"
    old = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    today = date.today()

    new = build_state(cfg, manual, old, today)
    changes = diff(old, new) if old else ["Dashboard gestartet, ab jetzt werden Änderungen erfasst."]

    state_path.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    feed = json.loads(changes_path.read_text(encoding="utf-8")) if changes_path.exists() else []
    feed = [{"date": today.isoformat(), "text": c} for c in changes] + feed
    changes_path.write_text(json.dumps(feed, ensure_ascii=False, indent=1), encoding="utf-8")
    append_history(DATA / "history.csv", new, today)
    stamp = new["updated"][:16].replace("-", "").replace(":", "") + "00Z"  # 2026-11-16T11:32 -> 20261116T113200Z
    (DATA / "termine.ics").write_bytes(ics(new["events"], cfg["name"], stamp).encode("utf-8"))

    for c in changes:
        print("•", c)
    for e in new["errors"]:
        print("FEHLER", e)
    if changes and os.environ.get("GITHUB_OUTPUT"):
        # Texte stammen teils von fie.org: Zeilenumbrüche raus, Zufalls-Delimiter gegen Output-Injection
        delim = "EOF_" + secrets.token_hex(16)
        body = "\n".join("• " + " ".join(c.split()) for c in changes)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"changed=true\nbody<<{delim}\n{body}\n{delim}\n")


if __name__ == "__main__":
    main()
