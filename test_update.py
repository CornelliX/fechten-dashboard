"""Schnelltest ohne Netz: python test_update.py"""
import json
from datetime import date

from update import match_album, parse_photo_albums, parse_dfb_news, build_state, diff, explain_dfb, explain_fie, ics, nuxt_queries, parse_opponents, season_of

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
        "results": lambda c, s, back=1: list(more),
        "field": lambda s, cid: field,
        "opponents": lambda c: [],
        "dfb_news": lambda c: {"date": "2026-11-16", "title": "T", "url": "https://www.fechten.org/n/t"},
        "photo_albums": lambda c: [],
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
ch = [c["text"] for c in diff(a, b)]
fie_c = next(c for c in diff(a, b) if c["text"].startswith("FIE"))
assert fie_c["url"].startswith("https://fie.org/athletes/detailed-ranking?season=2027&weapon=F"), fie_c
assert next(c for c in diff(a, b) if c["text"].startswith("Neues Ergebnis"))["url"] == "https://fie.org/athletes/1"
assert "FIE-Weltrangliste: Platz 312 → 290 ↑ (1,125 → 2 Punkte)" in ch, ch
assert "Neues Ergebnis: Weltcup Plovdiv: Platz 171" in ch, ch
assert "Shanghai World Cup 2026: Voranmeldung (Ophardt) → Gemeldet (FIE)" in ch, ch
assert not any("Tbilisi" in c for c in ch), ch
plov = next(r for r in b["results"] if r["key"] == "fie-2027-127")
u20 = next(r for r in b["results"] if r["key"] == "fie-2026-351-J")
assert plov["points"] == 0.25 and plov["field"] == 230 and u20["points"] is None

# 3. Manuelle DFB-Änderung + Quellen ausgefallen: alter FIE-Stand, Ergebnisse und Teilnehmerzahl bleiben
down = lambda *x: (_ for _ in ()).throw(OSError("down"))
broken = {k: down for k in ("ranking", "profile", "events", "results", "field", "opponents", "dfb_news", "photo_albums")}
c = build(dict(MANUAL, dfb={"rank": 5, "points": 60.75}), b, broken)
assert [x["text"] for x in diff(b, c)] == ["DFB-Rangliste: Platz 7 → 5 ↑ (48,25 → 60,75 Punkte)"], diff(b, c)
assert c["fie"]["rank"] == 290 and len(c["errors"]) == 7, c["errors"]
assert c["dfb_news"]["title"] == "T"  # alte Meldung bleibt bei Ausfall
assert next(r for r in c["results"] if r["key"] == "fie-2027-127")["field"] == 230

# 4. Saisonwechsel im August
assert season_of(date(2026, 7, 31)) == 2026 and season_of(date(2026, 8, 1)) == 2027

# 5. Nuxt/devalue-Dekoder
payload = [{"state": 1}, {"$svue-query": 2}, {"queries": 3}, [4], {"queryKey": 5, "state": 7},
           [12, 6], 60886, {"data": 8}, {"body": 9}, ["Reactive", 10], {"rank": 11}, 312, "fencers"]
html = f'<script type="application/json" id="__NUXT_DATA__">{json.dumps(payload)}</script>'
assert nuxt_queries(html) == {'["fencers", 60886]': {"rank": 312}}

# 6. Gegnerbilanz aus Ellas Sicht (Ella mal fencer1, mal fencer2)
def bout(d, me_score, other_score, me_first=True, name="Coupe du Monde "):
    me = {"id": 1, "score": me_score, "isWinner": me_score > other_score}
    other = {"id": 9, "score": other_score, "isWinner": other_score > me_score}
    f1, f2 = (me, other) if me_first else (other, me)
    return {"name": name, "date": f"{d} 00:00:00", "location": "Plovdiv", "category": "S",
            "fencer1": f1, "fencer2": f2}
