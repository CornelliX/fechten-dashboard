#!/usr/bin/env python3
"""Ellas Fecht-Dashboard: holt FIE-Daten, mischt manual.json (Ophardt) ein,
erkennt Änderungen und schreibt docs/data/{state.json, changes.json, history.csv}.
Nur Standardbibliothek. Aufruf: python update.py"""
import csv
import json
import os
import re
import secrets
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "docs" / "data"
FIE = "https://fie.org"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; fencing-dashboard/1.0)"}
TYPE_DE = {"World Cup": "Weltcup", "World Championship": "WM", "Zone Championships": "Zonen-Meisterschaft",
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
    comp_points = {k: float(v.strip("()")) for k, v in (me or {}).get("competitionPoints", {}).items()}
    return {
        "rank": me and me["rank"],
        "points": me and float(me["points"]),
        "comp_points": comp_points,
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
        "results": [{"key": f"fie-{x['season']}-{x['competitionId']}", "date": x["date"],
                     "name": f"{TYPE_DE.get(x['competitionType'], x['competitionType'])} {x['city']}",
                     "city": x["city"], "place": x["place"], "season": x["season"],
                     "competition_id": x["competitionId"], "source": "FIE"} for x in results],
        "bouts": [{"date": b["date"][:10], "event": f"{TYPE_DE.get(b['name'], b['name'])} {b['location']}",
                   "win": b["isWinner"], "score": f"{b['score']['fencer']}:{b['score']['opponent']}",
                   "opponent": " ".join(b["opponent"]["name"].split()), "nat": b["opponent"]["nationality"]}
                  for b in bouts],
    }


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
    f = fetchers or {"ranking": fetch_ranking, "profile": fetch_profile, "events": fetch_events}
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

    fie = dict(old.get("fie") or {}, season=season)
    if prof:
        fie.update(rank=prof["rank"], points=prof["points"], image=prof["image"], seasons=prof["seasons"])
    if rank and rank["rank"]:
        fie.update(rank=rank["rank"], points=rank["points"])
    if rank:
        fie["top_ger"] = rank["top_ger"]

    results = {r["key"]: r for r in old.get("results", []) if r.get("source") == "FIE"}
    for r in (prof or {}).get("results", []):
        pts = (rank or {}).get("comp_points", {}).get(f"{r['competition_id']}_{r['season']}")
        results[r["key"]] = dict(r, points=pts if pts is not None else results.get(r["key"], {}).get("points"))
    for m in manual.get("results", []):
        results[f"m-{m['date']}-{m['name']}"] = dict(m, key=f"m-{m['date']}-{m['name']}", source="Ophardt (manuell)")

    fie_events = events if events is not None else [e for e in old.get("events", []) if e.get("source") == "FIE"]
    all_events = [dict(e, status=event_status(e, manual)) for e in fie_events]
    all_events += [dict(m, key=f"m-{m['date']}-{m['name']}", source="Ophardt (manuell)") for m in manual.get("events", [])]

    return {
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "name": cfg["name"],
        "fie_id": cfg["fie_id"],
        "errors": errors,
        "fie": fie,
        "dfb": manual.get("dfb", {}),
        "results": sorted(results.values(), key=lambda r: str(r["date"]), reverse=True),
        "bouts": prof["bouts"] if prof else old.get("bouts", []),
        "events": sorted(all_events, key=lambda e: e["date"]),
    }


# ---------- Änderungen ----------

def de(x):
    return f"{x:g}".replace(".", ",") if isinstance(x, (int, float)) else str(x)


def dmy(s):
    p = str(s).split("-")
    return ".".join(reversed(p)) if len(p) == 3 else str(s)


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
    for r in new.get("results", []):
        o = old_r.get(r["key"])
        if o is None:
            out.append(f"Neues Ergebnis: {r['name']}: Platz {r['place']}")
        elif o.get("place") != r.get("place"):
            out.append(f"Ergebnis geändert: {r['name']}: Platz {o.get('place')} → {r.get('place')}")

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
