"""
engine/slope_estimator.py — Muestreo del perfil de intensidad y
estimación robusta de la pendiente (etapas H e I del Pipeline
Architecture; 11.2 del Maestro).

[PRINCIPIO] El modelo se mantiene lineal por fundamento óptico: el
desenfoque produce, en el rango de trabajo, una rampa de luminancia cuya
pendiente es proporcional al error refractivo. Lo que se rediseña es el
ESTIMADOR de esa pendiente, no el modelo — de ahí el patrón Strategy: los
cuatro candidatos (OLS, Huber, Theil-Sen, RANSAC) implementan el mismo
contrato EstimadorPendiente y son completamente intercambiables, tal como
exige el plan experimental de la sección 3.2 del Pipeline Architecture
(decisión aprobada en el diseño de la Fase 4, §0.3).

Cada estimador ignora POR COMPLETO los puntos marcados como inválidos en
`mascara_valida` (el reflejo de Purkinje detectado por reflex_mask.py) —
no les da menos peso, los excluye del ajuste, coherente con 11.1.
"""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import HuberRegressor, LinearRegression, RANSACRegressor, TheilSenRegressor

from .contratos_estimacion import ResultadoPendiente


def _coordenadas_muestreo(
    p1: tuple[float, float], p2: tuple[float, float]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(xs, ys, posiciones) — mismas coordenadas de píxel para cualquier
    array que se quiera muestrear a lo largo del segmento p1->p2, de modo
    que muestrear_perfil() y muestrear_mascara() queden perfectamente
    alineados punto a punto."""
    x1, y1 = p1
    x2, y2 = p2
    longitud = float(np.hypot(x2 - x1, y2 - y1))
    n_muestras = max(int(round(longitud)), 2)

    xs = np.linspace(x1, x2, n_muestras)
    ys = np.linspace(y1, y2, n_muestras)
    posiciones = np.linspace(0.0, longitud, n_muestras)
    return xs, ys, posiciones


def muestrear_perfil(
    imagen: np.ndarray, p1: tuple[float, float], p2: tuple[float, float]
) -> tuple[np.ndarray, np.ndarray]:
    """
    Muestrea la imagen píxel a píxel a lo largo del segmento p1->p2.
    Devuelve (posiciones, intensidades), ambos arrays 1D de igual longitud.
    posiciones es la distancia acumulada desde p1 (en píxeles).
    """
    xs, ys, posiciones = _coordenadas_muestreo(p1, p2)
    alto, ancho = imagen.shape[:2]
    xs_i = np.clip(np.round(xs).astype(int), 0, ancho - 1)
    ys_i = np.clip(np.round(ys).astype(int), 0, alto - 1)
    intensidades = imagen[ys_i, xs_i].astype(float)

    return posiciones, intensidades


def muestrear_mascara(
    mascara: np.ndarray, p1: tuple[float, float], p2: tuple[float, float]
) -> np.ndarray:
    """
    Muestrea una máscara booleana (p. ej. la de reflex_mask.detectar_reflejo)
    en las MISMAS coordenadas de píxel que muestrear_perfil() usaría para
    el mismo segmento, garantizando que ambos arrays queden alineados
    punto a punto para construir mascara_valida en motor.py.
    """
    xs, ys, _ = _coordenadas_muestreo(p1, p2)
    alto, ancho = mascara.shape[:2]
    xs_i = np.clip(np.round(xs).astype(int), 0, ancho - 1)
    ys_i = np.clip(np.round(ys).astype(int), 0, alto - 1)
    return mascara[ys_i, xs_i]


def _r2_robusto(y_real: np.ndarray, y_predicho: np.ndarray) -> float:
    """R² clásico; con pocos puntos o varianza nula se acota a [0, 1]."""
    ss_res = float(np.sum((y_real - y_predicho) ** 2))
    ss_tot = float(np.sum((y_real - np.mean(y_real)) ** 2))
    if ss_tot == 0.0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - ss_res / ss_tot))


def _filtrar_validos(
    posiciones: np.ndarray, intensidades: np.ndarray, mascara_valida: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    return posiciones[mascara_valida], intensidades[mascara_valida]


def _ajustar_con_modelo_sklearn(modelo, posiciones, intensidades, mascara_valida) -> ResultadoPendiente:
    x, y = _filtrar_validos(posiciones, intensidades, mascara_valida)
    if len(x) < 2:
        return ResultadoPendiente(pendiente=0.0, calidad=0.0)

    X = x.reshape(-1, 1)
    modelo.fit(X, y)
    pendiente = float(modelo.coef_[0] if hasattr(modelo, "coef_") else modelo.estimator_.coef_[0])
    y_predicho = modelo.predict(X)
    calidad = _r2_robusto(y, y_predicho)
    return ResultadoPendiente(pendiente=pendiente, calidad=calidad)


class EstimadorOLS:
    """Línea base: mínimos cuadrados ordinarios. Muy sensible a outliers (11.2)."""

    def ajustar(self, posiciones, intensidades, mascara_valida) -> ResultadoPendiente:
        return _ajustar_con_modelo_sklearn(
            LinearRegression(), posiciones, intensidades, mascara_valida
        )


class EstimadorHuber:
    """Candidato principal: compromiso OLS/robusto (11.2)."""

    def __init__(self, epsilon: float = 1.35):
        self._epsilon = epsilon

    def ajustar(self, posiciones, intensidades, mascara_valida) -> ResultadoPendiente:
        return _ajustar_con_modelo_sklearn(
            HuberRegressor(epsilon=self._epsilon), posiciones, intensidades, mascara_valida
        )


class EstimadorTheilSen:
    """Candidato principal: robusto (ruptura ~29%), determinista (11.2)."""

    def ajustar(self, posiciones, intensidades, mascara_valida) -> ResultadoPendiente:
        return _ajustar_con_modelo_sklearn(
            TheilSenRegressor(random_state=0), posiciones, intensidades, mascara_valida
        )


class EstimadorRANSAC:
    """Reserva: bueno con outliers masivos, estocástico (11.2)."""

    def __init__(self, random_state: int = 0):
        self._random_state = random_state

    def ajustar(self, posiciones, intensidades, mascara_valida) -> ResultadoPendiente:
        x, y = _filtrar_validos(posiciones, intensidades, mascara_valida)
        if len(x) < 2:
            return ResultadoPendiente(pendiente=0.0, calidad=0.0)
        modelo = RANSACRegressor(
            estimator=LinearRegression(), random_state=self._random_state
        )
        X = x.reshape(-1, 1)
        modelo.fit(X, y)
        pendiente = float(modelo.estimator_.coef_[0])
        y_predicho = modelo.predict(X)
        calidad = _r2_robusto(y, y_predicho)
        return ResultadoPendiente(pendiente=pendiente, calidad=calidad)
