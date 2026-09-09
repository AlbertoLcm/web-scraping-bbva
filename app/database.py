"""Conexión a Google Sheets y persistencia incremental de rechazos."""

from functools import lru_cache

import gspread
import pandas as pd
from gspread_dataframe import set_with_dataframe
from oauth2client.service_account import ServiceAccountCredentials

from app.config import CONFIG, info_credentials_gcp


@lru_cache(maxsize=1)
def get_gspread_client():
    """Autoriza al primer uso; importar módulos no requiere credenciales GCP."""
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(info_credentials_gcp, scope)
    return gspread.authorize(creds)


def notificar_novedades(nuevos_registros):
    """Reemplaza la pestaña Novedades con los rechazos recién guardados."""
    try:
        spreadsheet = get_gspread_client().open_by_key(CONFIG["SHEET_ID"])
        worksheet = spreadsheet.worksheet("Novedades")
        worksheet.clear()
        set_with_dataframe(worksheet, nuevos_registros)
        print("[GSPREAD] Hoja 'Novedades' actualizada.")
    except Exception as e:
        print(f"[ERROR GSPREAD] Al actualizar novedades: {e}")


def procesar_datos(df_nuevo: pd.DataFrame) -> pd.DataFrame:
    """Guarda rechazos nuevos por Folio-fecha y los devuelve para notificar."""
    if df_nuevo.empty:
        print("[INFO] No se encontraron datos en el escaneo.")
        return pd.DataFrame()

    try:
        spreadsheet = get_gspread_client().open_by_key(CONFIG["SHEET_ID"])
        worksheet = spreadsheet.worksheet("Resultados")
        df_existente = pd.DataFrame(worksheet.get_all_records())
        df_nuevo = df_nuevo.copy()
        df_nuevo["FolioID"] = (
            df_nuevo["Folio"].astype(str) + "-" + df_nuevo["Fecha de rechazo"].astype(str)
        )

        if not df_existente.empty:
            existentes_ids = set(
                df_existente["Folio"].astype(str)
                + "-"
                + df_existente["Fecha de rechazo"].astype(str)
            )
            nuevos_reales = df_nuevo[~df_nuevo["FolioID"].isin(existentes_ids)]
        else:
            nuevos_reales = df_nuevo

        nuevos_reales = nuevos_reales.drop_duplicates(subset="FolioID")
        if nuevos_reales.empty:
            print("[INFO] zzz Los datos escaneados ya existen en la base.")
            return nuevos_reales

        print(f"[DATOS] 💡 Se encontraron {len(nuevos_reales)} registros realmente nuevos.")
        set_with_dataframe(
            worksheet,
            nuevos_reales,
            row=1 if df_existente.empty else len(df_existente) + 2,
            include_column_header=df_existente.empty,
        )
        print("[EXITO] ✅ Datos guardados.")
        notificar_novedades(nuevos_reales)
        return nuevos_reales
    except Exception as e:
        print(f"[ERROR PROCESAMIENTO] {e}")
        return pd.DataFrame()
