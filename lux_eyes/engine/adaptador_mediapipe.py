"""
engine/adaptador_mediapipe.py — Implementación real de DetectorPupila
usando MediaPipe (Face Mesh o Face Landmarker, según la versión
disponible) + Transformada de Hough sobre el ROI del ojo.

[DECISIÓN] (2.3, reemplaza a Dlib/Roboflow): MediaPipe localiza el ojo con
sus landmarks faciales; la pupila en sí se segmenta con la Transformada
Circular de Hough sobre ese recorte — reutilizando la técnica ya validada
del notebook 1, pero acotada al ROI que MediaPipe entrega, no a la imagen
completa (más robusto y más rápido que Hough sobre toda la imagen).

DECISIÓN DE COMPATIBILIDAD (añadida tras detectar el problema en la
práctica: mediapipe>=0.10.30 eliminó la API legacy `mp.solutions` en
favor de la nueva API de Tasks, y no existe wheel de ninguna versión con
`mp.solutions` para Python 3.13+):

    Este adaptador detecta en tiempo de construcción cuál API está
    disponible y se adapta:

    - Si `mp.solutions.face_mesh` existe (mediapipe <0.10.30, típicamente
      Python <=3.12): se usa esa API directamente. No requiere ningún
      archivo de modelo externo (viene empaquetado en el propio paquete
      de pip).

    - Si no existe (mediapipe >=0.10.30, obligatorio en Python 3.13+):
      se usa la API de Tasks (`mp.tasks.vision.FaceLandmarker`), que
      requiere descargar un archivo de modelo (.task) y pasar su ruta
      local en `ruta_modelo_tasks`. Descárgalo desde:
      https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task

    Ambas rutas devuelven, internamente, una lista uniforme de objetos
    landmark con atributos .x/.y normalizados [0,1] — el resto del
    código (cálculo de ROI, Hough) es IDÉNTICO sin importar qué API se
    usó, gracias a _extraer_landmarks().

RESTRICCIÓN-ACTUAL:
    La rama de la API de Tasks se escribió y se verificó estructuralmente
    (construcción de FaceLandmarkerOptions, create_from_options con un
    archivo inexistente lanza FileNotFoundError como se esperaba — no un
    AttributeError, lo que confirma que los nombres de la API son
    correctos), pero NO se probó de extremo a extremo con un modelo real
    ni con una imagen de un rostro real, porque el entorno donde se
    escribió no tiene acceso de red a storage.googleapis.com.
ARQUITECTURA IDEAL:
    Validar el flujo completo (detección real sobre una imagen con
    rostro) en un entorno con el modelo .task descargado.
MEJORA FUTURA:
    Confirmar en tu máquina (con red real) que _extraer_landmarks()
    devuelve resultados sensatos con el modelo descargado, usando
    test_engine_mediapipe.py como base y añadiendo, si tienes, una foto
    real de un rostro.

Índices de landmarks de Face Mesh/Face Landmarker usados para cada ojo
(468 puntos, misma malla en ambas APIs): un recorte generoso alrededor
del ojo, no el contorno exacto del párpado, para no perder la pupila si
el recorte queda ligeramente descentrado.
"""

from __future__ import annotations

import cv2
import numpy as np

from .contratos_estimacion import DeteccionPupila
from .errores import FalloHardwareError

_LANDMARKS_OJO_DERECHO = (33, 133, 159, 145, 246, 161, 160, 144, 163, 7)
_LANDMARKS_OJO_IZQUIERDO = (362, 263, 386, 374, 466, 388, 387, 373, 390, 249)

_URL_MODELO_TASKS = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)


