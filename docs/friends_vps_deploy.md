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

Aktivieren:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mtg-draft-app
sudo systemctl status mtg-draft-app
```

## 6) Nginx + HTTPS

Nginx Site `/etc/nginx/sites-available/mtg-draft-app`:

```nginx
server {
    listen 80;
    server_name mtg.example.com;

    location / {
        proxy_pass http://127.0.0.1:10000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
    }
}
```

Aktivieren:

```bash
sudo ln -s /etc/nginx/sites-available/mtg-draft-app /etc/nginx/sites-enabled/mtg-draft-app
sudo nginx -t
sudo systemctl reload nginx
```

TLS (Let's Encrypt):

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d mtg.example.com
```

## 7) Backup- und Restore-Drill

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

## 8) Minimaler Betriebsrhythmus

- Vor jedem Deploy:
  - Backup laufen lassen
  - `flask --app run.py db upgrade`
  - `/healthz` pruefen
- Nach jedem Deploy:
  - Kernflow kurz testen (Start -> Save -> Next Round -> End)
- Woechentlich:
  - einen Restore-Smoke gegen Test-DB
