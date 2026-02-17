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
   APP_LOGIN_ENABLED=true
   APP_LOGIN_USERNAME=mtg
   APP_LOGIN_PASSWORD=<starkes-passwort>
   ```
   Fuer einen schlanken Online-Betrieb (du + Freunde) siehe auch:
   - `.env.friends-prod.example`
   - `docs/friends_vps_deploy.md`

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

### Betriebsregel: Source of Truth

- Primäre Wahrheit ist die Datenbank (PostgreSQL/SQLite via SQLAlchemy).
- Legacy-Dateien dienen nur noch als Fallback/Archiv und für Kompatibilität.
- Turnierstatus gilt als beendet, wenn mindestens eines dieser Signale vorliegt:
  - DB-Status `tournaments.status = ended`
  - `data/<tournament_id>/end_time.txt` vorhanden
  - Archivdatei in `tournament_results/` vorhanden
- Bei Konflikten hat der DB-Status Vorrang.

### Deterministisches Pairing (optional)

- Für reproduzierbare Pairings im Betrieb/Debugging kann ein fixer Seed gesetzt werden:
  - `MTG_PAIRING_SEED=12345`
- Ohne diese Variable verwendet die App einen deterministischen Seed pro Turnier/Stage/Runde.

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

## Qualität & Betrieb

### CI / Quality Gate

- GitHub Actions Workflow in `.github/workflows/ci.yml`
- Enthält:
  - `python -m pytest -q --cov=app --cov-fail-under=70`
  - Fokus-Gate für kritische Module (`app.routes`, `app.player_stats`, `app.services`)
  - kritischen Smoke-Test für Start -> Save -> Next Round -> End
  - Migrations-Smoketest via `flask --app run.py db upgrade` gegen frische SQLite-DB
  - Backup/Restore-Drill via `python scripts/sqlite_backup_restore_drill.py`

### Staging und Deployment-Basis

- Staging sollte dieselbe Migrationskette wie Produktion nutzen.
- Vor jedem Deploy:
  - Backup erstellen
  - `flask --app run.py db upgrade`
  - `GET /healthz` prüfen
- Release-/Rollback-Checkliste: `docs/release_rollback_checklist.md`
- VPS-Runbook fuer Friends-Prod: `docs/friends_vps_deploy.md`

### Observability

- Jede Request bekommt eine `X-Request-ID` Response-Header.
- Strukturierte HTTP-Logs enthalten Methode, Pfad, Status, Dauer und `tournament_id`.
- Healthcheck-Endpoint: `GET /healthz` erwartet `{"status": "ok"}`.

### Backup / Recovery (PostgreSQL)

Backup erstellen:
```bash
pg_dump -h localhost -U postgres -d mtg_draft_app -F c -f mtg_draft_app.backup
```

Backup einspielen (in leere DB):
```bash
createdb -h localhost -U postgres mtg_draft_app_restore
pg_restore -h localhost -U postgres -d mtg_draft_app_restore --clean --if-exists mtg_draft_app.backup
```

Nach Restore:
```bash
flask --app run.py db upgrade
python run.py
```

Automatisierbar per Skripten:
- Backup: `bash scripts/postgres_backup.sh`
- Restore-Smoke: `bash scripts/postgres_restore_smoke.sh backups/<file>.dump`

### Security-Baseline (Public-Betrieb)

- CSRF-Schutz für mutierende Requests aktiv.
- Session-Cookies mit `HttpOnly`, `SameSite=Lax`, `Secure` in Production.
- Security-Header (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy).
- Basis-Rate-Limit auf kritischen mutierenden Endpunkten.
- Optional/empfohlen für Friends-Prod: App-Login via `APP_LOGIN_*` Variablen.

## Lizenz

MIT-Lizenz, siehe `LICENSE`.