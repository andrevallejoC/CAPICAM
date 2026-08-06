"""
scripts_validacion_pi/verificar_2_camara.py — Verificación manual de la
captura de vídeo (adaptadores_picamera2.FuenteDeVideoPicamera2).

QUÉ HACE: construye la fuente con un RelojMonotono (el mismo tipo de
reloj que usará illumination), captura N frames seguidos SIN iluminación
IR controlada (esto solo prueba la cámara en sí), guarda algunos como
.png en CARPETA_SALIDA para inspección visual, e imprime estadísticas de
timestamps y metadatos para confirmar que:
  1. Los timestamps (ahora tomados del RELOJ COMPARTIDO, no de
     SensorTimestamp — ver la corrección documentada en
     adaptadores_picamera2.py) crecen de forma monótona y con un
     intervalo razonable.
  2. ExposureTime permanece FIJO (parámetros manuales, principio 5.1: sin
     autoexposición).
  3. FocusFoM (que slope_estimator.py usa para ponderar calidad) viene
     presente en los metadatos.

Ejecutar: python -m scripts_validacion_pi.verificar_2_camara
"""

import os

from lux_eyes.engine.adaptadores_gpio import RelojMonotono
from scripts_validacion_pi.config_pi import CARPETA_SALIDA, construir_fuente_video

N_FRAMES = 30
N_FRAMES_A_GUARDAR = 3


def main():
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    reloj = RelojMonotono()
    print("Construyendo e iniciando FuenteDeVideoPicamera2...")
    fuente = construir_fuente_video(reloj)
    fuente.iniciar()
    print("OK: cámara iniciada.\n")

    frames = []
    try:
        print(f"Capturando {N_FRAMES} frames...")
        while len(frames) < N_FRAMES:
            frame = fuente.leer_frame()
            if frame is not None:
                frames.append(frame)
    finally:
        fuente.detener()

    print(f"Capturados {len(frames)} frames.\n")

    # ── Timestamps (ahora en la base del reloj compartido) ──
    timestamps = [f.timestamp_sensor for f in frames]
    deltas = [b - a for a, b in zip(timestamps, timestamps[1:])]
    delta_medio = sum(deltas) / len(deltas) if deltas else 0.0
    print("Timestamps (segundos, reloj compartido):")
    print(f"  Primero: {timestamps[0]:.6f}  Último: {timestamps[-1]:.6f}")
    if delta_medio > 0:
        print(f"  Delta medio entre frames: {delta_medio*1000:.2f} ms "
              f"(~{1/delta_medio:.1f} fps aparente)")
    print(f"  ¿Todos los deltas son positivos (orden monótono)? "
          f"{'SI' if all(d > 0 for d in deltas) else 'NO -- PROBLEMA'}")

    # ── Exposición fija ──
    exposiciones = {f.duracion_exposicion for f in frames}
    print(f"\nValores distintos de duracion_exposicion vistos: {len(exposiciones)} "
          f"{'(OK: constante)' if len(exposiciones) <= 2 else '(revisar: variando)'}")

    # ── Metadatos ──
    con_focusfom = sum(1 for f in frames if f.metadatos.get("FocusFoM") is not None)
    print(f"\nFrames con FocusFoM presente: {con_focusfom}/{len(frames)} "
          f"{'(OK)' if con_focusfom == len(frames) else '(FALTA: revisar metadatos de picamera2)'}")

    con_hw_ts = sum(1 for f in frames if f.metadatos.get("SensorTimestampHardware") is not None)
    print(f"Frames con SensorTimestampHardware presente (diagnóstico): "
          f"{con_hw_ts}/{len(frames)}")

    # ── Guardar imágenes para inspección visual (opcional: requiere cv2) ──
    try:
        import cv2
        for i, frame in enumerate(frames[:N_FRAMES_A_GUARDAR]):
            ruta = os.path.join(CARPETA_SALIDA, f"verificar_2_frame_{i}.png")
            cv2.imwrite(ruta, frame.imagen)
            print(f"Guardado: {ruta}")
        print("\nRevisa las imágenes guardadas: deben verse como una foto IR real")
        print("(no negras, no saturadas, no corruptas). Si es así, y los")
        print("timestamps son monótonos con delta razonable, la cámara queda validada.")
    except ImportError:
        print("\nAVISO: opencv (cv2) no está instalado, así que no se guardaron")
        print("imágenes para inspección visual — pero los chequeos numéricos de")
        print("arriba (timestamps, exposición, metadatos) sí se completaron sin él.")
        print("Instala opencv más adelante (para los scripts 4, 5 y 6, que sí lo")
        print("necesitan) con: sudo apt install python3-opencv")


if __name__ == "__main__":
    main()
