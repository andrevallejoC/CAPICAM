"""
test_engine_haarcascade.py — Pruebas de aceptación de la Fase 4, parte 4:
DetectorPupilaHaar, el reemplazo de MediaPipe elegido para la Raspberry
Pi (ver adaptador_haarcascade.py — mediapipe no publica wheels ARM64).

A diferencia de test_engine_mediapipe.py, aquí SÍ se pudo probar con una
imagen de rostro real: "Lena", la imagen estándar de pruebas de visión
por computador, descargada del propio repositorio de OpenCV
(raw.githubusercontent.com, dominio con el que este entorno sí tiene
acceso de red — a diferencia del modelo de MediaPipe, que vive en
storage.googleapis.com). No es una imagen IR, así que no reemplaza la
validación real que debes hacer con tus propias capturas de la Pi
(criterio del Paso 3, "inspección visual"), pero sí confirma que la
cadena completa (rostro -> ROI del ojo lateral correcto -> Hough) da
resultados sensatos con un rostro real, no solo con ruido sintético.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from lux_eyes.engine.adaptador_haarcascade import DetectorPupilaHaar

VERDE = "\033[92m"; ROJO = "\033[91m"; AMARILLO = "\033[93m"; RESET = "\033[0m"
_ok = 0; _fail = 0; _saltadas = 0


def check(nombre, condicion):
    global _ok, _fail
    if condicion:
        _ok += 1
        print(f"  {VERDE}PASA{RESET}  {nombre}")
    else:
        _fail += 1
        print(f"  {ROJO}FALLA{RESET} {nombre}")


def saltar(nombre, razon):
    global _saltadas
    _saltadas += 1
    print(f"  {AMARILLO}SALTA{RESET} {nombre} ({razon})")


def main():
    print("\n=== engine/adaptador_haarcascade.py — detector real (sin mediapipe) ===\n")

    print("1) Construcción y validación de argumentos")
    try:
        DetectorPupilaHaar("od")
        check("se construye sin error para 'od'", True)
    except Exception as e:
        check(f"se construye sin error para 'od' ({e})", False)

    try:
        DetectorPupilaHaar("oi")
        check("se construye sin error para 'oi'", True)
    except Exception as e:
        check(f"se construye sin error para 'oi' ({e})", False)

    try:
        DetectorPupilaHaar("ojo_invalido")
        check("rechaza un valor de 'ojo' inválido", False)
    except ValueError:
        check("rechaza un valor de 'ojo' inválido", True)

    print("\n2) Comportamiento seguro sobre imágenes SIN rostro")
    detector_od = DetectorPupilaHaar("od")
    ruido = (np.random.default_rng(0).random((300, 300, 3)) * 255).astype(np.uint8)
    check("sobre ruido puro, devuelve None (no inventa una detección)",
          detector_od.detectar(ruido) is None)

    negro = np.zeros((300, 300, 3), dtype=np.uint8)
    check("sobre una imagen negra, también devuelve None de forma segura",
          detector_od.detectar(negro) is None)

    print("\n3) Detección sobre un rostro real (imagen de prueba estándar)")
    ruta_prueba = Path("/tmp/prueba_rostro.jpg")
    if not ruta_prueba.exists():
        saltar("detección sobre rostro real",
               f"no se encontró {ruta_prueba} — descárgala o ajusta la ruta")
    else:
        import cv2
        imagen = cv2.imread(str(ruta_prueba))
        check("la imagen de prueba se cargó correctamente", imagen is not None)

        det_od = DetectorPupilaHaar("od")
        det_oi = DetectorPupilaHaar("oi")
        resultado_od = det_od.detectar(imagen)
        resultado_oi = det_oi.detectar(imagen)

        check("se detectó una pupila para 'od'", resultado_od is not None)
        check("se detectó una pupila para 'oi'", resultado_oi is not None)

        if resultado_od is not None and resultado_oi is not None:
            check("'od' cae a la IZQUIERDA de 'oi' (mapeo lateral correcto, "
                  "relativo entre ambos, no contra el centro absoluto del "
                  "cuadro — el rostro puede no estar perfectamente centrado)",
                  resultado_od.centro_x < resultado_oi.centro_x)
            check("los dos centros detectados NO son el mismo punto",
                  abs(resultado_od.centro_x - resultado_oi.centro_x) > 10)
            check("los radios detectados son positivos y razonables (2-100px)",
                  0 < resultado_od.radio < 100 and 0 < resultado_oi.radio < 100)

    print(f"\n{'='*52}")
    total = _ok + _fail
    color = VERDE if _fail == 0 else ROJO
    print(f"{color}Resultado: {_ok}/{total} pruebas pasadas, {_fail} fallidas{RESET}"
          + (f", {_saltadas} saltadas" if _saltadas else ""))
    print("NOTA: la exactitud sobre imágenes IR reales de la Pi debe")
    print("verificarse con scripts_validacion_pi/verificar_4_deteccion_pupila.py")
    print(f"{'='*52}\n")
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
