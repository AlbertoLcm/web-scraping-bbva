# CNBV Web Scraping & Monitoreo de Rechazos

Este proyecto es un bot automatizado de Web Scraping desarrollado en **Python** que monitorea, extrae y gestiona el registro de **Rechazos** de oficios del portal de la **CNBV (Comisión Nacional Bancaria y de Valores)**. Los datos se procesan, se guardan de forma incremental en **Google Sheets** y se envían notificaciones en tiempo real a diferentes salas de **Google Chat** según el área de procedencia.

---

## Características Principales

*   **Scraping Automatizado con Playwright**: Navegación e inicio de sesión seguro y consulta por áreas en segundo plano (Headless Mode).
*   **Segmentación por Áreas**: Consulta los rechazos para las áreas de:
    *   `Hacendario`
    *   `Judicial`
    *   `Aseguramiento`
    *   `Operaciones Ilícitas`
*   **Base de Datos en Google Sheets**: Guarda los registros de manera inteligente (evitando duplicados utilizando un ID compuesto de `Folio-Fecha de rechazo`).
*   **Notificaciones Dinámicas (Google Chat)**: Envía tarjetas visuales e interactivas directamente a los webhooks correspondientes de cada equipo en Google Chat.
*   **Contenerización con Docker & Tini**: Preparado para producción usando una imagen base optimizada de Playwright y `tini` como init process para evitar procesos zombis.

---

## Variables de Entorno (`.env`)

Crea un archivo `.env` en la raíz del proyecto con la siguiente estructura:

```env
# --- Credenciales CNBV ---
CNBV_USER=tu_usuario_cnbv
CNBV_PASS=tu_contraseña_cnbv
URL_LOGIN=URL_LOGIN
URL_CONSULTA=URL_CONSULTA
URL_FUERA_SERVICIO=URL_FUERA_SERVICIO
URL_PUBLICADOS=URL_PUBLICADOS
URL_ENVIO_RESPUESTAS=URL_ENVIO_RESPUESTAS

# --- Hojas de Google Sheets ---
SHEET_ID=id_de_la_hoja_de_calculo_principal
SHEET_ID_MONITOREO=id_de_la_hoja_de_monitoreo

# --- Webhooks de Google Chat ---
CHAT_WEBHOOK_DATA=https://chat.googleapis.com/v1/spaces/...
CHAT_WEBHOOK_ESP=https://chat.googleapis.com/v1/spaces/...
CHAT_WEBHOOK_HAC=https://chat.googleapis.com/v1/spaces/...
CHAT_WEBHOOK_ASEG=https://chat.googleapis.com/v1/spaces/...

# --- Telegram (resumen de rechazos nuevos) ---
TELEGRAM_TOKEN=token_del_bot
TELEGRAM_CHAT_ID=id_del_chat

# --- Credenciales GCP Service Account ---
GCP_TYPE=service_account
GCP_PROJECT_ID=tu_proyecto_gcp
GCP_PRIVATE_KEY_ID=tu_private_key_id
GCP_PRIVATE_KEY="TU_PRIVATE_KEY"
GCP_CLIENT_EMAIL="tu-cuenta-de-servicio@tu-proyecto.iam.gserviceaccount.com"
GCP_CLIENT_ID=TU_CLIENT_ID
GCP_AUTH_URI=https://accounts.google.com/o/oauth2/auth
GCP_TOKEN_URI=https://oauth2.googleapis.com/token
GCP_AUTH_PROVIDER_X509_CERT_URL=https://www.googleapis.com/oauth2/v1/certs
GCP_CLIENT_X509_CERT_URL=https://www.googleapis.com/workspace/certs/...
GCP_UNIVERSE_DOMAIN=googleapis.com
```

---

## Instalación y Configuración Local

1.  **Clonar el repositorio**:
    ```bash
    git clone <url-del-repositorio>
    cd web-scraping-bbva
    ```

2.  **Crear y activar un entorno virtual**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # En Windows usa: venv\Scripts\activate
    ```

3.  **Instalar dependencias**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Instalar los navegadores de Playwright**:
    ```bash
    playwright install chromium
    ```

5.  **Ejecutar el bot**:
    ```bash
    python main.py --task rechazos
    ```

    Las otras tareas disponibles son:
    ```bash
    python main.py --task historico_diario
    python main.py --task pendientes
    ```

    `rechazos` guarda registros nuevos en Sheets y envía alertas. `historico_diario`
    consulta los publicados del día actual en CDMX; `pendientes` consulta los escritos
    de respuesta y rechazos pendientes. Estas dos tareas devuelven un DataFrame y
    muestran el total extraído; no tienen persistencia ni notificaciones configuradas.
    Todas las tareas usan Chromium en modo headless y omiten fines de semana en CDMX.

## Estructura del código

| Archivo | Responsabilidad |
| --- | --- |
| `main.py` | Selección de tarea mediante `--task` y validación del día de ejecución. |
| `app/config.py` | Carga de `.env`, credenciales, URLs, áreas y clasificación de oficios. |
| `app/database.py` | Conexión diferida a Sheets, deduplicación y actualización de Resultados/Novedades. |
| `app/notifier.py` | Tarjetas de Google Chat y resumen por Telegram. |
| `app/scraper/cnbv_client.py` | Inicio de sesión y cierre garantizado del navegador. |
| `app/scraper/task_rechazos.py` | Extracción y coordinación del guardado y las alertas de rechazos. |
| `app/scraper/task_historico.py` | Extracción de publicados y clasificación por expediente. |
| `app/scraper/task_pendientes.py` | Extracción de pendientes por área y tipo de respuesta. |

`app/main copy.py` delega al punto de entrada principal y acepta los mismos argumentos.
Para consultar otro intervalo desde Python, usa
`await ejecutar_extraccion_historica(date_start, date_end)` del módulo
`app.scraper.task_historico`, con fechas `datetime`.

Las pruebas usan servicios simulados y no envían mensajes ni modifican hojas:

```bash
python -m unittest discover -s tests -v
```

---

## Detalles del Funcionamiento

1.  **Validación de Horario**: El bot verifica que el día actual no sea fin de semana en CDMX antes de iniciar el escaneo.
2.  **Flujo de Scraping**:
    *   Inicia sesión en el portal CNBV.
    *   Itera a través de las áreas (`Hacendario`, `Judicial`, `Aseguramiento`, `Operaciones Ilícitas`).
    *   Selecciona la opción de "Rechazos", da clic en Consultar y extrae los datos de la tabla.
3.  **Procesamiento y Deduplicación**:
    *   Compara los registros obtenidos con los existentes en la hoja `Resultados` de Google Sheets.
    *   Filtra únicamente los registros nuevos (comparando el ID compuesto `Folio-Fecha de rechazo`).
4.  **Almacenamiento**:
    *   Los nuevos registros se añaden a la hoja `Resultados`.
    *   Se limpia y se actualiza la pestaña `Novedades` con los registros recién ingresados.
5.  **Notificaciones**:
    *   Agrupa las alertas por Área y envía una tarjeta informativa personalizada a Google Chat con enlace directo a la hoja de monitoreo.
    *   Envía un único resumen por Telegram con el total de rechazos nuevos guardados, cantidades por área y enlace a la hoja de monitoreo mediante [sendMessage](https://core.telegram.org/bots/api#sendmessage).
    *   Telegram usa `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID` del `.env`. Si faltan o el envío falla, se registra el aviso y continúa el flujo de Google Chat. No se envían alertas cuando no hay registros nuevos.
