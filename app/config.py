"""Configuración compartida, cargada antes de consultar el entorno."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

TIMEZONE = ZoneInfo("America/Mexico_City")

CONFIG = {
    "SHEET_ID": os.getenv("SHEET_ID"),
    "SHEET_ID_MONITOREO": os.getenv("SHEET_ID_MONITOREO"),
    "CNBV_USER": os.getenv("CNBV_USER"),
    "CNBV_PASS": os.getenv("CNBV_PASS"),
    "URL_LOGIN": os.getenv("URL_LOGIN"),
    "URL_CONSULTA": os.getenv("URL_CONSULTA"),
    "URL_FUERA_SERVICIO": os.getenv("URL_FUERA_SERVICIO"),
    "CHAT_WEBHOOK_DATA": os.getenv("CHAT_WEBHOOK_DATA"),
    "CHAT_WEBHOOK_ESP": os.getenv("CHAT_WEBHOOK_ESP"),
    "CHAT_WEBHOOK_HAC": os.getenv("CHAT_WEBHOOK_HAC"),
    "CHAT_WEBHOOK_ASEG": os.getenv("CHAT_WEBHOOK_ASEG"),
    "TELEGRAM_TOKEN": os.getenv("TELEGRAM_TOKEN"),
    "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID"),
    "URL_PUBLICADOS": os.getenv("URL_PUBLICADOS"),
    "URL_ENVIO_RESPUESTAS": os.getenv("URL_ENVIO_RESPUESTAS"),
}

URLS = {
    "LOGIN": CONFIG['URL_LOGIN'],
    "CONSULTA": CONFIG['URL_CONSULTA'],
    "PUBLICADOS": CONFIG['URL_PUBLICADOS'],
    "FUERA_SERVICIO": CONFIG['URL_FUERA_SERVICIO'],
    "ENVIO_RESPUESTAS": CONFIG['URL_ENVIO_RESPUESTAS'],
    "SHEET_BASE": f"https://docs.google.com/spreadsheets/d/{CONFIG['SHEET_ID']}",
    "SHEET_MONITOREO": f"https://docs.google.com/spreadsheets/d/{CONFIG['SHEET_ID_MONITOREO']}"
}

info_credentials_gcp = {
    "type": os.getenv("GCP_TYPE"),
    "project_id": os.getenv("GCP_PROJECT_ID"),
    "private_key_id": os.getenv("GCP_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GCP_PRIVATE_KEY").replace('\\n', '\n') if os.getenv("GCP_PRIVATE_KEY") else None,
    "client_email": os.getenv("GCP_CLIENT_EMAIL"),
    "client_id": os.getenv("GCP_CLIENT_ID"),
    "auth_uri": os.getenv("GCP_AUTH_URI"),
    "token_uri": os.getenv("GCP_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("GCP_AUTH_PROVIDER_X509_CERT_URL"),
    "client_x509_cert_url": os.getenv("GCP_CLIENT_X509_CERT_URL"),
    "universe_domain": os.getenv("GCP_UNIVERSE_DOMAIN"),
}

AREAS = ['Hacendario', 'Judicial', 'Aseguramiento', 'Operaciones Ilícitas']
SELECT_RESPUESTAS = ["Escrito de Respuesta", "Rechazos"]

MAP_CLASIFICACION_OFICIOS = {
    "DE": "Desbloqueo",
    "TF": "Transferencia o Situación de fondos",
    "AS": "Aseguramiento",
    "AR": "Amparo",
}