opp = parse_opponents([{"id": 9, "name": "AUDIBERT  Alicia", "flag": "fra",
                        "events": [bout("2026-11-12", 5, 4), bout("2026-11-12", 4, 15, me_first=False, name="Coupe du monde")]}], 1)
# gleicher Tag: das K.-o.-Gefecht (4:15) zählt als letztes, auch wenn FIE die Vorrunde danach listet
assert opp == [{"id": 9, "name": "AUDIBERT Alicia", "nat": "FRA", "wins": 1, "losses": 1,
                "last": {"date": "2026-11-12", "win": False, "score": "4:15", "event": "Weltcup Plovdiv"}}], opp

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

# 8. Erläuterungen: echter Fall DFB 19.10. -> 15.11.2026 (weniger Punkte, trotzdem einen Platz besser)
T = lambda *rows: [{"rank": i + 1, "name": n, "points": p} for i, (n, p) in enumerate(rows)]
dfb_old = {"rank": 7, "points": 48.25, "calculated": "2026-10-19",
           "top10": T(("Morandi", 160.5), ("Ebert", 76.25), ("Höfler", 67.75), ("Anne Kleibrink", 65), ("Kirschen", 55.75),
                      ("Kothieringer", 51), ("Ella Gamke", 48.25), ("Hohenadel", 38), ("Herwig", 38), ("Kirsch", 36.25))}
dfb_new = {"rank": 6, "points": 47.25, "calculated": "2026-11-15",
           "top10": T(("Morandi", 163), ("Ebert", 101.25), ("Höfler", 68), ("Kirschen", 56), ("Kothieringer", 53.75),
                      ("Ella Gamke", 47.25), ("Anne Kleibrink", 45), ("Seiffert", 41.75), ("Herwig", 38.25), ("Kirsch", 36.25))}
ex = explain_dfb(dfb_old, dfb_new)
assert ex[1] == "Platz 7 → 6, 48,25 → 47,25 Punkte (−1)." and "Konkurrentinnen vor ihr" in ex[2], ex
assert "– Überholt: Anne Kleibrink (65 → 45 Punkte)" in ex and not any("Vorbeigezogen" in x for x in ex), ex

# Vorheriger Stand wird beim Wechsel gemerkt und bleibt sonst erhalten
s1 = build(dict(MANUAL, dfb=dfb_old), {}, fake())
s2 = build(dict(MANUAL, dfb=dfb_new), s1, fake())
s3 = build(dict(MANUAL, dfb=dfb_new), s2, fake())
assert s2["dfb_prev"]["rank"] == 7 and s3["dfb_prev"]["rank"] == 7 and "Überholt" in " ".join(s3["explain"]["dfb"])

ef = explain_fie({"rank": 341, "points": 0.625, "label": "Saisonabschluss 2025/26",
                  "breakdown": [{"key": "458_2026", "label": "Grand Prix Turin 2026", "points": 0.375, "counted": True}]},
                 {"rank": 312, "points": 1.125, "breakdown": [
                     {"key": "458_2026", "label": "Grand Prix Turin 2026", "points": 0.375, "counted": True},
                     {"key": "127_2027", "label": "Weltcup Plovdiv 2026", "points": 0.25, "counted": True},
                     {"key": "118_2026", "label": "Weltcup Hong Kong 2026", "points": 8.0, "counted": False}]})
assert ef[0] == "Seit Saisonabschluss 2025/26:" and "– Neu gewertet: Weltcup Plovdiv 2026 (+0,25)" in ef, ef
assert "– Streichergebnis, zählt nicht: Weltcup Hong Kong 2026 (8)" in ef, ef

# 9. DFB-News: jüngstes Datum gewinnt (auch wenn angeheftete Topnews oben steht), fremde Links ignoriert
def item(d, href, title, cls=""):
    return (f'<div class="row news-list-item mb-3"><div class="col-md-9 {cls}"><h3 itemprop="headline">'
            f'<a itemprop="url" href="{href}">\n {title}\n</a></h3><time datetime="{d}">x</time>'
            f'<span class="label label-info">Sport</span><div class="lead"><p>Kurz &amp; gut…</p></div></div></div>')
