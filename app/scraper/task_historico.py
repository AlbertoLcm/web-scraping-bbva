"""Extracción de oficios publicados por fecha y área."""

from datetime import datetime
from typing import List, Optional

import pandas as pd
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from app.config import AREAS, MAP_CLASIFICACION_OFICIOS, TIMEZONE, URLS
from app.scraper.cnbv_client import abrir_sesion_cnbv


async def extraer_datos_tabla_js(page: Page) -> pd.DataFrame:
    """
    Extrae la tabla completa usando JavaScript puro para máxima velocidad.
    Retorna un DataFrame de Pandas inicializado.
    """
    js_script = """
        () => {
            const rows = document.querySelectorAll('#ctl00_DefaultPlaceholder_GridResult tr');
            const data = [];
            for (let i = 1; i < rows.length; i++) {
                const tds = rows[i].querySelectorAll('td');
                if (tds.length < 13) continue;

                const link1 = tds[10].querySelector('a');
                const link2 = tds[11].querySelector('a');
                const link3 = tds[12].querySelector('a');

                data.push({
                    row_index: i + 1,
                    "Oficio Autoridad": tds[5].innerText.trim(),
                    Expediente: tds[6].innerText.trim(),
                    Publicacion: tds[7].innerText.trim(),
                    Plazo: tds[9].innerText.trim(),
                    URL_oficio: link1 ? link1.href : "",
                    URL_req:    link2 ? link2.href : "",
                    URL_xml:    link3 ? link3.href : "",
                });
            }
            return data;
        }
    """

    datos_crudos = await page.evaluate(js_script)
    df = pd.DataFrame(datos_crudos)

    if not df.empty:
        df["Expediente Corto"] = df["Expediente"].apply(
            lambda x: x[-10:] if isinstance(x, str) and len(x) >= 10 else x
        )
        df["Clasificacion"] = df["Expediente"].apply(
            lambda x: MAP_CLASIFICACION_OFICIOS.get(x[2:4], "Sin Clasificación")
            if isinstance(x, str) and len(x) >= 4
            else "Sin Clasificación"
        )
        for col in ["Oficio", "Req", "XML"]:
            if col not in df.columns:
                df[col] = "PENDIENTE"
        for col in ["Archivo Oficio", "Archivo Req", "Archivo XML"]:
            if col not in df.columns:
                df[col] = ""

    return df


async def ejecutar_extraccion_publicados(page: Page, date_start: datetime, date_end: datetime) -> pd.DataFrame:
    """
    Extrae todos los oficios publicados por fecha seleccionada de todas las áreas
    Consultado el apartado Requerimientos / Publicados
    """

    if not isinstance(date_start, datetime) or not isinstance(date_end, datetime):
        print("[ERROR] Las fechas proporcionadas no son objetos datetime válidos.")
        return pd.DataFrame()

    if date_start > date_end:
        print("[ERROR] La fecha de inicio no puede ser mayor que la fecha de fin.")
        return pd.DataFrame()


    date_start_str = date_start.strftime("%Y-%m-%d")
    date_end_str = date_end.strftime("%Y-%m-%d")


    try:
        await page.goto(URLS['PUBLICADOS'], wait_until="domcontentloaded", timeout=5_000)

        dataframes_por_area: List[pd.DataFrame] = []

        for area in AREAS:
            print(f"--- Consultando: {area} ---")
            await page.select_option("#ctl00_DefaultPlaceholder_ComboBoxAreas", label=area)
            await page.select_option("#ctl00_DefaultPlaceholder_ComboBoxEstatusOficio", label="Todos")
            await page.fill("#ctl00_DefaultPlaceholder_TextFechaPublicacion1", date_start_str)
            await page.fill("#ctl00_DefaultPlaceholder_TextFechaPublicacion2", date_end_str)
            await page.get_by_role("button", name="Consultar").click()

            try:
                await page.wait_for_selector("#ctl00_DefaultPlaceholder_GridResult", timeout=30_000)
                print(f"[SUCCESS] Tabla consultada: {area}")

                try:
                    await page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:
                    pass

                # Esperar a que la tabla se estabilice
                filas_locator = page.locator("#ctl00_DefaultPlaceholder_GridResult tr")
                conteo_previo = 0
                estabilidad = 0
                max_intentos = 30
                intentos = 0
                while estabilidad < 5 and intentos < max_intentos:
                    await page.wait_for_timeout(1000)
                    conteo_actual = await filas_locator.count()
                    if conteo_actual == conteo_previo and conteo_actual > 1:
                        estabilidad += 1
                    else:
                        estabilidad = 0
                        conteo_previo = conteo_actual
                    intentos += 1

            except PlaywrightTimeoutError:
                print(f"    No se encontraron datos para '{area}'. Continuando con la siguiente área.")
                continue

            df_area = await extraer_datos_tabla_js(page)
            if df_area.empty:
                print(f"    No se encontraron registros para '{area}'.")
                continue

            df_area["Area"] = area
            dataframes_por_area.append(df_area)
            print(f"    Oficios totales: {len(df_area)} preparados.")

        if not dataframes_por_area:
            print("[INFO] No se encontraron registros en ninguna de las áreas seleccionadas.")
            return pd.DataFrame()

        df_resultado = pd.concat(dataframes_por_area, ignore_index=True)

        return df_resultado

    except Exception as e:
        print(f"[ERROR CRÍTICO] Fallo en navegación o extracción: {e}")
        return pd.DataFrame()


async def ejecutar_extraccion_historica(
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
) -> pd.DataFrame:
    """Consulta el día actual en CDMX, o el intervalo proporcionado."""
    if date_start is None:
        date_start = datetime.now(TIMEZONE)
    if date_end is None:
        date_end = date_start
    async with abrir_sesion_cnbv() as page:
        if page is None:
            return pd.DataFrame()
        return await ejecutar_extraccion_publicados(page, date_start, date_end)
