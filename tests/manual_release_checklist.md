# Manual Release Checklist (30-45 Minuten)

Diese Checkliste ist für einen gezielten E2E-Sanity-Run vor Releases gedacht.

## 1. Start und Persistenz

- App starten (`python run.py`) und Homepage laden.
- Neuen Tisch im Builder konfigurieren und Turnier starten.
- Browser-Refresh durchführen:
  - Aktuelle Runde bleibt erreichbar.
  - Leaderboard bleibt konsistent.
- Browser schließen und neu öffnen:
  - Über laufende Turniere das Turnier wieder laden.
  - Runde und Turnierstatus sind unverändert.

## 2. Ergebnisse und nächste Runde

- In Runde 1 mehrere Resultate eintragen (Win/Loss/Draw-Kombinationen).
- Einen Spieler als Dropout markieren.
- "Nächste Runde" klicken:
  - Keine Fehlermeldung bei vollständiger Runde.
  - Dropout-Spieler wird nicht mehr gepaart.
  - Keine Wiederholungsduelle, wenn vermeidbar.
- Leaderboard kontrollieren:
  - Punkte und Match-Record plausibel.
  - Keine Doppelzählung nach Reload.

## 3. Turnierende und Archiv

- Letzte Runde vollständig eintragen.
- Turnier beenden.
- Prüfen:
  - Endstandseite lädt.
  - Turnier erscheint im Archiv.
  - Turnier ist schreibgeschützt (keine weiteren Resultatänderungen).

## 4. Multi-Table Flow

- Zwei Tische mit unterschiedlichen Konfigurationen starten (z. B. Vintage/Liga + Pauper/Casual).
- Prüfen:
  - Beide Turniere sind aktiv.
  - Tournament-Switcher zeigt beide korrekt.
  - Resultate in Turnier A beeinflussen Turnier B nicht.

## 5. Gruppen- und Cube-CRUD

- Gruppe erstellen, umbenennen, löschen.
- Cube erstellen, umbenennen, löschen.
- Beim Löschen prüfen:
  - Gruppen-Reassign auf "Unkategorisiert".
  - Cube-Reassign auf "Vintage".
- Default-Objekte (Standardgruppe/Standardcube) dürfen nicht löschbar/umbenennbar sein.

## 6. Vintage-only Power Nine

- Vintage-Turnier:
  - Power-Nine-UI sichtbar.
  - Speichern funktioniert.
- Non-Vintage-Turnier:
  - Power-Nine-UI nicht sichtbar.
  - API/Seite bleibt robust (keine Fehler).
- Spielerstatistiken:
  - Bei Cube=Vintage Power-Nine-Werte sichtbar.
  - Bei Cube!=Vintage oder all ohne Vintage-Fokus keine falschen Power-Nine-Summen.

## 7. Fehler- und Randfälle

- Doppelte Spielernamen über mehrere Tische im Builder: Validierungsfehler erscheint.
- Ungültige Tischkonfigurationen (zu viele Spieler / zu wenige Spieler) werden blockiert.
- Reload einer nicht existierenden Runde zeigt verständliche Meldung statt Crash.

## 8. Abschlusskriterien

- Kein kritischer Fehler im Browser/Server-Log.
- Kernflows (Start, Results, Next Round, End, Stats) vollständig funktionsfähig.
- Persistenz konsistent über Refresh, Reload und Turnierwechsel.
