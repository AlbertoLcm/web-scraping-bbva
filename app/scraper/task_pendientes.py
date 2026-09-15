"""Consulta de escritos de respuesta y rechazos pendientes por área."""

import asyncio

import pandas as pd
from playwright.async_api import Page

from app.config import AREAS, URLS
from app.database import procesar_datos_pendientes
from app.notifier import enviar_alerta_pendientes_error
from app.scraper.cnbv_client import abrir_sesion_cnbv


async def ejecutar_extraccion_pendientes(page: Page) -> pd.DataFrame:
    """
    Extrae todos los oficios pendientes de todas las áreas
    Consultado el apartado Envio de respuestas en linea.
    """
    pendientes_list = []

    try:
        await page.goto(URLS["PENDIENTES"], wait_until="domcontentloaded", timeout=5_000)

        for area in AREAS:
            print(f"--- Consultado: {area}")
            await page.select_option("#ctl00_DefaultPlaceholder_ComboBoxAreas", label=area)

            try:
                # Creamos una promesa que espera a que haya una respuesta de red tras el click.
                # Esto es vital en ASP.NET para asegurar que el servidor respondió antes de leer la tabla.
                async with page.expect_response(lambda response: response.status == 200, timeout=180_000):
                    await page.get_by_role("button", name='Consultar').click(timeout=180_000)

                await asyncio.sleep(0.5)

                try:
                    await page.wait_for_function(
                            """() => {
                                const rows = document.querySelectorAll("#ctl00_DefaultPlaceholder_GridResult tr");
                                return rows.length >= 2;
                            }""",
                            timeout=1_000
                        )

                except Exception:
                    print(f"   [WARN] Tabla {area} sin datos.")
                    continue

                columnas = ["Situacion", "Desc", "Folio", "Año", "Oficio CNBV", "Expediente", "Publicación", "Disponibilidad", "Plazo", "Vencimiento"]

                datos_tabla = await page.evaluate(
                    """() => {
                        const rows = Array.from(document.querySelectorAll("#ctl00_DefaultPlaceholder_GridResult tbody tr")).slice(1);
                        return rows.map(tr => {
                            const celdas = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
                            return celdas;
                        });
                    }""",
                )

                if datos_tabla:
                    dfs = pd.DataFrame(datos_tabla, columns=columnas)

                    dfs['Area'] = area
                    cols_to_drop = [c for c in ["Situacion", "Desc"] if c in dfs.columns]
                    dfs = dfs.drop(columns=cols_to_drop)

                    pendientes_list.append(dfs)
                    print(f"   [OK] {len(dfs)} registros extraídos.")

            except Exception as e_area:
                print(f"   [ERROR AREA] Fallo procesando {area}: {e_area}")
                return pd.DataFrame()

    except Exception as e:
        print(f"[ERROR CRÍTICO] Fallo en navegación: {e}")
        return pd.DataFrame()

    if pendientes_list:
        return pd.concat(pendientes_list, ignore_index=True)

    return pd.DataFrame()


async def ejecutar_monitoreo_pendientes() -> pd.DataFrame:
    """Extrae pendientes, actualiza el reporte y avisa por Google Chat."""
    async with abrir_sesion_cnbv() as page:
        if page is None:
            return pd.DataFrame()
        df_pendientes = await ejecutar_extraccion_pendientes(page)

    if not df_pendientes.empty:
        _ = procesar_datos_pendientes(df_pendientes)
    else:
        print("[ERROR] No se pudo procesar correctamente. Ejecución detenida")
        enviar_alerta_pendientes_error()

    return df_pendientes
