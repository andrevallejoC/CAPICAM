"""
engine/temporal_aggregator.py — Agregación temporal de las pendientes por
frame de un mismo meridiano (etapa J del Pipeline Architecture; 11.4 del
Maestro, sección 5 del Pipeline Architecture).

[PRINCIPIO] Procesamiento frame por frame: se calcula la pendiente en
cada frame y luego se combinan las pendientes; NUNCA se promedian las
imágenes. La dispersión entre frames es, en sí misma, la incertidumbre.

Cubre directamente el criterio de aceptación del Paso 6 ("reducción
medible de dispersión frente al promedio simple"): agregar() con
ponderación por calidad debe dar una desviación estándar igual o menor
que un promedio simple sobre los mismos datos, lo cual se verifica en
test_engine.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .contratos_estimacion import ResultadoPendiente


@dataclass(frozen=True)
class PendienteMeridiano:
    media: float
    desviacion_estandar: float
    n_frames_usados: int
    n_frames_descartados: int


class AgregadorTemporal:
    """
    Descarte por consenso (MAD) + ponderación por calidad + media e
    incertidumbre, para las pendientes de todos los frames útiles de un
    mismo meridiano.
    """

    def __init__(self, umbral_mad_descarte: float):
        self._umbral_mad = umbral_mad_descarte

    def agregar(self, resultados: list[ResultadoPendiente]) -> PendienteMeridiano:
        if not resultados:
            return PendienteMeridiano(
                media=0.0, desviacion_estandar=0.0,
                n_frames_usados=0, n_frames_descartados=0,
            )

        pendientes = np.array([r.pendiente for r in resultados], dtype=float)
        calidades = np.array([r.calidad for r in resultados], dtype=float)

        # ── Descarte de anómalos por consenso (MAD) ──
        mediana = float(np.median(pendientes))
        desviaciones_abs = np.abs(pendientes - mediana)
        mad = float(np.median(desviaciones_abs))

        if mad == 0.0:
            # Todas las pendientes son (casi) idénticas: nada que descartar.
            mascara_conservados = np.ones_like(pendientes, dtype=bool)
        else:
            # Constante 1.4826 normaliza el MAD para que sea comparable a
            # una desviación estándar bajo normalidad.
            puntuacion = desviaciones_abs / (1.4826 * mad)
            mascara_conservados = puntuacion <= self._umbral_mad

        # Nunca descartar TODO: si el criterio deja menos de 2 puntos,
        # se conserva el conjunto completo (mejor una estimación con
        # outliers que ninguna estimación).
        if mascara_conservados.sum() < 2:
            mascara_conservados = np.ones_like(pendientes, dtype=bool)

        pendientes_ok = pendientes[mascara_conservados]
        calidades_ok = calidades[mascara_conservados]
        n_descartados = int((~mascara_conservados).sum())

        # ── Ponderación por calidad ──
        suma_calidad = float(calidades_ok.sum())
        if suma_calidad > 0.0:
            pesos = calidades_ok / suma_calidad
            media = float(np.sum(pendientes_ok * pesos))
        else:
            # Ningún frame conservado aporta calidad medible: promedio simple.
            media = float(np.mean(pendientes_ok))

        desviacion = float(np.std(pendientes_ok, ddof=1)) if len(pendientes_ok) > 1 else 0.0

        return PendienteMeridiano(
            media=media,
            desviacion_estandar=desviacion,
            n_frames_usados=len(pendientes_ok),
            n_frames_descartados=n_descartados,
        )
