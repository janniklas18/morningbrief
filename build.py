#!/usr/bin/env python3
"""Morgenbrief – baut aus RSS-Finanzquellen eine statische Übersichtsseite.

Ablauf:
  1. Alle Feeds aus feeds.py abrufen (robust, tote Feeds werden übersprungen).
  2. Artikel normalisieren, global deduplizieren, nach Zeit sortieren.
  3. M&A-/Deal-Meldungen per Stichwort erkennen und in eigene Sektion ziehen.
  4. Pro Sektion und Quelle deckeln (Vielfalt), dann nach dist/index.html rendern.
  5. Optional: kurzes Tagesbriefing via Anthropic-API, wenn ANTHROPIC_API_KEY gesetzt ist.

Lokal ausführen:
    python build.py                  # echter Abruf -> dist/index.html
    MORGENBRIEF_DEMO=1 python build.py   # Vorschau mit Beispieldaten, ohne Netz
"""

from __future__ import annotations

import html
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import feedparser
import requests

from feeds import FEEDS, CATEGORY_ORDER

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

TZ = ZoneInfo("Europe/Berlin")
OUTPUT_DIR = Path("dist")
OUTPUT_FILE = OUTPUT_DIR / "index.html"

HTTP_TIMEOUT = 12          # Sekunden pro Feed
USER_AGENT = "Mozilla/5.0 (Morgenbrief RSS Reader; +https://github.com/)"
MAX_PER_SECTION = 10       # Schlagzeilen pro Sektion
MAX_PER_SOURCE = 4         # max. Schlagzeilen einer Quelle je Sektion (Vielfalt)
MAX_MA = 10                # Schlagzeilen in der M&A-Sektion

MA_SECTION = "M&A & Deals"

# Stichwörter für die M&A-Erkennung (DE + EN). Auf Wortgrenzen geprüft, um
# Fehltreffer zu vermeiden (z. B. "deal" nicht in "dealer").
MA_KEYWORDS = [
    # Englisch
    r"merger", r"mergers", r"acquisition", r"acquisitions", r"acquires?",
    r"acquired", r"takeover", r"buyout", r"buys?", r"bid", r"divest\w*",
    r"spin[- ]?off", r"stake", r"\bIPO\b", r"in talks", r"to buy",
    # Deutsch
    r"übernahme", r"übernimmt", r"fusion", r"zusammenschluss", r"beteiligung",
    r"mehrheitsbeteiligung", r"börsengang", r"milliardendeal", r"\bdeal\b",
    r"kauft", r"verkauft", r"verkauf", r"abspaltung", r"einstieg bei",
]
MA_PATTERN = re.compile("|".join(MA_KEYWORDS), re.IGNORECASE)


# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------

@dataclass
class Article:
    title: str
    link: str
    source: str
    category: str
    lang: str
    published: datetime | None  # tz-aware (UTC) oder None
    skip_ma: bool = False

    @property
    def sort_key(self) -> datetime:
        # Artikel ohne Datum landen ganz unten.
        return self.published or datetime.min.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Abruf & Parsing
# ---------------------------------------------------------------------------

