"""
engine/acquisition.py — Adquisición de vídeo, sin interpretar (etapa C
del Pipeline Architecture).

[PRINCIPIO] (7.3): "la adquisición tiene prioridad y mínima carga: solo
recoge y almacena". Este módulo no filtra ni interpreta nada — esa
complejidad vive en synchronizer.py. Es deliberadamente delgado: la
implementación real para Raspberry Pi (adaptadores_picamera2.py) tampoco
tiene lógica propia más allá de traducir la API de Picamera2 al contrato
FuenteDeVideo.
"""

from __future__ import annotations

from typing import Callable

from .contratos_hardware import FrameCrudo, FuenteDeVideo


class AdquisidorVideo:
    """Envoltura delgada sobre una FuenteDeVideo: acumula frames sin juzgarlos."""

    def __init__(self, fuente: FuenteDeVideo):
        self._fuente = fuente

    def capturar_mientras(self, condicion: Callable[[], bool]) -> list[FrameCrudo]:
        """
        Lee frames de la fuente mientras condicion() sea True. condicion()
        se evalúa antes de cada lectura; un frame en curso nunca se
        interrumpe a mitad. Frames None (fuente sin dato disponible en ese
        instante) se ignoran sin error: es normal en un stream continuo.
        """
        frames: list[FrameCrudo] = []
        while condicion():
            frame = self._fuente.leer_frame()
            if frame is not None:
                frames.append(frame)
        return frames
