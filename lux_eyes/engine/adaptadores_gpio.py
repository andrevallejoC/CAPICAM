"""
engine/adaptadores_gpio.py — Implementación REAL de ControladorLED y Reloj
para Raspberry Pi (RPi.GPIO).

ADVERTENCIA IMPORTANTE:
    Este archivo NO pudo ejecutarse ni probarse en el entorno de
    desarrollo donde se escribió (no es una Raspberry Pi: RPi.GPIO se
    instala pero lanza RuntimeError al importarse fuera del hardware
    real). Está escrito siguiendo la API pública documentada de RPi.GPIO,
    pero DEBE validarse en el dispositivo físico antes de confiar en él.
    Todo lo demás en engine/ (la lógica científica) sí se probó de forma
    exhaustiva y automática; esto no.

DECISIÓN de arquitectura: no lleva NINGUNA lógica de secuenciación propia
— eso vive por completo en illumination.SecuenciadorIluminacion, que ya
está probado sin hardware. Este adaptador solo traduce encender()/apagar()
a llamadas de RPi.GPIO. Si mañana cambia el driver de LEDs (p. ej. a un
controlador PWM dedicado por I2C), solo este archivo se toca.

[DECISIÓN] (D4, deuda ya resuelta en el rediseño): LED en corriente
continua (DC) durante toda la ventana de captura útil, no PWM, para evitar
el banding/fluctuación fotométrica inter-frame documentado. Por eso
`encender()` simplemente pone el pin en HIGH, sin generar una señal PWM.

RESTRICCIÓN-ACTUAL:
    El mapeo GPIO -> meridiano se pasa como diccionario al construir el
    adaptador; no hay validación de que los pines sean físicamente
    correctos ni de que no colisionen con otros periféricos (p. ej. la
    pantalla táctil).
ARQUITECTURA IDEAL:
    Esa validación (y el mapeo en sí) debería venir de config/ cuando
    exista, no estar cableada en el sitio de construcción del adaptador.
MEJORA FUTURA:
    Mover pines_por_meridiano a ConfiguracionCaptura o a config/ cuando
    ese paquete se implemente (sin fase asignada todavía en el roadmap).
"""

from __future__ import annotations

import time

from .contratos_hardware import ControladorLED, Reloj
from .errores import FalloHardwareError


class RelojMonotono:
    """Implementación real de Reloj: usa time.monotonic() de la librería estándar."""

    def ahora(self) -> float:
        return time.monotonic()


class ControladorLEDGPIO:
    """
    Implementación real de ControladorLED sobre RPi.GPIO.

    pines_por_meridiano: p. ej. {0: 17, 60: 27, 120: 22} — número de pin
    BCM por meridiano en grados. Se valida al construirse que los tres
    meridianos configurados en ConfiguracionCaptura tengan pin asignado.
    """

    def __init__(self, pines_por_meridiano: dict[int, int]):
        try:
            import RPi.GPIO as GPIO
        except (ImportError, RuntimeError) as exc:
            raise FalloHardwareError(
                "No se pudo importar RPi.GPIO. Este adaptador solo funciona "
                "sobre una Raspberry Pi real con el módulo GPIO habilitado."
            ) from exc

        self._gpio = GPIO
        self._pines = dict(pines_por_meridiano)

        self._gpio.setmode(self._gpio.BCM)
        self._gpio.setwarnings(False)
        for pin in self._pines.values():
            self._gpio.setup(pin, self._gpio.OUT, initial=self._gpio.LOW)

        self._pin_encendido: int | None = None

    def encender(self, meridiano_grados: int) -> None:
        if meridiano_grados not in self._pines:
            raise FalloHardwareError(
                f"No hay pin GPIO configurado para el meridiano {meridiano_grados}°."
            )
        self.apagar()  # nunca dos LEDs encendidos a la vez
        pin = self._pines[meridiano_grados]
        self._gpio.output(pin, self._gpio.HIGH)
        self._pin_encendido = pin

    def apagar(self) -> None:
        if self._pin_encendido is not None:
            self._gpio.output(self._pin_encendido, self._gpio.LOW)
            self._pin_encendido = None

    def liberar(self) -> None:
        """Libera los pines GPIO. Llamar al apagar el dispositivo o al finalizar pruebas en la Pi."""
        self.apagar()
        self._gpio.cleanup(list(self._pines.values()))
