# MTG League Manager

Eine Flask-basierte Webanwendung zur Verwaltung von Magic: The Gathering Turnieren mit flexiblen Tischgrössen, automatischer Spielerpaarung und Turnierstatistiken.

## Features

- **Flexible Turnierverwaltung**: Unterstützung für verschiedene Tischgrössen (6, 8, 10, 12 Spieler)
- **Automatische Spielerpaarungen**: Intelligente Algorithmen für faire Paarungen
- **Spieler-Tracking**: Verfolge Spieler über mehrere Runden
- **Umfassende Statistiken**: Match-Gewinne, Game-Punkte, Tiebreaker und mehr
- **Responsive Design**: Funktioniert auf Desktop und mobilen Geräten
- **Dropout-Behandlung**: Markiere Spieler als Dropouts mit 🦵-Symbol
- **Turnierleaderboard**: Übersichtliche Darstellung mit farbcodierten Tischgrössen
- **Multiple Tische gleicher Größe**: Separate Leaderboards für mehrere Tische mit gleicher Spieleranzahl (z.B. zwei 6er-Tische)
- **Turnierarchiv**: Vergangene Turniere und deren Ergebnisse werden angezeigt

## Installation

### Voraussetzungen

- Python 3.8 oder höher
- pip (Python-Paketmanager)

### Setup

1. Repository klonen:
   ```
   git clone https://github.com/ruefeenr/MTG-Draft-App.git
   cd MTG-Draft-App
   ```

2. Virtuelle Umgebung erstellen und aktivieren:
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

4. Umgebungsvariablen einrichten:
   - Kopiere `.env.example` zu `.env`
   - Passe die Werte in `.env` an (z.B. setze einen sicheren Secret Key)

## Verwendung

### Anwendung starten

1. Lokaler Entwicklungsserver:
   ```
   python run.py
   ```
   Die Anwendung ist dann unter http://localhost:5000 verfügbar.

2. Produktionsserver (mit Gunicorn):
   ```
   gunicorn -c gunicorn_config.py wsgi:app
   ```

### Turnier erstellen

1. Gib Spielernamen ein (einen pro Zeile)
2. Wähle unterstützte Tischgrössen (6, 8, 10, 12)
3. Starte das Turnier mit "Turnier starten"

### Ergebnisse eintragen

1. Nach jeder Paarung können Ergebnisse eingetragen werden
2. Spieler können als Dropouts markiert werden
3. Nach Abschluss einer Runde kann die nächste Runde gestartet werden

### Turnier beenden

Nach Abschluss des Turniers kann ein Endstand mit Leaderboards für alle Tischgrössen angezeigt werden.
Abgeschlossene Turniere können erneut angesehen werden, ohne dass Änderungen vorgenommen werden können.

## Datenspeicherung

Die Anwendung verwendet eine dateibasierte Speicherung für alle Turnierdaten:

- **data/{tournament_id}/**: Verzeichnis für jedes Turnier
  - **player_groups.json**: Speichert die Zuordnung von Spielern zu Tischgrößen
  - **rounds/**: Enthält Rundeninformationen
    - **round_{n}.csv**: Eine CSV-Datei pro Runde mit den Paarungen und Ergebnissen
  
- **tournament_data/**: Globales Verzeichnis für Turnierergebnisse
  - **results.csv**: Kumulierte Ergebnisse aller Turniere und Runden

- **tournament_results/**: Archiv abgeschlossener Turniere
  - **{tournament_id}_results.json**: Turnierdaten und finales Leaderboard

## Technologie-Stack

- **Backend**: Flask (Python)
- **Frontend**: HTML, CSS, JavaScript
- **Datenbank**: Dateibasierte Speicherung (CSV, JSON)
- **Deployment**: Unterstützung für Render.com (über render.yaml)

## Entwicklung

### Projektstruktur

```
MTG-Draft-App/
├── app/
│   ├── __init__.py     # Flask App-Initialisierung
│   ├── routes.py       # Routen und Hauptlogik
│   └── templates/      # HTML-Templates
├── data/               # Turnierdaten (gitignore)
│   └── {tournament_id}/# Verzeichnisstruktur pro Turnier
│       ├── player_groups.json # Spielergruppenzuordnung
│       └── rounds/     # Rundeninformationen
├── tournament_data/    # Globale Ergebnisdaten
├── tournament_results/ # Abgeschlossene Turniere
├── config/             # Konfigurationsdateien
├── instance/           # Instanz-spezifische Daten (gitignore)
├── venv/               # Virtuelle Umgebung (gitignore)
├── .env.example        # Beispiel für Umgebungsvariablen
├── .gitignore          # Ignorierte Dateien
├── requirements.txt    # Python-Abhängigkeiten
├── run.py              # Entwicklungsserver
└── wsgi.py             # WSGI-Einstiegspunkt
```

### Sicherheit

- Secret Keys werden sicher über Umgebungsvariablen oder .env-Dateien verwaltet
- Sensible Dateien werden über .gitignore vom Repository ausgeschlossen
- Produktionsbereitstellungen sollten HTTPS verwenden

## Beitragende

- @ruefeenr - Hauptentwickler

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz - siehe die LICENSE-Datei für Details. 