"""
sync/cliente_api.py — Transporte HTTP puro contra los tres pasos del
contrato de la API (Documento Maestro, 13.1).

DECISIÓN de arquitectura:
    ClienteAPI no conoce Tamizaje, storage/, ni el ciclo de vida de
    sincronización. Solo sabe hacer tres llamadas HTTP y traducir la
    respuesta a un resultado tipado o a una excepción de excepciones.py.
    Si el contrato deja de ser HTTP, o cambia el mecanismo de autenticación,
    el cambio queda contenido en este único archivo.

[SUPUESTO] (13.1 del Documento Maestro): la API es una restricción externa,
desarrollada por otro integrante del equipo. Este cliente se adapta a ella,
no al revés.
"""

from __future__ import annotations

import requests

from .configuracion import ConfiguracionSync
from .excepciones import (
    ErrorAutenticacion,
    ErrorConectividad,
    ErrorPermanente,
    ErrorServidor,
)

_RUTA_SINCRONIZAR = "/api/v1/tamizaje/sincronizar"
_RUTA_SUBIR_IMAGENES = "/api/v1/tamizaje/subir-imagenes"
_RUTA_GENERAR_PDF = "/api/v1/tamizaje/generar-pdf/{registro_id}"


class ClienteAPI:
    """Cliente HTTPS de los tres pasos documentados en 13.1."""

    def __init__(self, config: ConfiguracionSync, sesion: requests.Session | None = None):
        self._config = config
        # Permite inyectar una sesión (p. ej. una simulada) en pruebas,
        # sin depender de red real. Ver test_sync.py.
        self._sesion = sesion or requests.Session()
        self._sesion.headers.update({
            "Authorization": f"Bearer {config.token}",
            "Content-Type": "application/json",
        })

    def _timeout(self) -> tuple[float, float]:
        return (self._config.timeout_conexion_segundos,
                self._config.timeout_lectura_segundos)

    def _url(self, ruta: str) -> str:
        return f"{self._config.url_base.rstrip('/')}{ruta}"

    def _traducir_fallo_http(self, status_code: int, cuerpo_texto: str) -> None:
        """Lanza la excepción tipada correspondiente a un status_code no-2xx."""
        if status_code in (401, 403):
            raise ErrorAutenticacion(f"Autenticación rechazada ({status_code})")
        if status_code in (400, 422):
            raise ErrorPermanente(
                f"Payload rechazado por el servidor ({status_code}): "
                f"{cuerpo_texto[:300]}"
            )
        if 500 <= status_code < 600:
            raise ErrorServidor(f"Error del servidor ({status_code})")
        # Cualquier código no contemplado explícitamente por el contrato:
        # nunca se trata como éxito silencioso. Se asume reintentable con
        # backoff, que es la opción más segura ante lo desconocido.
        raise ErrorServidor(f"Respuesta HTTP inesperada ({status_code})")

    # ── Paso 1 — Datos ──────────────────────────────────────────────────
    def enviar_datos(self, payload: dict) -> str:
        """
        POST /api/v1/tamizaje/sincronizar

        Devuelve el registro_id_servidor ("resultado_id" en el contrato).
        Lanza ErrorConectividad, ErrorAutenticacion, ErrorPermanente o
        ErrorServidor según corresponda.
        """
        try:
            respuesta = self._sesion.post(
                self._url(_RUTA_SINCRONIZAR), json=payload, timeout=self._timeout()
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise ErrorConectividad(f"No se pudo contactar al servidor: {exc}") from exc

        if not respuesta.ok:
            self._traducir_fallo_http(respuesta.status_code, respuesta.text)

        try:
            cuerpo = respuesta.json()
        except ValueError as exc:
            raise ErrorServidor("Respuesta 2xx con cuerpo no-JSON") from exc

        registro_id = cuerpo.get("resultado_id")
        if not registro_id:
            raise ErrorServidor(
                "Respuesta 2xx sin 'resultado_id': el backend incumplió el contrato"
            )
        return registro_id

    # ── Paso 2 — Imágenes (opcional, best-effort) ──────────────────────
    def subir_imagenes(self, registro_id: str, ruta_od: str | None,
                        ruta_oi: str | None) -> None:
        """
        POST /api/v1/tamizaje/subir-imagenes

        No condiciona el estado SINCRONIZADO del tamizaje (13.1, 13.2):
        quien llame a este método decide si un fallo aquí es tolerable.
        """
        archivos: dict = {}
        try:
            if ruta_od:
                archivos["imagen_od"] = open(ruta_od, "rb")
            if ruta_oi:
                archivos["imagen_oi"] = open(ruta_oi, "rb")
            if not archivos:
                return

            try:
                respuesta = self._sesion.post(
                    self._url(_RUTA_SUBIR_IMAGENES),
                    data={"registro_id": registro_id},
                    files=archivos,
                    timeout=self._timeout(),
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                raise ErrorConectividad(
                    f"No se pudo contactar al servidor (imágenes): {exc}"
                ) from exc

            if not respuesta.ok:
                self._traducir_fallo_http(respuesta.status_code, respuesta.text)
        finally:
            for f in archivos.values():
                f.close()

    # ── Paso 3 — PDF/Email (opcional, best-effort) ─────────────────────
    def generar_pdf(
        self, registro_id: str, colegio_nombre: str, dispositivo_id: str,
        correo_padre: str | None,
    ) -> None:
        """
        POST /api/v1/tamizaje/generar-pdf/{registro_id}

        [CORRECCIÓN] La versión original de este método no enviaba
        ningún parámetro — confirmado, al comparar contra un script de
        referencia del desarrollador del backend, que el endpoint real
        espera colegio_nombre, dispositivo_id y correo_padre como query
        params (no en el cuerpo). Sin esto, el Paso 3 llamaba al
        endpoint correcto pero sin los datos que necesita para generar
        y notificar el PDF.

        [SUPUESTO] correo_padre puede ser None/vacío si el formulario de
        paciente no lo capturó (es opcional en la UI) — se envía tal
        cual; no se ha confirmado con el backend qué hace ante un
        destinatario vacío (¿genera el PDF sin enviarlo? ¿lo rechaza?).
        Revisar con el equipo de backend si esto causa comportamiento
        inesperado en la práctica.
        """
        ruta = _RUTA_GENERAR_PDF.format(registro_id=registro_id)
        parametros = {
            "colegio_nombre": colegio_nombre,
            "dispositivo_id": dispositivo_id,
            "correo_padre": correo_padre or "",
        }
        try:
            respuesta = self._sesion.post(
                self._url(ruta), params=parametros, timeout=self._timeout()
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise ErrorConectividad(
                f"No se pudo contactar al servidor (PDF): {exc}"
            ) from exc

        if not respuesta.ok:
            self._traducir_fallo_http(respuesta.status_code, respuesta.text)
