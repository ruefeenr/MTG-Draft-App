# Changelog

Alle relevanten Änderungen an diesem Projekt werden hier dokumentiert.

Das Format orientiert sich an Keep a Changelog und nutzt SemVer.

## [Unreleased]

### Added
- Healthcheck-Endpoint `/healthz`
- Security-Baseline mit CSRF-Prüfung, Security-Headern und Basis-Rate-Limit
- CI-Coverage-Gate und zusätzlicher Smoke-Test
- Release-/Rollback-Checklist unter `docs/release_rollback_checklist.md`
- Automatisierter SQLite-Backup/Restore-Drill via `scripts/sqlite_backup_restore_drill.py`
- Optionaler App-Login (`/login`, `/logout`) für Friends-Prod-Betrieb

### Changed
- Lifecycle-Guards für mutierende Turnieroperationen mit einheitlichen Fehlercodes
- Deterministische Pairing- und Persistenz-Härtung erweitert
- CI nutzt `python -m pytest` für robustere lokale/CI-Aufrufe
- Zusätzliches Fokus-Coverage-Gate für `app.routes`, `app.player_stats`, `app.services`
