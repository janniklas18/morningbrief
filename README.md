# Morgenbrief

Eine persönliche, statische Übersichtsseite mit den aktuellsten Schlagzeilen aus
deutschen und internationalen Finanzquellen – gedacht zum Lesen jeden Morgen.
Baut sich automatisch über GitHub Actions und liegt kostenlos auf GitHub Pages.

- **M&A & Deals** ganz oben: über alle Quellen per Stichwort erkannt (Übernahme,
  Fusion, Beteiligung, Börsengang, merger, acquisition, IPO …).
- Sektionen **Märkte**, **Makro & Wirtschaft**, **Unternehmen & Tech**.
- DE/EN gemischt, Dedup über alle Feeds, Hell-/Dunkelmodus automatisch.
- Tote Feeds werden übersprungen und im Fuß der Seite gemeldet.

## Schnellstart (lokal)

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python build.py            # ruft die Feeds ab und schreibt dist/index.html
```

Dann `dist/index.html` im Browser öffnen.

Ohne Netz nur das Layout ansehen:

```bash
MORGENBRIEF_DEMO=1 python build.py   # Vorschau mit Beispieldaten
```

## Auf GitHub Pages veröffentlichen (täglich automatisch)

1. Neues GitHub-Repo anlegen und diese Dateien hineinpushen.
2. Im Repo unter **Settings → Pages** bei *Source* **„GitHub Actions"** wählen.
3. Fertig. Der Workflow `.github/workflows/deploy.yml` läuft ab jetzt:
   - jeden Morgen (Cron, siehe unten),
   - bei jedem Push auf `main`,
   - und manuell über **Actions → „Morgenbrief bauen & veröffentlichen" → Run workflow**.

Die Seite erscheint dann unter `https://<dein-name>.github.io/<repo>/`.

### Uhrzeit / Zeitzone

GitHub-Cron läuft in **UTC**. Voreingestellt ist `0 4 * * *` ≈ **06:00 Berlin im
Sommer / 05:00 im Winter** – also rechtzeitig vor dem Frühstück fertig. Zum Ändern
einfach die `cron`-Zeile in `deploy.yml` anpassen (z. B. `0 5 * * *` für eine
Stunde später).

## Quellen anpassen

Alle Feeds stehen in **`feeds.py`**. Dort Einträge hinzufügen, entfernen oder die
Kategorie ändern. Verlags-URLs wechseln gelegentlich – wenn eine Quelle im Fuß der
Seite als „nicht geladen" auftaucht, dort die URL korrigieren oder die Zeile
entfernen.

Feintuning in `build.py` (oben):
`MAX_PER_SECTION`, `MAX_PER_SOURCE`, `MAX_MA` (Anzahl Schlagzeilen) und
`MA_KEYWORDS` (Stichwörter der M&A-Erkennung).

## Optional: KI-Tagesbriefing

Ist die Umgebungsvariable `ANTHROPIC_API_KEY` gesetzt, schreibt Claude oben auf die
Seite eine 2–3-Satz-Zusammenfassung der Lage. Lokal:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python build.py
```

Für den automatischen Build: im Repo unter **Settings → Secrets and variables →
Actions** ein Secret namens `ANTHROPIC_API_KEY` anlegen. Ohne Key wird das Briefing
einfach weggelassen – der Build läuft trotzdem durch. Modell per
`MORGENBRIEF_MODEL` wählbar (Standard: ein günstiges Haiku-Modell).

## Dateien

| Datei | Zweck |
|-------|-------|
| `feeds.py` | Kuratierte Quellen + Kategorien |
| `build.py` | Abruf, M&A-Erkennung, Dedup, HTML-Rendering |
| `.github/workflows/deploy.yml` | Täglicher Build + Deploy auf Pages |
| `requirements.txt` | `feedparser`, `requests` |
