# Release und Rollback Checklist

## Vor dem Release

1. Versionsnummer nach SemVer erhöhen (`MAJOR.MINOR.PATCH`).
2. `CHANGELOG.md` für die neue Version aktualisieren.
3. `python -m pytest -q --cov=app --cov-fail-under=70` lokal erfolgreich ausführen.
4. Fokus-Coverage der kritischen Module prüfen:
   - `python -m pytest -q --cov=app.routes --cov=app.player_stats --cov=app.services --cov-fail-under=60`
5. Datenbank-Migration prüfen:
   - `flask --app run.py db upgrade`
6. Kritischen Smoke-Flow verifizieren:
   - Turnier starten
   - Ergebnis speichern
   - Nächste Runde erzeugen
   - Turnier beenden
7. Backup vor Deployment erstellen.
   - Optional automatisiert: `bash scripts/postgres_backup.sh`
8. Optionalen Drill lokal verifizieren:
   - `python scripts/sqlite_backup_restore_drill.py`

## Deployment

1. Backup erzeugen.
2. Neue Version deployen.
3. Migration anwenden (`flask --app run.py db upgrade`).
4. Healthcheck prüfen (`GET /healthz`).
5. Smoke-Flow in Staging oder Production-Slot durchführen.

## Rollback

1. Deployment auf letzte stabile Version zurücksetzen.
2. Datenbankzustand prüfen.
3. Falls nötig Backup einspielen.
   - Optional mit Skript und Restore-DB: `bash scripts/postgres_restore_smoke.sh backups/<file>.dump`
4. Erneut `GET /healthz` und Smoke-Flow prüfen.
5. Incident-Notiz mit Ursache und Follow-up Tasks erfassen.
