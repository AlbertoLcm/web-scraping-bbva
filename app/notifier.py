"""Notificaciones de nuevos rechazos en Google Chat y Telegram."""

from html import escape

import requests

from app.config import CONFIG, URLS


def _enviar_mensaje_telegram(texto: str, texto_boton: str, url_boton: str) -> bool:
    """Envía un mensaje de Telegram con formato HTML y un botón de acción."""

    token = CONFIG.get("TELEGRAM_TOKEN")
    chat_id = CONFIG.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[WARN] Telegram sin configurar: falta TELEGRAM_TOKEN o TELEGRAM_CHAT_ID.")
        return False

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": texto,
                "parse_mode": "HTML",
                "link_preview_options": {"is_disabled": True},
                "reply_markup": {
                    "inline_keyboard": [[{
                        "text": texto_boton,
                        "url": url_boton,
                    }]],
                },
            },
            timeout=15,
        )
        if response.status_code != 200:
            print(f"[ERROR TELEGRAM] Fallo al enviar mensaje. HTTP: {response.status_code}")
            return False
        if response.json().get("ok") is not True:
            print("[ERROR TELEGRAM] La API no confirmó el envío del mensaje.")
            return False
    except (requests.RequestException, ValueError):
        # Las excepciones HTTP pueden incluir la URL con el token del bot.
        print("[ERROR TELEGRAM] Fallo de conexión o respuesta inválida al enviar mensaje.")
        return False

    return True


def enviar_alerta_pendientes_error() -> bool:
    """Notifica por Telegram que el reporte de pendientes falló durante su ejecución."""

    mensaje = (
        "⚠️ <b>Reporte de pendientes con error</b>\n"
        "━━━━━━━━━━━━━━\n"
        "<i>Origen: CNBV</i>\n\n"
        "<b>Se requiere revisión</b>\n"
        "El proceso de actualización finalizó con un error.\n\n"
        "📌 Consulta el reporte para identificar el incidente."
    )

    if not _enviar_mensaje_telegram(
        mensaje,
        "Abrir Hoja de Monitoreo",
        URLS["SHEET_BASE"],
    ):
        return False

    print("[TELEGRAM] Alerta de error de pendientes enviada exitosamente.")
    return True


def enviar_alerta_telegram(df_nuevos) -> bool:
    """Envía una alerta visual por área con sus oficios y acceso al monitoreo."""
    if df_nuevos.empty:
        return False

    datos_por_area = df_nuevos.assign(Area=df_nuevos["Area"].fillna("Sin área"))
    for area, df_area in datos_por_area.groupby("Area", sort=False):
        oficios = df_area.get("Oficio CNBV")
        lineas_oficios = (
            [f"• <b>{escape(str(oficio))}</b>" for oficio in oficios]
            if oficios is not None
            else ["• <i>Sin número de oficio</i>"]
        )
        texto_oficios = "\n".join(lineas_oficios)
        cantidad = len(df_area)
        plural = "s" if cantidad != 1 else ""
        area_segura = escape(str(area))
        mensaje = (
            f"🚨 <b>Nuevos rechazos: {area_segura}</b>\n"
            "━━━━━━━━━━━━━━\n"
            "<i>Origen: CNBV</i>\n\n"
            f"<b>Se ha{'' if cantidad == 1 else 'n'} guardado {cantidad} "
            f"oficio{plural} nuevo{plural}</b>\n\n"
            f"{texto_oficios}\n\n"
            "📌 Consulta el detalle completo en la hoja de monitoreo."
        )

        if not _enviar_mensaje_telegram(
            mensaje,
            "Abrir Hoja de Monitoreo",
            URLS["SHEET_MONITOREO"],
        ):
            return False

    print("[TELEGRAM] Alertas enviadas exitosamente.")
    return True


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
