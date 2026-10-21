# Garmin → We-Fly

Home-Assistant-Add-on-Repository: holt MyVario-Flüge aus Garmin Connect,
wandelt sie in IGC um (mit Baro-Höhe) und lädt sie zu We-Fly hoch.

## In Home Assistant installieren

[![Repository zu Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fdni990%2Fha-garmin-wefly)

Oder manuell: Einstellungen → Add-ons → Add-on-Store → ⋮ → **Repositories** →
`https://github.com/dni990/ha-garmin-wefly` hinzufügen. Danach erscheint
„Garmin → We-Fly“ im Store. Einrichtung: [garmin_wefly/README.md](garmin_wefly/README.md).

Updates: `version` in `garmin_wefly/config.yaml` erhöhen und pushen – HA bietet
das Update dann im Add-on an.

## Inhalt

| Pfad | Zweck |
|---|---|
| `garmin_wefly/` | das Add-on (Dockerfile, `main.py`, Konverter `fit_to_igc.py`) |
| `garmin_wefly/get_tokens.py` | nur bei Garmin-MFA: Tokens einmalig erzeugen |
| `repository.yaml` | Metadaten für den Add-on-Store |
