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

# --- Hojas de Google Sheets ---
SHEET_ID=id_de_la_hoja_de_calculo_principal
SHEET_ID_MONITOREO=id_de_la_hoja_de_monitoreo

# --- Webhooks de Google Chat ---
CHAT_WEBHOOK_DATA=https://chat.googleapis.com/v1/spaces/...
CHAT_WEBHOOK_ESP=https://chat.googleapis.com/v1/spaces/...
CHAT_WEBHOOK_HAC=https://chat.googleapis.com/v1/spaces/...
CHAT_WEBHOOK_ASEG=https://chat.googleapis.com/v1/spaces/...

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
    python main.py
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
