"""
engine/errores.py — Jerarquía de errores propios del motor de fotorrefracción.

MotorFotorrefraccionLuxEyes.medir_ojo() deja que estas excepciones se
propaguen tal cual hacia orchestrator/, que ya sabe atraparlas y ofrecer
reintento del mismo ojo sin perder datos (Fase 3, ya implementada y
probada) — coincide exactamente con lo que contratos.MotorFotorrefraccion
documenta en orchestrator/.
"""

from __future__ import annotations


class ErrorMotor(Exception):
    """Raíz de los errores propios de engine/."""


class PupilaNoDetectadaError(ErrorMotor):
    """El detector de pupila no encontró un candidato válido en el frame."""


class VentanaInestableError(ErrorMotor):
    """
    Tras la sincronización LED-frame, un meridiano quedó con menos frames
    útiles de los mínimos necesarios para una estimación confiable (p. ej.
    parpadeo prolongado, movimiento, o fallo de asignación temporal).
    """


class FalloHardwareError(ErrorMotor):
    """La cámara o el controlador de LEDs fallaron a nivel de hardware."""
