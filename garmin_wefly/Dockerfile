# garminconnect braucht Python >= 3.12 und curl_cffi (glibc-Wheels),
# deshalb das offizielle Python-Image statt des Alpine-Basisimages von HA.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# fitdecode/fitparse sind vorinstalliert, damit dein Konverter sie direkt nutzen kann.
RUN pip install garminconnect curl_cffi requests fitdecode fitparse

COPY main.py fit_to_igc.py /app/

CMD ["python3", "/app/main.py"]
