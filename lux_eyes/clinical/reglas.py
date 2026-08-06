"""
clinical/reglas.py — ReglasClinicasAAPOS: clasificación de riesgo por
errores refractivos. Implementa el Protocol ReglasClinicas de
orchestrator/contratos.py.

[PRINCIPIO] Este módulo evalúa EXCLUSIVAMENTE condiciones refractivas
(miopía, hipermetropía, astigmatismo, anisometropía) detectables por
fotorrefracción. NO evalúa estrabismo manifiesto ni opacidad de medios
— ambos requieren evaluación clínica que este dispositivo no realiza
(alineación ocular, reflejo rojo/transiluminación). Por eso el campo
`observaciones` que devuelve clasificar() SIEMPRE incluye una nota de
limitación explícita: un resultado "SIN_RIESGO" de este módulo nunca
debe interpretarse como "sin ningún problema visual", solo como "sin
error refractivo significativo detectado por este método". Esto es
deliberado, no un descuido — omitirlo sería engañoso para el objetivo
clínico central del proyecto (detección temprana de riesgo de
ambliopía), que incluye causas (estrabismo, opacidad de medios) que
este módulo no puede ver.

Fórmulas (notación Thibos, cilindro con signo negativo — 17.1 del
Documento Maestro):
    meridiano_menor = esfera + cilindro
(el meridiano de menor potencia refractiva del ojo; usado para
anisometropía según especificación de Luxeyes, no esfera ni equivalente
esférico simple).
"""

from __future__ import annotations

from enum import Enum

from lux_eyes.common.tipos import ResultadoOjo

from .configuracion import UmbralesRiesgo


class NivelRiesgo(str, Enum):
    """Hereda de str, mismo patrón que EstadoSync/EstadoImagenes en common/tipos.py."""
    SIN_RIESGO = "SIN_RIESGO"
    BAJO = "BAJO"
    MODERADO = "MODERADO"
    ALTO = "ALTO"


_NOTA_LIMITACION = (
    "Este tamizaje evalúa únicamente errores refractivos (miopía, "
    "hipermetropía, astigmatismo, anisometropía) por fotorrefracción. "
    "No evalúa estrabismo ni opacidad de medios; ambos requieren "
    "evaluación clínica adicional."
)


def _cumple_hiperopia(ojo: ResultadoOjo, umbral: float) -> bool:
    if ojo.esfera is None:
        return False
    return ojo.esfera > umbral


def _cumple_miopia(ojo: ResultadoOjo, umbral: float) -> bool:
    if ojo.esfera is None:
        return False
    return ojo.esfera < umbral


def _cumple_astigmatismo(ojo: ResultadoOjo, umbral: float) -> bool:
    if ojo.cilindro is None:
        return False
    return abs(ojo.cilindro) > umbral


def _meridiano_menor(ojo: ResultadoOjo) -> float | None:
    if ojo.esfera is None or ojo.cilindro is None:
        return None
    return ojo.esfera + ojo.cilindro


def _cumple_anisometropia(od: ResultadoOjo, oi: ResultadoOjo, umbral: float) -> bool:
    m_od = _meridiano_menor(od)
    m_oi = _meridiano_menor(oi)
    if m_od is None or m_oi is None:
        return False
    return abs(m_od - m_oi) > umbral


class ReglasClinicasAAPOS:
    """
    Implementa el Protocol ReglasClinicas (orchestrator/contratos.py) con
    los umbrales de UmbralesRiesgo. El nombre refleja el origen de la
    tabla de referencia (criterios tipo AAPOS de cribado visual infantil).
    """

    def __init__(self, umbrales: UmbralesRiesgo | None = None):
        self._umbrales = umbrales or UmbralesRiesgo()

    def clasificar(
        self, od: ResultadoOjo, oi: ResultadoOjo, edad_meses: float
    ) -> tuple[str | None, bool | None, str]:
        u = self._umbrales
        estratificado_temprano = edad_meses < u.edad_corte_meses

        umbral_miopia = (
            u.miopia_menor_48m if estratificado_temprano else u.miopia_mayor_igual_48m
        )
        umbral_astigmatismo = (
            u.astigmatismo_menor_48m if estratificado_temprano
            else u.astigmatismo_mayor_igual_48m
        )

        hiperopia = (
            _cumple_hiperopia(od, u.hiperopia_dioptrias)
            or _cumple_hiperopia(oi, u.hiperopia_dioptrias)
        )
        miopia = _cumple_miopia(od, umbral_miopia) or _cumple_miopia(oi, umbral_miopia)
        astigmatismo = (
            _cumple_astigmatismo(od, umbral_astigmatismo)
            or _cumple_astigmatismo(oi, umbral_astigmatismo)
        )
        anisometropia = _cumple_anisometropia(od, oi, u.anisometropia_dioptrias)

        requiere_derivacion = any([miopia, hiperopia, astigmatismo, anisometropia])

        # Nivel más alto entre los criterios cumplidos, orden de
        # severidad ambliogénica según especificación de Luxeyes:
        # anisometropía > hipermetropía > (astigmatismo o miopía).
        if anisometropia:
            riesgo = NivelRiesgo.ALTO
        elif hiperopia:
            riesgo = NivelRiesgo.MODERADO
        elif astigmatismo or miopia:
            riesgo = NivelRiesgo.BAJO
        else:
            riesgo = NivelRiesgo.SIN_RIESGO

        criterios_cumplidos = []
        if miopia:
            criterios_cumplidos.append("miopía")
        if hiperopia:
            criterios_cumplidos.append("hipermetropía")
        if astigmatismo:
            criterios_cumplidos.append("astigmatismo")
        if anisometropia:
            criterios_cumplidos.append("anisometropía")

        if criterios_cumplidos:
            observaciones = (
                f"Criterios cumplidos: {', '.join(criterios_cumplidos)}. "
                f"{_NOTA_LIMITACION}"
            )
        else:
            observaciones = _NOTA_LIMITACION

        return riesgo.value, requiere_derivacion, observaciones
