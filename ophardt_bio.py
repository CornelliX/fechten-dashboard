"""Ophardt-Biografie (als Markdown-Clip gespeichert) -> docs/data/laufbahn.json

Aufruf:  python ophardt_bio.py "C:/Users/.../Downloads/ophardt.online.md"
Ophardt blockt Skripte (Cloudflare); die Seite wird deshalb im Browser gespeichert und hier nur ausgewertet.
Deutsche (/de/) und englische (/en/) Seite werden beide verstanden. Abschnitte bekommen feste englische
Schlüssel (für die Logik im Dashboard), Turniernamen zusätzlich einen deutschen Anzeigenamen ("name"),
denn Ophardt führt die Turniernamen auch auf der deutschen Seite meist englisch.
"""
import html, json, re, sys
from datetime import date, datetime
from pathlib import Path

OUT = Path(__file__).parent / "docs" / "data" / "laufbahn.json"

# Abschnitte der deutschen Seite -> feste Schlüssel
SECTIONS = {
    "Kontinentale Meisterschaft": "Zonal Championships", "Internationale Turniere": "International Tournaments",
    "Kontinentale Turniere": "Zonal Tournaments", "Nationale Meisterschaft": "National Championships",
    "Nationale Turniere": "National Tournaments", "Regionale Meisterschaft": "Regional Championships",
    "Regionale Turniere": "Regional Tournaments", "Turniere": "Tournaments", "Kontinental": "Continental",
}
MEDALS = {"National Championships": "national", "Nationale Meisterschaft": "national",
          "Regional championships": "regional", "Regionale Meisterschaft": "regional"}
KIND = {"Results": "results", "Ergebnisse": "results", "Rankings": "rankings", "Ranglisten": "rankings",
        "Match results": None, "Gefechtsergebnis": None, "Memberships": None, "Mitgliedschaft": None}

# Englische Turniernamen von Ophardt -> deutsch (Eigennamen bleiben, z. B. Babylon Cup, Prague Challenge)
NAMES = {
    "German Championships": "Deutsche Meisterschaft", "German Team Championships": "Deutsche Mannschaftsmeisterschaft",
    "European Championships": "Europameisterschaft", "World Championships": "Weltmeisterschaft",
    "World Cup": "Weltcup", "The Finals": "Die Finals",
    "International Competition": "Internationales Turnier", "International Tournament": "Internationales Turnier",
    "International Competition QuB": "Internationales Qualifikationsturnier",
    "Youth Tournament": "Jugendturnier", "Tournament of the Airport": "Flughafen-Turnier",
    "Fox of Wittenau": "Wittenauer Fuchs", "Sword of Bitterfeld": "Bitterfelder Schwert",
    "SFV Season end Tournament": "SFV-Saisonabschlussturnier", "Youth Cup of Chemnitz": "Chemnitzer Jugendcup",
    "Cadet Ciruit": "Kadetten-Circuit", "Saxonian Championships": "Sächsische Meisterschaft",
    "Central German Championships": "Mitteldeutsche Meisterschaft",
    "Championships Sachsen-Anhalt": "Landesmeisterschaft Sachsen-Anhalt",
    "Championships of Baden-Nord - Württemberg": "Meisterschaft Nordbaden-Württemberg",
}


def german_name(event):
    if event in NAMES:
        return NAMES[event]
    m = re.match(r"Cup (?:of )?(.+)$", event)                      # "Cup Wenzel", "Cup of Elbland" -> "Wenzel-Cup"
    if m:
        return m[1].replace(" ", "-") + "-Cup"
    m = re.match(r"(\d+\.\s*)?International (.+)$", event)         # "20.International Händel-Cup"
    if m:
        return f"{(m[1] or '').replace(' ', '').replace('.', '. ')}Internationaler {m[2]}"
    return event


def _cells(tr):
    return [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]


def _iso(text):
    """"25.04.26" (deutsch) oder "4/25/26" (englisch) -> "2026-04-25"."""
    text = text.strip()
    if "." in text:
        d, m, y = (int(x) for x in text.split("."))
    else:
        m, d, y = (int(x) for x in text.split("/"))
    return date(2000 + y if y < 100 else y, m, d).isoformat()


def _comp(text):
    """"Foil Women's U23 Team" / "Florett Damen U23 Team" / "Florett Senior Einzel" -> ("Florett", "U23", "Mannschaft")"""
    m = re.match(r"(\w+) (?:Women's |Damen )?(.+?) (Individual|Einzel|Team)$", text.strip())
    if not m:
        return text, "", ""
    weapon = {"Foil": "Florett", "Epee": "Degen", "Sabre": "Säbel"}.get(m[1], m[1])
    return weapon, m[2], "Mannschaft" if m[3] == "Team" else "Einzel"


def _exam(line):
    m = re.match(r"\|\s*\|\s*([^|]+?)\s*\|", line)
    if not m:
        return None
    for fmt in ("%d.%m.%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(m[1], fmt).date().isoformat()
        except ValueError:
            pass
    return None


def parse(md):
    out = {"source": (re.search(r'source: "([^"]+)"', md) or [None, None])[1],
           "medals": {}, "exam": None, "results": [], "rankings": []}
    section, kind = None, None
    for line in md.splitlines():
        h = re.match(r"#+\s*(.+)", line)
        if h:
            raw = h[1].strip()
            kind = KIND.get(raw, kind)
            section = SECTIONS.get(raw, raw)
            continue
        out["exam"] = out["exam"] or _exam(line)
        trs = re.findall(r"<tr>(.*?)</tr>", line)
        if section in ("Medals", "Medaillen") and len(trs) >= 3:
            name = _cells(trs[0])[0]
            out["medals"][MEDALS.get(name, name)] = [int(x) for x in _cells(trs[2])]
            continue
        for tr in trs:
            c = _cells(tr)
            if not c or not c[0].isdigit():
                continue
            if kind == "results" and len(c) >= 5:
                start, _, end = c[1].partition(" / ")
                weapon, age, typ = _comp(c[4])
                out["results"].append({"section": section, "date": _iso(start), "end": _iso(end) if end else None,
                                       "rank": int(c[0]), "city": c[2], "event": c[3], "name": german_name(c[3]),
                                       "weapon": weapon, "age": age, "type": typ})
            elif kind == "rankings" and len(c) >= 5:
                weapon, age, typ = _comp(c[4])
                out["rankings"].append({"level": section, "rank": int(c[0]), "points": float(c[1]),
                                        "season": int(c[2]), "title": c[3], "weapon": weapon, "age": age})
    # Doppelte Zeilen (Ophardt listet manche Ranglisten mehrfach) entfernen
    for k in ("results", "rankings"):
        seen, uniq = set(), []
        for r in out[k]:
            key = json.dumps(r, sort_keys=True)
            if key not in seen:
                seen.add(key), uniq.append(r)
        out[k] = sorted(uniq, key=lambda r: (str(r.get("date") or r.get("season")), r["rank"]), reverse=True)
    return out


if __name__ == "__main__":
    data = parse(Path(sys.argv[1]).read_text(encoding="utf-8"))
    data["imported"] = date.today().isoformat()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(data['results'])} Ergebnisse, {len(data['rankings'])} Ranglisten -> {OUT}")
