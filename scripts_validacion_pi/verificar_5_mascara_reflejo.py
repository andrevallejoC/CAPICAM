"""
scripts_validacion_pi/verificar_5_mascara_reflejo.py — Verificación del
criterio de aceptación documentado del Paso 4 del roadmap del motor
(16.2 del Documento Maestro): "inspección visual; la máscara cubre el
reflejo sin invadir el gradiente".

QUÉ HACE: enciende el LED del meridiano 0° (real, vía GPIO — antes este
script solo lo pedía por texto, sin encenderlo de verdad; corregido tras
detectar el problema en la práctica), y con un ojo real frente a la
cámara, intenta hasta N_FRAMES_MAXIMO capturas hasta lograr una en la
que se detecte la pupila. Calcula la máscara de reflejo de Purkinje
(reflex_mask.detectar_reflejo) sobre ese frame y guarda una imagen
compuesta con: la imagen original, la máscara resaltada en rojo
semitransparente, y los meridianos dibujados encima — para que
confirmes visualmente que la máscara cubre el reflejo (punto brillante)
sin comerse zonas del gradiente que sí aportan señal útil.

Este criterio es EXPLÍCITAMENTE de inspección visual según el propio
Pipeline Architecture — no hay forma de automatizarlo por completo.

Ejecutar: python -m scripts_validacion_pi.verificar_5_mascara_reflejo
"""

import os

import cv2
import numpy as np

from lux_eyes.engine.adaptadores_gpio import ControladorLEDGPIO, RelojMonotono
from lux_eyes.engine.configuracion import ConfiguracionCaptura
from lux_eyes.engine.geometry import calcular_geometria
from lux_eyes.engine.reflex_mask import detectar_reflejo_en_roi
from scripts_validacion_pi.config_pi import (
    CARPETA_SALIDA, PINES_POR_MERIDIANO, construir_detector_pupila, construir_fuente_video,
)

OJO_A_PROBAR = "od"
MERIDIANO_ILUMINACION = 0
N_FRAMES_MAXIMO = 30  # intentos antes de rendirse


def main():
    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    config = ConfiguracionCaptura()

    detector = construir_detector_pupila(OJO_A_PROBAR)

    reloj = RelojMonotono()
    led = ControladorLEDGPIO(PINES_POR_MERIDIANO)
    fuente = construir_fuente_video(reloj)

    print(f"Encendiendo LED del meridiano {MERIDIANO_ILUMINACION}°...")
    led.encender(MERIDIANO_ILUMINACION)
    fuente.iniciar()

    print(f"Buscando un frame con pupila detectada (hasta {N_FRAMES_MAXIMO} "
          f"intentos). Asegúrate de estar ya bien posicionado, a ~50cm, "
          f"mirando al centro, ANTES de correr este script...")

    frame_valido = None
    geo_valida = None
    ultimo_frame_visto = None
    try:
        for _ in range(N_FRAMES_MAXIMO):
            frame = fuente.leer_frame()
            if frame is None:
                continue
            ultimo_frame_visto = frame
            geo = calcular_geometria(
                frame.imagen, detector, config.angulos_meridianos,
                config.fraccion_longitud_meridiano, config.fraccion_borde_excluido,
            )
            if geo is not None:
                frame_valido = frame
                geo_valida = geo
                break
    finally:
        fuente.detener()
        led.liberar()

    if frame_valido is None:
        print("\nNo se detectó pupila en ningún intento.")
        if ultimo_frame_visto is not None:
            ruta_diagnostico = os.path.join(
                CARPETA_SALIDA, f"verificar_5_SIN_DETECCION_{OJO_A_PROBAR}.png"
            )
            cv2.imwrite(ruta_diagnostico, ultimo_frame_visto.imagen)
            print(f"Guardado el último frame crudo para diagnóstico: {ruta_diagnostico}")
        print("Revisa posicionamiento/distancia (mismo criterio que en "
              "verificar_4_deteccion_pupila.py, que ya validaste).")
        return

    mascara = detectar_reflejo_en_roi(
        frame_valido.imagen,
        geo_valida.deteccion.centro_x, geo_valida.deteccion.centro_y,
        geo_valida.deteccion.radio, config.margen_roi_reflejo,
        config.percentil_umbral_reflejo, config.umbral_absoluto_reflejo,
        config.area_min_reflejo, config.area_max_reflejo,
        config.circularidad_min_reflejo,
    )

    print(f"\nPupila detectada. Máscara: {mascara.sum()} píxeles marcados "
          f"como reflejo (de {mascara.size} totales).")

    # ── Imagen compuesta para inspección visual ──
    imagen_color = cv2.cvtColor(frame_valido.imagen, cv2.COLOR_GRAY2BGR)
    overlay = imagen_color.copy()
    overlay[mascara] = (0, 0, 255)  # rojo donde la máscara excluye
    compuesta = cv2.addWeighted(overlay, 0.4, imagen_color, 0.6, 0)

    for angulo, (p1, p2) in geo_valida.meridianos.items():
        color = {0: (0, 255, 0), 60: (255, 0, 0), 120: (0, 255, 255)}.get(angulo, (255, 255, 255))
        cv2.line(compuesta, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), color, 1)

    ruta = os.path.join(CARPETA_SALIDA, f"verificar_5_mascara_{OJO_A_PROBAR}.png")
    cv2.imwrite(ruta, compuesta)
    print(f"\nGuardado: {ruta}")
    print("Revísala: el área roja debe cubrir el punto brillante del reflejo")
    print("de Purkinje (si lo hay en este frame) sin invadir el resto del")
    print("gradiente a lo largo de los meridianos dibujados (líneas de color).")
    if mascara.sum() == 0:
        print("\nNOTA: la máscara no marcó ningún píxel en este frame — puede")
        print("ser normal si el reflejo no era muy brillante en este ángulo, o")
        print("puede indicar que los umbrales necesitan ajuste. Prueba con")
        print("varios frames/ángulos antes de concluir.")


if __name__ == "__main__":
    main()