page = (item("2026-10-01", "/n/alt", "Alte Topnews", "topnews") + item("2026-11-16", "/n/neu", "Neu &quot;heute&quot;")
        + item("2026-12-31", "https://evil.example/x", "Fremd"))
n = parse_dfb_news(page)
assert n == {"date": "2026-11-16", "title": 'Neu "heute"', "url": "https://www.fechten.org/n/neu",
             "category": "Sport", "teaser": "Kurz & gut…"}, n

# 10. DFB-Fotoarchiv: Titel+Datum ohne Links, Zuordnung über Datum, Ort und Waffe
arch = ('<div class="news-list-item"><h3 itemprop="headline"><a itemprop="url" title="Weltcup Plovdiv Florett" '
        'target="_blank" href="https://pfm-archiv.quickconnect.to/mo/sharing/x"></a></h3><time datetime="2026-11-12">x</time></div>'
        '<div class="news-list-item"><h3 itemprop="headline"><a title="Weltcup Bern Herrendegen" href="h"></a></h3>'
        '<time datetime="2026-11-12">x</time></div>')
albums = parse_photo_albums(arch)
assert albums == [{"title": "Weltcup Plovdiv Florett", "date": "2026-11-12"},
                  {"title": "Weltcup Bern Herrendegen", "date": "2026-11-12"}], albums
assert "quickconnect" not in json.dumps(albums)
plov_r = {"date": "2026-11-12", "city": "Plovdiv"}
assert match_album(albums[0], plov_r)
assert not match_album(albums[1], plov_r)                                        # andere Stadt
assert not match_album(albums[0], {"date": "2026-11-12", "city": "Shanghai"})    # anderer Ort
assert not match_album({"title": "Weltcup Plovdiv Florett", "date": "2026-12-03"}, plov_r)  # 3 Wochen später
assert not match_album({"title": "Weltcup Plovdiv Herrensäbel", "date": "2026-11-13"}, plov_r)  # andere Waffe
assert match_album({"title": "Weltcup Plovdiv", "date": "2026-11-14"}, plov_r)   # ohne Waffe im Titel
assert match_album({"title": "QB Künzelsau", "date": "2026-10-24"}, {"date": "2026-10-24", "city": "Kunzelsau"})

# Zuordnung im State + genau ein News-Eintrag, beim nächsten Lauf keiner mehr
PLOV = dict(PLOVDIV, city="Plovdiv")
f_ph = dict(fake(results=[PLOV]), photo_albums=lambda c: albums)
p1 = build(MANUAL, {}, fake(results=[PLOV]))
p2 = build(MANUAL, p1, f_ph)
assert next(r for r in p2["results"] if r["key"] == "fie-2027-127")["photos"] == "Weltcup Plovdiv Florett"
assert diff(p1, p2) == [{"text": "Neue Fotos im DFB-Fotoarchiv: Weltcup Plovdiv Florett",
                         "url": "https://www.fechten.org/service/foto-archiv"}], diff(p1, p2)  # keine Dopplung
p3 = build(MANUAL, p2, dict(f_ph, photo_albums=lambda c: []))  # Album nicht mehr unter den 12 neuesten
assert diff(p2, p3) == [] and len(p3["photo_albums"]) == 2

print("ok")

# Laufbahn: ohne ältere FIE-Ergebnisse im State wird weiter zurück geladen, danach nur zwei Saisons
calls = []
f_back = dict(fake(), results=lambda c, s, back=1: calls.append(back) or [])
build(MANUAL, {}, f_back)
build(MANUAL, {"results": [{"key": "fie-2024-1-J", "source": "FIE", "season": 2024, "date": "2023-11-04",
                            "name": "Weltcup Istanbul (U20)", "place": 99}]}, f_back)
assert calls == [4, 1], calls
print("ok")

