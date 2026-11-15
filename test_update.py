"""Schnelltest ohne Netz: python test_update.py"""
import json
from datetime import date

from update import build_state, diff, nuxt_queries, season_of

CFG = {"name": "Ella Gamke", "fie_id": 1, "fie_search": "X", "weapon": "F", "gender": "F", "category": "S"}
MANUAL = {"dfb": {"rank": 7, "points": 48.25}, "fie_status": {"131": "Voranmeldung (Ophardt)"},
          "events": [{"date": "2026-12-05", "name": "Händel-Cup", "status": "Gemeldet"}], "results": []}


def fake(rank=312, points=1.125, entered=False, results=()):
    return {
        "ranking": lambda c, s: {"rank": rank, "points": points, "comp_points": {"127_2027": 0.25}, "top_ger": []},
        "profile": lambda c: {"rank": rank, "points": points, "image": None, "seasons": [], "bouts": [],
                              "results": list(results)},
        "events": lambda c: [{"key": "fie-131", "fie_id": 131, "date": "2026-12-10", "end": "2026-12-13",
                              "name": "Shanghai World Cup 2026", "entered": entered, "source": "FIE"}],
    }


PLOVDIV = {"key": "fie-2027-127", "date": "2026-11-12", "name": "Weltcup Plovdiv", "place": 171,
           "season": 2027, "competition_id": 127, "source": "FIE"}
TODAY = date(2026, 11, 16)

# 1. Gleicher Stand -> keine Änderungen (kein Rauschen)
a = build_state(CFG, MANUAL, {}, TODAY, fake())
assert diff(a, build_state(CFG, MANUAL, a, TODAY, fake())) == []
assert [e["status"] for e in a["events"]] == ["Gemeldet", "Voranmeldung (Ophardt)"]

# 2. Ranglistenwechsel, neues Ergebnis (mit Punkten), Meldestatus
b = build_state(CFG, MANUAL, a, TODAY, fake(rank=290, points=2.0, entered=True, results=[PLOVDIV]))
ch = diff(a, b)
assert "FIE-Weltrangliste: Platz 312 → 290 ↑ (1,125 → 2 Punkte)" in ch, ch
assert "Neues Ergebnis: Weltcup Plovdiv: Platz 171" in ch, ch
assert "Shanghai World Cup 2026: Voranmeldung (Ophardt) → Gemeldet (FIE)" in ch, ch
assert b["results"][0]["points"] == 0.25

# 3. Manuelle DFB-Änderung + Quelle ausgefallen: alter FIE-Stand und Ergebnisse bleiben
broken = {k: (lambda *x: (_ for _ in ()).throw(OSError("down"))) for k in ("ranking", "profile", "events")}
c = build_state(CFG, dict(MANUAL, dfb={"rank": 5, "points": 60.75}), b, TODAY, broken)
assert diff(b, c) == ["DFB-Rangliste: Platz 7 → 5 ↑ (48,25 → 60,75 Punkte)"], diff(b, c)
assert c["fie"]["rank"] == 290 and len(c["errors"]) == 3 and c["results"][0]["key"] == "fie-2027-127"

# 4. Saisonwechsel im August
assert season_of(date(2026, 7, 31)) == 2026 and season_of(date(2026, 8, 1)) == 2027

# 5. Nuxt/devalue-Dekoder
payload = [{"state": 1}, {"$svue-query": 2}, {"queries": 3}, [4], {"queryKey": 5, "state": 7},
           [12, 6], 60886, {"data": 8}, {"body": 9}, ["Reactive", 10], {"rank": 11}, 312, "fencers"]
html = f'<script type="application/json" id="__NUXT_DATA__">{json.dumps(payload)}</script>'
assert nuxt_queries(html) == {'["fencers", 60886]': {"rank": 312}}

print("ok")
