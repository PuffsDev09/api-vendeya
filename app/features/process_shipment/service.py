# ============================================================================
# service.py — Orquestación: login → filleo → preregister → set_code → register
# ============================================================================
# Cada llamada crea su propio HttpClient con sesión independiente.
# Esto permite múltiples llamadas concurrentes sin interferencia.
# ============================================================================

import logging

from app.features.process_shipment.auth.service import login
from app.features.process_shipment.filleo.schemas import FilleoRequest
from app.features.process_shipment.filleo.service import fill_book, fillear
from app.features.process_shipment.preregister.schemas import SendRequest
from app.features.process_shipment.preregister.service import obtener_envios
from app.features.process_shipment.register.schemas import RegisterRequest
from app.features.process_shipment.register.service import registrar_orden
from app.features.process_shipment.schemas import (
    ProcessShipmentRequest,
    ProcessShipmentResponse,
)
from app.shared.http_client import HttpClient
from app.features.process_shipment.set_code.service import (
    set_code,
    send_shipment_pushover_notification,
)
from app.features.process_shipment.set_code.schemas import SetCodeRequest

from app.core.config import settings

logger = logging.getLogger("process_shipment")


async def _notify_pushover(
    datos: ProcessShipmentRequest, success: bool, error_detail: str | None = None
):
    """Helper para enviar notificación Pushover sin afectar el response."""
    try:
        await send_shipment_pushover_notification(
            telefono=datos.telefono,
            dni=datos.dni,
            clave_paquete=settings.CLAVE_PAQUETE,
            success=success,
            error_detail=error_detail,
        )
    except Exception as exc:
        logger.warning(f"Error enviando notificación Pushover: {exc}")


async def procesar_envio(
    datos: ProcessShipmentRequest,
) -> ProcessShipmentResponse:
    """
    Ejecuta secuencialmente los 5 pasos del flujo de envío,
    cada uno con su propio cliente HTTP independiente.

    0. Login      – crea cliente, inicia sesión y obtiene cookies.
    1. Filleo     – llena el Excel y lo sube.
    2. Preregister – obtiene los pre-envíos y extrae el id.
    3. Set Code   – asigna el código a los envíos.
    4. Register   – registra la orden con el id obtenido.

    Si cualquier paso falla, retorna inmediatamente indicando
    cuál fue el paso que falló. El cliente se cierra siempre al final.
    Al finalizar (éxito o error) envía notificación Pushover.
    """

    client = HttpClient()

    try:
        # ── Paso 0: Login ────────────────────────────────────────────────
        
        try:
            await login(client)
            
        except Exception as exc:
            detail = f"Error en login: {exc}"
            await _notify_pushover(datos, success=False, error_detail=detail)
            return ProcessShipmentResponse(
                success=False,
                failed_step="login",
                detail=detail,
            )

        # ── Paso 1: Filleo ───────────────────────────────────────────────
        
        try:
            filleo_request = FilleoRequest(
                dni=datos.dni,
                telefono=datos.telefono,
                destino=datos.destino,
            )
            ruta = fill_book("formato-envio.xlsx", filleo_request)
            await fillear(client, ruta)
            
        except Exception as exc:
            detail = f"Error en filleo: {exc}"
            await _notify_pushover(datos, success=False, error_detail=detail)
            return ProcessShipmentResponse(
                success=False,
                failed_step="filleo",
                detail=detail,
            )

        # ── Paso 2: Preregister ──────────────────────────────────────────
        
        try:
            preregister_request = SendRequest(converted=False, send=False)
            response = await obtener_envios(client, preregister_request)
            order_id: int = response["data"][0]["id"]
            print(f"EL ID DE LA ORDEN ES: {order_id}")
            
        except Exception as exc:
            detail = f"Error en preregister: {exc}"
            await _notify_pushover(datos, success=False, error_detail=detail)
            return ProcessShipmentResponse(
                success=False,
                failed_step="preregister",
                detail=detail,
            )

        # ── Paso 3: Set Code ────────────────────────────────────────────
        
        try:
            set_code_request = SetCodeRequest(code=settings.CLAVE_PAQUETE, ids=[order_id])
            print(set_code_request.json())
            await set_code(client, set_code_request)
            
        except Exception as exc:
            detail = f"Error en set_code: {exc}"
            await _notify_pushover(datos, success=False, error_detail=detail)
            return ProcessShipmentResponse(
                success=False,
                failed_step="set_code",
                detail=detail,
            )

        # ── Paso 4: Register ────────────────────────────────────────────
        
        try:
            register_request = RegisterRequest(serviceOrder=[order_id])
            resultado = await registrar_orden(client, register_request)
            
        except Exception as exc:
            detail = f"Error en register: {exc}"
            await _notify_pushover(datos, success=False, error_detail=detail)
            return ProcessShipmentResponse(
                success=False,
                failed_step="register",
                detail=detail,
            )

        # ── Todo bien ────────────────────────────────────────────────────
        
        await _notify_pushover(datos, success=True)

        return ProcessShipmentResponse(
            success=True,
            order_id=order_id,
            detail=f"Envío procesado correctamente. Resultado: {resultado}",
        )

    finally:
        # Siempre cerrar el cliente, haya éxito o error
        await client.close()

