"""
engine/reflex_mask.py — Detección del reflejo de Purkinje como máscara de
EXCLUSIÓN (etapa G del Pipeline Architecture; 11.1 del Maestro).

[PRINCIPIO] No modificar la información fotométrica original: esta
función NUNCA altera los píxeles de la imagen. Reutiliza la técnica de
detección del notebook 1 (umbral + morfología + filtro por área y
circularidad) pero cambia por completo el destino: en el notebook, el
resultado alimentaba un inpainting (reconstrucción de píxeles, ELIMINADA
en el rediseño). Aquí el resultado es una máscara booleana de exclusión
que slope_estimator.py usa para ignorar esos puntos del ajuste — la
imagen en sí nunca se toca.

Es una función pura sobre un array numpy: no requiere cámara ni hardware.
"""

from __future__ import annotations

import cv2
import numpy as np


def detectar_reflejo(
    imagen: np.ndarray,
    percentil_umbral: float,
    umbral_absoluto: int,
    area_min: int,
    area_max: int,
    circularidad_min: float,
) -> np.ndarray:
    """
    Devuelve una máscara booleana (misma forma que `imagen`), True donde
    el píxel pertenece al reflejo de Purkinje detectado y debe EXCLUIRSE
    del ajuste de pendiente. No modifica `imagen`.

    Umbral combinado (percentil adaptativo + mínimo absoluto), igual que
    en el notebook 1, para marcar solo regiones extremadamente brillantes.
    Filtro por área y circularidad para descartar otras estructuras
    brillantes que no sean el reflejo especular.
    """
    if imagen.ndim == 3:
        imagen = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)

    umbral_percentil = float(np.percentile(imagen, percentil_umbral))
    umbral = max(umbral_percentil, float(umbral_absoluto))

    binaria = (imagen >= umbral).astype(np.uint8)

    kernel = np.ones((3, 3), np.uint8)
    binaria = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, kernel)
    binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, kernel)

    contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    mascara = np.zeros(imagen.shape, dtype=bool)
    for contorno in contornos:
        area = cv2.contourArea(contorno)
        if area < area_min or area > area_max:
            continue
        perimetro = cv2.arcLength(contorno, True)
        if perimetro == 0:
            continue
        circularidad = 4 * np.pi * area / (perimetro ** 2)
        if circularidad < circularidad_min:
            continue
        cv2.drawContours(mascara.view(np.uint8), [contorno], -1, 1, thickness=cv2.FILLED)

    return mascara


def detectar_reflejo_en_roi(
    imagen: np.ndarray,
    centro_x: float,
    centro_y: float,
    radio: float,
    margen_factor: float,
    percentil_umbral: float,
    umbral_absoluto: int,
    area_min: int,
    area_max: int,
    circularidad_min: float,
) -> np.ndarray:
    """
    Igual que detectar_reflejo(), pero el umbral por percentil se calcula
    SOLO sobre un recorte alrededor de (centro_x, centro_y), no sobre la
    imagen completa.

    [CORRECCIÓN, detectada al validar en hardware real] Con
    detectar_reflejo() aplicado a la imagen completa, el umbral por
    percentil (99 por defecto) se calcula sobre TODA la cara — si la
    imagen está sobreexpuesta (caso real observado: rostro con gran parte
    del área ya cerca de saturación por la iluminación IR en DC), ese
    umbral queda empujado muy alto, y el reflejo de Purkinje de UN ojo
    puede no superarlo mientras el del otro sí, de forma inconsistente
    entre ambos ojos del mismo frame. Acotar el cálculo del umbral a un
    recorte local alrededor del ojo que se está procesando hace que el
    reflejo (el punto más brillante DE ESE OJO) se detecte de forma
    consistente, sin depender del brillo del resto de la cara.

    Devuelve una máscara del MISMO tamaño que `imagen` (False fuera del
    recorte), para que slope_estimator.muestrear_mascara() siga usando
    coordenadas de imagen completa sin ningún cambio.
    """
    alto, ancho = imagen.shape[:2]
    margen = int(radio * margen_factor)
    x_min = max(int(centro_x - margen), 0)
    x_max = min(int(centro_x + margen), ancho)
    y_min = max(int(centro_y - margen), 0)
    y_max = min(int(centro_y + margen), alto)

    mascara_completa = np.zeros((alto, ancho), dtype=bool)
    if x_max <= x_min or y_max <= y_min:
        return mascara_completa

    recorte = imagen[y_min:y_max, x_min:x_max]
    mascara_recorte = detectar_reflejo(
        recorte, percentil_umbral, umbral_absoluto,
        area_min, area_max, circularidad_min,
    )
    mascara_completa[y_min:y_max, x_min:x_max] = mascara_recorte
    return mascara_completa
