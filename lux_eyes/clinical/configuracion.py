"""
clinical/configuracion.py — Umbrales de riesgo clínico, inyectables.

Fuente: tabla de prescripción de lentes correctores (referencia citada
como nota 22 en el documento proporcionado por Luxeyes). Cubre
EXCLUSIVAMENTE condiciones refractivas: miopía, hipermetropía,
astigmatismo, anisometropía. NO cubre estrabismo ni opacidad de medios
(ver reglas.ReglasClinicasAAPOS, que documenta esta limitación de forma
explícita en cada resultado que produce).

DECISIÓN de arquitectura: mismo patrón que engine/configuracion.py — una
dataclass de inyección propia, sin importar el futuro paquete config/,
para que los umbrales puedan actualizarse si la guía clínica de
referencia cambia, sin tocar la lógica de clasificación en reglas.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UmbralesRiesgo:
    """
    Todos los umbrales en dioptrías, salvo edad_corte_meses.

    RESTRICCIÓN-ACTUAL:
        Miopía y astigmatismo están estratificados por edad (un único
        corte a los 48 meses, según la fuente). Hipermetropía y
        anisometropía se usan SIN estratificar por edad, por
        especificación explícita de Luxeyes al validar esta tabla —
        aunque el documento original sí distinguía franjas etarias para
        hipermetropía, se optó por el valor de referencia único (>4.00D).
    ARQUITECTURA IDEAL:
        Si en el futuro se dispone de umbrales de hipermetropía y/o
        anisometropía estratificados por edad, añadir esos campos aquí
        sin tocar reglas.py más que para leer el campo correspondiente.
    """

    edad_corte_meses: float = 48.0

    hiperopia_dioptrias: float = 4.00

    miopia_menor_48m: float = -3.00
    miopia_mayor_igual_48m: float = -2.00

    astigmatismo_menor_48m: float = 3.00        # sobre |cilindro|
    astigmatismo_mayor_igual_48m: float = 1.75   # sobre |cilindro|

    anisometropia_dioptrias: float = 1.25        # sobre |meridiano_menor_OD - meridiano_menor_OI|
