#!/usr/bin/env python3
"""Garmin Connect -> FIT -> IGC (eigener Konverter) -> We-Fly.

Läuft als Home-Assistant-Add-on. Konfiguration kommt aus /data/options.json,
der Verarbeitungsstand liegt in /data/state.json (überlebt Neustarts/Updates).

Für Tests außerhalb von HA lassen sich die Pfade über GW_DATA_DIR / GW_SHARE_DIR
umbiegen; mit --once wird genau ein Durchlauf gemacht.
"""
import datetime as dt
import io
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
import argparse
from pathlib import Path

import requests
from garminconnect import Garmin

DATA = Path(os.environ.get("GW_DATA_DIR", "/data"))
OPTIONS = DATA / "options.json"
STATE = DATA / "state.json"
TOKENS = DATA / "garmin_tokens"
SHARE = Path(os.environ.get("GW_SHARE_DIR", "/share/garmin_wefly"))
CONVERTER = Path(__file__).resolve().parent / "fit_to_igc.py"
SHARE_TOKENS = SHARE / "tokens"
ARCHIVE = SHARE / "igc"
MFA_FILE = SHARE / "mfa_code.txt"
MAX_ATTEMPTS = 5
MFA_WAIT_SECONDS = 15 * 60
LOGIN_BACKOFF_SECONDS = 60 * 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("garmin_wefly")


# ---------------------------------------------------------------- helpers

class LoginError(RuntimeError):
    """Login bei Garmin gescheitert – nicht sofort erneut versuchen (Drosselung)."""


def load_options():
    return json.loads(OPTIONS.read_text())


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"since": None, "activities": {}}


def save_state(state):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE)


def notify(opts, title, message):
    """Persistente Benachrichtigung in Home Assistant."""
    if not opts.get("notify", True):
        return
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return
    try:
        requests.post(
            "http://supervisor/core/api/services/persistent_notification/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": title, "message": message},
            timeout=10,
        )
    except requests.RequestException as err:
        log.warning("HA-Benachrichtigung fehlgeschlagen: %s", err)


def install_extra_packages(opts):
    pkgs = [p for p in opts.get("pip_packages", []) if p.strip()]
    if pkgs:
        log.info("Installiere zusätzliche Pakete: %s", " ".join(pkgs))
        subprocess.run([sys.executable, "-m", "pip", "install", *pkgs], check=False)


def import_tokens_from_share():
    """Tokens, die am PC mit get_tokens.py erzeugt wurden, einmalig übernehmen."""
    if not SHARE_TOKENS.is_dir() or not any(SHARE_TOKENS.iterdir()):
        return
    TOKENS.mkdir(parents=True, exist_ok=True)
    for f in SHARE_TOKENS.iterdir():
        if f.is_file():
            shutil.copy2(f, TOKENS / f.name)
    done = SHARE / "tokens_imported"
    shutil.rmtree(done, ignore_errors=True)
    SHARE_TOKENS.rename(done)
    log.info("Garmin-Tokens aus %s übernommen.", SHARE_TOKENS)


def wait_for_mfa_code(opts):
    """Wird von garminconnect während des Logins aufgerufen, wenn Garmin einen Code verlangt.

    Der Code kommt per E-Mail/App und wird vom Nutzer in MFA_FILE geschrieben,
    z. B. im HA-Terminal: echo 123456 > /share/garmin_wefly/mfa_code.txt
    """
    msg = (
        f"Garmin verlangt einen Bestätigungscode. Schreib ihn innerhalb von "
        f"{MFA_WAIT_SECONDS // 60} Minuten in {MFA_FILE}, z. B. im Terminal: "
        f"echo 123456 > {MFA_FILE}"
    )
    log.warning(msg)
    notify(opts, "Garmin: Bestätigungscode nötig", msg)
    deadline = time.monotonic() + MFA_WAIT_SECONDS
    while time.monotonic() < deadline:
        if MFA_FILE.exists():
            code = "".join(MFA_FILE.read_text(errors="replace").split())
            MFA_FILE.unlink(missing_ok=True)
            if code:
                log.info("Bestätigungscode gelesen, melde an …")
                return code
        time.sleep(5)
    raise RuntimeError(f"Kein Bestätigungscode in {MFA_FILE} eingegangen")


