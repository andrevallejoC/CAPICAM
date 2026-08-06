"""
engine/illumination.py — Secuenciación de la iluminación IR (etapa D del
Pipeline Architecture; máquina de estados de 7.4).

DECISIÓN de arquitectura (Fase 4, §0.5): la coordinación se implementa
como código puro y síncrono, manejado por llamadas explícitas a avanzar()
en vez de gestionar hilos propios. Esto es lo que permite probar toda la
máquina de estados con un Reloj y un ControladorLED falsos, sin sleep()
real y sin hardware. El "runner" con hilos reales para la Raspberry Pi
vive en adaptadores_gpio.py — es deliberadamente delgado y no lleva
lógica propia de secuenciación.

Estados: INICIO -> [por cada repetición y meridiano:
LED_ON_ESTABILIZANDO -> CAPTURA_UTIL -> LED_OFF] -> FIN_CAPTURA.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from .configuracion import ConfiguracionCaptura
from .contratos_hardware import ControladorLED, Reloj
from .synchronizer import EventoLed


class _FaseInterna(Enum):
    SIN_INICIAR = auto()
    ESTABILIZANDO = auto()
    CAPTURA_UTIL = auto()
    ENTRE_MERIDIANOS = auto()
    TERMINADO = auto()


class SecuenciadorIluminacion:
    """
    Cicla los meridianos configurados, el número de repeticiones
    configurado, encendiendo cada LED en DC (D4) y registrando el
    intervalo "estable" de cada uno (ya excluido el transitorio de
    estabilización) como una lista de EventoLed lista para
    synchronizer.asignar_frames_a_meridianos().
    """

    def __init__(self, controlador: ControladorLED, reloj: Reloj,
                 config: ConfiguracionCaptura):
        self._controlador = controlador
        self._reloj = reloj
        self._config = config
        self._fase = _FaseInterna.SIN_INICIAR
        self._eventos: list[EventoLed] = []
        self._plan: list[int] = []
        self._indice_plan = 0
        self._t_cambio_fase = 0.0
        self._meridiano_actual: int | None = None

    def iniciar_ciclo(self) -> None:
        """Arranca la secuencia con los meridianos y repeticiones de la configuración."""
        self._plan = list(self._config.angulos_meridianos) * self._config.repeticiones_ciclo
        self._indice_plan = 0
        self._eventos = []
        self._controlador.apagar()
        self._avanzar_al_siguiente_meridiano()

    def _avanzar_al_siguiente_meridiano(self) -> None:
        if self._indice_plan >= len(self._plan):
            self._controlador.apagar()
            self._fase = _FaseInterna.TERMINADO
            self._meridiano_actual = None
            return

        self._meridiano_actual = self._plan[self._indice_plan]
        self._indice_plan += 1
        self._controlador.encender(self._meridiano_actual)
        self._t_cambio_fase = self._reloj.ahora()
        self._fase = _FaseInterna.ESTABILIZANDO

    def avanzar(self) -> None:
        """
        Se llama repetidamente (polling síncrono). Consulta el reloj y
        decide si toca transicionar de fase. No bloquea ni duerme.
        """
        if self._fase in (_FaseInterna.SIN_INICIAR, _FaseInterna.TERMINADO):
            return

        ahora = self._reloj.ahora()

        if self._fase is _FaseInterna.ESTABILIZANDO:
            if ahora - self._t_cambio_fase >= self._config.duracion_estabilizacion_segundos:
                # El intervalo "estable" arranca AHORA, ya sin el transitorio.
                self._t_cambio_fase = ahora
                self._fase = _FaseInterna.CAPTURA_UTIL

        elif self._fase is _FaseInterna.CAPTURA_UTIL:
            # La duración de captura útil se controla por número de frames
            # recogidos, no por tiempo — quien orquesta (motor.py) decide
            # cuándo hay frames suficientes y llama a cerrar_meridiano_actual().
            pass

    def cerrar_meridiano_actual(self) -> None:
        """
        Cierra el intervalo estable del meridiano en curso (se recogieron
        frames suficientes o se agotó el tiempo máximo) y avanza al
        siguiente meridiano del plan.
        """
        if self._fase is not _FaseInterna.CAPTURA_UTIL:
            return
        ahora = self._reloj.ahora()
        self._eventos.append(EventoLed(
            meridiano_grados=self._meridiano_actual,
            inicio_estable=self._t_cambio_fase,
            fin_estable=ahora,
        ))
        self._avanzar_al_siguiente_meridiano()

    def en_captura_util(self) -> bool:
        return self._fase is _FaseInterna.CAPTURA_UTIL

    def meridiano_actual(self) -> int | None:
        return self._meridiano_actual

    def terminado(self) -> bool:
        return self._fase is _FaseInterna.TERMINADO

    def eventos(self) -> list[EventoLed]:
        """Eventos ya cerrados, listos para synchronizer.asignar_frames_a_meridianos()."""
        return list(self._eventos)
