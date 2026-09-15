"""Conexión a Google Sheets y persistencia incremental de rechazos."""

from functools import lru_cache

import gspread
import pandas as pd
from gspread_dataframe import set_with_dataframe
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date

from app.config import CONFIG, info_credentials_gcp

def estandarizar_fechas(fecha):
    from datetime import datetime
    meses_es = {
        "ene": "01", "feb": "02", "mar": "03", "abr": "04", "may": "05", "jun": "06",
        "jul": "07", "ago": "08", "sep": "09", "oct": "10", "nov": "11", "dic": "12"
    }

    fecha = str(fecha).strip().lower()

    if pd.isnull(fecha) or fecha == 'nat' or fecha == '':
        return ''

    for mes, num in meses_es.items():
        if mes in fecha:
            fecha = fecha.replace(mes, num)
            break  # Solo reemplazamos el primer mes encontrado

    formatos = [
        "%Y-%m-%d",  # yyyy-mm-dd
        "%d-%m-%Y",  # dd-mm-yyyy
        "%d/%m/%Y",  # dd/mm/yyyy
        "%Y/%m/%d",  # yyyy/mm/dd
        "%d-%m-%y",  # dd-mm-yy
        "%d-%m-%Y",  # dd-mm-yyyy
        "%d %m %Y",
        "%m/%d/%Y",
        "%d/%m/%Y %H:%M:%S",  # dd/mm/yyyy hh:mm:ss
        "%d/%m/%y %H:%M:%S",  # dd/mm/yy hh:mm:ss
        "%d-%m-%Y %H:%M:%S",  # dd-mm-yyyy hh:mm:ss
        "%Y-%m-%d %H:%M:%S",  # yyyy-mm-dd hh:mm:ss
        "%d-%m-%y %H:%M:%S",  # dd-mm-yy hh:mm:ss
    ]

    for formato in formatos:
        try:
            fecha_obj = datetime.strptime(fecha, formato)
            return fecha_obj.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return ""

@lru_cache(maxsize=1)
def get_gspread_client():
    """Autoriza al primer uso; importar módulos no requiere credenciales GCP."""
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        info_credentials_gcp, scope
    )
    return gspread.authorize(creds)


def notificar_novedades(nuevos_registros):
    """Reemplaza la pestaña Novedades con los rechazos recién guardados."""
    try:
        spreadsheet = get_gspread_client().open_by_key(CONFIG["SHEET_ID"])
        worksheet = spreadsheet.worksheet("Novedades")
        worksheet.clear()
        set_with_dataframe(worksheet, nuevos_registros)

    except Exception as e:
        print(f"[ERROR GSPREAD] Al actualizar novedades: {e}")


def actualizar_metricas_pendientes(
    spreadsheet,
    df_actual: pd.DataFrame,
) -> None:

    worksheet = spreadsheet.worksheet("Metricas Pendientes")

    hoy = pd.Timestamp.now(tz="America/Mexico_City").date()

    fecha_hoy = hoy.isoformat()

    df = df_actual.copy()

    df["Vencimiento"] = pd.to_datetime(
        df["Vencimiento"],
        errors="coerce",
        dayfirst=True,
    )

    df["Dias_Vencimiento"] = (df["Vencimiento"].dt.date - hoy).apply(
        lambda x: x.days if pd.notna(x) else None
    )

    resumen = {
        "Fecha": fecha_hoy,
        "Pendientes": int(len(df)),
        "Vencidos": int((df["Dias_Vencimiento"] < 0).sum()),
        "<(-15) días": int((df["Dias_Vencimiento"] < -15).sum()),
        "(-6)-(-15) días": int(df["Dias_Vencimiento"].between(-15, -6).sum()),
        "(-1)-(-5) días": int(df["Dias_Vencimiento"].between(-5, -1).sum()),
        "0-5 días": int(df["Dias_Vencimiento"].between(0, 5).sum()),
        "6-15 días": int(df["Dias_Vencimiento"].between(6, 15).sum()),
        ">15 días": int((df["Dias_Vencimiento"] > 15).sum()),
    }

    df_metricas = pd.DataFrame(worksheet.get_all_records())

    if df_metricas.empty:

        df_metricas = pd.DataFrame([resumen])

        print(f"[METRICAS] Métricas del " f"{fecha_hoy} agregadas.")

    else:

        df_metricas["Fecha"] = pd.to_datetime(
            df_metricas["Fecha"],
            errors="coerce",
        ).dt.date.astype(str)

        mask_hoy = df_metricas["Fecha"] == fecha_hoy

        if mask_hoy.any():

            for columna, valor in resumen.items():
                df_metricas.loc[mask_hoy, columna] = valor

            print(f"[METRICAS] Métricas del " f"{fecha_hoy} actualizadas.")

        else:

            df_metricas = pd.concat(
                [
                    df_metricas,
                    pd.DataFrame([resumen]),
                ],
                ignore_index=True,
            )

            print(f"[METRICAS] Métricas del " f"{fecha_hoy} agregadas.")

    df_metricas["Fecha"] = pd.to_datetime(
        df_metricas["Fecha"],
        errors="coerce",
    )

    df_metricas = df_metricas.sort_values("Fecha").reset_index(drop=True)

    df_metricas["Fecha"] = df_metricas["Fecha"].dt.strftime("%Y-%m-%d").fillna("")

    columnas = [
        "Fecha",
        "Pendientes",
        "Vencidos",
        "<(-15) días",
        "(-6)-(-15) días",
        "(-1)-(-5) días",
        "0-5 días",
        "6-15 días",
        ">15 días",
    ]

    df_metricas = df_metricas.reindex(
        columns=columnas,
        fill_value=0,
    )

    set_with_dataframe(
        worksheet,
        df_metricas,
        include_index=False,
        resize=True,
    )


