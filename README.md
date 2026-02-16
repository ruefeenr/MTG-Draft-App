# MTG League Manager

Flask-Webapp zur Verwaltung von MTG-Draftturnieren mit Multi-Table-Builder, Gruppen/Cubes, Vintage-only Power Nine und SQL-Datenbankpersistenz.

## Features

- Single-Page Table Builder mit mehreren Tischen pro Start
- Tischgrößen 6/8/10/12, ungerade Spielerzahl mit BYE in Runde 1
- Gruppen- und Cube-Verwaltung über eigene Management-Seiten
- Turnier-Switcher in der Rundenansicht für parallele Turniere
- Spielerstatistiken mit Group-/Cube-Filtern
- Power Nine nur für Vintage-Turniere (UI + Statistik)
- Turnierarchiv mit Endstand und Metadaten

## Installation

### Voraussetzungen

- Python 3.10+
- pip
- PostgreSQL 14+ (empfohlen)

### Setup

1. Repository klonen:
   ```
   git clone https://github.com/ruefeenr/MTG-Draft-App.git
   cd MTG-Draft-App
   ```

2. Virtuelle Umgebung erstellen/aktivieren:
   ```
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # Linux/macOS
   source venv/bin/activate
   ```

3. Abhängigkeiten installieren:
   ```
   pip install -r requirements.txt
   ```

4. PostgreSQL-Datenbank erstellen:
   ```sql
   CREATE DATABASE mtg_draft_app;
   ```

5. `.env` anlegen:
   ```
   FLASK_SECRET_KEY=<zufaelliger-langer-key>
   DATABASE_URL=postgresql+psycopg://postgres:<passwort>@localhost:5432/mtg_draft_app
   ```

6. Migrationen anwenden:
   ```
   flask --app run.py db upgrade
   ```

## Verwendung

### App starten

```
python run.py
```

Danach unter `http://127.0.0.1:5000`.

### Optional: lokal ohne PostgreSQL (SQLite)

PowerShell:
```
$env:DATABASE_URL="sqlite:///mtg_local.db"
python run.py
```

## Datenbank

Die App nutzt SQLAlchemy + Flask-Migrate.

- Schemaänderungen:
  - `flask --app run.py db migrate -m "..."`  
  - `flask --app run.py db upgrade`
- Primärziel ist PostgreSQL über `DATABASE_URL`.
- Legacy-Dateien in `data/`, `tournament_data/`, `tournament_results/` können lokal noch als Fallback/Archiv bestehen.

### DB-Inhalt prüfen

Mit `psql`:
```bash
psql -h localhost -U postgres -d mtg_draft_app
\dt
SELECT * FROM tournaments LIMIT 20;
```

## Projektstruktur

```
MTG-Draft-App/
├── app/
│   ├── __init__.py
│   ├── db.py
│   ├── models.py
│   ├── routes.py
│   ├── services/
│   └── templates/
├── migrations/
├── .env.example
├── requirements.txt
├── run.py
└── wsgi.py
```

## Sicherheit

- `FLASK_SECRET_KEY` geheim halten, nie committen
- `.env` bleibt lokal und ist per `.gitignore` ausgeschlossen
- Produktionsumgebung über echte Env-Variablen konfigurieren

## Lizenz

MIT-Lizenz, siehe `LICENSE`.