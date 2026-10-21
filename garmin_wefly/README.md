# Garmin → We-Fly (Home-Assistant-Add-on)

Holt neue MyVario-Flüge aus Garmin Connect, wandelt die Original-FIT mit
`fit_to_igc.py` (im Add-on enthalten) in IGC um (Baro bleibt erhalten) und lädt sie
per API zu We-Fly hoch.

## Installation auf Home Assistant

1. Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories →
   `https://github.com/dni990/ha-garmin-wefly` hinzufügen, dann „Garmin → We-Fly“
   installieren.
2. Konfiguration ausfüllen: Garmin-Login, We-Fly-API-Key (`wf_key_…`, aus dem
   We-Fly-Developer-Dashboard, Scope `flights:write`).
   Filter erst nach dem ersten Start setzen (siehe unten).
   `pilot`/`glider_type` landen im IGC-Kopf.
3. Direkt auf HA testen: erst mit `dry_run: true` starten. Das Protokoll-Tab zeigt die
   Aktivitätsliste, die IGCs liegen unter `/share/garmin_wefly/igc/`
   (Samba-Freigabe `share`). Passt alles, `dry_run` auf `false` und neu starten.

`converter_cmd` leer lassen, dann wird der eingebaute Konverter genutzt. Nur für
einen anderen Konverter setzen; `{fit}` und `{igc}` werden ersetzt.

## Filter einrichten (wichtig)

Ohne Filter lädt das Add-on absichtlich nichts hoch. Beim ersten Start steht im
Protokoll eine Liste deiner letzten Aktivitäten mit `typeKey` und Namen. Daraus:

- `activity_type_keys`: z. B. den `typeKey`, unter dem MyVario-Flüge erscheinen
- `name_contains`: z. B. ein Wort aus dem Aktivitätsnamen

Sind beide gesetzt, müssen beide passen. Danach `list_activities` auf `false`.

Zum Testen erst `dry_run: true`: dann wird nur konvertiert und die IGC unter
`/share/garmin_wefly/igc/` abgelegt, ohne Upload. (Im Dry-Run wird der Flug nicht
als erledigt markiert, er wird also nach dem Umschalten normal hochgeladen.)

## Welche Flüge werden berücksichtigt?

Nur Aktivitäten, die nach dem ersten Start des Add-ons beginnen. Willst du ältere
nachholen, setze `upload_since`, z. B. `2026-09-01` – eine Änderung wird beim
nächsten Start übernommen.
Der Stand liegt in `/data/state.json`; zum kompletten Zurücksetzen das Add-on
deinstallieren und neu installieren.

## Garmin mit Bestätigungscode (MFA)

Verlangt Garmin beim ersten Login einen Code, wartet das Add-on 15 Minuten darauf
(Hinweis im Protokoll und als HA-Benachrichtigung). Den Code aus Mail/App im
Terminal eintragen:

```sh
echo 123456 > /share/garmin_wefly/mfa_code.txt
```

Danach speichert das Add-on die Anmeldung und braucht keinen Code mehr. Läuft die
Zeit ab, versucht es das Add-on erst nach 60 Minuten wieder (sonst sperrt Garmin
die Logins, Fehler 429) – oder sofort nach einem Neustart des Add-ons.

Alternativ: `get_tokens.py` auf einem Rechner ausführen und den Ordner `tokens`
nach `/share/garmin_wefly/tokens` kopieren.

## Zu prüfen

- We-Fly-Upload laut `we-fly.cloud/doc/openapi.yaml`: Multipart-Feld `file`,
  Antwort 201 = neu, 200 = Duplikat.
- Braucht ein eigener Konverter weitere Pakete als `fitdecode`/`fitparse`, trag sie unter
  `pip_packages` ein.
- Die Garmin-Anbindung nutzt die inoffizielle Bibliothek `python-garminconnect`.
  Ändert Garmin den Login, kann es zeitweise hängen – dann hilft meist ein Update
  der Bibliothek (Add-on neu bauen).
