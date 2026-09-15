"""Notificaciones de nuevos rechazos en Google Chat y Telegram."""

import requests

from app.config import CONFIG, URLS


def enviar_alerta_pendientes_error() -> bool:
    """Notifica al chat de datos que el reporte de pendientes falló durante su ejecución."""

    webhook = CONFIG.get("CHAT_WEBHOOK_DATA")

    if not webhook:
        print(
            "[WARN] Chat de datos sin configurar: "
            "falta CHAT_WEBHOOK_DATA. No se enviará la alerta de error."
        )
        return False

    mensaje = (
        "⚠️ Reporte de pendientes | Error de ejecución\n\n"
        "El proceso de actualización del reporte de pendientes "
        "finalizó con un error y requiere revisión.\n\n"
        f"<{URLS['SHEET_BASE']}|Abrir reporte de pendientes>"
    )

    try:
        response = requests.post(
            webhook,
            json={"text": mensaje},
            timeout=15,
        )

        if not response.ok:
            print(
                "[ERROR CHAT] Fallo al enviar la alerta de error de pendientes. "
                f"HTTP: {response.status_code}"
            )
            return False

    except requests.RequestException:
        print(
            "[ERROR CHAT] Fallo de conexión al enviar "
            "la alerta de error de pendientes."
        )
        return False

    print("[CHAT] Alerta de error de pendientes enviada exitosamente.")
    return True


def enviar_alerta_telegram(df_nuevos) -> bool:
    """Envía un resumen del lote guardado: total, cantidades por área y enlace."""
    if df_nuevos.empty:
        return False

    token = CONFIG.get("TELEGRAM_TOKEN")
    chat_id = CONFIG.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[WARN] Telegram sin configurar: falta TELEGRAM_TOKEN o TELEGRAM_CHAT_ID.")
        return False

    cantidades = df_nuevos["Area"].fillna("Sin área").value_counts()
    lineas = ["CNBV | Nuevos rechazos", f"Total guardados: {len(df_nuevos)}", ""]
    lineas.extend(f"• {area}: {cantidad}" for area, cantidad in cantidades.items())
    lineas.extend(["", f"Hoja de monitoreo: {URLS['SHEET_BASE']}"])
    try:

        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "\n".join(lineas),
                "link_preview_options": {"is_disabled": True},
            },
            timeout=15,
        )
        if response.status_code != 200:
            print(f"[ERROR TELEGRAM] Fallo al enviar resumen. HTTP: {response.status_code}")
            return False
        if response.json().get("ok") is not True:
            print("[ERROR TELEGRAM] La API no confirmó el envío del resumen.")
            return False
    except (requests.RequestException, ValueError):
        # Las excepciones HTTP pueden incluir la URL con el token del bot.
        print("[ERROR TELEGRAM] Fallo de conexión o respuesta inválida al enviar resumen.")
        return False

    print("[TELEGRAM] Resumen enviado exitosamente.")
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
