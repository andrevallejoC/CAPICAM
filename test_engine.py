"""
test_engine.py — Pruebas de aceptación de la Fase 4 (motor de
fotorrefracción), parte 1: lógica científica pura, sin hardware.

Sigue la misma disciplina que test_storage.py, test_sync.py y
test_orchestrator.py: cada pieza se prueba de forma aislada, con datos
sintéticos o dobles de prueba (Reloj y ControladorLED falsos para
illumination.py), sin cámara, sin GPIO, sin MediaPipe real donde no hace
falta.

test_engine_mediapipe.py (archivo aparte) cubre el detector de pupila
real, que sí requiere la librería MediaPipe pero no hardware físico.
test_engine_motor.py cubre el motor completo de extremo a extremo con
TODOS los componentes como dobles de prueba.
"""

import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from lux_eyes.engine.configuracion import ConfiguracionCaptura
from lux_eyes.engine.contratos_estimacion import ResultadoPendiente
from lux_eyes.engine.contratos_hardware import FrameCrudo
from lux_eyes.engine.geometry import calcular_geometria, region_automatica, trazar_meridiano
from lux_eyes.engine.contratos_estimacion import DeteccionPupila
from lux_eyes.engine.illumination import SecuenciadorIluminacion
from lux_eyes.engine.incertidumbre import propagar_incertidumbre
from lux_eyes.engine.reflex_mask import detectar_reflejo, detectar_reflejo_en_roi
from lux_eyes.engine.refraction import (
    CalibracionRefraccion, parametros_clinicos, potencia_meridional, vectores_potencia,
)
from lux_eyes.engine.slope_estimator import (
    EstimadorHuber, EstimadorOLS, EstimadorRANSAC, EstimadorTheilSen, muestrear_perfil,
)
from lux_eyes.engine.synchronizer import EventoLed, asignar_frames_a_meridianos
from lux_eyes.engine.temporal_aggregator import AgregadorTemporal
from lux_eyes.engine.adaptadores_picamera2 import _K_ROT90_POR_GRADOS

VERDE = "\033[92m"; ROJO = "\033[91m"; RESET = "\033[0m"
_ok = 0; _fail = 0


def check(nombre, condicion):
    global _ok, _fail
    if condicion:
        _ok += 1
        print(f"  {VERDE}PASA{RESET}  {nombre}")
    else:
        _fail += 1
        print(f"  {ROJO}FALLA{RESET} {nombre}")


def cerca(a, b, tol=1e-6):
    return abs(a - b) < tol


# ── Dobles de prueba para illumination.py ────────────────────────────────
class RelojFalso:
    def __init__(self):
        self._t = 0.0

    def ahora(self):
        return self._t

    def avanzar(self, delta):
        self._t += delta


class ControladorLEDFalso:
    def __init__(self):
        self.llamadas: list[str] = []
        self.encendido: int | None = None

    def encender(self, meridiano_grados):
        self.llamadas.append(f"encender({meridiano_grados})")
        self.encendido = meridiano_grados

    def apagar(self):
        self.llamadas.append("apagar()")
        self.encendido = None


