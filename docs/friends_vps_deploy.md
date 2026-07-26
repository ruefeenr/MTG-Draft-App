# Friends-Prod Deployment (VPS)

Dieses Runbook ist fuer einen kleinen privaten Online-Betrieb (du + Freunde):
- Sicherheitsbaseline aktiv
- schlanker Betrieb
- schneller Restore im Notfall

## 1) Server vorbereiten (Ubuntu)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx postgresql postgresql-contrib
```

## 2) App-User und Verzeichnis

```bash
sudo adduser --system --group --home /opt/mtg-draft-app mtgapp
sudo mkdir -p /opt/mtg-draft-app
sudo chown -R mtgapp:mtgapp /opt/mtg-draft-app
```

Code nach `/opt/mtg-draft-app` deployen (git clone oder rsync).

## 3) PostgreSQL einrichten

```bash
sudo -u postgres psql
CREATE USER mtg_user WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE mtg_draft_app OWNER mtg_user;
\q
```

## 4) Python-Umgebung + Migration

```bash
cd /opt/mtg-draft-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.env` aus `.env.friends-prod.example` erstellen:

```bash
cp .env.friends-prod.example .env
```

Dann `.env` anpassen:
- `FLASK_SECRET_KEY`
- `DATABASE_URL`
- `APP_LOGIN_ENABLED=true`
- `APP_LOGIN_USERNAME`
- `APP_LOGIN_PASSWORD`
- optional `RATE_LIMIT_MAX_REQUESTS`

Migrationen:

```bash
source .venv/bin/activate
flask --app run.py db upgrade
```

## 5) Systemd-Service

Datei `/etc/systemd/system/mtg-draft-app.service`:

Die versionierte Vorlage liegt unter `deploy/systemd/mtg-draft-app.service` und
kann direkt kopiert werden:

```bash
sudo cp /opt/mtg-draft-app/deploy/systemd/mtg-draft-app.service /etc/systemd/system/
```

Wichtig:
- Die `.env` muss `FLASK_SECRET_KEY`, `DATABASE_URL` (PostgreSQL) und
  `FLASK_ENV=production` enthalten. Ohne `FLASK_SECRET_KEY` verweigert die App
  in Production bewusst den Start (Schutz vor Session-/CSRF-Fehlern durch
  unterschiedliche Worker-Keys).
- Der Service startet erst nach `network-online.target` und `postgresql.service`.

Aktivieren:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mtg-draft-app
sudo systemctl status mtg-draft-app
```

## 6) Claro Calendar auf demselben VPS

Code separat nach `/opt/claro-calendar` deployen:

```bash
sudo adduser --system --group --home /opt/claro-calendar claroapp
sudo mkdir -p /opt/claro-calendar
sudo chown -R claroapp:claroapp /opt/claro-calendar
sudo -u claroapp git clone https://github.com/ruefeenr/claro-calendar.git /opt/claro-calendar
cd /opt/claro-calendar
sudo -u claroapp npm ci
```

In `next.config.ts` muss die App unter `/claro` laufen:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  basePath: "/claro",
  typedRoutes: true,
};

export default nextConfig;
```

Eine kopierbare Vorlage liegt unter `deploy/claro-calendar/next.config.ts`.

Danach `.env.local` anlegen:

```bash
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```

Build:

```bash
sudo -u claroapp npm run build
```

Systemd-Service `/etc/systemd/system/claro-calendar.service` anlegen. Eine Vorlage liegt unter `deploy/systemd/claro-calendar.service`:

```bash
sudo cp /opt/mtg-draft-app/deploy/systemd/claro-calendar.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now claro-calendar
sudo systemctl status claro-calendar
```

Hinweis: Die Vorlage startet das Next-Binary direkt
(`/opt/claro-calendar/node_modules/.bin/next start -p 3000`). Dafuer muessen
`npm ci` und `npm run build` im Verzeichnis `/opt/claro-calendar` gelaufen sein.

## 7) Nginx + HTTPS

### 7a) TLS-Status pruefen

Zuerst pruefen, ob bereits ein Zertifikat existiert:

```bash
sudo certbot certificates
curl -I https://example.com/healthz
```

Falls kein Zertifikat existiert, eines ausstellen (dafuer muss die Domain
per DNS auf den Server zeigen und Port 80 erreichbar sein):

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot certonly --nginx -d example.com
```

### 7b) Nginx-Site einrichten

Die versionierte Vorlage liegt unter `deploy/nginx/apps-homepage.conf`.
Sie enthaelt:

- Port 80: nur ACME-Challenge + Redirect `301 https://...` (behebt das
  fehlende HTTP-zu-HTTPS-Routing)
- Port 443: TLS-Block mit certbot-Zertifikatspfaden und HSTS
- `map $http_upgrade $connection_upgrade` fuer saubere Websocket-Upgrades
  der Claro-App
- `X-Forwarded-Proto`/`X-Forwarded-Host` fuer beide Apps (die Flask-App wertet
  diese Header seit dem ProxyFix-Update aus)

Einrichten (vorher ueberall `example.com` durch die echte Domain ersetzen):

