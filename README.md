# Garmin → We-Fly

Home-Assistant-Add-on-Repository: holt MyVario-Flüge aus Garmin Connect,
wandelt sie in IGC um (mit Baro-Höhe) und lädt sie zu We-Fly hoch.

## In Home Assistant installieren

Das Repo ist privat, daher als lokales Add-on per SSH-Terminal klonen:

```sh
git clone https://github.com/dni990/ha-garmin-wefly /addons/ha-garmin-wefly
```

Dann Add-on-Store → ⋮ → „Nach Updates suchen“ → „Lokale Add-ons“ → „Garmin → We-Fly“.
Details: [garmin_wefly/README.md](garmin_wefly/README.md).

Updates: Am PC ändern, `version` in `garmin_wefly/config.yaml` erhöhen, pushen.
Auf HA `git pull` im Ordner, dann im Add-on „Aktualisieren“.

(Wird das Repo mal öffentlich, geht es auch direkt über Add-on-Store → ⋮ →
Repositories mit der Repo-URL – dafür liegt `repository.yaml` bereit.)

## Inhalt

| Pfad | Zweck |
|---|---|
| `garmin_wefly/` | das Add-on (Dockerfile, `main.py`, Konverter `fit_to_igc.py`) |
| `garmin_wefly/get_tokens.py` | nur bei Garmin-MFA: Tokens einmalig erzeugen |
| `repository.yaml` | Metadaten, falls das Repo als Add-on-Repository eingebunden wird |
