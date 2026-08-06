"""
engine/contratos_estimacion.py — Contratos de la capa de estimación
científica, como Protocols.

DetectorPupila aísla MediaPipe (o cualquier otro detector) exactamente
igual que contratos_hardware.py aísla la cámara y los LEDs: la lógica de
trazado de meridianos y región automática (geometry.py) se prueba con un
detector falso; el detector real solo se ejercita con imágenes reales.

EstimadorPendiente es el contrato del patrón Strategy acordado en el
diseño de la Fase 4 (§0.3): cuatro implementaciones intercambiables
(OLS, Huber, Theil-Sen, RANSAC) sin que el resto del pipeline sepa cuál
está en uso.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class DeteccionPupila:
    centro_x: float
    centro_y: float
    radio: float


@runtime_checkable
class DetectorPupila(Protocol):
    def detectar(self, imagen: object) -> DeteccionPupila | None:
        """None si no se detecta ninguna pupila válida en la imagen."""
        ...


@dataclass(frozen=True)
class ResultadoPendiente:
    pendiente: float
    calidad: float   # combinación de bondad de ajuste + nitidez del frame (ver slope_estimator.py)


@runtime_checkable
class EstimadorPendiente(Protocol):
    def ajustar(self, posiciones: object, intensidades: object,
                mascara_valida: object) -> ResultadoPendiente:
        """
        posiciones/intensidades: arrays 1D del perfil muestreado.
        mascara_valida: array booleano de la misma longitud; True = punto
        utilizable (False = excluido, p. ej. por caer sobre el reflejo de
        Purkinje). El estimador debe ignorar por completo los puntos
        enmascarados, no solo darles menos peso.
        """
        ...
