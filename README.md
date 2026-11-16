# Ellas Fecht-Dashboard

Statische Seite (`docs/`), die ein GitHub-Workflow jeden Morgen neu befüllt:

- **Automatisch von fie.org:** Weltranglistenplatz und Punkte, Ergebnisse mit FIE-Punkten, Einzelgefechte, Saisonkalender Damen-Florett Senior, Meldestatus in den FIE-Meldelisten, deutsche Konkurrenz in der Weltrangliste.
- **Von Hand in `manual.json`:** DFB-Rangliste, nationale Turniere und Meldestatus bei Ophardt. Ophardt sperrt automatische Abrufe per Cloudflare-Bot-Schutz, deshalb dieser Weg.

Jede Änderung (Platz, Punkte, neues Ergebnis, neuer Termin, Meldestatus, Terminverschiebung) landet im Feed „Letzte News“, in `docs/data/history.csv` und, falls eingerichtet, per Mail bei dir.

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

`manual.json` direkt auf GitHub bearbeiten (Stift-Symbol) und speichern. Der Workflow läuft dann sofort und mailt die Änderung.

- `dfb`: Platz, Punkte, Berechnungsdatum und Top 10 der DFB-Rangliste.
- `fie_status`: Ophardt-Status für FIE-Turniere, Schlüssel ist die FIE-Turnier-ID aus der URL (`fie.org/tournaments/2027/131` → `"131"`). Steht Ella in der FIE-Meldeliste, zeigt das Dashboard automatisch „Gemeldet (FIE)“.
- `events` / `results`: nationale Turniere und Ergebnisse.

Die Startwerte stammen aus dem Grok-Dashboard vom 13.11.2026. Einige ältere Ergebnisse haben dort kein genaues Datum.

## Lokal

```bash
python test_update.py
python update.py
python -m http.server 8765 -d docs
```

Nur Python-Standardbibliothek, nichts zu installieren.

## Wenn etwas nicht stimmt

Fällt fie.org aus oder ändert die Seitenstruktur, bleibt der letzte Stand stehen und die Seite zeigt oben einen gelben Hinweis mit der Fehlermeldung. GitHub pausiert geplante Workflows nach 60 Tagen ohne Commits; der tägliche Commit (Zeitstempel in `state.json`) verhindert das. Falls die Mails trotzdem ausbleiben: unter Actions nachsehen, ob der Workflow deaktiviert wurde.
