"""
sync/ — Cola de sincronización con la plataforma web (Fase 2).

Consume la cola de pendientes de storage/ (sin modificarlo) y la envía a
la API externa documentada en el Documento Maestro (13.1). No conoce la UI
ni el orquestador; expone únicamente lo necesario para que cualquiera de
los dos la use en el futuro sin acoplarse a sus componentes internos.
"""

from .configuracion import ConfiguracionSync
from .excepciones import (
    ErrorAutenticacion,
    ErrorConectividad,
    ErrorPermanente,
    ErrorReintentable,
    ErrorServidor,
    ErrorSincronizacion,
)
from .cliente_api import ClienteAPI
from .sincronizador import ResumenSincronizacion, SincronizadorWeb

__all__ = [
    "ConfiguracionSync",
    "ClienteAPI",
    "SincronizadorWeb",
    "ResumenSincronizacion",
    "ErrorSincronizacion",
    "ErrorReintentable",
    "ErrorConectividad",
    "ErrorServidor",
    "ErrorPermanente",
    "ErrorAutenticacion",
]
