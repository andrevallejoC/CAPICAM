"""
engine/contratos_hardware.py — Contratos de hardware, como Protocols.

DECISIÓN de arquitectura (aprobada en el diseño de la Fase 4, §0.2):
    Toda la lógica científica del motor (secuenciación, sincronización,
    geometría, máscara, estimación, agregación, refracción) se prueba
    contra estos contratos con implementaciones falsas, sin GPIO ni cámara
    reales. Las implementaciones concretas para Raspberry Pi
    (adaptadores_gpio.py, adaptadores_picamera2.py) son adaptadores
    delgados que solo pueden validarse en el dispositivo físico — nunca
    llevan lógica propia que valga la pena testear unitariamente aparte
    de "¿llama correctamente a la librería de hardware?".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@runtime_checkable
class Reloj(Protocol):
    """Fuente de tiempo monótono común entre iluminación y adquisición (7.3)."""

    def ahora(self) -> float:
        """Segundos, monótono. No es tiempo de pared: solo importan las diferencias."""
        ...


@runtime_checkable
class ControladorLED(Protocol):
    """Contrato que el adaptador GPIO real deberá cumplir."""

    def encender(self, meridiano_grados: int) -> None:
        """Enciende el LED del meridiano indicado en corriente continua (DC, D4)."""
        ...

    def apagar(self) -> None:
        """Apaga cualquier LED que estuviera encendido."""
        ...


@dataclass(frozen=True)
class FrameCrudo:
    """
    Un frame de la cámara con sus metadatos, sin interpretar. `imagen` es
    un array 2D (escala de grises) o 3D (con canal), según la fuente.
    """
    imagen: object                    # numpy.ndarray — sin importar numpy aquí
    timestamp_sensor: float           # segundos, mismo reloj monótono que ControladorLED
    duracion_exposicion: float        # segundos (6.4: regla de contención de exposición)
    metadatos: dict = field(default_factory=dict)   # FocusFoM, LensPosition, etc. (17.6)


@runtime_checkable
class FuenteDeVideo(Protocol):
    """Contrato que el adaptador Picamera2 real deberá cumplir."""

    def iniciar(self) -> None:
        """Arranca el stream continuo. Parámetros fijos, enfoque bloqueado (5.1, etapas 1-3)."""
        ...

    def leer_frame(self) -> FrameCrudo | None:
        """Devuelve el siguiente frame disponible, o None si no hay ninguno pendiente."""
        ...

    def detener(self) -> None:
        """Detiene el stream y libera los recursos de la cámara."""
        ...
