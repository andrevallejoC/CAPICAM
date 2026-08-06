"""
engine/adaptador_haarcascade.py — Implementación real de DetectorPupila
usando los clasificadores Haar en cascada de OpenCV (rostro + ojo) +
Transformada de Hough sobre el ROI del ojo.

[DECISIÓN REVISADA respecto a 2.3 del Documento Maestro]
    2.3 declaraba MediaPipe como detector principal (reemplazando a
    Dlib/Roboflow). Se añade esta implementación alternativa tras
    descubrir, validando en la Raspberry Pi física (ver
    scripts_validacion_pi/), que Google NO publica en PyPI ningún wheel
    de `mediapipe` para Linux ARM64 — para ninguna versión del paquete,
    no es un problema de versión de Python local. Es una limitación de
    la plataforma, confirmada revisando directamente los archivos
    publicados de mediapipe 0.10.35 (solo win_amd64,
    manylinux_2_28_x86_64, macosx_11_0_arm64).

    Alternativas evaluadas antes de esta decisión:
      A) Compilar mediapipe desde código fuente para ARM64 (Google
         documenta un pipeline oficial con Docker + Bazel específico
         para Raspberry Pi). Descartada por ahora: horas de build en
         hardware limitado, y fragilidad de mantenimiento futuro (cada
         actualización de mediapipe requeriría recompilar).
      B) Usar un wheel viejo de la comunidad (mediapipe 0.8.x, ~2021).
         Descartada: alto riesgo de incompatibilidad con numpy/protobuf
         actuales y con Python 3.13.
      C) [ELEGIDA] Reemplazar MediaPipe por clasificadores Haar de
         OpenCV, ya incluidos en el paquete opencv-python que el
         proyecto ya usa y ya está validado funcionando en la Pi (ver
         verificar_2_camara.py / verificar_3_sincronizacion.py). Cero
         descargas externas, cero problemas de wheel por arquitectura,
         coherente además con que el resto del pipeline (reflex_mask.py,
         la propia detección de pupila por Hough) ya usa técnicas de
         visión clásica, no aprendizaje profundo.

    adaptador_mediapipe.py NO se elimina: sigue siendo válido en
    cualquier entorno x86_64/macOS (por ejemplo, desarrollo o pruebas
    fuera de la Pi, como se hizo en esta misma conversación). Este
    archivo es el que se usa por defecto para la Raspberry Pi.

RESTRICCIÓN-ACTUAL:
    Los clasificadores Haar son menos robustos que MediaPipe ante
    variaciones de pose/ángulo/oclusión parcial, y fueron entrenados
    sobre fotografía de espectro visible, no IR. Su desempeño real sobre
    las imágenes IR del dispositivo NO se ha validado todavía — igual
    que ya estaba advertido para MediaPipe, es un criterio de inspección
    visual (Paso 3 del roadmap del motor), no algo verificable sin
    hardware real.
ARQUITECTURA IDEAL:
    Un detector de rostro/ojo entrenado o afinado específicamente sobre
    imágenes IR capturadas por el propio dispositivo, con wheels ARM64
    nativos disponibles.
MEJORA FUTURA:
    Si la Opción A (compilar mediapipe para ARM64) resulta viable y
    estable en el tiempo, o si Google publica wheels ARM64 oficiales,
    comparar ambos detectores con el mismo protocolo de validación ya
    usado para los estimadores de pendiente (11.2): repetibilidad de la
    posición del centro pupilar detectado sobre las mismas imágenes.

DECISIÓN de mapeo lateral (igual que adaptador_mediapipe.py): 'od' (ojo
derecho del PACIENTE) corresponde al lado IZQUIERDO de la imagen cuando
el paciente mira de frente a la cámara (imagen no espejada).
"""

from __future__ import annotations

import os

import cv2
import numpy as np

from .contratos_estimacion import DeteccionPupila


