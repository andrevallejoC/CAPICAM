"""
orchestrator/excepciones.py — Errores propios de orchestrator/.
"""

from __future__ import annotations


class ErrorOrquestador(Exception):
    """Raíz de los errores propios de orchestrator/."""


class EstadoInvalidoError(ErrorOrquestador):
    """
    Se llamó a un método del flujo en un estado en el que no corresponde
    (p. ej. recibir_datos_paciente() antes de recibir_datos_sesion(), o
    cualquier método tras COMPLETADO/CANCELADO sin llamar antes a
    iniciar_nuevo_tamizaje()). Es un error de programación de quien invoca
    al orquestador (ui/ o las pruebas), no una situación recuperable del
    flujo de uso en sí — a diferencia de un fallo de validación o de
    captura, que se reportan vía ObservadorDeFlujo.en_error() y no lanzan
    excepción.
    """