# Ophardt-Biografie-Import
import ophardt_bio
BIO = '''---
source: "https://fencing.ophardt.online/en/biography/athlete/1"
---
### Medals
<table><thead><tr><th colspan="3">National Championships</th></tr><tr><th>g</th><th>s</th><th>b</th></tr></thead><tbody><tr><td>7</td><td>0</td><td>0</td></tr></tbody></table>
|  | Apr 17, 2016 | Turnierreifeprüfung |  |
### Results
##### National Championships
<table><thead><tr><th>Rank</th><th>Date</th><th colspan="4">Competition</th></tr></thead><tbody><tr><td>1</td><td>5/7/22 / 5/8/22</td><td><a href="x">Winsen Luhe</a></td><td>German Championships</td><td>Foil Women's U17 Individual</td></tr><tr><td>1</td><td>6/27/26 / 6/28/26</td><td>Koblenz</td><td>German Team Championships</td><td>Foil Women's Senior Team</td></tr></tbody></table>
### Rankings
#### National
<table><tbody><tr><td>5</td><td>62.2500</td><td>2025</td><td>Deutsche Rangliste</td><td>Foil Senior Individual</td></tr><tr><td>5</td><td>62.2500</td><td>2025</td><td>Deutsche Rangliste</td><td>Foil Senior Individual</td></tr></tbody></table>
'''
b = ophardt_bio.parse(BIO)
assert b["medals"]["national"] == [7, 0, 0] and b["exam"] == "2016-04-17", b
assert [(r["date"], r["rank"], r["age"], r["type"]) for r in b["results"]] == \
    [("2026-06-27", 1, "Senior", "Mannschaft"), ("2022-05-07", 1, "U17", "Einzel")], b["results"]
assert b["rankings"] == [{"level": "National", "rank": 5, "points": 62.25, "season": 2025,
                          "title": "Deutsche Rangliste", "weapon": "Florett", "age": "Senior"}], b["rankings"]
print("ok")

# Deutsche Ophardt-Seite: deutsche Abschnitte/Daten, Turniernamen bekommen deutschen Anzeigenamen
BIO_DE = """---
source: "https://fencing.ophardt.online/de/biography/athlete/1"
---
### Medaillen
<table><thead><tr><th colspan="3">Nationale Meisterschaft</th></tr><tr><th>g</th><th>s</th><th>b</th></tr></thead><tbody><tr><td>7</td><td>0</td><td>0</td></tr></tbody></table>
|  | 17.04.2016 | Turnierreifeprüfung (Deutscher Fechter-Bund e.V.) |  |
### Ergebnisse
##### Nationale Meisterschaft
<table><tbody><tr><td>1</td><td>07.05.22 / 08.05.22</td><td>Winsen Luhe</td><td>German Championships</td><td>Florett Damen U17 Einzel</td></tr></tbody></table>
##### Regionale Turniere
<table><tbody><tr><td>2</td><td>02.04.22 / 03.04.22</td><td>Schkeuditz</td><td>Tournament of the Airport</td><td>Florett Damen U17 Einzel</td></tr><tr><td>1</td><td>17.03.18</td><td>Altenburg</td><td>Cup Wenzel</td><td>Florett Damen U12 Einzel</td></tr></tbody></table>
"""
d = ophardt_bio.parse(BIO_DE)
assert d["medals"]["national"] == [7, 0, 0] and d["exam"] == "2016-04-17", d
assert sorted((r["date"], r["section"], r["age"], r["type"]) for r in d["results"]) == [
    ("2018-03-17", "Regional Tournaments", "U12", "Einzel"), ("2022-04-02", "Regional Tournaments", "U17", "Einzel"),
    ("2022-05-07", "National Championships", "U17", "Einzel")], d["results"]
assert {r["name"] for r in d["results"]} == {"Flughafen-Turnier", "Deutsche Meisterschaft", "Wenzel-Cup"}, d["results"]
assert all(r["section"] in ("National Championships", "Regional Tournaments") for r in d["results"])
print("ok")
