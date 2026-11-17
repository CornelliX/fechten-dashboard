"""Jahresbilanz für die Silvesterseite (docs/silvester.html): python jahresbilanz.py [Jahr] [--silvester]

Schreibt docs/data/jahresbilanz.json ({"2026": {...}}, ältere Jahre bleiben erhalten).
Gefechte nur von FIE-Turnieren (nationale Einzelgefechte gibt es nirgends maschinenlesbar),
Platzierungen aus der Ophardt-Laufbahn plus neueren FIE-Ergebnissen, Ranglisten aus history.csv.
"""
import csv, json, os, secrets, sys
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent / "docs" / "data"


def _score(b):
    me, other = (int(x) for x in b["score"].split(":"))
    return me - other, -other  # größte Differenz; bei Gleichstand weniger Gegentreffer (5:0 vor 15:10)


def bilanz(state, laufbahn, history, jahr):
    y = str(jahr)
    bouts = [dict(b, opponent=o["name"], nat=o["nat"]) for o in state.get("opponents", [])
             for b in o.get("bouts", []) if b["date"].startswith(y)]
    wins = [b for b in bouts if b["win"] and all(x.isdigit() for x in b["score"].split(":"))]
    top = max(wins, key=_score, default=None)

    # Platzierungen: Laufbahn (mit Bereich und Einzel/Mannschaft) + FIE-Ergebnisse, die nach dem Import kamen
    rows = [{"date": r["date"], "place": r["rank"], "team": r["type"] != "Einzel",
             "national": r["section"].startswith("National"), "name": r["name"], "city": r.get("city", "")}
            for r in laufbahn.get("results", []) if r["date"].startswith(y) and r.get("rank")]
    known = {(r["date"], r["team"]) for r in rows}
    rows += [{"date": r["date"], "place": r["place"], "team": False, "national": False, "name": r["name"], "city": ""}
             for r in state.get("results", []) if r.get("source") == "FIE" and r["date"].startswith(y)
             and (r["date"], False) not in known]
    # schönere Namen aus dem Dashboard (z. B. "Turnier Dörnigheim" statt "Internationales Turnier")
    names = {(r["date"], "Mannschaft" in r["name"]): r["name"] for r in state.get("results", [])}
    for r in rows:
        r["name"] = names.get((r["date"], r["team"])) or " ".join(x for x in (r["name"], r["city"]) if x)
        del r["city"]

    def best(national):
        c = [r for r in rows if not r["team"] and r["national"] == national]
        b = min(c, key=lambda r: (r["place"], [-int(x) for x in r["date"].split("-")]), default=None)
        return b and {k: b[k] for k in ("date", "place", "name")}  # bei Gleichstand das jüngere

    def best_rank(source):
        ranks = [int(h["rank"]) for h in history if h["source"] == source and h["date"].startswith(y) and h["rank"]]
        return min(ranks, default=None)

    return {
        "year": jahr,
        "bouts": len(bouts), "wins": len(wins),
        "tournaments": len({(b["date"], b["event"]) for b in bouts}),
        "top_win": top and {k: top[k] for k in ("score", "opponent", "nat", "event", "date")},
        "best_national": best(True), "best_international": best(False),
        "team": sorted(({k: r[k] for k in ("date", "place", "name")} for r in rows if r["team"] and r["place"] <= 3),
                       key=lambda r: (r["place"], r["date"])),
        "dfb_rank": best_rank("DFB"), "fie_rank": best_rank("FIE"),
    }


def silvester_news(feed, jahr, base):
    """News-Eintrag zur Silvesterseite vorn in den Feed; zweiter Aufruf ändert nichts (False)."""
    url = f"{base}silvester.html?jahr={jahr}"
    if any(c.get("url") == url for c in feed):
        return feed, False
    return [{"date": f"{jahr}-12-31", "text": f"Ellas Fecht-Jahr {jahr}: Die Jahresbilanz ist da!", "url": url}] + feed, True


if __name__ == "__main__":
    # python jahresbilanz.py [Jahr]          Bilanz berechnen und speichern (Vorschau)
    # python jahresbilanz.py --silvester     wie oben fürs aktuelle Jahr + News + Benachrichtigungstext (silvester.yml)
    silvester = "--silvester" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    jahr = int(args[0]) if args else date.today().year
    load = lambda n: json.loads((DATA / n).read_text(encoding="utf-8"))
    with open(DATA / "history.csv", encoding="utf-8") as f:
        history = list(csv.DictReader(f))
    out = DATA / "jahresbilanz.json"
    alle = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    alle[str(jahr)] = bilanz(load("state.json"), load("laufbahn.json"), history, jahr)
    out.write_text(json.dumps(alle, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(alle[str(jahr)], ensure_ascii=False, indent=1))
    if silvester:
        from turniertag import DASHBOARD
        feed, neu = silvester_news(load("changes.json"), jahr, DASHBOARD)
        (DATA / "changes.json").write_text(json.dumps(feed, ensure_ascii=False, indent=1), encoding="utf-8")
        # Benachrichtigung nur beim ersten Lauf (der News-Eintrag ist zugleich der Merker)
        if neu and os.environ.get("GITHUB_OUTPUT"):
            b, link = alle[str(jahr)], feed[0]["url"]
            push = f"{b['wins']} von {b['bouts']} internationalen Gefechten gewonnen. Prost auf {jahr + 1}!"
            body = f"Ellas Fecht-Jahr {jahr}: Die Jahresbilanz ist da!\n\n{link}\n\nDashboard: {DASHBOARD}"
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                delim = f"EOF_{secrets.token_hex(16)}"
                f.write(f"send=true\nlink={link}\npush={push}\nbody<<{delim}\n{body}\n{delim}\n")
