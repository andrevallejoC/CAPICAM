"""
sync/excepciones.py — Jerarquía de errores propios de sync/.

DECISIÓN de arquitectura:
    cliente_api.py es el ÚNICO lugar que traduce excepciones de la librería
    HTTP (requests) a estas excepciones tipadas. El resto de sync/ (y
    cualquier módulo futuro que use sync/) nunca debería atrapar
    requests.RequestException directamente: eso acoplaría el resto del
    sistema a la elección de librería HTTP, violando la misma disciplina de
    aislamiento que storage/ ya aplica con sqlite3.

La clasificación en cuatro subtipos no es solo semántica: cada una implica
un efecto distinto sobre el ciclo de vida del Tamizaje en storage/ (ver
politica_reintentos.ClasificadorErrores y sincronizador.SincronizadorWeb).
"""

from __future__ import annotations


class ErrorSincronizacion(Exception):
    """Raíz de todos los errores de sync/."""


class ErrorReintentable(ErrorSincronizacion):
    """
    El intento falló, pero un reintento futuro tiene sentido. No se lanza
    directamente: se usan las subclases concretas, que determinan si el
    fallo consume presupuesto de reintentos (intentos_sync) o no.
    """


class ErrorConectividad(ErrorReintentable):
    """
    La solicitud nunca llegó a obtener respuesta del servidor (timeout,
    DNS, conexión rechazada, sin red). Es un fallo AMBIENTAL del
    dispositivo, no del tamizaje en particular: no debe consumir el
    presupuesto de reintentos de ese registro (ver Documento Maestro 13.2,
    "Sin Wi-Fi → Queda PENDIENTE; uso no interrumpido").
    """


class ErrorServidor(ErrorReintentable):
    """
    El servidor respondió, pero con un fallo transitorio de su lado (5xx,
    o una respuesta 2xx que incumple el contrato). Sí consume presupuesto
    de reintentos y activa backoff.
    """


class ErrorPermanente(ErrorSincronizacion):
    """
    El servidor rechazó el payload de forma definitiva (400/422). Reintentar
    el mismo payload sin cambios nunca tendrá éxito: no tiene sentido
    esperar a agotar max_intentos para reconocerlo.
    """


class ErrorAutenticacion(ErrorSincronizacion):
    """
    401/403. Es un problema de configuración del dispositivo (token
    inválido o expirado), no del tamizaje. Debe abortar el ciclo completo
    en curso en lugar de penalizar registros individuales.
    """
