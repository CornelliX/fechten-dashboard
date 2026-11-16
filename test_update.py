"""Schnelltest ohne Netz: python test_update.py"""
import json
from datetime import date

from update import build_state, diff, ics, nuxt_queries, parse_opponents, season_of

CFG = {"name": "Ella Gamke", "fie_id": 1, "fie_search": "X", "weapon": "F", "gender": "F", "category": "S"}
MANUAL = {"dfb": {"rank": 7, "points": 48.25}, "fie_status": {"131": "Voranmeldung (Ophardt)"},
          "events": [{"date": "2026-12-05", "name": "Händel-Cup", "status": "Gemeldet"}], "results": []}
NOW = "2026-11-16T05:00+00:00"  # fester Zeitstempel, damit die 45-Tage-Regel nicht von der Uhr abhängt


def fake(rank=312, points=1.125, entered=False, results=(), more=(), field=230):
    return {
        "ranking": lambda c, s: {"rank": rank, "points": points, "comp_points": {"127_2027": 0.25}, "top_ger": []},
        "profile": lambda c: {"rank": rank, "points": points, "image": None, "seasons": [], "bouts": [],
                              "results": list(results)},
        "events": lambda c: [{"key": "fie-131", "fie_id": 131, "date": "2026-12-10", "end": "2026-12-13",
                              "name": "Shanghai World Cup 2026", "entered": entered, "source": "FIE"}],
        "results": lambda c, s: list(more),
        "field": lambda s, cid: field,
        "opponents": lambda c: [],
    }


def build(manual, old, f):
    return dict(build_state(CFG, manual, old, TODAY, f), updated=NOW)


PLOVDIV = {"key": "fie-2027-127", "date": "2026-11-12", "name": "Weltcup Plovdiv", "place": 171,
           "season": 2027, "competition_id": 127, "category": "S", "source": "FIE"}
OLD_U20 = {"key": "fie-2026-351-J", "date": "2026-02-24", "name": "EM Tbilisi (U20)", "place": 12,
           "season": 2026, "competition_id": 351, "category": "J", "source": "FIE"}
TODAY = date(2026, 11, 16)

# 1. Gleicher Stand -> keine Änderungen (kein Rauschen)
a = build(MANUAL, {}, fake())
assert diff(a, build(MANUAL, a, fake())) == []
assert [e["status"] for e in a["events"]] == ["Gemeldet", "Voranmeldung (Ophardt)"]

# 2. Ranglistenwechsel, neues Ergebnis (mit Punkten + Teilnehmerzahl), Meldestatus;
#    älteres, erst jetzt mitgeladenes U20-Ergebnis erscheint nicht im Feed
b = build(MANUAL, a, fake(rank=290, points=2.0, entered=True, results=[PLOVDIV], more=[OLD_U20]))
ch = diff(a, b)
assert "FIE-Weltrangliste: Platz 312 → 290 ↑ (1,125 → 2 Punkte)" in ch, ch
assert "Neues Ergebnis: Weltcup Plovdiv: Platz 171" in ch, ch
assert "Shanghai World Cup 2026: Voranmeldung (Ophardt) → Gemeldet (FIE)" in ch, ch
assert not any("Tbilisi" in c for c in ch), ch
plov = next(r for r in b["results"] if r["key"] == "fie-2027-127")
u20 = next(r for r in b["results"] if r["key"] == "fie-2026-351-J")
assert plov["points"] == 0.25 and plov["field"] == 230 and u20["points"] is None

# 3. Manuelle DFB-Änderung + Quellen ausgefallen: alter FIE-Stand, Ergebnisse und Teilnehmerzahl bleiben
down = lambda *x: (_ for _ in ()).throw(OSError("down"))
broken = {k: down for k in ("ranking", "profile", "events", "results", "field", "opponents")}
c = build(dict(MANUAL, dfb={"rank": 5, "points": 60.75}), b, broken)
assert diff(b, c) == ["DFB-Rangliste: Platz 7 → 5 ↑ (48,25 → 60,75 Punkte)"], diff(b, c)
assert c["fie"]["rank"] == 290 and len(c["errors"]) == 5, c["errors"]
assert next(r for r in c["results"] if r["key"] == "fie-2027-127")["field"] == 230

# 4. Saisonwechsel im August
assert season_of(date(2026, 7, 31)) == 2026 and season_of(date(2026, 8, 1)) == 2027

# 5. Nuxt/devalue-Dekoder
payload = [{"state": 1}, {"$svue-query": 2}, {"queries": 3}, [4], {"queryKey": 5, "state": 7},
           [12, 6], 60886, {"data": 8}, {"body": 9}, ["Reactive", 10], {"rank": 11}, 312, "fencers"]
html = f'<script type="application/json" id="__NUXT_DATA__">{json.dumps(payload)}</script>'
assert nuxt_queries(html) == {'["fencers", 60886]': {"rank": 312}}

# 6. Gegnerbilanz aus Ellas Sicht (Ella mal fencer1, mal fencer2)
def bout(d, me_score, other_score, me_first=True):
    me = {"id": 1, "score": me_score, "isWinner": me_score > other_score}
    other = {"id": 9, "score": other_score, "isWinner": other_score > me_score}
    f1, f2 = (me, other) if me_first else (other, me)
    return {"name": "Coupe du Monde ", "date": f"{d} 00:00:00", "location": "Plovdiv", "category": "S",
            "fencer1": f1, "fencer2": f2}
opp = parse_opponents([{"id": 9, "name": "AUDIBERT  Alicia", "flag": "fra",
                        "events": [bout("2026-11-12", 5, 4), bout("2026-11-13", 4, 15, me_first=False)]}], 1)
assert opp == [{"id": 9, "name": "AUDIBERT Alicia", "nat": "FRA", "wins": 1, "losses": 1,
                "last": {"date": "2026-11-13", "win": False, "score": "4:15", "event": "Weltcup Plovdiv"}}], opp

# 7. Kalenderdatei: ganztägig, Ende exklusiv, Sonderzeichen escaped, "Nicht relevant" ausgelassen
cal = ics([{"key": "fie-131", "date": "2026-12-10", "end": "2026-12-13", "name": "Shanghai, World Cup",
            "city": "Shanghai", "status": "Gemeldet"},
           {"key": "m-x", "date": "2027-04-03", "name": "Veteranen", "status": "Nicht relevant"}],
          "Ella Gamke", "20261116T050000Z")
assert "DTSTART;VALUE=DATE:20261210\r\nDTEND;VALUE=DATE:20261214" in cal
assert "SUMMARY:Shanghai\\, World Cup" in cal and "Veteranen" not in cal and cal.endswith("END:VCALENDAR\r\n")
assert all(len(line.encode()) <= 75 for line in cal.split("\r\n"))
evil = ics([{"key": "x", "date": "2026-12-05", "name": "A\r\nBEGIN:VEVENT\x00", "status": "s",
             "url": "javascript:alert(1)"}], "E", "S")
assert evil.split("\r\n").count("BEGIN:VEVENT") == 1 and "\x00" not in evil and "javascript" not in evil, evil
long = ics([{"key": "m-ä ö", "date": "2026-12-05", "name": "Händel-Cup " * 12, "status": "x"}], "E", "S")
assert all(len(line.encode()) <= 75 for line in long.split("\r\n")) and "UID:m@fechten-dashboard" in long, long

print("ok")
