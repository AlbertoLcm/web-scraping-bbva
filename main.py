import asyncio
import pandas as pd
from datetime import datetime
from playwright.async_api import async_playwright
from io import StringIO
from html import escape
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import set_with_dataframe
import os
from dotenv import load_dotenv
import requests
import sys

load_dotenv()
# ================= CONFIGURACIÓN SEGURA =================
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
}

URLS = {
    "LOGIN": CONFIG['URL_LOGIN'],
    "CONSULTA": CONFIG['URL_CONSULTA'],
    "FUERA_SERVICIO": CONFIG['URL_FUERA_SERVICIO'],
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

# ================= CONEXIÓN GOOGLE SHEETS =================
def get_gspread_client():
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    creds = ServiceAccountCredentials.from_json_keyfile_dict(info_credentials_gcp, scope)
    
    return gspread.authorize(creds)

gc = get_gspread_client()

# ================= NOTIFICACIONES =================

def crear_mensajes_telegram(df_nuevos):
    """Resume los oficios por área y divide el texto sin romper el formato HTML."""
    if df_nuevos.empty:
        return []

    cantidad = len(df_nuevos)
    plural = "s" if cantidad != 1 else ""
    lineas = [
        ("🚨 ¡Nuevos Rechazos!", True),
        ("Origen: CNBV", False),
        (f"Se han guardado {cantidad} oficio{plural} nuevo{plural}:", False),
    ]
    for area, df_area in df_nuevos.groupby('Area', dropna=False):
        lineas.append((f"\n{area} ({len(df_area)}):", True))
        for oficio in df_area['Oficio CNBV']:
            lineas.append((f"• {oficio}", True))

    mensajes = []
    mensaje = []
    longitud = 0
    for texto, negrita in lineas:
        # Se divide antes de escapar HTML para conservar entidades y etiquetas.
        # 2000 caracteres ocupan como máximo 4000 unidades UTF-16.
        for inicio in range(0, len(texto), 2000):
            fragmento = texto[inicio:inicio + 2000]
            tamano = len(fragmento.encode('utf-16-le')) // 2
            separador = 1 if mensaje else 0
            if longitud + separador + tamano > 4096:
                mensajes.append("\n".join(mensaje))
                mensaje = []
                longitud = 0
                separador = 0
            contenido = escape(fragmento, quote=False)
            mensaje.append(f"<b>{contenido}</b>" if negrita else contenido)
            longitud += separador + tamano
    if mensaje:
        mensajes.append("\n".join(mensaje))
    return mensajes


def enviar_alerta_telegram(df_nuevos):
    """Envía el resumen de registros nuevos al chat configurado en Telegram."""
    if df_nuevos.empty:
        return

    token = CONFIG.get("TELEGRAM_TOKEN")
    chat_id = CONFIG.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[WARN] Falta TELEGRAM_TOKEN o TELEGRAM_CHAT_ID. No se enviará mensaje a Telegram.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for texto in crear_mensajes_telegram(df_nuevos):
        payload = {
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [[{
                    "text": "Abrir Hoja de Monitoreo",
                    "url": URLS['SHEET_MONITOREO'],
                }]],
            },
        }
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code != 200:
                print(f"[ERROR TELEGRAM] Fallo al enviar resumen. HTTP: {response.status_code}")
                return
            resultado = response.json()
            if not isinstance(resultado, dict) or resultado.get("ok") is not True:
                print("[ERROR TELEGRAM] La API no confirmó el envío del resumen.")
                return
            print("[TELEGRAM] Mensaje de resumen enviado exitosamente.")
        except requests.RequestException as e:
            # Las excepciones de requests pueden incluir la URL con el token.
            print(f"[ERROR TELEGRAM] Fallo de conexión al enviar resumen: {type(e).__name__}")
            return
        except ValueError:
            print("[ERROR TELEGRAM] La API devolvió una respuesta JSON inválida.")
            return