def garmin_login(opts):
    TOKENS.mkdir(parents=True, exist_ok=True)
    MFA_FILE.unlink(missing_ok=True)  # alten Code nicht versehentlich verwenden
    email = opts.get("garmin_email") or None
    password = opts.get("garmin_password") or None
    client = Garmin(email, password, prompt_mfa=lambda: wait_for_mfa_code(opts))
    try:
        client.login(str(TOKENS))
    except Exception as err:  # noqa: BLE001 - Bibliothek wirft diverse Typen
        raise LoginError(
            f"Garmin-Login fehlgeschlagen ({err}). Nächster Versuch in "
            f"{LOGIN_BACKOFF_SECONDS // 60} Minuten oder nach Neustart des Add-ons."
        ) from err
    return client


def parse_gmt(value):
    return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)


def activity_matches(act, opts):
    type_key = ((act.get("activityType") or {}).get("typeKey") or "").lower()
    name = (act.get("activityName") or "").lower()
    types = [t.lower() for t in opts.get("activity_type_keys", []) if t.strip()]
    names = [n.lower() for n in opts.get("name_contains", []) if n.strip()]
    if not types and not names:
        return False  # ohne Filter wird sicherheitshalber nichts hochgeladen
    ok_type = not types or type_key in types
    ok_name = not names or any(n in name for n in names)
    return ok_type and ok_name


def download_fit(client, activity_id, target):
    data = client.download_activity(
        activity_id, dl_fmt=client.ActivityDownloadFormat.ORIGINAL
    )
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        fits = [n for n in zf.namelist() if n.lower().endswith(".fit")]
        if not fits:
            raise RuntimeError("Keine .fit-Datei im Garmin-Download gefunden")
        target.write_bytes(zf.read(fits[0]))


