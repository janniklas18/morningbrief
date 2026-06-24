"""Kuratierte RSS-Quellen für den Morgenbrief.

Jeder Eintrag: name (Anzeigequelle), url (RSS), category, lang ("de"/"en").

Kategorien:
  - "Märkte"              Börsen, Indizes, Rohstoffe, Anleihen
  - "Makro & Wirtschaft"  Konjunktur, Notenbanken, Politik
  - "Unternehmen & Tech"  Einzelwerte, Tech, Earnings

Hinweis: M&A-/Deal-Meldungen werden NICHT über eine eigene Quelle bezogen,
sondern automatisch per Stichwort über ALLE Feeds erkannt und in einer eigenen
Sektion ganz oben gebündelt (siehe build.py -> MA_KEYWORDS).

Feed-URLs ändern sich bei Verlagen gelegentlich. Tote Feeds werden beim Build
übersprungen und im Footer der Seite gemeldet – einfach hier anpassen/ausmisten.
"""

FEEDS = [
    # --- Märkte -------------------------------------------------------------
    {"name": "MarketWatch",   "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",        "category": "Märkte",             "lang": "en"},
    {"name": "Investing.com", "url": "https://www.investing.com/rss/news.rss",                            "category": "Märkte",             "lang": "en"},
    {"name": "finanzen.net",  "url": "https://www.finanzen.net/rss/news",                                 "category": "Märkte",             "lang": "de"},
    {"name": "CNBC Markets",  "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", "category": "Märkte", "lang": "en"},
    # Einzelwert-Feed: Ocugen (OCGN)
    {"name": "Yahoo – OCGN",  "url": "https://finance.yahoo.com/rss/headline?s=OCGN",                     "category": "Märkte",             "lang": "en"},

    # --- Makro & Wirtschaft -------------------------------------------------
    {"name": "tagesschau",    "url": "https://www.tagesschau.de/wirtschaft/index~rss2.xml",               "category": "Makro & Wirtschaft", "lang": "de"},
    {"name": "Handelsblatt",  "url": "https://www.handelsblatt.com/contentexport/feed/schlagzeilen",      "category": "Makro & Wirtschaft", "lang": "de"},
    {"name": "The Economist", "url": "https://www.economist.com/finance-and-economics/rss.xml",           "category": "Makro & Wirtschaft", "lang": "en"},
    {"name": "NYT Business",  "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",          "category": "Makro & Wirtschaft", "lang": "en"},

    # --- Unternehmen & Tech -------------------------------------------------
    {"name": "manager magazin","url": "https://www.manager-magazin.de/unternehmen/index.rss",             "category": "Unternehmen & Tech", "lang": "de"},
    {"name": "WirtschaftsWoche","url": "https://www.wiwo.de/contentexport/feed/rss/unternehmen",          "category": "Unternehmen & Tech", "lang": "de"},
    {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex",                           "category": "Unternehmen & Tech", "lang": "en"},
    {"name": "CNBC Tech",     "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910", "category": "Unternehmen & Tech", "lang": "en"},

    # --- Venture Capital (Fokus DE/EU, ggf. relevante US-News) --------------
    {"name": "Gründerszene",  "url": "https://www.gruenderszene.de/feed",                                 "category": "Venture Capital",    "lang": "de"},
    {"name": "t3n",           "url": "https://t3n.de/rss.xml",                                            "category": "Venture Capital",    "lang": "de"},
    {"name": "EU-Startups",   "url": "https://www.eu-startups.com/feed/",                                 "category": "Venture Capital",    "lang": "en"},
    {"name": "Sifted",        "url": "https://sifted.eu/feed",                                            "category": "Venture Capital",    "lang": "en"},
    {"name": "TechCrunch VC", "url": "https://techcrunch.com/category/venture/feed/",                     "category": "Venture Capital",    "lang": "en"},
]

# Reihenfolge der Sektionen auf der Seite (M&A wird in build.py vorangestellt).
CATEGORY_ORDER = ["Märkte", "Makro & Wirtschaft", "Unternehmen & Tech", "Venture Capital"]
