# Dashboards und Blueprints

Fertige Lovelace-Dashboards, drei Blueprints und ein Generator für die eigenen Entity-IDs. Alles besteht aus den
Entitäten dieser Integration und nutzt **nur eingebaute Karten**; die einzige Ausnahme ist eine optionale, getrennte
Ansicht, die die HACS-Karte [apexcharts-card](https://github.com/RomRider/apexcharts-card) braucht.

## Für wen

| Ansicht | Für | Inhalt |
|---|---|---|
| Übersicht | Alle, die die Steuerung einem Planer wie dem Heat Pump Optimizer überlassen | Verbindung, Betriebsart, Status, Temperaturen, Leistung, COP, Hinweise bei EVU-Sperre und Sperren. Nur Anzeige: Ein Tipp auf eine Sperre schaltet nichts. |
| Energie | Nutzer von Energiemanagement (HEMS) | Strom- und Wärmeenergie heute, diese Woche, diesen Monat (Langzeitstatistik, keine Hilfsentitäten nötig), Energie pro Tag je Bereich, COP |
| Sperren und Netz | HEMS-Nutzer | Sperren für Heizen, Warmwasser, Kühlen und Pool, Leistungsbegrenzung, Zirkulation, Extra-Warmwasser, EVU-Sperre, Hinweise zum PV-Überschuss |
| Steuerung | Wer die Wärmepumpe selbst steuert | Thermostat, Warmwasser, Betriebsart, Sollwert (mit wirksamem Sollwert der Regelung), Anhebung und Stufe je Kreis |
| Diagnose | Support und Fehlersuche | Firmware, Puffertyp, Fehlernummer, Erzeuger-Bits, Ausstattung, Statusverlauf, Fehlersuche |
| Automation | Wer Automationen schreibt | Tabelle aller Entitäten (Schlüssel und Entity-ID), Blueprint-Import, Beispiel-Automationen |

## Einrichten

1. Datei wählen: `dashboards/luxtronik_shi.<Profil>.<Sprache>.yaml`.
   * **basic**: ohne optionale Teile. **full**: zusätzlich Mischkreise 1 bis 3, Kühlen, Pool und Raumeinheit.
   * Nicht vorhandene Entitäten zeigen eine Fehlerkarte; nimm *basic*, wenn du die Teile nicht hast, oder erzeuge dein eigenes Dashboard (unten).
2. Dashboard anlegen (Einstellungen > Dashboards > Dashboard hinzufügen), öffnen, dann drei Punkte > Bearbeiten >
   drei Punkte > *Rohkonfigurations-Editor* und die Datei einfügen.
3. Die Entity-IDs in den mitgelieferten Dateien sind für ein Gerät namens `Wärmepumpe` (der Standardname) in der
   Sprache der Datei **vorhergesagt**. Hat dein Gerät einen anderen Namen oder hast du Entitäten umbenannt, erzeuge dein eigenes.

Für ein YAML-Dashboard die Datei dort ablegen, wohin `configuration.yaml` zeigt
(`lovelace: dashboards: <name>: mode: yaml, filename: ...`).

## Eigene Entity-IDs

Home Assistant bildet die Entity-ID aus dem Gerätenamen und dem Entitätsnamen in der Sprache, die beim Anlegen aktiv
war. Der Generator löst das, indem er die IDs in deiner Entity-Registry nachschlägt:

```bash
pip install pyyaml
python tools/gen_dashboard.py --registry /config/.storage/core.entity_registry --lang de > mein_dashboard.yaml
```

* Deaktivierte und fehlende Entitäten werden weggelassen, optionale Teile an den vorhandenen Entitäten erkannt,
  umbenannte Entitäten über ihre Unique-ID (`<entry_id>_<key>`) gefunden.
* Mehrere Wärmepumpen: `--entry-id <Config-Entry-ID>` ergänzen.
* Ohne Registry-Datei: `--name "Meine Wärmepumpe" --lang de --profile full` sagt die IDs vorher.
* `--hacs` schreibt die optionale Ansicht mit apexcharts-card.
* Die mitgelieferten Dateien sind erzeugt; `tests/test_dashboard.py` schlägt fehl, wenn sie veraltet sind, und prüft die
  Vorhersage gegen die Entity-IDs, die Home Assistant tatsächlich anlegt (Englisch und Deutsch).

Nicht geprüft: wie die Dashboards im Browser aussehen. Aufbau, Entity-IDs und Blueprints sind gegen die simulierte
Wärmepumpe getestet; die optische Darstellung wurde nicht kontrolliert.

## Blueprints

| Blueprint | Macht |
|---|---|
| Heizen oder Warmwasser sperren, solange ein Signal an ist | Schaltet die Sperren ein, solange ein Signal (Preis, EVU-Signal, Zeitplan) an ist, und gibt sie danach frei, optional nach einer Höchstdauer |
| Auslöser mit Hysterese | Führt deine Aktionen aus, wenn ein Wert (PV-Überschuss, Preis, Leistung) einige Minuten über der oberen oder unter der unteren Schwelle bleibt; schreibt selbst nichts |
| Bei Problemen benachrichtigen | Führt deine Benachrichtigung aus bei Verbindungsverlust, geänderter Fehlernummer oder langer EVU-Sperre; schreibt nichts |

Import über die Links in der Ansicht *Automation* oder mit den Schaltflächen:

[![Sperren, solange ein Signal an ist](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/Bankaifan/ha-luxtronik-shi/blob/main/blueprints/automation/luxtronik_shi/block_while_signal.yaml)
[![Auslöser mit Hysterese](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/Bankaifan/ha-luxtronik-shi/blob/main/blueprints/automation/luxtronik_shi/surplus_trigger.yaml)
[![Bei Problemen benachrichtigen](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/Bankaifan/ha-luxtronik-shi/blob/main/blueprints/automation/luxtronik_shi/notify_problems.yaml)

Die Blueprints wählen Entitäten dieser Integration über einen Filter, Entity-IDs müssen also nie getippt werden.
Sperren wirken direkt auf die Wärmepumpe: nicht zusammen mit einem Planer für denselben Kreis verwenden (der letzte
Schreibvorgang gewinnt), und beachten, dass der Regler über die Schnittstelle gesetzte Werte nach 10 Minuten ohne
Zugriff oder nach einem Neustart verwirft.

## Grenzen

* Die Wirkung der Betriebsarten der Leistungsbegrenzung (weich, hart) auf den Regler ist in diesem Projekt nicht geprüft.
* Die Fehlernummer hat keinen Text: Die Schnittstelle liefert keinen.
* Die Übersicht zeigt die Werte des Reglers; sie entscheidet nichts.
