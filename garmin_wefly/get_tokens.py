#!/usr/bin/env python3
"""Einmalig am PC ausführen, falls dein Garmin-Konto MFA nutzt.

    pip install garminconnect curl_cffi
    python get_tokens.py

Danach den erzeugten Ordner "tokens" nach /share/garmin_wefly/tokens
auf dem Home-Assistant-Pi kopieren (z. B. per Samba-Add-on) und das Add-on neu starten.
"""
import getpass

from garminconnect import Garmin

email = input("Garmin-E-Mail: ").strip()
password = getpass.getpass("Garmin-Passwort: ")

client = Garmin(email, password, prompt_mfa=lambda: input("MFA-Code: ").strip())
client.login("./tokens")
print("Fertig. Tokens liegen in ./tokens – diesen Ordner nach /share/garmin_wefly/tokens kopieren.")
