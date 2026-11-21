# Ellas Fecht-Dashboard

Statische Seite (`docs/`), die ein GitHub-Workflow jeden Morgen neu befüllt:

- **Automatisch von fie.org:** Weltranglistenplatz und Punkte, Ergebnisse mit FIE-Punkten, Einzelgefechte, Saisonkalender Damen-Florett Senior, Meldestatus in den FIE-Meldelisten, deutsche Konkurrenz in der Weltrangliste.
- **Von Hand in `manual.json`:** DFB-Rangliste, nationale Turniere und Meldestatus bei Ophardt. Ophardt sperrt automatische Abrufe per Cloudflare-Bot-Schutz, deshalb dieser Weg.

Jede Änderung (Platz, Punkte, neues Ergebnis, neuer Termin, Meldestatus, Terminverschiebung) landet im Feed „Letzte News“ und in `docs/data/history.csv`. Mails gibt es nur für Turnier-Tage, den Weihnachtsgruß (24.12., 10 Uhr) und die Silvester-Bilanz.

## Einrichtung (einmalig, ca. 10 Minuten)

1. Auf github.com ein neues Repository anlegen, z. B. `fechten-dashboard` (öffentlich, sonst kostet Pages Geld). Den Inhalt dieses Ordners hochladen (ohne `.claude/`).
2. **Settings → Pages:** Source „Deploy from a branch“, Branch `main`, Ordner `/docs`. Die Seite liegt danach unter `https://<dein-name>.github.io/fechten-dashboard/`.
3. **Settings → Secrets and variables → Actions → New repository secret**, für die Mail:

   | Secret | Gmail | iCloud |
   |---|---|---|
   | `MAIL_SERVER` | `smtp.gmail.com` | `smtp.mail.me.com` |
   | `MAIL_PORT` | `465` | `587` |
   | `MAIL_USER` | deine Gmail-Adresse | deine iCloud-Adresse |
   | `MAIL_PASS` | App-Passwort (Google-Konto → Sicherheit) | app-spezifisches Passwort (appleid.apple.com) |
   | `MAIL_TO` | Empfänger, mehrere mit Komma | |

   Ohne Secrets läuft alles, nur ohne Mail.
4. **Actions → „Täglich aktualisieren“ → Run workflow**, einmal von Hand starten und prüfen.

## Ophardt-Daten pflegen

`manual.json` direkt auf GitHub bearbeiten (Stift-Symbol) und speichern. Der Workflow läuft dann sofort und übernimmt die Änderung.

- `dfb`: Platz, Punkte, Berechnungsdatum und Top 10 der DFB-Rangliste.
- `fie_status`: Ophardt-Status für FIE-Turniere, Schlüssel ist die FIE-Turnier-ID aus der URL (`fie.org/tournaments/2027/131` → `"131"`). Steht Ella in der FIE-Meldeliste, zeigt das Dashboard automatisch „Gemeldet (FIE)“.
- `events` / `results`: nationale Turniere und Ergebnisse.
- `news`: eigene Meldungen für „Letzte News“, z. B. Neuigkeiten von direkten Konkurrentinnen (`{"text": "…", "url": "…"}`). Jede erscheint einmal, am Tag des nächsten Laufs.

Die Startwerte stammen aus dem Grok-Dashboard vom 13.11.2026. Einige ältere Ergebnisse haben dort kein genaues Datum.

## Lokal

```bash
python test_update.py
python update.py
python -m http.server 8765 -d docs
```

Nur Python-Standardbibliothek, nichts zu installieren.

## Wenn etwas nicht stimmt

## Turnier-Tag-Mail

An Wettkampftagen, für die Ella gemeldet ist, kommt gegen 9 Uhr eine Mail „Turnier-Tag! Let's go, Ella!“ mit Direktlink (Workflow `turniertag.yml`, Skript `turniertag.py`).

- **FIE-Turniere** mit Status „Gemeldet …“ oder Eintrag in der FIE-Meldeliste: am ersten Tag des Einzels, Link zur Live-Seite des Wettbewerbs auf fie.org. Den Team-Tag gibt es nur, wenn im Status `fie_status` in `manual.json` „Team“ oder „Mannschaft“ steht, z. B. `"Gemeldet (Einzel + Team)"`.
- **Eigene Termine** in `manual.json` mit Status „Gemeldet …“: jeden Tag von `date` bis `end`. Optional `"days": ["2026-12-05"]` für nur bestimmte Tage und `"live": "https://…"` als Direktlink (sonst `url`).
- **Testmail:** Actions → „Turnier-Tag“ → Run workflow, Datum eines Turniertags eintragen.
- **Banner aufs Handy:** zusätzlich als Push über [ntfy](https://ntfy.sh). App „ntfy“ installieren, ein schwer zu erratendes Thema abonnieren (z. B. `ella-turnier-` plus Zufallszeichen) und denselben Namen als Repo-Secret `NTFY_TOPIC` eintragen. Ohne Secret entfällt der Push, die Mail kommt trotzdem. Das Thema ist das einzige Schloss: nicht veröffentlichen.

## Silvester-Bilanz

Jedes Jahr am 31.12. um 16 Uhr erscheint Ellas Fecht-Jahresbilanz auf `silvester.html` (vorher Countdown, Vorschau mit `?vorschau`). Workflow `silvester.yml` rechnet sie mit `jahresbilanz.py --silvester` aus, setzt einen Eintrag mit Link in „Letzte News“ und schickt Mail und ntfy-Push (gleiche Secrets wie oben). Danach steht jedes Jahr zugeklappt unter Statistik → Jahresbilanzen. Gefechte zählen nur von FIE-Turnieren; der beste DFB-Rang stammt aus `history.csv` (seit Oktober 2026).

Fällt fie.org aus oder ändert die Seitenstruktur, bleibt der letzte Stand stehen und die Seite zeigt oben einen gelben Hinweis mit der Fehlermeldung. GitHub pausiert geplante Workflows nach 60 Tagen ohne Commits; der tägliche Commit (Zeitstempel in `state.json`) verhindert das. Falls die Mails trotzdem ausbleiben: unter Actions nachsehen, ob der Workflow deaktiviert wurde.
