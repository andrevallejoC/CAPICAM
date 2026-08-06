"""
engine/synchronizer.py — Asignación frame -> meridiano por correlación
temporal (6.4 del Documento Maestro, etapa E del Pipeline Architecture).

Función pura: recibe listas de datos con timestamps, nunca toca cámara ni
GPIO. Es el criterio de aceptación documentado del Paso 1 ("0 frames mal
asignados en una secuencia conocida") llevado directamente a una prueba
unitaria con timestamps sintéticos.

[PRINCIPIO] Regla de contención de exposición (6.4): como el sensor es
rolling shutter, un frame es válido para un meridiano solo si su ventana
de integración completa [timestamp - exposicion, timestamp] cae ENTERA
dentro del intervalo estable de ese LED. Los frames que solapan un cambio
de LED se descartan. La asignación es por correlación temporal, no por
conteo de frames — inmune a frames perdidos.

[DECISIÓN] (6.5): se descartan además los primeros
`frames_a_descartar_tras_cambio` frames de cada intervalo estable, por el
transitorio del sensor tras el cambio de iluminación.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contratos_hardware import FrameCrudo


@dataclass(frozen=True)
class EventoLed:
    """Un intervalo en el que un meridiano estuvo estable (LED encendido, sin transitorio)."""
    meridiano_grados: int
    inicio_estable: float   # segundos, reloj monótono — ya excluye el transitorio inicial
    fin_estable: float      # segundos


def _ventana_contenida(frame: FrameCrudo, evento: EventoLed) -> bool:
    inicio_ventana = frame.timestamp_sensor - frame.duracion_exposicion
    fin_ventana = frame.timestamp_sensor
    return inicio_ventana >= evento.inicio_estable and fin_ventana <= evento.fin_estable


def asignar_frames_a_meridianos(
    frames: list[FrameCrudo],
    eventos_led: list[EventoLed],
) -> dict[int, list[FrameCrudo]]:
    """
    Asigna cada frame al meridiano cuyo intervalo estable contiene por
    completo su ventana de exposición. Un frame que no cae enteramente
    dentro de ningún intervalo estable (porque solapa un cambio de LED, o
    porque cae en un tramo de transitorio ya excluido de `eventos_led`) se
    descarta silenciosamente — es el comportamiento correcto, no un error:
    ese frame simplemente no es utilizable para ningún meridiano.

    El descarte de frames de transitorio (6.5) se resuelve ANTES de llamar
    a esta función: `eventos_led` debe contener ya los intervalos con el
    inicio recortado tras el descarte de estabilización (ver
    illumination.SecuenciadorIluminacion.eventos()).
    """
    resultado: dict[int, list[FrameCrudo]] = {e.meridiano_grados: [] for e in eventos_led}

    for frame in frames:
        for evento in eventos_led:
            if _ventana_contenida(frame, evento):
                resultado[evento.meridiano_grados].append(frame)
                break  # un frame pertenece como máximo a un meridiano

    return resultado
