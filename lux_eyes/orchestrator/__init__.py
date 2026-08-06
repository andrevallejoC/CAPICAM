"""
orchestrator/ — Coordina el flujo de uso de un tamizaje (Fase 3).

Depende de storage/ (sin modificarlo) y, por contrato estructural
(typing.Protocol), de las futuras implementaciones de engine/ y clinical/
(Fase 4). No conoce ningún framework gráfico: expone ObservadorDeFlujo
como el único punto de contacto que una futura ui/ (Fase 5) necesitará
implementar. No gestiona sincronización: eso sigue siendo exclusivamente
de sync/, operado de forma independiente y asíncrona.
"""

from .contexto import (
    ContextoInvalidoError,
    ContextoTamizajeEnCurso,
    DatosPaciente,
    DatosSesion,
)
from .contratos import MotorFotorrefraccion, ObservadorDeFlujo, ReglasClinicas
from .excepciones import ErrorOrquestador, EstadoInvalidoError
from .maquina_estados import ESTADOS_CANCELABLES, ESTADOS_TERMINALES, EstadoFlujo
from .orquestador import OrquestadorTamizaje

__all__ = [
    "OrquestadorTamizaje",
    "EstadoFlujo",
    "ESTADOS_TERMINALES",
    "ESTADOS_CANCELABLES",
    "ObservadorDeFlujo",
    "MotorFotorrefraccion",
    "ReglasClinicas",
    "ContextoTamizajeEnCurso",
    "DatosSesion",
    "DatosPaciente",
    "ContextoInvalidoError",
    "ErrorOrquestador",
    "EstadoInvalidoError",
]
