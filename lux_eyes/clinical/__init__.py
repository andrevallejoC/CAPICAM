"""
clinical/ — Reglas de clasificación de riesgo por errores refractivos.

Sin fase numerada en el roadmap del MANIFEST; resuelve la deuda D6
("umbrales clínicos, sin definir"). Implementa el Protocol ReglasClinicas
que orchestrator/contratos.py ya definía desde la Fase 3 — cero cambios
en orchestrator/ para conectar esto, salvo el parámetro edad_meses
agregado a la firma del contrato (ver orchestrator/contratos.py).

[PRINCIPIO] Evalúa EXCLUSIVAMENTE condiciones refractivas — ver
reglas.ReglasClinicasAAPOS para la limitación explícita que se incluye
en cada resultado (no cubre estrabismo ni opacidad de medios).
"""

from .configuracion import UmbralesRiesgo
from .reglas import NivelRiesgo, ReglasClinicasAAPOS

__all__ = ["UmbralesRiesgo", "NivelRiesgo", "ReglasClinicasAAPOS"]