def convert(opts, fit_path, igc_path):
    custom = (opts.get("converter_cmd") or "").strip()
    if custom:
        cmd = custom.format(fit=shlex.quote(str(fit_path)), igc=shlex.quote(str(igc_path)))
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
    else:
        # Eingebauter Konverter (fit_to_igc.py liegt neben main.py)
        cmd = [sys.executable, str(CONVERTER), str(fit_path), "-o", str(igc_path),
               "--pilot", opts.get("pilot") or "", "--glider-type", opts.get("glider_type") or "",
               "--gnss-altitude", opts.get("gnss_altitude") or "gps"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if res.stdout.strip():
        log.info("Konverter: %s", res.stdout.strip()[-1000:])
    if res.returncode != 0:
        raise RuntimeError(f"Konverter-Fehler ({res.returncode}): {res.stderr.strip()[-1000:]}")
    if not igc_path.exists() or igc_path.stat().st_size == 0:
        raise RuntimeError("Konverter hat keine IGC-Datei erzeugt")
    text = igc_path.read_text(errors="replace")
    if not text.startswith("A") or "\nB" not in text:
        raise RuntimeError("IGC-Datei sieht ungültig aus (A-Record oder B-Records fehlen)")


def upload(opts, igc_path):
    key = opts.get("wefly_api_key") or ""
    if not key:
        raise RuntimeError("Kein We-Fly-API-Key konfiguriert")
    field = opts.get("wefly_file_field") or "file"
    with igc_path.open("rb") as fh:
        resp = requests.post(
            opts["wefly_upload_url"],
            headers={"Authorization": f"Bearer {key}"},
            files={field: (igc_path.name, fh, "application/octet-stream")},
            timeout=120,
        )
    # laut OpenAPI: 201 = neu angelegt, 200 = Flug existierte schon
    if resp.status_code == 200:
        return "Duplikat (schon auf We-Fly)"
    if resp.status_code in (401, 403):
        raise PermissionError(f"We-Fly lehnt den API-Key ab ({resp.status_code})")
    if resp.status_code >= 400:
        raise RuntimeError(f"We-Fly-Upload fehlgeschlagen ({resp.status_code}): {resp.text[:500]}")
    return "hochgeladen"


# ---------------------------------------------------------------- main loop

def process(client, opts, state):
    acts = client.get_activities(0, opts.get("lookback_activities", 20))

    if opts.get("list_activities", True):
        log.info("Letzte Aktivitäten (für die Filter-Einstellung):")
        for a in acts:
            log.info(
                "  id=%s  typeKey=%s  name=%r  start=%s",
                a.get("activityId"),
                (a.get("activityType") or {}).get("typeKey"),
                a.get("activityName"),
                a.get("startTimeLocal"),
            )

    since = dt.datetime.fromisoformat(state["since"])
    ARCHIVE.mkdir(parents=True, exist_ok=True)

    for act in sorted(acts, key=lambda a: a.get("startTimeGMT") or ""):
        aid = str(act.get("activityId"))
        entry = state["activities"].get(aid, {})
        if entry.get("status") in ("done", "failed"):
            continue
        if not act.get("startTimeGMT") or parse_gmt(act["startTimeGMT"]) < since:
            continue
        if not activity_matches(act, opts):
            continue

        name = act.get("activityName") or aid
        start = act.get("startTimeLocal", "").replace(":", "").replace(" ", "_")
        log.info("Verarbeite %s (%s)", name, aid)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                fit_path = Path(tmp) / f"{aid}.fit"
                suffix = "_baro" if opts.get("gnss_altitude") == "baro" else ""
                igc_path = Path(tmp) / f"{start}_{aid}{suffix}.igc"
                download_fit(client, act["activityId"], fit_path)
                convert(opts, fit_path, igc_path)
                shutil.copy2(igc_path, ARCHIVE / igc_path.name)
                if opts.get("dry_run"):
                    result = "Dry-Run: nur konvertiert, nicht hochgeladen"
                else:
                    result = upload(opts, igc_path)
            log.info("  -> %s", result)
            if not opts.get("dry_run"):
                state["activities"][aid] = {"status": "done", "result": result, "name": name}
                notify(opts, "We-Fly: Flug übertragen", f"{name} ({act.get('startTimeLocal')}): {result}")
        except PermissionError as err:
            log.error("  -> %s", err)
            notify(opts, "We-Fly: API-Key ungültig", str(err))
            return  # alle weiteren Uploads würden genauso scheitern
        except Exception as err:  # noqa: BLE001
            attempts = entry.get("attempts", 0) + 1
            status = "failed" if attempts >= MAX_ATTEMPTS else "retry"
            state["activities"][aid] = {"status": status, "attempts": attempts, "error": str(err), "name": name}
            log.error("  -> Fehler (Versuch %d/%d): %s", attempts, MAX_ATTEMPTS, err)
            if status == "failed":
                notify(opts, "We-Fly: Upload aufgegeben", f"{name}: {err}")
        finally:
            save_state(state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="nur ein Durchlauf, dann beenden")
    args = parser.parse_args()

    opts = load_options()
    state = load_state()
    install_extra_packages(opts)
    SHARE.mkdir(parents=True, exist_ok=True)

    # Neu berechnen beim ersten Start oder wenn upload_since geändert wurde
    since_option = opts.get("upload_since") or ""
    if not state.get("since") or state.get("since_option", since_option) != since_option:
        if since_option:
            since = dt.datetime.fromisoformat(opts["upload_since"])
            if since.tzinfo is None:
                since = since.replace(tzinfo=dt.timezone.utc)
        else:
            since = dt.datetime.now(dt.timezone.utc)
        state["since"] = since.isoformat()
        state["since_option"] = since_option
        save_state(state)
    log.info("Berücksichtige Flüge ab %s", state["since"])

    if not opts.get("activity_type_keys") and not opts.get("name_contains"):
        log.warning(
            "Kein Filter gesetzt (activity_type_keys / name_contains). "
            "Es wird nichts hochgeladen – schau in die Aktivitätsliste unten und setze einen Filter."
        )

    interval = int(opts.get("interval_minutes", 15)) * 60
    client = None
    while True:
        wait = interval
        try:
            import_tokens_from_share()
            if client is None:
                client = garmin_login(opts)
                log.info("Bei Garmin Connect angemeldet.")
            process(client, opts, state)
        except LoginError as err:
            log.error("%s", err)
            notify(opts, "Garmin-Login fehlgeschlagen", str(err))
            client = None
            wait = max(interval, LOGIN_BACKOFF_SECONDS)
            if args.once:
                sys.exit(1)
        except Exception as err:  # noqa: BLE001
            log.error("Durchlauf fehlgeschlagen: %s", err)
            if "429" in str(err) or "Too Many" in str(err):
                log.info("Garmin drosselt – warte zusätzlich 30 Minuten.")
                wait += 1800
            client = None  # beim nächsten Mal neu anmelden
            if args.once:
                sys.exit(1)
        if args.once:
            return
        time.sleep(wait)


if __name__ == "__main__":
    main()
