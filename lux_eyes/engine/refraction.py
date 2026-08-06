"""
engine/refraction.py — Conversión de pendientes a esfera/cilindro/eje
(etapa K del Pipeline Architecture; apéndice 17.1 del Maestro).

Traducción directa de las fórmulas documentadas, con la calibración
inyectable (CalibracionRefraccion) para cuando exista calibración propia
del hardware (deuda D3) — sin tocar este archivo cuando eso ocurra.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CalibracionRefraccion:
    """R(ángulo) = factor * pendiente + offset. Provisional: Agarwala et al. (deuda D3)."""
    factor: float = 0.98
    offset: float = 1.35


def potencia_meridional(pendiente: float, calibracion: CalibracionRefraccion) -> float:
    """R(ángulo), en dioptrías."""
    return calibracion.factor * pendiente + calibracion.offset


def vectores_potencia(r0: float, r60: float, r120: float) -> tuple[float, float, float]:
    """(M, J0, J45) según Thibos, Wheeler & Horner (1997)."""
    m = (r0 + r60 + r120) / 3.0
    j0 = (2 * r0 - r60 - r120) / 3.0
    j45 = (r60 - r120) / math.sqrt(3.0)
    return m, j0, j45


def parametros_clinicos(m: float, j0: float, j45: float) -> tuple[float, float, float]:
    """
    (esfera, cilindro, eje) a partir de los vectores de potencia. El eje
    se normaliza al rango clínico [0, 180).
    """
    magnitud_astigmatismo = math.hypot(j0, j45)
    esfera = m + magnitud_astigmatismo
    cilindro = -2.0 * magnitud_astigmatismo

    eje_rad = 0.5 * math.atan2(j45, j0)
    eje_grados = math.degrees(eje_rad) % 180.0

    return esfera, cilindro, eje_grados
