"""Inicio de sesión y ciclo de vida del navegador CNBV."""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from app.config import CONFIG, URLS


async def load_page_siti(context: BrowserContext, user: str, password: str) -> Optional[Page]:
    """
    Carga la pagina principal de SITI.
    Realiza un manejo de Login y retorna el elemento PAGE
    """
    page = await context.new_page()
    try:
        await page.goto(URLS["LOGIN"], wait_until="domcontentloaded", timeout=10_000)
        await page.fill("#ctl00_DefaultPlaceholder_textBoxUser", user)
        await page.fill("#ctl00_DefaultPlaceholder_textBoxPassword", password)
        async with page.expect_navigation():
            await page.click("input[type='submit']")

        if URLS['FUERA_SERVICIO'] and URLS['FUERA_SERVICIO'] in page.url:
            print("[INFO] Portal Fuera de Horario de Operación.")
            return None

        return page

    except PlaywrightTimeoutError:
        print("[ERROR] Timeout al cargar la página o al hacer login.")
        return None
    except Exception as e:
        print(f"[ERROR] Excepción inesperada al cargar la página: {e}")
        return None


@asynccontextmanager
async def abrir_sesion_cnbv(*, headless: bool = True) -> AsyncIterator[Optional[Page]]:
    """Abre una sesión y cierra el navegador incluso si falla una tarea."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        try:
            context = await browser.new_context()
            page = await load_page_siti(context, CONFIG["CNBV_USER"], CONFIG["CNBV_PASS"])
            yield page
        finally:
            await browser.close()
