"""
scripts_validacion_pi/verificar_3_sincronizacion.py — Verificación del
criterio de aceptación documentado del Paso 1 del roadmap del motor
(16.2 del Documento Maestro): "0 frames mal asignados en una secuencia
conocida".

QUÉ HACE: ejecuta un ciclo real de iluminación + adquisición (con
hardware real: LEDs y cámara), usando la MISMA instancia de RelojMonotono
para ambos (ver el fix documentado en adaptadores_picamera2.py), y la
misma lógica (SecuenciadorIluminacion, AdquisidorVideo, synchronizer) que
MotorFotorrefraccionLuxEyes.medir_ojo() usa internamente. Luego verifica
PROGRAMÁTICAMENTE — no solo visualmente — que cada frame asignado a un
meridiano cumple la regla de contención de exposición (6.4 del Maestro):
su ventana de exposición completa cae dentro del intervalo estable del
LED correspondiente.

Este es el script más importante de esta carpeta: valida en hardware
real la pieza que synchronizer.py ya tenía probada con timestamps
sintéticos (test_engine.py, sección 4).

Ejecutar: python -m scripts_validacion_pi.verificar_3_sincronizacion
"""

from lux_eyes.engine.acquisition import AdquisidorVideo
from lux_eyes.engine.adaptadores_gpio import ControladorLEDGPIO, RelojMonotono
from lux_eyes.engine.configuracion import ConfiguracionCaptura
from lux_eyes.engine.illumination import SecuenciadorIluminacion
from lux_eyes.engine.synchronizer import asignar_frames_a_meridianos
from scripts_validacion_pi.config_pi import PINES_POR_MERIDIANO, construir_fuente_video


def main():
    # UNA sola instancia de reloj, compartida entre iluminación y cámara
    # — exactamente el [PRINCIPIO CRÍTICO] de 7.3 del Maestro.
    reloj = RelojMonotono()
    led = ControladorLEDGPIO(PINES_POR_MERIDIANO)
    fuente = construir_fuente_video(reloj)
    config = ConfiguracionCaptura(
        angulos_meridianos=(0, 60, 120), repeticiones_ciclo=1,
        frames_objetivo_por_meridiano=30,
    )

    secuenciador = SecuenciadorIluminacion(led, reloj, config)

    print("Iniciando ciclo de iluminación + adquisición real...")
    secuenciador.iniciar_ciclo()
    fuente.iniciar()

    frames = []
    frames_en_actual = 0
    try:
        while not secuenciador.terminado():
            secuenciador.avanzar()
            if secuenciador.en_captura_util():
                frame = fuente.leer_frame()
                if frame is not None:
                    frames.append(frame)
                    frames_en_actual += 1
                    if frames_en_actual >= config.frames_objetivo_por_meridiano:
                        secuenciador.cerrar_meridiano_actual()
                        frames_en_actual = 0
    finally:
        fuente.detener()
        led.liberar()

    eventos = secuenciador.eventos()
    print(f"\nCapturados {len(frames)} frames en total, en {len(eventos)} eventos LED.")

    asignados = asignar_frames_a_meridianos(frames, eventos)
    total_asignado = sum(len(v) for v in asignados.values())
    print(f"Total asignado a algún meridiano: {total_asignado}/{len(frames)}")
    for angulo, lista in asignados.items():
        print(f"  Meridiano {angulo}°: {len(lista)} frames")

    # ── Auto-verificación programática de la regla de contención (6.4) ──
    errores = 0
    for angulo, lista_frames in asignados.items():
        evento = next(e for e in eventos if e.meridiano_grados == angulo)
        for frame in lista_frames:
            inicio_ventana = frame.timestamp_sensor - frame.duracion_exposicion
            fin_ventana = frame.timestamp_sensor
            dentro = inicio_ventana >= evento.inicio_estable and fin_ventana <= evento.fin_estable
            if not dentro:
                errores += 1
                print(f"  ERROR: frame en meridiano {angulo}° con ventana "
                      f"[{inicio_ventana:.6f}, {fin_ventana:.6f}] fuera del "
                      f"intervalo estable [{evento.inicio_estable:.6f}, "
                      f"{evento.fin_estable:.6f}]")

    print(f"\nFrames mal asignados: {errores} (el criterio de aceptación exige 0)")
    if errores == 0 and total_asignado > 0:
        print("CRITERIO CUMPLIDO: 0 frames mal asignados.")
    elif total_asignado == 0:
        print("SIN DATOS: no se asignó ningún frame a ningún meridiano — "
              "revisar timestamps y duración de estabilización antes de "
              "sacar conclusiones.")
    else:
        print("CRITERIO NO CUMPLIDO. Primera causa a revisar: latencia entre "
              "el instante real de exposición y reloj.ahora() en "
              "leer_frame() (ver RESTRICCIÓN-ACTUAL en "
              "adaptadores_picamera2.py) — puede requerir aumentar "
              "duracion_estabilizacion_segundos en ConfiguracionCaptura.")


if __name__ == "__main__":
    main()
