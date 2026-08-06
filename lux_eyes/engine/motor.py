"""
engine/motor.py — MotorFotorrefraccionLuxEyes: implementa el Protocol
MotorFotorrefraccion que orchestrator/contratos.py ya define desde la
Fase 3. Es el único componente de engine/ que conoce TODOS los demás
submódulos a la vez — mismo rol que SincronizadorWeb en sync/ y
OrquestadorTamizaje en orchestrator/.

Este método es exactamente lo que OrquestadorTamizaje ya espera: cero
cambios necesarios en orchestrator/ para integrarlo.
"""

from __future__ import annotations

from typing import Callable

from lux_eyes.common.tipos import ResultadoOjo

from .configuracion import ConfiguracionCaptura
from .contratos_estimacion import DetectorPupila, EstimadorPendiente
from .contratos_hardware import ControladorLED, FuenteDeVideo, Reloj
from .errores import PupilaNoDetectadaError, VentanaInestableError
from .geometry import calcular_geometria
from .illumination import SecuenciadorIluminacion
from .incertidumbre import propagar_incertidumbre
from .reflex_mask import detectar_reflejo_en_roi
from .refraction import CalibracionRefraccion, parametros_clinicos, potencia_meridional, vectores_potencia
from .slope_estimator import muestrear_mascara, muestrear_perfil
from .synchronizer import asignar_frames_a_meridianos
from .temporal_aggregator import AgregadorTemporal


