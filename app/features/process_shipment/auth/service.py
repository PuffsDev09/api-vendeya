# ============================================================================
# service.py — Lógica de autenticación
# ============================================================================

import urllib.parse

# pyrefly: ignore [missing-import]
from bs4 import BeautifulSoup
from fastapi import HTTPException

from app.core.config import settings
from app.shared.http_client import HttpClient


async def login(client: HttpClient) -> dict:
    """
    Inicia sesión y guarda las cookies de sesión.

    Flujo:
    1. GET /login → obtiene el HTML con el token CSRF (_token)
    2. POST /login → envía credenciales + token CSRF
    3. Si redirige a /dashboard → login exitoso, cookies guardadas
    """
    # Paso 0: Limpiar cookies anteriores para forzar una nueva sesión limpia
    client.client.cookies.clear()

    # Paso 1: Obtener el token CSRF del formulario de login
    response = await client.client.get("/login?origin=WEB")
    soup = BeautifulSoup(response.text, "html.parser")
    token_input = soup.find("input", {"name": "_token"})

    if not token_input:
        raise HTTPException(
            status_code=502,
            detail="No se pudo obtener el token CSRF",
        )

    token = token_input["value"]

    # Paso 2: Enviar las credenciales (se leen desde .env, no hardcoded)
    datos_login = {
        "_token": token,
        "email": settings.CLIENT_EMAIL,
        "password": settings.CLIENT_PASSWORD,
    }

    response_login = await client.client.post(
        "/login", 
        data=datos_login, 
        follow_redirects=True,
        headers={
            "Origin": settings.CLIENT_BASE_URL,
            "Referer": f"{settings.CLIENT_BASE_URL}/login"
        }
    )


    # Paso 3: Verificar que el login fue exitoso
    if "dashboard" in str(response_login.url) or response_login.status_code == 200:
        cookie_token_crudo = client.client.cookies.get("XSRF-TOKEN", "")
        token_limpio = urllib.parse.unquote(cookie_token_crudo)

        return {
            "estado": "exito",
            "mensaje": "Sesión iniciada correctamente. El backend ya tiene las cookies listas.",
            "xsrf_token": token_limpio,
        }
    else:
        raise HTTPException(
            status_code=401,
            detail="Credenciales incorrectas o el login falló",
        )