def _parse_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def fetch_feed(feed: dict) -> tuple[list[Article], str | None]:
    """Liefert (Artikel, Fehlermeldung-oder-None)."""
    try:
        resp = requests.get(
            feed["url"],
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:  # Netzwerk, Timeout, HTTP-Fehler …
        return [], f"{type(exc).__name__}: {exc}"

    if parsed.bozo and not parsed.entries:
        return [], f"unlesbarer Feed ({parsed.bozo_exception})"

    articles: list[Article] = []
    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        articles.append(
            Article(
                title=html.unescape(title),
                link=link,
                source=feed["name"],
                category=feed["category"],
                lang=feed["lang"],
                published=_parse_time(entry),
                skip_ma=feed.get("skip_ma", False),
            )
        )
    return articles, None


def collect_all() -> tuple[list[Article], dict]:
    """Alle Feeds abrufen. Gibt Artikel + Health-Report zurück."""
    all_articles: list[Article] = []
    ok, failed = [], {}
    for feed in FEEDS:
        articles, error = fetch_feed(feed)
        if error:
            failed[feed["name"]] = error
        else:
            ok.append(feed["name"])
            all_articles.extend(articles)
    health = {"ok": ok, "failed": failed, "total": len(FEEDS)}
    return all_articles, health


# ---------------------------------------------------------------------------
# Verarbeitung
# ---------------------------------------------------------------------------

def _norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", title.lower())).strip()


def dedupe(articles: list[Article]) -> list[Article]:
    """Global nach Zeit sortieren und Duplikate (Titel/Link) entfernen."""
    articles.sort(key=lambda a: a.sort_key, reverse=True)
    seen_titles: set[str] = set()
    seen_links: set[str] = set()
    out: list[Article] = []
    for art in articles:
        nt = _norm_title(art.title)
        if nt in seen_titles or art.link in seen_links:
            continue
        seen_titles.add(nt)
        seen_links.add(art.link)
        out.append(art)
    return out


def is_ma(article: Article) -> bool:
    if article.skip_ma:
        return False
    return bool(MA_PATTERN.search(article.title))


def build_sections(articles: list[Article]) -> dict[str, list[Article]]:
    """Artikel auf Sektionen verteilen. M&A-Treffer landen NUR in M&A."""
    buckets: dict[str, list[Article]] = {MA_SECTION: []}
    for cat in CATEGORY_ORDER:
        buckets[cat] = []

    for art in articles:
        target = MA_SECTION if is_ma(art) else art.category
        buckets.setdefault(target, []).append(art)

    # Pro Sektion: nach Zeit sortiert, je Quelle deckeln, gesamt deckeln.
    limited: dict[str, list[Article]] = {}
    for section, items in buckets.items():
        items.sort(key=lambda a: a.sort_key, reverse=True)
        cap = MAX_MA if section == MA_SECTION else MAX_PER_SECTION
        per_source: dict[str, int] = {}
        picked: list[Article] = []
        for art in items:
            if per_source.get(art.source, 0) >= MAX_PER_SOURCE:
                continue
            per_source[art.source] = per_source.get(art.source, 0) + 1
            picked.append(art)
            if len(picked) >= cap:
                break
        limited[section] = picked
    return limited


# ---------------------------------------------------------------------------
# Optionales Tagesbriefing via Anthropic-API
# ---------------------------------------------------------------------------

def maybe_generate_briefing(sections: dict[str, list[Article]]) -> str | None:
    """Kurzes deutsches Briefing, falls ANTHROPIC_API_KEY gesetzt ist.

    Schlägt der Aufruf fehl, wird None zurückgegeben – der Build bricht nie ab.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    headlines = []
    for section in [MA_SECTION] + CATEGORY_ORDER:
        for art in sections.get(section, [])[:5]:
            headlines.append(f"- [{section}] {art.title} ({art.source})")
    if not headlines:
        return None

    prompt = (
        "Hier sind die wichtigsten Finanz-Schlagzeilen von heute Morgen:\n\n"
        + "\n".join(headlines)
        + "\n\nFasse die Lage in 2–3 nüchternen deutschen Sätzen zusammen "
        "(Was bewegt die Märkte? Auffällige Deals?). Keine Aufzählung, "
        "keine Einleitung wie 'Hier ist' – nur die Zusammenfassung."
    )

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            timeout=30,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": os.environ.get("MORGENBRIEF_MODEL", "claude-haiku-4-5-20251001"),
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ).strip()
        return text or None
    except Exception as exc:
        print(f"  [Briefing übersprungen: {exc}]")
        return None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt_time(dt: datetime | None, now: datetime) -> str:
    if dt is None:
        return "—"
    local = dt.astimezone(TZ)
    if local.date() == now.date():
        return local.strftime("%H:%M")
    return local.strftime("%d.%m %H:%M")


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def render_article(art: Article, now: datetime) -> str:
    meta_time = _fmt_time(art.published, now)
    lang_badge = "EN" if art.lang == "en" else "DE"
    return f"""        <li class="item">
          <a class="headline" href="{_esc(art.link)}" target="_blank" rel="noopener">{_esc(art.title)}</a>
          <span class="meta"><span class="src">{_esc(art.source)}</span> · {meta_time} · {lang_badge}</span>
        </li>"""


def render_section(name: str, items: list[Article], now: datetime, index: int) -> str:
    is_ma_section = name == MA_SECTION
    section_class = "section ma" if is_ma_section else "section"
    if items:
        body = "\n".join(render_article(a, now) for a in items)
        body = f'      <ul class="items">\n{body}\n      </ul>'
    else:
        body = '      <p class="empty">Heute keine Meldungen.</p>'
    return f"""    <section class="{section_class}">
      <h2 class="section-title"><span class="num">{index:02d}</span>{_esc(name)}</h2>
{body}
    </section>"""


def render_html(sections: dict[str, list[Article]], briefing: str | None,
                health: dict, now: datetime) -> str:
    order = [MA_SECTION] + CATEGORY_ORDER
    sections_html = "\n".join(
        render_section(name, sections.get(name, []), now, i + 1)
        for i, name in enumerate(order)
    )

    date_line = now.strftime("%A, %d. %B %Y")
    # Wochentage/Monate eindeutschen (ohne locale-Abhängigkeit im CI).
    for en, de in {
        "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
        "Thursday": "Donnerstag", "Friday": "Freitag", "Saturday": "Samstag",
        "Sunday": "Sonntag", "January": "Januar", "February": "Februar",
        "March": "März", "April": "April", "May": "Mai", "June": "Juni",
        "July": "Juli", "August": "August", "September": "September",
        "October": "Oktober", "November": "November", "December": "Dezember",
    }.items():
        date_line = date_line.replace(en, de)

    updated = now.strftime("%H:%M")
    ok_n = len(health["ok"])
    total = health["total"]

    briefing_html = ""
    if briefing:
        briefing_html = f"""    <section class="briefing">
      <span class="briefing-label">Lage</span>
      <p>{_esc(briefing)}</p>
    </section>"""

    failed = health["failed"]
    failed_html = ""
    if failed:
        rows = "\n".join(
            f"        <li><span class=\"src\">{_esc(name)}</span> — {_esc(err)}</li>"
            for name, err in failed.items()
        )
        failed_html = f"""
      <details class="failed">
        <summary>{len(failed)} Feed(s) nicht geladen</summary>
        <ul>
{rows}
        </ul>
      </details>"""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Morgenbrief · {date_line}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,900&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --paper:    #F5F4EF;
    --ink:      #18181B;
    --muted:    #6B6B71;
    --hairline: #E1E0D8;
    --accent:   #0F6E66;   /* Petrol – Links/Marke */
    --flag:     #B26A00;   /* Amber – M&A-Akzent   */
    --surface:  #FBFAF6;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --paper:    #111214;
      --ink:      #ECEAE3;
      --muted:    #8C8C94;
      --hairline: #28292E;
      --accent:   #54B7AC;
      --flag:     #DB9A4A;
      --surface:  #16171A;
    }}
  }}
  * {{ box-sizing: border-box; }}
  html {{ -webkit-text-size-adjust: 100%; }}
  body {{
    margin: 0;
    background: var(--paper);
    color: var(--ink);
    font-family: "Inter", system-ui, sans-serif;
    line-height: 1.45;
    padding: clamp(1.25rem, 4vw, 3rem) clamp(1rem, 5vw, 2rem) 4rem;
  }}
  .wrap {{ max-width: 720px; margin: 0 auto; }}

  /* Kopf */
  .masthead {{
    display: flex; align-items: baseline; justify-content: space-between;
    gap: 1rem; flex-wrap: wrap;
    border-bottom: 2px solid var(--ink);
    padding-bottom: 0.75rem;
  }}
  .brand {{
    font-family: "Fraunces", Georgia, serif;
    font-weight: 900; font-size: clamp(2.1rem, 7vw, 3.2rem);
    letter-spacing: -0.02em; line-height: 0.95; margin: 0;
  }}
  .brand small {{
    display: block; font-size: 0.85rem; font-weight: 500; letter-spacing: 0.04em;
    color: var(--muted); margin-top: 0.35rem; font-family: "Inter", sans-serif;
  }}
  .stamp {{
    font-family: "JetBrains Mono", monospace; font-size: 0.78rem;
    color: var(--muted); text-align: right; white-space: nowrap;
  }}
  .stamp .date {{ color: var(--ink); }}

  /* Briefing */
  .briefing {{
    margin: 1.5rem 0 0; padding: 1rem 1.1rem;
    background: var(--surface); border: 1px solid var(--hairline);
    border-radius: 2px;
  }}
  .briefing-label {{
    font-family: "JetBrains Mono", monospace; font-size: 0.68rem;
    text-transform: uppercase; letter-spacing: 0.12em; color: var(--accent);
  }}
  .briefing p {{ margin: 0.35rem 0 0; font-size: 1rem; }}

  /* Sektionen */
  .section {{ margin-top: 2.4rem; }}
  .section.ma {{
    border-left: 3px solid var(--flag);
    padding-left: 1.1rem; margin-left: -1.1rem;
  }}
  .section-title {{
    font-family: "Fraunces", Georgia, serif;
    font-size: 1.35rem; font-weight: 600; margin: 0 0 0.9rem;
    display: flex; align-items: baseline; gap: 0.6rem;
    border-bottom: 1px solid var(--hairline); padding-bottom: 0.5rem;
  }}
  .section.ma .section-title {{ color: var(--flag); }}
  .num {{
    font-family: "JetBrains Mono", monospace; font-size: 0.78rem;
    color: var(--muted); font-weight: 400;
  }}
  .items {{ list-style: none; margin: 0; padding: 0; }}
  .item {{ padding: 0.7rem 0; border-bottom: 1px solid var(--hairline); }}
  .item:last-child {{ border-bottom: none; }}
  .headline {{
    color: var(--ink); text-decoration: none; font-size: 1.05rem;
    font-weight: 500; line-height: 1.35; display: block;
    transition: color 0.12s ease;
  }}
  .headline:hover, .headline:focus-visible {{ color: var(--accent); }}
  .meta {{
    display: block; margin-top: 0.25rem;
    font-family: "JetBrains Mono", monospace; font-size: 0.74rem;
    color: var(--muted);
  }}
  .meta .src {{ color: var(--accent); }}
  .section.ma .meta .src {{ color: var(--flag); }}
  .empty {{ color: var(--muted); font-style: italic; margin: 0.3rem 0; }}

  /* Fuß */
  footer {{
    margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--hairline);
    font-family: "JetBrains Mono", monospace; font-size: 0.72rem; color: var(--muted);
  }}
  footer a {{ color: var(--accent); }}
  .failed {{ margin-top: 0.6rem; }}
  .failed summary {{ cursor: pointer; }}
  .failed ul {{ margin: 0.4rem 0 0; padding-left: 1.1rem; }}
  .failed li {{ margin: 0.2rem 0; }}

  @media (prefers-reduced-motion: reduce) {{
    * {{ transition: none !important; }}
  }}
</style>
</head>
<body>
  <div class="wrap">
    <header class="masthead">
      <h1 class="brand">Morgenbrief<small>Finanzen · weltweit</small></h1>
      <div class="stamp">
        <div class="date">{date_line}</div>
        <div>Stand {updated} Uhr</div>
      </div>
    </header>

{briefing_html}

{sections_html}

    <footer>
      {ok_n} von {total} Feeds geladen · erzeugt {now.strftime('%d.%m.%Y %H:%M')} (Europe/Berlin){failed_html}
    </footer>
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Beispieldaten für die Vorschau (MORGENBRIEF_DEMO=1)
# ---------------------------------------------------------------------------

def _demo_articles(now: datetime) -> list[Article]:
    base = now.astimezone(timezone.utc)
    def mk(t, link, src, cat, lang, mins):
        return Article(t, link, src, cat, lang,
                       base.replace(microsecond=0).fromtimestamp(base.timestamp() - mins * 60, timezone.utc))
    return [
        mk("SAP übernimmt KI-Startup für 2,3 Milliarden Euro", "https://example.com/1", "Handelsblatt", "Unternehmen & Tech", "de", 25),
        mk("Private equity firm acquires majority stake in logistics group", "https://example.com/2", "Investing.com", "Märkte", "en", 40),
        mk("DAX startet vorsichtig – Anleger warten auf US-Inflationsdaten", "https://example.com/3", "finanzen.net", "Märkte", "de", 12),
        mk("Fed signals patience as inflation cools further", "https://example.com/4", "CNBC Markets", "Makro & Wirtschaft", "en", 55),
        mk("EZB hält Leitzins stabil, deutet aber Senkung im Herbst an", "https://example.com/5", "tagesschau", "Makro & Wirtschaft", "de", 90),
        mk("Nvidia shares climb on strong data-center demand", "https://example.com/6", "Yahoo Finance", "Unternehmen & Tech", "en", 33),
        mk("Siemens prüft Börsengang der Medizintechnik-Sparte", "https://example.com/7", "manager magazin", "Unternehmen & Tech", "de", 70),
        mk("Oil steadies after volatile session", "https://example.com/8", "MarketWatch", "Märkte", "en", 18),
        mk("Talks heat up over cross-border banking merger", "https://example.com/9", "The Economist", "Makro & Wirtschaft", "en", 110),
        mk("Deutsche Bank verkauft Tochtergesellschaft an US-Investor", "https://example.com/10", "WirtschaftsWoche", "Unternehmen & Tech", "de", 130),
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    now = datetime.now(TZ)
    demo = os.environ.get("MORGENBRIEF_DEMO") == "1"

    if demo:
        print("Demo-Modus: Beispieldaten, kein Netzabruf.")
        articles = _demo_articles(now)
        health = {"ok": ["(Demo)"], "failed": {}, "total": 1}
    else:
        print(f"Rufe {len(FEEDS)} Feeds ab …")
        articles, health = collect_all()
        print(f"  {len(health['ok'])} ok, {len(health['failed'])} fehlgeschlagen, "
              f"{len(articles)} Artikel.")
        for name, err in health["failed"].items():
            print(f"  ! {name}: {err}")

    articles = dedupe(articles)
    sections = build_sections(articles)
    briefing = maybe_generate_briefing(sections) if not demo else None

    html_out = render_html(sections, briefing, health, now)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html_out, encoding="utf-8")
    print(f"Geschrieben: {OUTPUT_FILE} ({len(html_out):,} Bytes)")


if __name__ == "__main__":
    main()