class DetectorPupilaMediaPipe:
    """
    Implementación real de DetectorPupila. ojo ∈ {'od', 'oi'} determina
    qué conjunto de landmarks se usa para acotar el ROI antes de aplicar
    Hough. Se adapta automáticamente a la API de MediaPipe disponible
    (ver docstring del módulo).
    """

    def __init__(self, ojo: str, radio_min: int = 8, radio_max: int = 60,
                 margen_roi_px: int = 15, ruta_modelo_tasks: str | None = None):
        if ojo not in ("od", "oi"):
            raise ValueError(f"ojo debe ser 'od' u 'oi', no {ojo!r}")

        # Importación diferida: mediapipe es pesado de cargar; solo se
        # paga ese costo si de verdad se instancia este detector.
        import mediapipe as mp

        self._landmarks = _LANDMARKS_OJO_DERECHO if ojo == "od" else _LANDMARKS_OJO_IZQUIERDO
        self._radio_min = radio_min
        self._radio_max = radio_max
        self._margen = margen_roi_px
        self._mp = mp

        if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh"):
            self._modo = "solutions"
            self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True, max_num_faces=1, refine_landmarks=True,
                min_detection_confidence=0.5,
            )
        else:
            self._modo = "tasks"
            if ruta_modelo_tasks is None:
                raise FalloHardwareError(
                    "Esta versión de mediapipe no expone mp.solutions "
                    "(típico en mediapipe>=0.10.30 / Python 3.13+). Debes "
                    "descargar el modelo Face Landmarker y pasar su ruta "
                    "local en ruta_modelo_tasks. Descárgalo desde: "
                    f"{_URL_MODELO_TASKS}"
                )
            opciones = mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=ruta_modelo_tasks),
                running_mode=mp.tasks.vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.5,
            )
            self._face_landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(opciones)

    def _extraer_landmarks(self, imagen_rgb: np.ndarray) -> list | None:
        """
        Devuelve una lista de landmarks (objetos con .x/.y normalizados)
        del primer rostro detectado, o None si no hay ninguno. Uniforma
        las dos APIs posibles de MediaPipe (ver docstring del módulo).
        """
        if self._modo == "solutions":
            resultado = self._face_mesh.process(imagen_rgb)
            if not resultado.multi_face_landmarks:
                return None
            return resultado.multi_face_landmarks[0].landmark

        # modo == "tasks"
        imagen_mp = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=imagen_rgb)
        resultado = self._face_landmarker.detect(imagen_mp)
        if not resultado.face_landmarks:
            return None
        return resultado.face_landmarks[0]

    def detectar(self, imagen: np.ndarray) -> DeteccionPupila | None:
        if imagen.ndim == 2:
            imagen_rgb = cv2.cvtColor(imagen, cv2.COLOR_GRAY2RGB)
        else:
            imagen_rgb = cv2.cvtColor(imagen, cv2.COLOR_BGR2RGB)

        alto, ancho = imagen_rgb.shape[:2]

        landmarks = self._extraer_landmarks(imagen_rgb)
        if landmarks is None:
            return None

        puntos = [
            (landmarks[i].x * ancho, landmarks[i].y * alto) for i in self._landmarks
        ]
        xs = [p[0] for p in puntos]
        ys = [p[1] for p in puntos]

        x_min = max(int(min(xs)) - self._margen, 0)
        x_max = min(int(max(xs)) + self._margen, ancho)
        y_min = max(int(min(ys)) - self._margen, 0)
        y_max = min(int(max(ys)) + self._margen, alto)
        if x_max <= x_min or y_max <= y_min:
            return None

        roi_gris = cv2.cvtColor(imagen_rgb[y_min:y_max, x_min:x_max], cv2.COLOR_RGB2GRAY)
        roi_suave = cv2.medianBlur(roi_gris, 5)

        circulos = cv2.HoughCircles(
            roi_suave, cv2.HOUGH_GRADIENT, dp=1.2,
            minDist=roi_suave.shape[0],
            param1=100, param2=25,
            minRadius=self._radio_min, maxRadius=self._radio_max,
        )
        if circulos is None:
            return None

        centro_roi_x = roi_suave.shape[1] / 2
        centro_roi_y = roi_suave.shape[0] / 2
        mejor = min(
            circulos[0],
            key=lambda c: (c[0] - centro_roi_x) ** 2 + (c[1] - centro_roi_y) ** 2,
        )
        cx, cy, r = mejor
        return DeteccionPupila(centro_x=float(cx + x_min), centro_y=float(cy + y_min), radio=float(r))