```bash
sudo cp /opt/mtg-draft-app/deploy/nginx/apps-homepage.conf /etc/nginx/sites-available/apps-homepage
sudo sed -i 's/example.com/DEINE-DOMAIN/g' /etc/nginx/sites-available/apps-homepage
sudo ln -sf /etc/nginx/sites-available/apps-homepage /etc/nginx/sites-enabled/apps-homepage
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### 7c) HTTPS verifizieren

```bash
# HTTP muss auf HTTPS umleiten (301):
curl -I http://DEINE-DOMAIN/mtg/

# HTTPS muss funktionieren:
curl -I https://DEINE-DOMAIN/healthz
curl -I https://DEINE-DOMAIN/mtg/
curl -I https://DEINE-DOMAIN/claro/

# Automatische Zertifikatserneuerung testen:
sudo certbot renew --dry-run
```

Wichtig: In der `.env` der MTG-App muss `FLASK_ENV=production` gesetzt sein
(Session-Cookies bekommen dann das `Secure`-Flag). Der Login funktioniert dann
nur noch ueber HTTPS - das ist gewollt.

## 8) Backup- und Restore-Drill

Backup:

```bash
cd /opt/mtg-draft-app
source .venv/bin/activate
export DATABASE_URL="postgresql+psycopg://mtg_user:***@127.0.0.1:5432/mtg_draft_app"
bash scripts/postgres_backup.sh
```

Restore-Smoke in Test-DB:

```bash
export RESTORE_DATABASE_URL="postgresql+psycopg://mtg_user:***@127.0.0.1:5432/mtg_draft_app_restore"
export FLASK_SECRET_KEY="replace-me"
bash scripts/postgres_restore_smoke.sh backups/<backup-file>.dump
```

## 9) Minimaler Betriebsrhythmus

- Vor jedem Deploy:
  - Backup laufen lassen
  - `flask --app run.py db upgrade`
  - `/healthz`, `/mtg/healthz`, `/mtg/` und `/claro/` pruefen
- Nach jedem Deploy:
  - Kernflow kurz testen (Start -> Save -> Next Round -> End)
- Woechentlich:
  - einen Restore-Smoke gegen Test-DB

## 10) Konfigurations-Checkliste (Produktion)

Diese Punkte muessen auf dem Server erfuellt sein:

- [ ] `.env` der MTG-App enthaelt:
  - `FLASK_SECRET_KEY` (lang, zufaellig - App startet in Production sonst nicht)
  - `DATABASE_URL=postgresql+psycopg://...` (PostgreSQL, nicht SQLite)
  - `FLASK_ENV=production`
  - `APP_LOGIN_ENABLED=true` + `APP_LOGIN_USERNAME`/`APP_LOGIN_PASSWORD`
- [ ] TLS-Zertifikat vorhanden und gueltig (`sudo certbot certificates`)
- [ ] `curl -I http://DOMAIN/` liefert `301` auf `https://`
- [ ] `curl -I https://DOMAIN/healthz` liefert `200`
- [ ] `curl -I https://DOMAIN/claro/` liefert `200`
- [ ] `sudo certbot renew --dry-run` laeuft fehlerfrei
- [ ] Beide Services laufen: `systemctl is-active mtg-draft-app claro-calendar`

## 11) Troubleshooting

### Logs finden

```bash
# Flask-App (gunicorn):
sudo journalctl -u mtg-draft-app -n 200 --no-pager

# Claro Calendar (Next.js):
sudo journalctl -u claro-calendar -n 200 --no-pager

# Nginx:
sudo tail -n 100 /var/log/nginx/error.log
sudo tail -n 100 /var/log/nginx/access.log
```

### "Internal Server Error" einem Request zuordnen

Jede Antwort der MTG-App enthaelt einen `X-Request-ID` Header; die
Fehlerseite zeigt die ID ebenfalls an. Damit laesst sich der Fehler im Log
finden:

```bash
sudo journalctl -u mtg-draft-app --no-pager | grep "<request-id>"
```

Unbehandelte Fehler werden zusaetzlich als `unhandled_error`-Events mit
Stacktrace geloggt:

```bash
sudo journalctl -u mtg-draft-app --no-pager | grep unhandled_error
```

### Typische Symptome

| Symptom | Wahrscheinliche Ursache | Massnahme |
|---|---|---|
| Login-Loop / sofort wieder ausgeloggt | Seite laeuft ueber HTTP, Cookie hat `Secure`-Flag | HTTPS-Setup pruefen (Abschnitt 7) |
| `403 CSRF_ORIGIN_MISMATCH` bei POSTs | nginx sendet `X-Forwarded-Proto` nicht oder App laeuft ohne ProxyFix | nginx-Config aus `deploy/nginx/` verwenden, App aktualisieren |
| App startet nicht, `RuntimeError: FLASK_SECRET_KEY` | Key fehlt in `.env` | Key generieren: `python3 -c "import os; print(os.urandom(32).hex())"` |
| `503 DB_SCHEMA_OUTDATED` | Migrationen nicht eingespielt | `flask --app run.py db upgrade` |
| Claro-Service startet nicht | Build fehlt oder `node_modules/.bin/next` nicht vorhanden | `sudo -u claroapp npm ci && sudo -u claroapp npm run build`, dann Service neu starten |
