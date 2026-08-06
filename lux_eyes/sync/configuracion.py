"""
sync/configuracion.py — Configuración de la que depende el módulo sync/.

DECISIÓN de arquitectura:
    sync/ no importa el futuro paquete config/ (todavía sin fase asignada
    en el roadmap). En su lugar define esta dataclass propia como punto de
    inyección: quien construya SincronizadorWeb decide de dónde vienen estos
    valores (archivo, variables de entorno, o el futuro config/). sync/ solo
    depende de esta abstracción, nunca de la fuente concreta.

RESTRICCIÓN-ACTUAL:
    El mecanismo de token de autenticación (D9) no está definido; aquí se
    modela simplemente como una cadena. No hay refresco automático de token.
ARQUITECTURA IDEAL:
    config/ gestiona la obtención, almacenamiento seguro y rotación del
    token, y expone esta misma dataclass ya poblada.
MEJORA FUTURA:
    Cuando exista config/, construir ConfiguracionSync a partir de él sin
    tocar el resto de sync/.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfiguracionSync:
    """
    Todo lo que sync/ necesita del exterior para operar.

    Campos de identidad del dispositivo (dispositivo_id, version_firmware):
    forman parte del contrato JSON (apéndice 17.3) pero son propiedades del
    dispositivo, no del tamizaje individual; viven aquí y no en Tamizaje.

    Campos de reintentos y backoff: ver politica_reintentos.RegistroBackoff.
    max_intentos DEBE coincidir con el valor que se le pase a
    storage.listar_pendientes(max_intentos=...), para que ambos módulos
    compartan la misma noción de "cuándo un registro pasa a ERROR_PERMANENTE".
    """

    # ── Identidad del dispositivo (contrato 17.3) ──
    dispositivo_id: str
    version_firmware: str

    # ── Conexión ──
    url_base: str
    token: str
    timeout_conexion_segundos: float = 5.0
    timeout_lectura_segundos: float = 15.0

    # ── Reintentos ──
    max_intentos: int = 5

    # ── Backoff exponencial en memoria (ver §0 del diseño aprobado) ──
    backoff_base_segundos: float = 2.0
    backoff_factor: float = 2.0
    backoff_max_segundos: float = 300.0
    backoff_jitter_segundos: float = 1.0

    def __post_init__(self) -> None:
        if not self.token:
            raise ValueError(
                "ConfiguracionSync.token no puede estar vacío: HTTPS + token "
                "es prerrequisito de cualquier envío (Documento Maestro, 13.4)."
            )
        if not self.url_base:
            raise ValueError("ConfiguracionSync.url_base no puede estar vacío.")
        if self.max_intentos < 1:
            raise ValueError("ConfiguracionSync.max_intentos debe ser >= 1.")
