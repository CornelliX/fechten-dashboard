"""Ophardt-Biografie (als Markdown-Clip gespeichert) -> docs/data/laufbahn.json

Aufruf:  python ophardt_bio.py "C:/Users/.../Downloads/ophardt.online.md"
Ophardt blockt Skripte (Cloudflare); die Seite wird deshalb im Browser gespeichert und hier nur ausgewertet.
"""
import html, json, re, sys
from datetime import date, datetime
from pathlib import Path

OUT = Path(__file__).parent / "docs" / "data" / "laufbahn.json"


def _cells(tr):
    return [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]


def _iso(mdy):
    m, d, y = (int(x) for x in mdy.strip().split("/"))
    return date(2000 + y if y < 100 else y, m, d).isoformat()


def _comp(text):
    """"Foil Women's U23 Team" / "Foil Senior Individual" -> ("Florett", "U23", "Mannschaft")"""
    m = re.match(r"(\w+) (?:Women's )?(.+?) (Individual|Team)$", text.strip())
    if not m:
        return text, "", ""
    weapon = {"Foil": "Florett", "Epee": "Degen", "Sabre": "Säbel"}.get(m[1], m[1])
    return weapon, m[2], "Mannschaft" if m[3] == "Team" else "Einzel"


def parse(md):
    out = {"source": (re.search(r'source: "([^"]+)"', md) or [None, None])[1],
           "medals": {}, "exam": None, "results": [], "rankings": []}
    section, kind = None, None
    for line in md.splitlines():
        h = re.match(r"#+\s*(.+)", line)
        if h:
            section = h.group(1).strip()
            kind = {"Rankings": "rankings", "Match results": None, "Memberships": None}.get(section, kind)
            if section == "Results":
                kind = "results"
            continue
        ex = re.match(r"\|\s*\|\s*(\w{3} \d{1,2}, \d{4})\s*\|", line)
        if ex:
            out["exam"] = datetime.strptime(ex.group(1), "%b %d, %Y").date().isoformat()
        trs = re.findall(r"<tr>(.*?)</tr>", line)
        if section == "Medals" and len(trs) >= 3:
            name = _cells(trs[0])[0]
            out["medals"][{"National Championships": "national", "Regional championships": "regional"}.get(name, name)] = \
                [int(x) for x in _cells(trs[2])]
            continue
        for tr in trs:
            c = _cells(tr)
            if not c or not c[0].isdigit():
                continue
            if kind == "results" and len(c) >= 5:
                start, _, end = c[1].partition(" / ")
                weapon, age, typ = _comp(c[4])
                out["results"].append({"section": section, "date": _iso(start), "end": _iso(end) if end else None,
                                       "rank": int(c[0]), "city": c[2], "event": c[3],
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
