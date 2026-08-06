"""
test_engine_mediapipe.py — Pruebas de aceptación de la Fase 4, parte 3:
DetectorPupilaMediaPipe, la única implementación de engine/ que usa una
librería real (MediaPipe) en lugar de un doble de prueba.

DECISIÓN DE COMPATIBILIDAD: mediapipe>=0.10.30 eliminó la API legacy
`mp.solutions` (obligatorio en Python 3.13+, donde no existe NINGÚN wheel
con esa API). DetectorPupilaMediaPipe detecta automáticamente cuál API
está disponible y se adapta (ver docstring de adaptador_mediapipe.py).
Este archivo de pruebas hace lo mismo: detecta qué API tienes disponible
y ejercita la rama correspondiente, en vez de asumir una versión fija.

LIMITACIÓN RECONOCIDA: no se dispone en este entorno de fotografías
reales de ojos para verificar la EXACTITUD de la detección (eso es,
además, un criterio de "inspección visual" según el propio Paso 3 del
Pipeline Architecture, no una prueba unitaria automatizable). Tampoco se
dispone, en el entorno donde se escribió este archivo, del modelo .task
que la rama "tasks" necesita (requiere descarga desde
storage.googleapis.com, fuera de la red permitida en ese entorno) — si
tu mediapipe usa esa rama y no le pasas ruta_modelo_tasks, las pruebas 2+
se saltan con una nota explicativa en vez de fallar.

Lo que sí se verifica aquí, de forma automática y real:
  1. El detector se construye correctamente con la API disponible en TU
     entorno (solutions o tasks), sin asumir una versión fija.
  2. Sobre una imagen sin ningún rostro, devuelve None de forma segura
     (nunca lanza excepción ni devuelve una detección inventada) —
     SOLO si tu entorno puede construir el detector (rama 'solutions',
     o rama 'tasks' con ruta_modelo_tasks provista).
  3. Valida 'od'/'oi' como únicos valores aceptados de `ojo`.

La verificación de exactitud REAL sobre fotografías de ojos capturadas
por la Raspberry Pi queda pendiente de que tú la hagas con el
dispositivo físico, tal como exige el criterio de aceptación documentado
del Paso 3 ("dispersión del centro pupilar entre frames bajo pocos
píxeles").
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from lux_eyes.engine.adaptador_mediapipe import DetectorPupilaMediaPipe
from lux_eyes.engine.errores import FalloHardwareError

# Si tienes el modelo descargado, pon aquí su ruta local para que las
# pruebas 2+ se ejecuten completas también en la rama "tasks":
#   https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
RUTA_MODELO_TASKS = None  # p. ej.: r"C:\Users\Fisiquito\Desktop\face_landmarker.task"

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
    print("\n=== engine/adaptador_mediapipe.py — detector real (sin fotos de ojos) ===\n")

    import mediapipe as mp
    modo_disponible = "solutions" if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh") else "tasks"
    print(f"API de mediapipe detectada en este entorno: '{modo_disponible}' "
          f"(mediapipe {mp.__version__})\n")

    print("1) Construcción y validación de argumentos")
    kwargs = {} if modo_disponible == "solutions" else {"ruta_modelo_tasks": RUTA_MODELO_TASKS}

    detector_construido = None
    try:
        detector_construido = DetectorPupilaMediaPipe("od", **kwargs)
        check("se construye sin error para 'od'", True)
    except FalloHardwareError as e:
        if modo_disponible == "tasks" and RUTA_MODELO_TASKS is None:
            saltar("se construye sin error para 'od'",
                   "rama 'tasks' sin RUTA_MODELO_TASKS configurada en este archivo")
        else:
            check(f"se construye sin error para 'od' ({e})", False)
    except Exception as e:
        check(f"se construye sin error para 'od' ({type(e).__name__}: {e})", False)

    try:
        DetectorPupilaMediaPipe("oi", **kwargs)
        check("se construye sin error para 'oi'", True)
    except FalloHardwareError:
        if modo_disponible == "tasks" and RUTA_MODELO_TASKS is None:
            saltar("se construye sin error para 'oi'",
                   "rama 'tasks' sin RUTA_MODELO_TASKS configurada en este archivo")
        else:
            check("se construye sin error para 'oi'", False)
    except Exception as e:
        check(f"se construye sin error para 'oi' ({type(e).__name__}: {e})", False)

    try:
        DetectorPupilaMediaPipe("ojo_invalido", **kwargs)
        check("rechaza un valor de 'ojo' inválido", False)
    except ValueError:
        check("rechaza un valor de 'ojo' inválido", True)
    except FalloHardwareError:
        # La validación de 'ojo' ocurre ANTES de construir el modelo, así
        # que si llega aquí en vez de ValueError, es un fallo real.
        check("rechaza un valor de 'ojo' inválido", False)

    print("\n2) Comportamiento seguro sobre una imagen SIN rostro")
    if detector_construido is None:
        saltar("sobre ruido puro, devuelve None",
               "el detector no se pudo construir (ver sección 1)")
        saltar("sobre una imagen negra, devuelve None",
               "el detector no se pudo construir (ver sección 1)")
    else:
        ruido = (np.random.default_rng(0).random((300, 300, 3)) * 255).astype(np.uint8)
        resultado = detector_construido.detectar(ruido)
        check("sobre ruido puro, devuelve None (no inventa una detección)",
              resultado is None)

        negro = np.zeros((300, 300, 3), dtype=np.uint8)
        resultado2 = detector_construido.detectar(negro)
        check("sobre una imagen negra, también devuelve None de forma segura",
              resultado2 is None)

    print(f"\n{'='*52}")
    total = _ok + _fail
    color = VERDE if _fail == 0 else ROJO
    print(f"{color}Resultado: {_ok}/{total} pruebas pasadas, {_fail} fallidas{RESET}"
          + (f", {_saltadas} saltadas" if _saltadas else ""))
    if _saltadas:
        print(f"{AMARILLO}Para ejecutar las pruebas saltadas, descarga el modelo y "
              f"configura RUTA_MODELO_TASKS al inicio de este archivo.{RESET}")
    print("NOTA: la exactitud de detección sobre ojos reales debe")
    print("verificarse en el dispositivo físico (criterio del Paso 3).")
    print(f"{'='*52}\n")
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
