"""
sync/politica_reintentos.py — Clasificación de errores y backoff.

DECISIÓN de arquitectura:
    Se separan deliberadamente dos responsabilidades en dos clases dentro
    del mismo archivo:

    - ClasificadorErrores: función pura (excepción -> decisión). Sin
      estado, sin I/O. Fácil de probar de forma aislada, igual que el resto
      de componentes puros del proyecto (p. ej. las fórmulas de refraction).

    - RegistroBackoff: el ÚNICO componente con estado mutable de todo el
      módulo sync/. Mantiene en memoria, por uuid_local, el instante antes
      del cual no debe reintentarse un envío.

RESTRICCIÓN-ACTUAL:
    El backoff vive únicamente en memoria del proceso (Opción A, aprobada
    para la Fase 2). Se pierde si el proceso se reinicia o si se construye
    una instancia nueva de RegistroBackoff en lugar de reutilizar la
    existente. Ver también sincronizador.SincronizadorWeb, que documenta la
    obligación de instanciarse una sola vez por proceso.
ARQUITECTURA IDEAL:
    El tiempo de espera antes del próximo intento debería persistir en
    storage/ (p. ej. una columna proximo_intento_no_antes_de en la tabla
    tamizajes), sobreviviendo a reinicios del dispositivo y a la
    reconstrucción de objetos en memoria.
MEJORA FUTURA:
    Añadir esa columna cuando se diseñe el mecanismo de migración de
    esquema (deuda D11) o cuando el volumen de reintentos lo justifique.
    Registrado como deuda D12 en el Documento Maestro.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from enum import Enum

from .configuracion import ConfiguracionSync
from .excepciones import (
    ErrorAutenticacion,
    ErrorConectividad,
    ErrorPermanente,
    ErrorServidor,
)


class DecisionReintento(str, Enum):
    """
    Qué debe hacer SincronizadorWeb con el registro tras un fallo. Cada
    valor corresponde a una fila de la tabla de clasificación de errores
    del diseño aprobado.
    """
    REINTENTAR_AMBIENTAL = "REINTENTAR_AMBIENTAL"       # -> PENDIENTE, sin incrementar
    REINTENTAR_CON_BACKOFF = "REINTENTAR_CON_BACKOFF"   # -> ERROR_REINTENTABLE, incrementa
    PERMANENTE = "PERMANENTE"                           # -> ERROR_PERMANENTE
    ABORTAR_CICLO = "ABORTAR_CICLO"                      # -> revertir a PENDIENTE, cortar el for


class ClasificadorErrores:
    """Componente puro: excepción de sync/ -> DecisionReintento."""

    def clasificar(self, error: Exception) -> DecisionReintento:
        if isinstance(error, ErrorAutenticacion):
            return DecisionReintento.ABORTAR_CICLO
        if isinstance(error, ErrorPermanente):
            return DecisionReintento.PERMANENTE
        if isinstance(error, ErrorServidor):
            return DecisionReintento.REINTENTAR_CON_BACKOFF
        if isinstance(error, ErrorConectividad):
            return DecisionReintento.REINTENTAR_AMBIENTAL
        # Cualquier excepción no prevista explícitamente: por seguridad se
        # trata como ambiental, para no penalizar el presupuesto de
        # reintentos de un tamizaje por un fallo que no supimos clasificar.
        return DecisionReintento.REINTENTAR_AMBIENTAL


class RegistroBackoff:
    """
    Tabla en memoria {uuid_local: no_antes_de}. Ver restricciones en el
    docstring del módulo.
    """

    def __init__(self, config: ConfiguracionSync):
        self._config = config
        self._no_antes_de: dict[str, datetime] = {}

    def listo_para_intentar(self, uuid_local: str) -> bool:
        limite = self._no_antes_de.get(uuid_local)
        if limite is None:
            return True
        return datetime.now(timezone.utc) >= limite

    def programar_siguiente(self, uuid_local: str, intentos_sync: int) -> None:
        """
        Calcula y registra el próximo instante permitido de reintento,
        usando backoff exponencial con tope y jitter aleatorio (para evitar
        que, con varios dispositivos futuros, todos reintenten a la vez).
        """
        espera = min(
            self._config.backoff_base_segundos
            * (self._config.backoff_factor ** max(intentos_sync, 0)),
            self._config.backoff_max_segundos,
        )
        jitter = random.uniform(0, self._config.backoff_jitter_segundos)
        self._no_antes_de[uuid_local] = (
            datetime.now(timezone.utc) + timedelta(seconds=espera + jitter)
        )

    def olvidar(self, uuid_local: str) -> None:
        """
        Libera la entrada de un uuid_local que ya no debe seguir ocupando
        memoria: se llama tras SINCRONIZADO o ERROR_PERMANENTE, los dos
        estados en los que el registro deja de aparecer en
        listar_pendientes().
        """
        self._no_antes_de.pop(uuid_local, None)