def enviar_alerta_chat(df_nuevos):
    """
    Envía un mensaje a Google Chat con el resumen de los datos nuevos.
    """
    webhook_data = CONFIG.get("CHAT_WEBHOOK_DATA")
    webhook_esp = CONFIG.get("CHAT_WEBHOOK_ESP")
    webhook_hac = CONFIG.get("CHAT_WEBHOOK_HAC")
    webhook_aseg = CONFIG.get("CHAT_WEBHOOK_ASEG")
    
    if not any([webhook_data, webhook_esp, webhook_hac, webhook_aseg]):
        print("[WARN] No hay URL de Webhook configurada. No se enviará mensaje a Chat.")
        return
    
    rutas_webhooks = {
        'Hacendario': [webhook_hac],
        'Operaciones Ilícitas': [webhook_esp, webhook_aseg], 
        'Aseguramiento': [webhook_aseg],
    }

    def despachar_mensaje(url, payload, nombre_area):
        if not url:
            return
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                print(f"[CHAT] Mensaje enviado exitosamente a {nombre_area}.")
            else:
                print(f"[ERROR CHAT] Fallo al enviar a {nombre_area}. HTTP: {response.status_code}")
        except Exception as e:
            print(f"[ERROR CHAT] Excepción al enviar webhook a {nombre_area}: {e}")

    oficios_por_area = {area: df_area for area, df_area in df_nuevos.groupby('Area')}

    for area, df_area in oficios_por_area.items():
        
        oficios = df_area.to_dict(orient='records')
        lineas = [f"<b>• {dato['Oficio CNBV']}</b> - {dato['Area']}" for dato in oficios]
        texto_oficios = "<br>".join(lineas)

        cantidad = len(oficios)
        texto_header = f"Se han guardado {cantidad} oficio{'s' if cantidad > 1 else ''} nuevo{'s' if cantidad > 1 else ''}:"

        payload_tarjeta = {
            "cardsV2": [{
                "cardId": f"alerta_{area}",
                "card": {
                    "header": {
                        "title": f"¡Nuevos Rechazos: {area}!",
                        "subtitle": "Origen: CNBV",
                        "imageUrl": "https://img.icons8.com/color/48/000000/high-importance--v1.png",
                        "imageType": "CIRCLE"
                    },
                    "sections": [{
                        "header": texto_header,
                        "widgets": [
                            {"textParagraph": {"text": texto_oficios}},
                            {"buttonList": {"buttons": [{
                                "text": "Abrir Hoja de Monitoreo", 
                                "onClick": {"openLink": {"url": URLS['SHEET_MONITOREO']}}
                            }]}}
                        ]
                    }]
                }
            }]
        }

        urls_destino = rutas_webhooks.get(area, [])
        
        if not urls_destino:
            print(f"[WARN] El área '{area}' no tiene webhooks asignados en las rutas.")
            continue

        for url in urls_destino:
            despachar_mensaje(url, payload_tarjeta, area)

def notificar_novedades(nuevos_registros):
    try:
        spreadsheet = gc.open_by_key(CONFIG['SHEET_ID'])
        worksheet = spreadsheet.worksheet('Novedades')
        
        worksheet.clear()
        set_with_dataframe(worksheet, nuevos_registros)
        print("[GSPREAD] Hoja 'Novedades' actualizada.")
        
    except Exception as e:
        print(f"[ERROR GSPREAD] Al actualizar novedades: {e}")

# ================= LÓGICA DE DATOS =================
def procesar_datos(df_nuevo):
    """
    Compara y guarda. Optimizado para append en lugar de overwrite total.
    """
    if df_nuevo.empty:
        print("[INFO] No se encontraron datos en el escaneo.")
        return

    try:
        spreadsheet = gc.open_by_key(CONFIG['SHEET_ID'])
        worksheet = spreadsheet.worksheet("Resultados")
        
        datos_existentes = worksheet.get_all_records()
        df_existente = pd.DataFrame(datos_existentes)
        
        df_existente['FolioID'] = df_existente['Folio'].astype(str) + "-" + df_existente['Fecha de rechazo']
        df_nuevo['FolioID'] = df_nuevo['Folio'].astype(str) + "-" + df_nuevo['Fecha de rechazo']

        col_id = "FolioID"
        nuevos_reales = pd.DataFrame()

        if not df_existente.empty and col_id in df_existente.columns and col_id in df_nuevo.columns:
            existentes_ids = set(df_existente[col_id].astype(str))
            nuevos_reales = df_nuevo[~df_nuevo[col_id].astype(str).isin(existentes_ids)]
        else:
            nuevos_reales = df_nuevo

        if not nuevos_reales.empty:
            print(f"[DATOS] 💡 Se encontraron {len(nuevos_reales)} registros realmente nuevos.")
            
            row_to_start = len(df_existente) + 2 
            set_with_dataframe(worksheet, nuevos_reales, row=row_to_start, include_column_header=False)
            
            print(f"[EXITO] ✅ Datos guardados.")
            
            notificar_novedades(nuevos_reales)

            enviar_alerta_telegram(nuevos_reales)
            enviar_alerta_chat(nuevos_reales)
        else:
            print("[INFO] zzz Los datos escaneados ya existen en la base.")

    except Exception as e:
        print(f"[ERROR PROCESAMIENTO] {e}")