class MotorFotorrefraccionLuxEyes:
    """
    Ejecuta el pipeline completo de fotorrefracción para UN ojo por
    llamada a medir_ojo(). El orquestador llama a medir_ojo('od') y luego
    medir_ojo('oi') como dos capturas independientes (cada una con su
    propio ciclo de iluminación de los 3 meridianos), SOBRE LA MISMA
    instancia de este motor.

    [CORRECCIÓN] (detectada al integrar ui/ con hardware real por
    primera vez): DetectorPupilaHaar/DetectorPupilaMediaPipe son
    instancias FIJAS a un lado de la cara ('od' u 'oi' — ver sus propios
    constructores). Como medir_ojo() se llama para ambos ojos sobre la
    MISMA instancia del motor, un único detector_pupila no puede servir
    para los dos: el ojo que no coincidiera con el detector fijado se
    mediría con el detector del lado equivocado. Se corrige recibiendo
    DOS detectores (uno por ojo) y seleccionando el correcto dentro de
    medir_ojo() según el parámetro `ojo`. Ningún otro componente de
    engine/ cambia — DetectorPupila (el contrato) sigue siendo el mismo.
    """

    def __init__(
        self,
        controlador_led: ControladorLED,
        fuente_video: FuenteDeVideo,
        reloj: Reloj,
        detector_pupila_od: DetectorPupila,
        detector_pupila_oi: DetectorPupila,
        estimador: EstimadorPendiente,
        config: ConfiguracionCaptura,
        calibracion: CalibracionRefraccion | None = None,
    ):
        self._controlador_led = controlador_led
        self._fuente_video = fuente_video
        self._reloj = reloj
        self._detectores_por_ojo = {"od": detector_pupila_od, "oi": detector_pupila_oi}
        self._estimador = estimador
        self._config = config
        self._calibracion = calibracion or CalibracionRefraccion(
            factor=config.calibracion_factor, offset=config.calibracion_offset
        )
        self._agregador = AgregadorTemporal(config.umbral_mad_descarte)

    # ── Implementación del Protocol MotorFotorrefraccion ────────────────
    def medir_ojo(self, ojo: str, reportar_progreso: Callable[[str], None]) -> ResultadoOjo:
        reportar_progreso(f"iniciando captura de {ojo}")
        frames = self._capturar_frames(reportar_progreso)

        secuenciador_eventos = self._ultimo_secuenciador.eventos()
        asignados = asignar_frames_a_meridianos(frames, secuenciador_eventos)

        reportar_progreso("procesando meridianos")
        pendientes_por_meridiano = {}
        for angulo in self._config.angulos_meridianos:
            frames_meridiano = asignados.get(angulo, [])
            if len(frames_meridiano) < self._config.frames_minimos_utiles:
                raise VentanaInestableError(
                    f"Meridiano {angulo}°: solo {len(frames_meridiano)} frames "
                    f"útiles tras la sincronización (mínimo "
                    f"{self._config.frames_minimos_utiles})."
                )
            pendientes_por_meridiano[angulo] = self._procesar_meridiano(
                angulo, frames_meridiano, ojo
            )

        reportar_progreso("calculando refracción")
        resultado = self._calcular_resultado(pendientes_por_meridiano)
        reportar_progreso(f"captura de {ojo} completada")
        return resultado

    # ── Internos ─────────────────────────────────────────────────────────
    def _capturar_frames(self, reportar_progreso: Callable[[str], None]) -> list:
        secuenciador = SecuenciadorIluminacion(self._controlador_led, self._reloj, self._config)
        self._ultimo_secuenciador = secuenciador
        secuenciador.iniciar_ciclo()
        self._fuente_video.iniciar()

        frames_recolectados = []
        frames_en_meridiano_actual = 0
        meridiano_anterior = secuenciador.meridiano_actual()

        try:
            while not secuenciador.terminado():
                secuenciador.avanzar()

                if secuenciador.meridiano_actual() != meridiano_anterior:
                    frames_en_meridiano_actual = 0
                    meridiano_anterior = secuenciador.meridiano_actual()
                    if meridiano_anterior is not None:
                        reportar_progreso(f"iluminando meridiano {meridiano_anterior}°")

                if secuenciador.en_captura_util():
                    frame = self._fuente_video.leer_frame()
                    if frame is not None:
                        frames_recolectados.append(frame)
                        frames_en_meridiano_actual += 1
                        if frames_en_meridiano_actual >= self._config.frames_objetivo_por_meridiano:
                            secuenciador.cerrar_meridiano_actual()
        finally:
            self._fuente_video.detener()

        return frames_recolectados

    def _procesar_meridiano(self, angulo: int, frames_meridiano: list, ojo: str):
        resultados_pendiente = []
        alguna_geometria_valida = False
        detector = self._detectores_por_ojo[ojo]

        for frame in frames_meridiano:
            geo = calcular_geometria(
                frame.imagen, detector, (angulo,),
                self._config.fraccion_longitud_meridiano,
                self._config.fraccion_borde_excluido,
            )
            if geo is None:
                continue  # frame individual sin pupila detectada: se descarta, no aborta el ojo
            alguna_geometria_valida = True

            mascara_reflejo = detectar_reflejo_en_roi(
                frame.imagen,
                geo.deteccion.centro_x, geo.deteccion.centro_y, geo.deteccion.radio,
                self._config.margen_roi_reflejo,
                self._config.percentil_umbral_reflejo,
                self._config.umbral_absoluto_reflejo,
                self._config.area_min_reflejo,
                self._config.area_max_reflejo,
                self._config.circularidad_min_reflejo,
            )

            p1, p2 = geo.meridianos[angulo]
            posiciones, intensidades = muestrear_perfil(frame.imagen, p1, p2)
            reflejo_en_perfil = muestrear_mascara(mascara_reflejo, p1, p2)

            inicio_region, fin_region = geo.region
            dentro_de_region = (posiciones >= inicio_region) & (posiciones <= fin_region)
            mascara_valida = dentro_de_region & ~reflejo_en_perfil

            resultado_pendiente = self._estimador.ajustar(posiciones, intensidades, mascara_valida)
            resultados_pendiente.append(resultado_pendiente)

        if not alguna_geometria_valida:
            raise PupilaNoDetectadaError(
                f"No se detectó pupila en ningún frame del meridiano {angulo}°."
            )

        return self._agregador.agregar(resultados_pendiente)

    def _calcular_resultado(self, pendientes_por_meridiano: dict) -> ResultadoOjo:
        angulos = self._config.angulos_meridianos
        r = {}
        r_sd = {}
        for angulo in angulos:
            pm = pendientes_por_meridiano[angulo]
            r[angulo] = potencia_meridional(pm.media, self._calibracion)
            # La SD de la pendiente se propaga a la SD de R(ángulo) mediante
            # el mismo factor de calibración (transformación lineal): sin
            # offset porque el offset no aporta varianza.
            r_sd[angulo] = abs(self._calibracion.factor) * pm.desviacion_estandar

        # RESTRICCIÓN-ACTUAL: las fórmulas de Thibos (17.1) requieren
        # exactamente los 3 meridianos estándar 0/60/120°. Si en el futuro
        # se soportan otros conjuntos de ángulos, refraction.py y esta
        # función deberán generalizarse — fuera del alcance de esta fase.
        if {0, 60, 120} - set(r.keys()):
            raise ValueError(
                "El cálculo de esfera/cilindro/eje (Thibos) requiere "
                "exactamente los meridianos 0°, 60° y 120° en "
                "ConfiguracionCaptura.angulos_meridianos."
            )
        r0, r60, r120 = r[0], r[60], r[120]
        sd_r0, sd_r60, sd_r120 = r_sd[0], r_sd[60], r_sd[120]

        m, j0, j45 = vectores_potencia(r0, r60, r120)
        esfera, cilindro, eje = parametros_clinicos(m, j0, j45)
        esfera_sd, cilindro_sd, eje_sd = propagar_incertidumbre(
            r0, r60, r120, sd_r0, sd_r60, sd_r120
        )

        return ResultadoOjo(
            esfera=esfera, cilindro=cilindro, eje=eje,
            esfera_sd=esfera_sd, cilindro_sd=cilindro_sd, eje_sd=eje_sd,
            reflejo_rojo=None,  # placeholder honesto: sin módulo de detección (D5)
        )
