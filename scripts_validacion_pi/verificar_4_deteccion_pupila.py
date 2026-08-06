"""
scripts_validacion_pi/verificar_4_deteccion_pupila.py — Verificación del
criterio de aceptación documentado del Paso 3 del roadmap del motor
(16.2 del Documento Maestro): "dispersión del centro pupilar entre
frames bajo pocos píxeles".

QUÉ HACE: enciende el LED del meridiano 0° (para tener iluminación IR
real durante la prueba — SIN esto, la escena no tiene suficiente
contraste para ningún detector), y con un OJO REAL frente a la cámara
(pide que un sujeto se coloque y fije la mirada, como en la sesión
real), captura N frames seguidos y ejecuta el detector de pupila
configurado sobre cada uno. Calcula automáticamente la dispersión
(desviación estándar) del centro detectado entre frames — el número que
el criterio de aceptación exige — y guarda una imagen con el círculo
detectado dibujado encima para inspección visual adicional.

Ejecutar: python -m scripts_validacion_pi.verificar_4_deteccion_pupila
"""

import os

import cv2
import numpy as np

from lux_eyes.engine.adaptadores_gpio import ControladorLEDGPIO, RelojMonotono
from scripts_validacion_pi.config_pi import (
    CARPETA_SALIDA, PINES_POR_MERIDIANO, construir_detector_pupila, construir_fuente_video,
)

N_FRAMES = 20
OJO_A_PROBAR = "od"  # cambia a "oi" para probar el otro ojo
MERIDIANO_ILUMINACION = 0  # cuál LED encender durante esta prueba


def main():
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    print(f"Construyendo detector de pupila para '{OJO_A_PROBAR}'...")
    detector = construir_detector_pupila(OJO_A_PROBAR)
    print("OK: construido.\n")

    reloj = RelojMonotono()
    led = ControladorLEDGPIO(PINES_POR_MERIDIANO)
    fuente = construir_fuente_video(reloj)

    print(f"Encendiendo LED del meridiano {MERIDIANO_ILUMINACION}° para tener "
          f"iluminación IR real durante la captura...")
    led.encender(MERIDIANO_ILUMINACION)
    fuente.iniciar()

    print(f"Capturando {N_FRAMES} frames. Asegúrate de que el sujeto está frente "
          f"a la cámara, a ~50cm, mirando al centro, sin moverse...")
    frames = []
    try:
        while len(frames) < N_FRAMES:
            frame = fuente.leer_frame()
            if frame is not None:
                frames.append(frame)
    finally:
        fuente.detener()
        led.liberar()

    detecciones = []
    for frame in frames:
        d = detector.detectar(frame.imagen)
        if d is not None:
            detecciones.append(d)

    print(f"\nPupila detectada en {len(detecciones)}/{len(frames)} frames.")
    if len(detecciones) < 2:
        print("MUY POCAS DETECCIONES. Antes de sospechar del detector, revisa "
              "en orden:")
        print("  1. ¿Se vio encendido el LED durante la captura? (si no, revisa "
              "el cableado del meridiano 0°, ya validado en verificar_1_leds.py)")
        print("  2. Distancia real ~50cm, mirando derecho a la cámara.")
        print("  3. Revisa la imagen guardada más abajo (si se guardó alguna) "
              "para ver qué está viendo realmente la cámara.")
        # Guarda igual el último frame crudo, aunque no hubo detección, para
        # poder diagnosticar visualmente qué vio la cámara.
        if frames:
            ruta_diagnostico = os.path.join(
                CARPETA_SALIDA, f"verificar_4_SIN_DETECCION_{OJO_A_PROBAR}.png"
            )
            cv2.imwrite(ruta_diagnostico, frames[-1].imagen)
            print(f"  Guardado el último frame crudo (sin anotar) para diagnóstico: "
                  f"{ruta_diagnostico}")
        return

    centros_x = np.array([d.centro_x for d in detecciones])
    centros_y = np.array([d.centro_y for d in detecciones])
    radios = np.array([d.radio for d in detecciones])

    dispersion_x = float(np.std(centros_x))
    dispersion_y = float(np.std(centros_y))
    dispersion_radio = float(np.std(radios))

    print(f"\nCentro pupilar detectado — media: ({centros_x.mean():.1f}, "
          f"{centros_y.mean():.1f}) px, radio medio: {radios.mean():.1f} px")
    print(f"Dispersión (desviación estándar) entre frames:")
    print(f"  centro_x: {dispersion_x:.2f} px")
    print(f"  centro_y: {dispersion_y:.2f} px")
    print(f"  radio:    {dispersion_radio:.2f} px")
    print("\nEl criterio de aceptación pide 'bajo pocos píxeles' sin un número")
    print("exacto documentado — usa este valor como línea base y decide si es")
    print("aceptable para tu caso (valores de 1-3 px son razonables; más de")
    print("5-10 px sugiere revisar enfoque, iluminación o distancia).")

    # ── Imagen anotada para inspección visual ──
    ultimo_frame = frames[-1]
    ultima_deteccion = detecciones[-1]
    imagen_color = cv2.cvtColor(ultimo_frame.imagen, cv2.COLOR_GRAY2BGR)
    cv2.circle(
        imagen_color,
        (int(ultima_deteccion.centro_x), int(ultima_deteccion.centro_y)),
        int(ultima_deteccion.radio), (0, 255, 0), 2,
    )
    cv2.circle(
        imagen_color,
        (int(ultima_deteccion.centro_x), int(ultima_deteccion.centro_y)),
        2, (0, 0, 255), -1,
    )
    ruta = os.path.join(CARPETA_SALIDA, f"verificar_4_deteccion_{OJO_A_PROBAR}.png")
    cv2.imwrite(ruta, imagen_color)
    print(f"\nGuardado: {ruta}")
    print("Revísala: el círculo verde debe coincidir con el borde de la pupila,")
    print("y el punto rojo con su centro.")


if __name__ == "__main__":
    main()
