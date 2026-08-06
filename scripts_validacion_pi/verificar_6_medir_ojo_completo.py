"""
scripts_validacion_pi/verificar_6_medir_ojo_completo.py — Primera
medición real de extremo a extremo: MotorFotorrefraccionLuxEyes.medir_ojo()
con TODOS los adaptadores reales (LEDs, cámara, MediaPipe), sobre un ojo
real. Esto es lo más cerca que se puede estar, con esta fase, de una
sesión real del dispositivo.

Ejecuta ESTE script AL FINAL, después de que los 5 anteriores hayan
pasado — si alguno de ellos falla, es más fácil diagnosticar el problema
ahí que aquí, donde todo corre junto.

Ejecutar: python -m scripts_validacion_pi.verificar_6_medir_ojo_completo
"""

from lux_eyes.engine.adaptadores_gpio import ControladorLEDGPIO, RelojMonotono
from lux_eyes.engine.configuracion import ConfiguracionCaptura
from lux_eyes.engine.errores import ErrorMotor
from lux_eyes.engine.motor import MotorFotorrefraccionLuxEyes
from lux_eyes.engine.slope_estimator import EstimadorOLS
from scripts_validacion_pi.config_pi import (
    PINES_POR_MERIDIANO, construir_detector_pupila, construir_fuente_video,
)

OJO_A_PROBAR = "od"


def main():
    # Reloj ÚNICO compartido entre iluminación y cámara — obligatorio
    # (ver el fix documentado en adaptadores_picamera2.py).
    reloj = RelojMonotono()
    led = ControladorLEDGPIO(PINES_POR_MERIDIANO)
    fuente = construir_fuente_video(reloj)

    # Se construyen los DOS detectores aunque este script solo mida un
    # ojo por corrida (OJO_A_PROBAR): MotorFotorrefraccionLuxEyes ahora
    # exige ambos siempre — cada uno fijo a su lado de la cara (ver la
    # corrección documentada en engine/motor.py).
    detector_od = construir_detector_pupila("od")
    detector_oi = construir_detector_pupila("oi")

    config = ConfiguracionCaptura()
    # OLS como línea base para esta primera prueba (línea base documentada
    # en 11.2 del Maestro); una vez validado el flujo, compara con
    # EstimadorHuber/EstimadorTheilSen/EstimadorRANSAC — ese es justamente
    # el plan experimental de la sección 3.2 del Pipeline Architecture.
    estimador = EstimadorOLS()

    motor = MotorFotorrefraccionLuxEyes(
        controlador_led=led, fuente_video=fuente, reloj=reloj,
        detector_pupila_od=detector_od, detector_pupila_oi=detector_oi,
        estimador=estimador, config=config,
    )

    def reportar_progreso(mensaje: str) -> None:
        print(f"  [progreso] {mensaje}")

    print(f"Iniciando medición completa de '{OJO_A_PROBAR}'. Asegúrate de que "
          f"el sujeto está posicionado y fija la mirada al centro de la cámara.\n")

    try:
        resultado = motor.medir_ojo(OJO_A_PROBAR, reportar_progreso)
    except ErrorMotor as e:
        print(f"\nERROR DEL MOTOR ({type(e).__name__}): {e}")
        print("\nRevisa, en orden: verificar_1_leds, verificar_2_camara, "
              "verificar_3_sincronizacion y verificar_4_deteccion_pupila "
              "antes de reintentar aquí.")
        return
    finally:
        led.liberar()

    print("\n=== Resultado ===")
    print(f"  Esfera:   {resultado.esfera:.2f} D  (SD: {resultado.esfera_sd:.3f})")
    print(f"  Cilindro: {resultado.cilindro:.2f} D  (SD: {resultado.cilindro_sd:.3f})")
    print(f"  Eje:      {resultado.eje:.1f}°  (SD: {resultado.eje_sd:.2f})")
    print(f"  Reflejo rojo: {resultado.reflejo_rojo} (None = no evaluado, D5)")

    print("\nRECUERDA (deuda D3): la calibración (factor/offset) es la de")
    print("Agarwala et al., NO recalibrada para tu hardware. Los valores")
    print("absolutos de esfera/cilindro pueden estar sesgados; compara sobre")
    print("todo la REPETIBILIDAD (repite esta medición varias veces con el")
    print("mismo sujeto sin recolocar, y luego recolocando, y compara la SD")
    print("reportada contra la dispersión real observada).")


if __name__ == "__main__":
    main()