class DetectorPupilaHaar:
    """
    Implementación real de DetectorPupila usando cv2.CascadeClassifier
    (rostro + ojo, ambos incluidos en el paquete opencv-python) + Hough
    Circles sobre el ROI del ojo — mismo enfoque de segmentación de
    pupila que adaptador_mediapipe.py, solo cambia cómo se acota el ROI.
    """

    # Rutas donde pueden vivir los XML de Haar, según cómo se instaló
    # opencv. El wheel de pip (opencv-python/-headless) expone
    # cv2.data.haarcascades apuntando a los XML empaquetados DENTRO del
    # paquete. El paquete de Debian/apt (python3-opencv) NO define
    # cv2.data en absoluto — coloca los XML como archivos de sistema en
    # una ruta fija (detectado al validar en la Raspberry Pi real, donde
    # python3-opencv se instaló vía apt). Se prueban ambos, en orden.
    _RUTAS_CANDIDATAS_CASCADAS = [
        None,  # se resuelve dinámicamente: cv2.data.haarcascades, si existe
        "/usr/share/opencv4/haarcascades/",
        "/usr/share/opencv4/haarcascades",
        "/usr/local/share/opencv4/haarcascades/",
        "/usr/share/opencv/haarcascades/",
        "/usr/share/doc/opencv-data/haarcascades/",
    ]

    def __init__(self, ojo: str, radio_min: int = 8, radio_max: int = 60,
                 margen_roi_px: int = 10):
        if ojo not in ("od", "oi"):
            raise ValueError(f"ojo debe ser 'od' u 'oi', no {ojo!r}")

        self._ojo = ojo
        self._radio_min = radio_min
        self._radio_max = radio_max
        self._margen = margen_roi_px

        carpeta_cascadas = self._resolver_carpeta_cascadas()
        ruta_rostro = os.path.join(carpeta_cascadas, "haarcascade_frontalface_default.xml")
        ruta_ojo = os.path.join(carpeta_cascadas, "haarcascade_eye.xml")

        self._clasificador_rostro = cv2.CascadeClassifier(ruta_rostro)
        self._clasificador_ojo = cv2.CascadeClassifier(ruta_ojo)

        if self._clasificador_rostro.empty() or self._clasificador_ojo.empty():
            raise RuntimeError(
                "No se pudieron cargar los clasificadores Haar de OpenCV "
                f"desde {carpeta_cascadas!r}. Localízalos manualmente con: "
                "sudo find / -name 'haarcascade_frontalface_default.xml' "
                "y agrega esa carpeta a _RUTAS_CANDIDATAS_CASCADAS en este archivo."
            )

    @classmethod
    def _resolver_carpeta_cascadas(cls) -> str:
        """
        Busca, en orden, una carpeta que contenga los XML de Haar
        necesarios. Prueba primero cv2.data.haarcascades (wheel de pip);
        si ese atributo no existe (paquete de Debian/apt, ver docstring
        del módulo), prueba rutas de sistema conocidas.
        """
        for candidata in cls._RUTAS_CANDIDATAS_CASCADAS:
            if candidata is None:
                carpeta = getattr(getattr(cv2, "data", None), "haarcascades", None)
            else:
                carpeta = candidata

            if carpeta is None:
                continue

            ruta_prueba = os.path.join(carpeta, "haarcascade_frontalface_default.xml")
            if os.path.isfile(ruta_prueba):
                return carpeta

        raise RuntimeError(
            "No se encontró haarcascade_frontalface_default.xml en ninguna "
            "ruta conocida. Localízalo manualmente en tu sistema con: "
            "sudo find / -name 'haarcascade_frontalface_default.xml' "
            "2>/dev/null — y agrega la carpeta resultante a "
            "DetectorPupilaHaar._RUTAS_CANDIDATAS_CASCADAS en "
            "adaptador_haarcascade.py."
        )

    def _region_ojo_dentro_de_rostro(
        self, rostro_gris: np.ndarray, fx: int, fy: int
    ) -> tuple[int, int, int, int] | None:
        """
        Detecta ojos dentro del ROI del rostro y devuelve el bounding box
        (en coordenadas de la imagen COMPLETA) del que corresponde a
        self._ojo, según su posición horizontal dentro del rostro.
        """
        ojos = self._clasificador_ojo.detectMultiScale(
            rostro_gris, scaleFactor=1.1, minNeighbors=8, minSize=(20, 20)
        )
        if len(ojos) == 0:
            return None

        ancho_rostro = rostro_gris.shape[1]
        centro_rostro_x = ancho_rostro / 2

        # 'od' (ojo derecho del paciente) aparece en la mitad IZQUIERDA
        # de la imagen (paciente de frente, imagen no espejada).
        candidatos = [
            (ex, ey, ew, eh) for (ex, ey, ew, eh) in ojos
            if (ex + ew / 2 < centro_rostro_x) == (self._ojo == "od")
        ]
        if not candidatos:
            return None

        # Si hay varios candidatos del lado correcto (p. ej. una ceja
        # detectada como falso positivo), toma el más grande.
        ex, ey, ew, eh = max(candidatos, key=lambda c: c[2] * c[3])
        return (fx + ex, fy + ey, ew, eh)

    def detectar(self, imagen: np.ndarray) -> DeteccionPupila | None:
        gris = imagen if imagen.ndim == 2 else cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
        alto, ancho = gris.shape[:2]

        rostros = self._clasificador_rostro.detectMultiScale(
            gris, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
        )
        if len(rostros) == 0:
            return None
        # Rostro más grande (más cercano/central) — mismo criterio que
        # max_num_faces=1 de MediaPipe.
        fx, fy, fw, fh = max(rostros, key=lambda r: r[2] * r[3])
        rostro_gris = gris[fy:fy + fh, fx:fx + fw]

        region_ojo = self._region_ojo_dentro_de_rostro(rostro_gris, fx, fy)
        if region_ojo is None:
            return None
        ex, ey, ew, eh = region_ojo

        x_min = max(ex - self._margen, 0)
        x_max = min(ex + ew + self._margen, ancho)
        y_min = max(ey - self._margen, 0)
        y_max = min(ey + eh + self._margen, alto)
        if x_max <= x_min or y_max <= y_min:
            return None

        roi_gris = gris[y_min:y_max, x_min:x_max]
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
