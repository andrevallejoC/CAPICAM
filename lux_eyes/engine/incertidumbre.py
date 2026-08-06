"""
engine/incertidumbre.py — Propagación de incertidumbre de las pendientes
meridionales a esfera/cilindro/eje (11.4 del Maestro).

[DECISIÓN] (Fase 4, §0.4): se implementa propagación ANALÍTICA LINEAL —
derivar esfera, cilindro y eje respecto a R(0)/R(60)/R(120) y combinar con
las desviaciones estándar de cada meridiano, asumiendo independencia entre
meridianos. Es determinista, barata (adecuada para la Raspberry Pi) y
verificable con casos calculados a mano.

Aislado en su propio archivo porque es la pieza de mayor incertidumbre de
DISEÑO del proyecto: si la validación experimental (Fase 4, Paso 7) revela
que la aproximación lineal no captura bien la sensibilidad angular del eje
(el eje es muy sensible al balance J0/J45 cerca de un astigmatismo bajo,
17.6), el reemplazo por una propagación Monte Carlo queda contenido en
este único archivo, sin tocar refraction.py ni motor.py.

RESTRICCIÓN-ACTUAL:
    La propagación lineal asume que las funciones (esfera, cilindro, eje)
    son aproximadamente lineales en el entorno de la medición. Cerca de un
    astigmatismo muy bajo (J0, J45 ambos cercanos a 0), el eje se vuelve
    angularmente muy sensible y la aproximación lineal puede subestimar su
    incertidumbre real.
ARQUITECTURA IDEAL:
    Propagación por simulación (Monte Carlo): muestrear repetidamente de
    N(R(ángulo), sd(ángulo)) para cada meridiano, recalcular esfera/
    cilindro/eje muchas veces, tomar la dispersión resultante. Captura
    correctamente la no linealidad de atan2 sin asumir nada sobre el
    régimen de operación.
MEJORA FUTURA:
    Sustituir esta función por una implementación Monte Carlo si la
    validación experimental (Paso 7) muestra que la incertidumbre del eje
    reportada aquí no es representativa de la dispersión real observada en
    repeticiones test-retest. El cambio queda contenido en este archivo.
"""

from __future__ import annotations

import math

# Jacobiano constante de (M, J0, J45) respecto a (r0, r60, r120).
_J_VECTORES = (
    (1 / 3, 1 / 3, 1 / 3),          # dM/d(r0,r60,r120)
    (2 / 3, -1 / 3, -1 / 3),        # dJ0/d(r0,r60,r120)
    (0.0, 1 / math.sqrt(3), -1 / math.sqrt(3)),  # dJ45/d(r0,r60,r120)
)

_EPSILON_ASTIGMATISMO = 1e-9


def propagar_incertidumbre(
    r0: float, r60: float, r120: float,
    sd_r0: float, sd_r60: float, sd_r120: float,
) -> tuple[float, float, float]:
    """
    Devuelve (esfera_sd, cilindro_sd, eje_sd) por propagación analítica
    lineal, asumiendo independencia entre las tres pendientes meridionales.
    """
    m = (r0 + r60 + r120) / 3.0
    j0 = (2 * r0 - r60 - r120) / 3.0
    j45 = (r60 - r120) / math.sqrt(3.0)
    a = math.hypot(j0, j45)  # magnitud del astigmatismo

    if a < _EPSILON_ASTIGMATISMO:
        # Astigmatismo (casi) nulo: cilindro y eje son degenerados en este
        # punto (el eje no está definido para un ojo perfectamente
        # esférico). La aproximación lineal no es válida aquí; se reporta
        # incertidumbre nula para cilindro/eje en vez de dividir por cero.
        d_esfera_dj0 = d_esfera_dj45 = 0.0
        d_cilindro_dj0 = d_cilindro_dj45 = 0.0
        d_eje_dj0 = d_eje_dj45 = 0.0
    else:
        d_esfera_dj0 = j0 / a
        d_esfera_dj45 = j45 / a
        d_cilindro_dj0 = -2.0 * j0 / a
        d_cilindro_dj45 = -2.0 * j45 / a
        # d(atan2(j45,j0))/dj0 = -j45/a^2 ; d/dj45 = j0/a^2 ; luego *0.5 y a grados.
        factor_grados = math.degrees(1.0)
        d_eje_dj0 = 0.5 * (-j45 / (a * a)) * factor_grados
        d_eje_dj45 = 0.5 * (j0 / (a * a)) * factor_grados

    # Jacobianos de (esfera, cilindro, eje) respecto a (M, J0, J45).
    j_salida = (
        (1.0, d_esfera_dj0, d_esfera_dj45),
        (0.0, d_cilindro_dj0, d_cilindro_dj45),
        (0.0, d_eje_dj0, d_eje_dj45),
    )

    sd_entrada = (sd_r0, sd_r60, sd_r120)
    resultados = []
    for fila_salida in j_salida:
        # Jacobiano total fila = fila_salida @ _J_VECTORES (combina M,J0,J45 -> r0,r60,r120)
        derivadas_r = [
            sum(fila_salida[k] * _J_VECTORES[k][i] for k in range(3))
            for i in range(3)
        ]
        varianza = sum((derivadas_r[i] * sd_entrada[i]) ** 2 for i in range(3))
        resultados.append(math.sqrt(varianza))

    esfera_sd, cilindro_sd, eje_sd = resultados
    return esfera_sd, cilindro_sd, eje_sd