def main():
    print("\n=== engine/ — lógica científica pura (sin hardware) ===\n")

    # ── 1. Sistema de referencia angular (geometry.trazar_meridiano) ───
    print("1) Sistema de referencia angular (casos cardinales)")
    # 0 grados = eje vertical hacia abajo: dx=0, dy=+L/2 (p2 más abajo)
    p1, p2 = trazar_meridiano(100, 100, 0, 40)
    check("0°: p1=(100, 80), p2=(100, 120)",
          cerca(p1[0], 100) and cerca(p1[1], 80) and cerca(p2[0], 100) and cerca(p2[1], 120))

    # 90 grados: antihorario desde vertical -> horizontal.
    # ang=90: dx=-sin(90)*L/2=-L/2, dy=cos(90)*L/2=0 -> p1=(100+L/2,100), p2=(100-L/2,100)
    p1, p2 = trazar_meridiano(100, 100, 90, 40)
    check("90°: horizontal, dy=0",
          cerca(p1[1], 100) and cerca(p2[1], 100)
          and cerca(p1[0], 120) and cerca(p2[0], 80))

    # 60 grados y 120 grados: verificación cruzada con la fórmula directa
    for angulo in (60, 120):
        p1, p2 = trazar_meridiano(0, 0, angulo, 100)
        rad = math.radians(angulo)
        dx_esperado = -math.sin(rad) * 50
        dy_esperado = math.cos(rad) * 50
        check(f"{angulo}°: coincide con la fórmula dx=-sin,dy=cos",
              cerca(p2[0], dx_esperado) and cerca(p2[1], dy_esperado))

    # ── 2. Región automática ─────────────────────────────────────────────
    # ── 1b. Dirección de rotación de FuenteDeVideoPicamera2 (montajes rotados) ──
    print("\n1b) Corrección de montaje rotado (_K_ROT90_POR_GRADOS)")
    marcador = np.zeros((5, 5), dtype=int)
    marcador[0, 4] = 1  # esquina superior-derecha

    rotado_90 = np.rot90(marcador, _K_ROT90_POR_GRADOS[90])
    check("90° (horario): esquina superior-derecha -> inferior-derecha",
          tuple(np.argwhere(rotado_90 == 1)[0]) == (4, 4))

    rotado_270 = np.rot90(marcador, _K_ROT90_POR_GRADOS[270])
    check("270° (antihorario): esquina superior-derecha -> superior-izquierda",
          tuple(np.argwhere(rotado_270 == 1)[0]) == (0, 0))

    rotado_180 = np.rot90(marcador, _K_ROT90_POR_GRADOS[180])
    check("180°: esquina superior-derecha -> inferior-izquierda",
          tuple(np.argwhere(rotado_180 == 1)[0]) == (4, 0))

    check("0°: sin cambio", _K_ROT90_POR_GRADOS[0] == 0)

    print("\n2) Región automática (fracción del diámetro, no píxeles fijos)")
    inicio, fin = region_automatica(diametro_pupilar=100, fraccion_borde=0.15)
    check("excluye 15% en cada extremo", cerca(inicio, 15.0) and cerca(fin, 85.0))
    inicio2, fin2 = region_automatica(diametro_pupilar=50, fraccion_borde=0.15)
    check("la MISMA fracción se aplica igual a una pupila más pequeña "
          "(reproducibilidad inter-paciente)",
          cerca(inicio2, 7.5) and cerca(fin2, 42.5))

    # ── 3. calcular_geometria con detector falso ────────────────────────
    print("\n3) calcular_geometria (con DetectorPupila falso)")
    class DetectorFalso:
        def __init__(self, deteccion):
            self._deteccion = deteccion
        def detectar(self, imagen):
            return self._deteccion

    geo = calcular_geometria(
        imagen=None, detector=DetectorFalso(DeteccionPupila(50, 50, 20)),
        angulos_grados=(0, 60, 120), fraccion_longitud=0.8, fraccion_borde=0.15,
    )
    check("geometria no es None con detector exitoso", geo is not None)
    check("tiene los 3 meridianos", set(geo.meridianos.keys()) == {0, 60, 120})

    geo_none = calcular_geometria(
        imagen=None, detector=DetectorFalso(None),
        angulos_grados=(0, 60, 120), fraccion_longitud=0.8, fraccion_borde=0.15,
    )
    check("geometria es None si el detector no encuentra pupila", geo_none is None)

    # ── 4. synchronizer: asignación frame->meridiano ─────────────────────
    print("\n4) Sincronización LED-frame (asignar_frames_a_meridianos)")
    eventos = [
        EventoLed(meridiano_grados=0, inicio_estable=0.10, fin_estable=0.30),
        EventoLed(meridiano_grados=60, inicio_estable=0.40, fin_estable=0.60),
        EventoLed(meridiano_grados=120, inicio_estable=0.70, fin_estable=0.90),
    ]
    frames = [
        FrameCrudo(imagen=None, timestamp_sensor=0.15, duracion_exposicion=0.02, metadatos={}),  # -> 0
        FrameCrudo(imagen=None, timestamp_sensor=0.20, duracion_exposicion=0.02, metadatos={}),  # -> 0
        FrameCrudo(imagen=None, timestamp_sensor=0.11, duracion_exposicion=0.02, metadatos={}),  # ventana empieza en 0.09 < 0.10: descartado
        FrameCrudo(imagen=None, timestamp_sensor=0.31, duracion_exposicion=0.02, metadatos={}),  # solapa cambio 0->60: descartado
        FrameCrudo(imagen=None, timestamp_sensor=0.50, duracion_exposicion=0.02, metadatos={}),  # -> 60
        FrameCrudo(imagen=None, timestamp_sensor=0.85, duracion_exposicion=0.02, metadatos={}),  # -> 120
        FrameCrudo(imagen=None, timestamp_sensor=1.50, duracion_exposicion=0.02, metadatos={}),  # fuera de todo: descartado
    ]
    asignados = asignar_frames_a_meridianos(frames, eventos)
    check("meridiano 0 tiene 2 frames válidos", len(asignados[0]) == 2)
    check("meridiano 60 tiene 1 frame válido", len(asignados[60]) == 1)
    check("meridiano 120 tiene 1 frame válido", len(asignados[120]) == 1)
    check("0 frames mal asignados (criterio de aceptación del Paso 1): "
          "total asignado = 4 de 7",
          sum(len(v) for v in asignados.values()) == 4)

    # ── 5. illumination.SecuenciadorIluminacion (con Reloj/ControladorLED falsos) ──
    print("\n5) SecuenciadorIluminacion (máquina de estados pura)")
    reloj = RelojFalso()
    led = ControladorLEDFalso()
    config = ConfiguracionCaptura(
        angulos_meridianos=(0, 60, 120), repeticiones_ciclo=1,
        duracion_estabilizacion_segundos=0.05,
    )
    seq = SecuenciadorIluminacion(led, reloj, config)
    seq.iniciar_ciclo()
    check("arranca encendiendo el primer meridiano (0°)", led.encendido == 0)
    check("aún no está en captura útil (estabilizando)", not seq.en_captura_util())

    reloj.avanzar(0.05)
    seq.avanzar()
    check("tras la estabilización, entra en captura útil", seq.en_captura_util())

    seq.cerrar_meridiano_actual()
    check("tras cerrar, avanza automáticamente al siguiente meridiano (60°)",
          led.encendido == 60)

    reloj.avanzar(0.05); seq.avanzar(); seq.cerrar_meridiano_actual()
    check("y al tercero (120°)", led.encendido == 120)

    reloj.avanzar(0.05); seq.avanzar(); seq.cerrar_meridiano_actual()
    check("con 1 repetición y 3 meridianos, tras cerrar el tercero termina",
          seq.terminado())
    check("apaga el LED al terminar", led.encendido is None)
    check("se registraron exactamente 3 eventos (uno por meridiano)",
          len(seq.eventos()) == 3)

    # ── 6. reflex_mask: detección sobre imagen sintética ─────────────────
    print("\n6) Máscara de exclusión del reflejo de Purkinje")
    imagen = np.full((100, 100), 50, dtype=np.uint8)  # fondo oscuro uniforme
    imagen[45:55, 45:55] = 255  # blob brillante circular-ish al centro
    original = imagen.copy()
    mascara = detectar_reflejo(
        imagen, percentil_umbral=95.0, umbral_absoluto=200,
        area_min=10, area_max=500, circularidad_min=0.3,
    )
    check("la imagen original NUNCA se modifica", np.array_equal(imagen, original))
    check("la máscara marca al menos parte del blob brillante",
          mascara[45:55, 45:55].sum() > 0)
    check("la máscara NO marca el fondo oscuro",
          mascara[0:10, 0:10].sum() == 0)

    # ── 6b. detectar_reflejo_en_roi: caso real detectado en la Pi ──
    print("\n6b) Máscara acotada al ROI (caso real: región sobreexpuesta en otra "
          "parte del frame)")
    # Simula lo observado al validar en hardware: una región del frame
    # AJENA a ningún ojo (p. ej. una zona de la cara mucho más iluminada)
    # empuja el umbral por percentil GLOBAL muy por encima del reflejo
    # real del ojo B — aunque ese reflejo sigue siendo, con diferencia,
    # el punto más brillante de SU entorno local.
    imagen_mixta = np.full((200, 300), 60, dtype=np.uint8)  # fondo normal
    imagen_mixta[0:60, 0:150] = 240   # región sobreexpuesta, lejos de ambos ojos
    imagen_mixta[96:104, 46:54] = 255   # ojo A: reflejo intenso, lejos del distractor
    imagen_mixta[96:104, 221:229] = 200  # ojo B: reflejo más tenue, pero el punto más brillante de su entorno

    mascara_global_mixta = detectar_reflejo(
        imagen_mixta, percentil_umbral=99.0, umbral_absoluto=100,
        area_min=10, area_max=500, circularidad_min=0.3,
    )
    check("con umbral GLOBAL, el reflejo del ojo A sí se detecta",
          mascara_global_mixta[96:104, 46:54].sum() > 0)
    check("con umbral GLOBAL, el reflejo del ojo B se PIERDE — el umbral quedó "
          "empujado por una región sobreexpuesta ajena a ambos ojos, "
          "exactamente el problema observado al validar en la Pi real",
          mascara_global_mixta[96:104, 221:229].sum() == 0)

    mascara_roi_b = detectar_reflejo_en_roi(
        imagen_mixta, centro_x=225, centro_y=100, radio=20,
        margen_factor=2.5, percentil_umbral=99.0, umbral_absoluto=100,
        area_min=10, area_max=500, circularidad_min=0.3,
    )
    check("con detectar_reflejo_en_roi() acotado al ojo B, SÍ se detecta su "
          "propio reflejo (el fix resuelve el problema)",
          mascara_roi_b[96:104, 221:229].sum() > 0)
    check("detectar_reflejo_en_roi() no marca nada fuera del recorte del ojo B",
          mascara_roi_b[96:104, 46:54].sum() == 0)

    # ── 7. slope_estimator: los 4 estimadores, limpio vs. con outliers ──
    print("\n7) Estimadores de pendiente (limpio vs. con outliers)")
    rng = np.random.default_rng(42)
    posiciones = np.linspace(0, 100, 50)
    pendiente_real = -2.5
    intensidades_limpias = 200 + pendiente_real * posiciones + rng.normal(0, 1.0, 50)
    mascara_valida = np.ones(50, dtype=bool)

    for nombre, Estimador in [
        ("OLS", EstimadorOLS), ("Huber", EstimadorHuber),
        ("Theil-Sen", EstimadorTheilSen), ("RANSAC", EstimadorRANSAC),
    ]:
        r = Estimador().ajustar(posiciones, intensidades_limpias, mascara_valida)
        check(f"{nombre}: con datos limpios recupera la pendiente real (±0.3)",
              abs(r.pendiente - pendiente_real) < 0.3)

    # Contaminar con outliers (simulando el reflejo residual)
    intensidades_con_outliers = intensidades_limpias.copy()
    intensidades_con_outliers[10:15] = 255  # picos de reflejo

    resultado_ols = EstimadorOLS().ajustar(posiciones, intensidades_con_outliers, mascara_valida)
    resultado_theilsen = EstimadorTheilSen().ajustar(posiciones, intensidades_con_outliers, mascara_valida)
    error_ols = abs(resultado_ols.pendiente - pendiente_real)
    error_theilsen = abs(resultado_theilsen.pendiente - pendiente_real)
    check("con outliers SIN enmascarar, Theil-Sen degrada menos que OLS "
          "(hipótesis del Pipeline Architecture, 3.1)",
          error_theilsen <= error_ols)

    # Con máscara de exclusión correcta, incluso OLS debe recuperar la pendiente
    mascara_excluye_outliers = np.ones(50, dtype=bool)
    mascara_excluye_outliers[10:15] = False
    resultado_ols_enmascarado = EstimadorOLS().ajustar(
        posiciones, intensidades_con_outliers, mascara_excluye_outliers
    )
    check("con la máscara de exclusión aplicada, OLS también recupera la "
          "pendiente real (confirma que la máscara hace su trabajo)",
          abs(resultado_ols_enmascarado.pendiente - pendiente_real) < 0.3)

    # ── 8. temporal_aggregator: descarte MAD + ponderación ───────────────
    print("\n8) Agregación temporal (descarte MAD + ponderación por calidad)")
    agregador = AgregadorTemporal(umbral_mad_descarte=3.5)
    resultados_limpios = [ResultadoPendiente(pendiente=-2.5 + rng.normal(0, 0.05), calidad=0.95)
                          for _ in range(30)]
    agregado = agregador.agregar(resultados_limpios)
    check("con datos limpios, ningún frame se descarta",
          agregado.n_frames_descartados == 0)
    check("la media recupera la pendiente real (±0.1)",
          abs(agregado.media - (-2.5)) < 0.1)

    resultados_con_anomalos = list(resultados_limpios) + [
        ResultadoPendiente(pendiente=50.0, calidad=0.1),   # anómalo evidente
        ResultadoPendiente(pendiente=-80.0, calidad=0.1),  # anómalo evidente
    ]
    agregado_filtrado = agregador.agregar(resultados_con_anomalos)
    check("con anómalos evidentes, el descarte por MAD los excluye",
          agregado_filtrado.n_frames_descartados == 2)
    check("la media tras el descarte sigue cerca de la pendiente real",
          abs(agregado_filtrado.media - (-2.5)) < 0.15)

    # Criterio de aceptación del Paso 6: ponderación reduce dispersión
    # frente al promedio simple, cuando la calidad varía.
    mixtos = (
        [ResultadoPendiente(pendiente=-2.5 + rng.normal(0, 0.02), calidad=0.99) for _ in range(15)]
        + [ResultadoPendiente(pendiente=-2.5 + rng.normal(0, 0.8), calidad=0.2) for _ in range(15)]
    )
    agregado_mixto = agregador.agregar(mixtos)
    promedio_simple = float(np.mean([r.pendiente for r in mixtos]))
    check("la media ponderada está más cerca de la pendiente real que el "
          "promedio simple, cuando la calidad varía entre frames",
          abs(agregado_mixto.media - (-2.5)) <= abs(promedio_simple - (-2.5)))

    # ── 9. refraction: fórmulas de Thibos contra casos calculados a mano ─
    print("\n9) Fórmulas de refracción (Thibos)")
    calib = CalibracionRefraccion(factor=0.98, offset=1.35)
    r0 = potencia_meridional(-2.0, calib)
    check("potencia_meridional: R = 0.98*(-2.0)+1.35 = -0.61",
          cerca(r0, 0.98 * -2.0 + 1.35))

    m, j0, j45 = vectores_potencia(1.0, 2.0, 3.0)
    check("M = (1+2+3)/3 = 2.0", cerca(m, 2.0))
    check("J0 = (2*1-2-3)/3 = -1.0", cerca(j0, -1.0))
    check("J45 = (2-3)/sqrt(3)", cerca(j45, -1.0 / math.sqrt(3)))

    esfera, cilindro, eje = parametros_clinicos(2.0, 0.0, 1.0)
    check("esfera = M + hypot(J0,J45) = 2+1 = 3.0", cerca(esfera, 3.0))
    check("cilindro = -2*hypot(J0,J45) = -2.0", cerca(cilindro, -2.0))
    check("eje en rango [0,180)", 0.0 <= eje < 180.0)

    # Caso sin astigmatismo: cilindro = 0
    esfera0, cilindro0, _ = parametros_clinicos(1.5, 0.0, 0.0)
    check("sin astigmatismo (J0=J45=0), cilindro=0 y esfera=M",
          cerca(cilindro0, 0.0) and cerca(esfera0, 1.5))

    # ── 10. incertidumbre: propagación analítica ─────────────────────────
    print("\n10) Propagación analítica de incertidumbre")
    esf_sd, cil_sd, eje_sd = propagar_incertidumbre(
        r0=1.0, r60=1.2, r120=0.9, sd_r0=0.1, sd_r60=0.1, sd_r120=0.1
    )
    check("esfera_sd es positiva y finita", esf_sd > 0 and math.isfinite(esf_sd))
    check("cilindro_sd es positiva y finita", cil_sd > 0 and math.isfinite(cil_sd))
    check("eje_sd es positiva y finita", eje_sd > 0 and math.isfinite(eje_sd))

    # Mayor incertidumbre de entrada -> mayor incertidumbre de salida (monotonía)
    esf_sd_2x, cil_sd_2x, eje_sd_2x = propagar_incertidumbre(
        r0=1.0, r60=1.2, r120=0.9, sd_r0=0.2, sd_r60=0.2, sd_r120=0.2
    )
    check("duplicar la SD de entrada duplica la SD de salida (linealidad)",
          cerca(esf_sd_2x, 2 * esf_sd, tol=1e-4)
          and cerca(cil_sd_2x, 2 * cil_sd, tol=1e-4))

    # Caso degenerado: sin astigmatismo, no debe explotar (división por cero)
    esf_sd_deg, cil_sd_deg, eje_sd_deg = propagar_incertidumbre(
        r0=1.0, r60=1.0, r120=1.0, sd_r0=0.1, sd_r60=0.1, sd_r120=0.1
    )
    check("caso degenerado (sin astigmatismo) no lanza excepción ni produce NaN",
          all(math.isfinite(v) for v in (esf_sd_deg, cil_sd_deg, eje_sd_deg)))

    print(f"\n{'='*52}")
    total = _ok + _fail
    color = VERDE if _fail == 0 else ROJO
    print(f"{color}Resultado: {_ok}/{total} pruebas pasadas, {_fail} fallidas{RESET}")
    print(f"{'='*52}\n")
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
