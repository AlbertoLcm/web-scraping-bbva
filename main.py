import argparse
import asyncio
from datetime import datetime

from app.config import TIMEZONE
from app.scraper.task_historico import ejecutar_extraccion_historica
from app.scraper.task_pendientes import ejecutar_monitoreo_pendientes
from app.scraper.task_rechazos import ejecutar_monitoreo_rechazos


async def main():
    parser = argparse.ArgumentParser(description="Bot CNBV - Automatizaciones")
    parser.add_argument(
        "--task",
        choices=["rechazos", "historico_diario", "pendientes"],
        required=True,
        help="Especifica la tarea a ejecutar"
    )
    args = parser.parse_args()

    if datetime.now(TIMEZONE).weekday() >= 5:
        print("[INFO] Fin de semana en CDMX. Omite ejecución.")
        return

    if args.task == "rechazos":
        resultado = await ejecutar_monitoreo_rechazos()
    elif args.task == "historico_diario":
        resultado = await ejecutar_extraccion_historica()
    elif args.task == "pendientes":
        resultado = await ejecutar_monitoreo_pendientes()

    print(f"[INFO] Tarea {args.task}: {len(resultado)} registros extraídos.")
    return resultado


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot detenido por usuario.")