def procesar_datos_pendientes(
    df_pendientes: pd.DataFrame,
) -> pd.DataFrame | None:
    """Actualiza el reporte y devuelve nuevos registros, o None si falla."""

    try:
        spreadsheet = get_gspread_client().open_by_key(CONFIG["SHEET_ID"])
        worksheet = spreadsheet.worksheet("Pendientes")

        df_historico = pd.DataFrame(worksheet.get_all_records())

        df_actual = df_pendientes.copy()

        hoy = pd.Timestamp.now(tz="America/Mexico_City").date().isoformat()

        df_actual["FolioID"] = (
            df_actual["Folio"].astype(str).str.strip() + "-" + df_actual["Publicación"]
        )

        if df_historico.empty:
            df_actual["Primera deteccion"] = hoy
            df_actual["Ultima deteccion"] = hoy
            df_actual["Fecha salida"] = ""
            df_actual["Estado"] = "Pendiente"

            df_historico = df_actual.copy()
            df_nuevos = df_actual.copy()

        else:
            df_historico["FolioID"] = df_historico["FolioID"].astype(str).str.strip()

            ids_actuales = set(df_actual["FolioID"])
            ids_historicos = set(df_historico["FolioID"])

            pendientes_anteriores = (df_historico["Estado"] == "Pendiente").sum()

            if (
                pendientes_anteriores > 0
                and len(df_actual) < pendientes_anteriores * 0.5
            ):
                raise ValueError(
                    "El número de registros obtenidos es "
                    "anormalmente bajo. Se cancela la actualización "
                    "para evitar cierres masivos incorrectos."
                )

            df_nuevos = df_actual[~df_actual["FolioID"].isin(ids_historicos)].copy()

            if not df_nuevos.empty:
                df_nuevos["Primera deteccion"] = hoy
                df_nuevos["Ultima deteccion"] = hoy
                df_nuevos["Fecha salida"] = ""
                df_nuevos["Estado"] = "Pendiente"

                df_historico = pd.concat([df_historico, df_nuevos], ignore_index=True)

            mask_siguen_pendientes = df_historico["FolioID"].isin(ids_actuales)
            df_historico.loc[mask_siguen_pendientes, "Ultima deteccion"] = hoy
            df_historico.loc[mask_siguen_pendientes, "Fecha salida"] = ""
            df_historico.loc[mask_siguen_pendientes, "Estado"] = "Pendiente"

            mask_resueltos = ~df_historico["FolioID"].isin(ids_actuales) & (
                df_historico["Estado"] == "Pendiente"
            )
            df_historico.loc[mask_resueltos, "Fecha salida"] = hoy
            df_historico.loc[mask_resueltos, "Estado"] = "Atendido"

            columnas_actualizables = [
                "Folio",
                "Año",
                "Oficio CNBV",
                "Expediente",
                "Publicación",
                "Disponibilidad",
                "Plazo",
                "Vencimiento",
                "Area",
            ]

            df_actual_indexado = df_actual.set_index("FolioID")

            for columna in columnas_actualizables:

                mask = df_historico["FolioID"].isin(df_actual_indexado.index)

                df_historico.loc[mask, columna] = (
                    df_historico.loc[mask, "FolioID"]
                    .map(df_actual_indexado[columna])
                    .values
                )


        if not df_nuevos.empty:
            print(f"[DATOS] 💡 Se detectaron {len(df_nuevos)} pendientes nuevos.")

        print(f"[DATOS] Pendientes actuales: {len(df_actual)}")
        print(f"[DATOS] Histórico acumulado: {len(df_historico)}")

        columns = [
            "Folio",
            "Año",
            "Oficio CNBV",
            "Expediente",
            "Publicación",
            "Disponibilidad",
            "Plazo",
            "Vencimiento",
            "Area",
            "FolioID",
            "Primera deteccion",
            "Ultima deteccion",
            "Fecha salida",
            "Estado",
        ]

        df_historico = df_historico[columns]

        # Filtramos fechas desde el 2026 (por error en el portal SITI)
        df_historico["Vencimiento"] = df_historico["Vencimiento"].apply(estandarizar_fechas)
        df_historico["Vencimiento"] = pd.to_datetime(df_historico["Vencimiento"])
        df_historico = df_historico[df_historico["Vencimiento"] >= pd.to_datetime("2026-01-01")]

        set_with_dataframe(
            worksheet,
            df_historico,
            include_index=False,
            resize=True,
        )

        actualizar_metricas_pendientes(
            spreadsheet,
            df_actual,
        )

        return df_nuevos

    except Exception as e:

        print(f"[ERROR PROCESAMIENTO] {e}")

        return None


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
            df_nuevo["Folio"].astype(str)
            + "-"
            + df_nuevo["Fecha de rechazo"].astype(str)
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

        print(
            f"[DATOS] 💡 Se encontraron {len(nuevos_reales)} registros realmente nuevos."
        )
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
