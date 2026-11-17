"""Turnier-Tag-Benachrichtigung: läuft morgens per GitHub Actions (turniertag.yml).

Ist heute ein Wettkampftag, an dem Ella gemeldet ist, schreibt das Skript Betreff und Text für die Mail
nach $GITHUB_OUTPUT und merkt sich den Tag in docs/data/turniertag.json (damit nur eine Mail pro Tag kommt).

Welche Tage zählen:
- FIE-Turniere mit Meldung ("Gemeldet …" oder in der FIE-Meldeliste): erster Tag des Einzels (Damenflorett,
  Senioren); der Team-Tag nur, wenn der Status "Team" oder "Mannschaft" enthält. Link: Live-Seite des Wettbewerbs.
- Eigene Termine aus manual.json mit Status "Gemeldet …": jeder Tag von date bis end, oder nur die Tage in
  "days" (z. B. ["2026-12-05"]). Link: "live", sonst "url" des Termins.
"""
import json, os, secrets, sys
from datetime import date, datetime, timedelta
from pathlib import Path

from update import FIE, get

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "docs" / "data"
DASHBOARD = "https://cornellix.github.io/fechten-dashboard/"


def _days(start, end):
    d, e = date.fromisoformat(start), date.fromisoformat(end or start)
    while d <= e:
        yield d.isoformat()
        d += timedelta(days=1)


def todays_bouts(state, cfg, today, fetch=lambda tid: json.loads(get(f"{FIE}/api/fie/tournaments/{tid}"))):
    """[(Name, Wettbewerb, Link)] für heute; leer, wenn kein Turnier-Tag ist."""
    out = []
    for e in state.get("events", []):
        status = e.get("status") or ""
        if not (e.get("entered") or status.startswith("Gemeldet")) or not e["date"] <= today <= (e.get("end") or e["date"]):
            continue
        if e.get("source") != "FIE":
            if today in (e.get("days") or list(_days(e["date"], e.get("end")))):
                out.append((e["name"], "", e.get("live") or e.get("url") or DASHBOARD))
            continue
        team = any(w in status for w in ("Team", "Mannschaft"))
        tid = int(e["fie_id"])  # nur numerische IDs in URLs
        for c in fetch(tid).get("events", []):
            if (c["weapon"], c["gender"], c["category"]) != (cfg["weapon"], cfg["gender"], cfg["category"]):
                continue
            # ponytail: Einzel nur am ersten Tag (dort ficht Ella sicher); spätere Einzeltage erfordern das Weiterkommen
            if (today == c["startDate"]) if not c["isTeam"] else (team and today in _days(c["startDate"], c["endDate"])):
                out.append((e["name"], "Team" if c["isTeam"] else "Einzel",
                            f"{FIE}/tournaments/{int(c['season'])}/{tid}/event/{int(c['competitionId'])}"))
    return out


def message(bouts):
    lines = ["Turnier-Tag! Let's go, Ella!", ""]
    for name, kind, url in bouts:
        lines += [f"{name}{f' ({kind})' if kind else ''}", f"Direkt zum Turnier-Tag: {url}", ""]
    return "\n".join(lines + [f"Dashboard: {DASHBOARD}"])


if __name__ == "__main__":
    marker = DATA / "turniertag.json"
    # Testlauf für ein bestimmtes Datum: python turniertag.py 2026-12-11 (ohne Zeitfenster, ohne Merker)
    force = len(sys.argv) > 1
    if force:
        today = sys.argv[1]
    else:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/Berlin"))
        today = now.date().isoformat()
        sent = json.loads(marker.read_text(encoding="utf-8")).get("sent") if marker.exists() else None
        # Zwei Läufe am Morgen (Sommer-/Winterzeit, GitHub startet oft verspätet): der erste ab 8:30 Uhr sendet
        if sent == today or not "08:30" <= now.strftime("%H:%M") <= "12:00":
            print(f"Nichts zu tun ({now:%H:%M}, zuletzt gesendet {sent})")
            sys.exit(0)
    state = json.loads((DATA / "state.json").read_text(encoding="utf-8"))
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    bouts = todays_bouts(state, cfg, today)
    print(message(bouts) if bouts else f"{today}: kein Turnier-Tag")
    if bouts and not force:
        marker.write_text(json.dumps({"sent": today}) + "\n", encoding="utf-8")
    if bouts and os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"send=true\nbody<<EOF\n{message(bouts)}\nEOF\n")
