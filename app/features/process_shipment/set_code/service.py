# ============================================================================
# service.py — Lógica de set_code + generación de códigos + Pushover
# ============================================================================

import time
import random
import string
import hmac
import hashlib
from app.features.process_shipment.set_code.schemas import SetCodeRequest
from app.shared.http_client import HttpClient
import httpx


def generate_shalom_security_headers(method: str, url_path: str) -> dict:
    """
    Genera los headers de seguridad requeridos por la API de Shalom.
    Basado en la lógica de su frontend:
    t = Math.floor(Date.now() / 1e3)
    n = Math.random().toString(36).substring(2, 10)
    a = e.method.toUpperCase() + e.url.replace(/^\//, "") + t + n
    r = s.a.HmacSHA256(a, "sk_over_nn43Df3L6;:-Zn=8Xu_bUn]J;)Z,E=^)]k=!Pg|I*(-").toString();
    """
    timestamp = str(int(time.time()))
    
    # Generar un nonce (cadena alfanumérica aleatoria como en JS: toString(36).substring(2, 10))
    # toString(36) genera números y letras minúsculas. Son unos 8 o 9 caracteres en JS, pero el substring toma hasta 8.
    chars = string.ascii_lowercase + string.digits
    nonce = ''.join(random.choice(chars) for _ in range(8))
    
    # Limpiar el path por si empieza con /
    clean_url_path = url_path.lstrip('/')
    
    # Construir la cadena a firmar "a"
    message_to_sign = method.upper() + clean_url_path + timestamp + nonce
    
    # El secreto extraído del código JS
    secret = "sk_over_nn43Df3L6;:-Zn=8Xu_bUn]J;)Z,E=^)]k=!Pg|I*(-"
    
    # Generar HMAC SHA256 "r"
    signature = hmac.new(
        secret.encode('utf-8'),
        message_to_sign.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return {
        "X-API-KEY": "pk_over_5pg91gO6CSgmT627cf2sC8B7dqjxcLFQhW7HhnitKq3",
        "X-TIMESTAMP": timestamp,
        "X-NONCE": nonce,
        "X-SIGNATURE": signature
    }

async def set_code(client: HttpClient, datos: SetCodeRequest):

    client.verificar_sesion()
    headers = client.obtener_headers_ajax()
    
    # Generar las cabeceras de seguridad dinámicamente para este endpoint y método
    endpoint = "/service-orders/security-code/massive"
    security_headers = generate_shalom_security_headers("POST", endpoint)
    headers.update(security_headers)

    response = await client.client.post(
        endpoint,
        headers=headers,
        json=datos.model_dump(),
    )
    print(response.json())
    return response.json()


def generate_code(previous_code: str = "") -> str:
    """
    Genera un código de 4 dígitos que cumple:
      1. No todos los dígitos iguales  (ej: 1111, 5555)
      2. No secuencia consecutiva asc/desc (ej: 1234, 9876)
      3. Diferente al código anterior
    """
    while True:
        code = str(random.randint(1000, 9999))

        # Regla 1: no todos iguales
        if len(set(code)) == 1:
            continue

        # Regla 2: no consecutivos ascendentes ni descendentes
        digits = [int(d) for d in code]
        diffs = [digits[i + 1] - digits[i] for i in range(len(digits) - 1)]
        if diffs == [1, 1, 1] or diffs == [-1, -1, -1]:
            continue

        # Regla 3: diferente al anterior
        if code == previous_code:
            continue

        return code


async def send_pushover_notification(code: str) -> dict:
    """
    Envía una notificación a Pushover con el nuevo código diario.
    Tokens hardcoded según preferencia del proyecto.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.pushover.net/1/messages.json",
            json={
                "token": "akjdd8361vnrmn7775p5db1eeqh8bv",
                "user": "uc4s3r8tb8uu24v7xef9qcrypew3ep",
                "message": f"🔐 Nuevo código diario: {code}",
            },
        )
        return response.json()


async def send_shipment_pushover_notification(
    telefono: str,
    dni: str,
    clave_paquete: str,
    success: bool,
    error_detail: str | None = None,
) -> dict:
    """
    Envía una notificación Pushover con el resultado del registro de un paquete.
    Se envía tanto en éxito como en error.
    """
    if success:
        message = (
            f"✅ Paquete registrado exitosamente\n"
            f"• Número: {telefono}\n"
            f"• DNI: {dni}\n"
            f"• Clave: {clave_paquete}"
        )
    else:
        message = (
            f"❌ Error al registrar paquete\n"
            f"• Número: {telefono}\n"
            f"• DNI: {dni}\n"
            f"• Clave: {clave_paquete}\n"
            f"• Error: {error_detail}"
        )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.pushover.net/1/messages.json",
            json={
                "token": "a81e6ie5dnk8nw53yb4duqh5exmsqf",
                "user": "utyv57a6ecrp9btkaqadpx7c3epejb",
                "message": message,
            },
        )
        return response.json()