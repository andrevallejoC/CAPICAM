"""
engine/geometry.py — Geometría del ojo: pupila, meridianos y región de
ajuste (etapas F y H del Pipeline Architecture; 5.2, 11.3 del Maestro).

[PRINCIPIO CRÍTICO] (5.2): los ángulos 0°/60°/120° se miden respecto al
eje VERTICAL de la imagen (no horizontal), y crecen en sentido
antihorario. Como en coordenadas de imagen el eje Y crece hacia abajo:
    dx = -sin(ángulo) * L/2
    dy =  cos(ángulo) * L/2
Este detalle se corrigió y validó durante el desarrollo previo del
proyecto (ver informe de reconstrucción de contexto, Fase 1) — es fácil
de invertir por error si se reescribe sin este archivo como referencia.
test_engine.py fija explícitamente los casos cardinales (0°, 60°, 90°,
120°) contra coordenadas calculadas a mano para que nunca vuelva a
romperse silenciosamente.

[DECISIÓN] (11.3, reemplaza la deuda D8): la región de ajuste se expresa
como fracción del diámetro pupilar, no en píxeles absolutos — reproducible
entre pacientes y resoluciones de cámara.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .contratos_estimacion import DeteccionPupila, DetectorPupila


def trazar_meridiano(
    centro_x: float, centro_y: float, angulo_grados: float, longitud: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """
    Devuelve (p1, p2), los extremos del segmento del meridiano, centrado
    en (centro_x, centro_y), de la longitud dada. Fórmula exacta del
    apéndice 17.2 del Documento Maestro.
    """
    angulo_rad = math.radians(angulo_grados)
    dx = -math.sin(angulo_rad) * (longitud / 2)
    dy = math.cos(angulo_rad) * (longitud / 2)
    p1 = (centro_x - dx, centro_y - dy)
    p2 = (centro_x + dx, centro_y + dy)
    return p1, p2


def region_automatica(diametro_pupilar: float, fraccion_borde: float) -> tuple[float, float]:
    """
    Devuelve (posicion_inicio, posicion_fin) a lo largo del meridiano
    completo, en las mismas unidades que la longitud del meridiano,
    excluyendo `fraccion_borde` de cada extremo — donde la transición
    pupila-iris rompe la linealidad del gradiente (11.3).
    """
    longitud_meridiano_completo = diametro_pupilar
    inicio = longitud_meridiano_completo * fraccion_borde
    fin = longitud_meridiano_completo * (1.0 - fraccion_borde)
    return inicio, fin


@dataclass(frozen=True)
class GeometriaOjo:
    deteccion: DeteccionPupila
    meridianos: dict[int, tuple[tuple[float, float], tuple[float, float]]]
    region: tuple[float, float]


def calcular_geometria(
    imagen: object,
    detector: DetectorPupila,
    angulos_grados: tuple[int, ...],
    fraccion_longitud: float,
    fraccion_borde: float,
) -> GeometriaOjo | None:
    """
    Orquesta detección + trazado + región para un frame. Devuelve None si
    el detector no encuentra pupila — el llamador (motor.py) lo traduce
    en PupilaNoDetectadaError.
    """
    deteccion = detector.detectar(imagen)
    if deteccion is None:
        return None

    diametro = deteccion.radio * 2
    longitud_meridiano = diametro * fraccion_longitud

    meridianos = {
        angulo: trazar_meridiano(deteccion.centro_x, deteccion.centro_y, angulo, longitud_meridiano)
        for angulo in angulos_grados
    }
    region = region_automatica(longitud_meridiano, fraccion_borde)

    return GeometriaOjo(deteccion=deteccion, meridianos=meridianos, region=region)
