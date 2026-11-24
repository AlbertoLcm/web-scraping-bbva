"""Consulta de escritos de respuesta y rechazos pendientes por área."""

import asyncio

import pandas as pd
from playwright.async_api import Page

from app.config import AREAS, URLS
from app.database import procesar_datos_pendientes
from app.notifier import enviar_alerta_pendientes_error
from app.scraper.cnbv_client import abrir_sesion_cnbv


async def _consultar_tabla(
    page: Page,
    area: str,
    columnas: list[str],
    tipo_respuesta: str | None = None,
) -> pd.DataFrame:
    """Ejecuta una consulta y devuelve sus filas, o propaga su error."""
    print(f"--- Consultando: {area}")
    await page.select_option("#ctl00_DefaultPlaceholder_ComboBoxAreas", label=area)
    if tipo_respuesta is not None:
        await page.select_option(
            "#ctl00_DefaultPlaceholder_ComboBoxTipoRespuesta",
            label=tipo_respuesta,
        )

    async with page.expect_response(
        lambda response: response.status == 200,
        timeout=180_000,
    ):
        await page.get_by_role("button", name="Consultar").click(timeout=180_000)

    # La tabla debe existir; que no haya filas es una consulta válida.
    await page.wait_for_selector(
        "#ctl00_DefaultPlaceholder_GridResult",
        state="attached",
        timeout=180_000,
    )
    await asyncio.sleep(0.5)
    datos_tabla = await page.evaluate(
        """() => Array.from(
            document.querySelectorAll("#ctl00_DefaultPlaceholder_GridResult tbody tr")
        ).slice(1).map(tr => Array.from(tr.querySelectorAll("td"))
            .map(td => td.innerText.trim()))""",
    )

    # También valida que el portal conserve el número esperado de columnas.
    df = pd.DataFrame(datos_tabla, columns=columnas)
    mensaje = "sin registros" if df.empty else f"{len(df)} registros extraídos"
    print(f"   [OK] {area}: {mensaje}.")
    return df


async def ejecutar_extraccion_pendientes(page: Page) -> pd.DataFrame:
    """Extrae pendientes y escritos de respuesta; falla de forma atómica."""
    columnas_pendientes = [
        "Situacion", "Desc", "Folio", "Año", "Oficio CNBV", "Expediente",
        "Publicación", "Disponibilidad", "Plazo", "Vencimiento",
    ]
    columnas_respuestas = [
        "Check", "Folio", "Año", "Oficio CNBV", "Expediente", "ComentarioRechazo",
    ]
    pendientes_list: list[pd.DataFrame] = []
    respuestas_list: list[pd.DataFrame] = []

    await page.goto(URLS["PENDIENTES"], wait_until="domcontentloaded", timeout=5_000)
    for area in AREAS:
        try:
            df = await _consultar_tabla(page, area, columnas_pendientes)
        except Exception as exc:
            raise RuntimeError(f"Falló la consulta de pendientes para {area}") from exc
        if not df.empty:
            df["Area"] = area
            pendientes_list.append(df.drop(columns=["Situacion", "Desc"]))

    await page.goto(URLS["ENVIO_RESPUESTAS"], wait_until="domcontentloaded", timeout=5_000)
    for area in AREAS:
        try:
            df = await _consultar_tabla(
                page,
                area,
                columnas_respuestas,
                tipo_respuesta="Escrito de Respuesta",
            )
        except Exception as exc:
            raise RuntimeError(f"Falló la consulta de escritos de respuesta para {area}") from exc
        if not df.empty:
            df["Area"] = area
            respuestas_list.append(df.drop(columns=["Check", "ComentarioRechazo"]))

    pendientes_df = (
        pd.concat(pendientes_list, ignore_index=True)
        if pendientes_list
        else pd.DataFrame(columns=["Folio", "Año", "Oficio CNBV", "Expediente", "Publicación", "Disponibilidad", "Plazo", "Vencimiento", "Area"])
    )
    respuestas_df = (
        pd.concat(respuestas_list, ignore_index=True)
        if respuestas_list
        else pd.DataFrame(columns=["Folio", "Año", "Oficio CNBV", "Expediente", "Area"])
    )
    return pendientes_df[pendientes_df["Oficio CNBV"].isin(respuestas_df["Oficio CNBV"])]


async def ejecutar_monitoreo_pendientes() -> pd.DataFrame:
    """Extrae pendientes, actualiza el reporte y avisa por Google Chat."""
    try:
        async with abrir_sesion_cnbv() as page:
            if page is None:
                raise RuntimeError("No fue posible abrir sesión en CNBV")
            df_pendientes = await ejecutar_extraccion_pendientes(page)
    except Exception:
        # La alerta no puede ocultar el error original de la consulta.
        try:
            enviar_alerta_pendientes_error()
        except Exception as alerta_error:
            print(f"[ERROR ALERTA] No se pudo enviar la alerta: {alerta_error}")
        raise

    if not df_pendientes.empty:
        resultado = procesar_datos_pendientes(df_pendientes)
        if resultado is None:
            raise RuntimeError("Falló la actualización del reporte de pendientes")
    else:
        print("[INFO] Consulta completada sin pendientes con escrito de respuesta.")

    return df_pendientes
