"""
scripts_validacion_pi/01_verificar_leds.py — Verificación manual del
control de LEDs (adaptadores_gpio.ControladorLEDGPIO).

QUÉ HACE: enciende cada uno de los 3 LEDs, uno a la vez, con una pausa
para que confirmes VISUALMENTE que se enciende el LED correcto en el
meridiano correcto (0°, luego 60°, luego 120°), y que encender() apaga
automáticamente cualquier LED anterior (nunca dos encendidos a la vez —
requisito de illumination.SecuenciadorIluminacion).

NO requiere cámara. Ejecuta ESTE script antes que cualquier otro de esta
carpeta: si esto falla, nada más va a funcionar.

Ejecutar (desde la raíz del proyecto, en la Raspberry Pi):
    python -m scripts_validacion_pi.01_verificar_leds
"""

import time

from lux_eyes.engine.adaptadores_gpio import ControladorLEDGPIO
from scripts_validacion_pi.config_pi import PINES_POR_MERIDIANO


def main():
    print("Pines configurados:", PINES_POR_MERIDIANO)
    print("Construyendo ControladorLEDGPIO...")
    led = ControladorLEDGPIO(PINES_POR_MERIDIANO)
    print("OK: construido sin error.\n")

    try:
        for angulo in (0, 60, 120):
            print(f"Encendiendo meridiano {angulo}° (pin BCM {PINES_POR_MERIDIANO[angulo]})...")
            led.encender(angulo)
            print("  -> ¿Se encendió el LED correcto? Tienes 3 segundos para mirar.")
            time.sleep(3)
            led.apagar()
            print("  -> Apagado.\n")
            time.sleep(0.5)

        print("Probando que encender() de un meridiano nuevo apaga el anterior "
              "automáticamente (nunca dos LEDs a la vez)...")
        led.encender(0)
        time.sleep(1)
        led.encender(60)
        print("  -> ¿Ves SOLO el LED de 60° encendido (NO el de 0°)? 3 segundos.")
        time.sleep(3)
        led.apagar()

    finally:
        led.liberar()
        print("\nGPIO liberado. Fin de la verificación.")

    print("\nSi los 3 LEDs se encendieron en el orden y el pin correctos, y el "
          "segundo encendido apagó el primero automáticamente, "
          "ControladorLEDGPIO queda validado.")


if __name__ == "__main__":
    main()
