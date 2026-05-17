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

```ini
[Unit]
Description=MTG Draft App
After=network.target

[Service]
User=mtgapp
Group=mtgapp
WorkingDirectory=/opt/mtg-draft-app
EnvironmentFile=/opt/mtg-draft-app/.env
ExecStart=/opt/mtg-draft-app/.venv/bin/gunicorn -c gunicorn_config.py wsgi:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Eine versionierte Vorlage liegt unter `deploy/systemd/mtg-draft-app.service`.

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

Systemd-Service `/etc/systemd/system/claro-calendar.service` anlegen. Eine Vorlage liegt unter `deploy/systemd/claro-calendar.service`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now claro-calendar
sudo systemctl status claro-calendar
```

## 7) Nginx + HTTPS

Nginx Site `/etc/nginx/sites-available/apps-homepage`:

```nginx
server {
    listen 80;
    server_name example.com;

    location = /mtg {
        return 301 /mtg/;
    }

    location = /claro {
        return 301 /claro/;
    }

    location /claro/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:10000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
    }
}
```

Eine versionierte Vorlage liegt unter `deploy/nginx/apps-homepage.conf`.

Aktivieren:

```bash
sudo ln -s /etc/nginx/sites-available/apps-homepage /etc/nginx/sites-enabled/apps-homepage
sudo nginx -t
sudo systemctl reload nginx
```

TLS (Let's Encrypt):

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d example.com
```

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