# ================= AUTOMATIZACIÓN (PLAYWRIGHT) =================
async def extraer_datos_web():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Iniciando escaneo web...")
    data_list = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # --- LOGIN ---
            await page.goto(URLS["LOGIN"])
            await page.fill("#ctl00_DefaultPlaceholder_textBoxUser", CONFIG["CNBV_USER"])
            await page.fill("#ctl00_DefaultPlaceholder_textBoxPassword", CONFIG["CNBV_PASS"])
            
            async with page.expect_navigation():
                await page.click("input[type='submit']")

            # --- NAVEGACIÓN A CONSULTA ---
            await page.goto(URLS["CONSULTA"], wait_until="domcontentloaded", timeout=5_000)
            
            if URLS['FUERA_SERVICIO'] in page.url:
                print(f"[INFO] Portal Fuera de Horario de Operación.")
                return pd.DataFrame()
            
            areas = ['Hacendario', 'Judicial', 'Aseguramiento', 'Operaciones Ilícitas']
            
            for area in areas:
                print(f"--- Consultando: {area} ---")
                try:
                    await page.select_option("#ctl00_DefaultPlaceholder_ComboBoxAreas", label=area)
                    await page.select_option("#ctl00_DefaultPlaceholder_ComboBoxTipoRespuesta", label="Rechazos")
                    
                    # Creamos una promesa que espera a que haya una respuesta de red tras el click.
                    # Esto es vital en ASP.NET para asegurar que el servidor respondió antes de leer la tabla.
                    async with page.expect_response(lambda response: response.status == 200, timeout=10000) as response_info:
                        await page.get_by_role("button", name='Consultar').click()
                    
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

                    columnas = ["Check", "Folio", "Año", "Oficio CNBV", "Expediente", "ComentarioRechazo", "Fecha de rechazo", "Ver mas"]

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
                        
                        cols_to_drop = [c for c in ["Check", "Ver mas"] if c in dfs.columns]
                        dfs = dfs.drop(columns=cols_to_drop)
                        
                        data_list.append(dfs)
                        print(f"   [OK] {len(dfs)} registros extraídos.")
                    
                except Exception as e_area:
                    print(f"   [ERROR AREA] Fallo procesando {area}: {e_area}")
                    continue

        except Exception as e:
            print(f"[ERROR CRÍTICO] Fallo en navegación: {e}")
            await page.screenshot(path="error_login.png")
        
        finally:
            await browser.close()
    
    if data_list:
        return pd.concat(data_list, ignore_index=True)
    return pd.DataFrame()

# ================= BUCLE PRINCIPAL =================
async def main_loop():
    hora_actual = datetime.now()

    if hora_actual.weekday() >= 5:
        print(f"[{hora_actual}] Es fin de semana en CDMX. Deteniendo ejecución.")
        sys.exit(0)

    print(f"[{hora_actual}] Ejecutando web scraping...")

    try:
        df_resultado = await extraer_datos_web()
        
        if not df_resultado.empty:
            procesar_datos(df_resultado)
        
    except KeyboardInterrupt:
        print("\nBot detenido por usuario.")
    except Exception as e:
        print(f"[ERROR GLOBAL] {e}")

if __name__ == "__main__":
    asyncio.run(main_loop())
