"""
engine/configuracion.py — Configuración de la que depende engine/.

DECISIÓN de arquitectura (igual que sync/configuracion.py y el resto del
proyecto): engine/ no importa el futuro paquete config/ (sin fase asignada
en el roadmap). Define su propia dataclass de inyección; quien construya
MotorFotorrefraccionLuxEyes decide de dónde vienen estos valores.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConfiguracionCaptura:
    """Todo lo que engine/ necesita del exterior para operar."""

    # ── Meridianos (5.2, 6.1 del Documento Maestro) ──
    angulos_meridianos: tuple[int, ...] = (0, 60, 120)
    repeticiones_ciclo: int = 3

    # ── Temporización de iluminación (6.4, 6.5) ──
    duracion_estabilizacion_segundos: float = 0.05   # descarte tras cambio de LED
    frames_a_descartar_tras_cambio: int = 4           # 3-5 según 6.5
    frames_objetivo_por_meridiano: int = 35           # ~35-40 para ~30 útiles
    frames_minimos_utiles: int = 15                   # bajo esto: VentanaInestableError

    # ── Geometría (5.1 etapa 8, 11.3) ──
    fraccion_longitud_meridiano: float = 0.80          # 80% del diámetro pupilar
    fraccion_borde_excluido: float = 0.15              # [HIPÓTESIS A VALIDAR] 10/15/20%

    # ── Máscara de reflejo (11.1) ──
    # CALIBRACIÓN EMPÍRICA: umbral_absoluto_reflejo=180 validado en
    # hardware real, junto con exposicion_us=10000/ganancia_analoga=2.0
    # de FuenteDeVideoPicamera2 (ver docstring de ese archivo). Estos tres
    # valores están acoplados entre sí — si cambian exposición/ganancia,
    # este umbral casi seguro necesita recalibrarse también.
    percentil_umbral_reflejo: float = 99.0
    umbral_absoluto_reflejo: int = 180
    area_min_reflejo: int = 4
    area_max_reflejo: int = 400
    circularidad_min_reflejo: float = 0.5
    margen_roi_reflejo: float = 2.5   # múltiplo del radio pupilar, ver detectar_reflejo_en_roi

    # ── Agregación temporal (11.4) ──
    umbral_mad_descarte: float = 3.5   # desviaciones MAD para descartar un frame

    # ── Calibración (11.5, deuda D3) ──
    calibracion_factor: float = 0.98
    calibracion_offset: float = 1.35

    def __post_init__(self) -> None:
        if len(self.angulos_meridianos) == 0:
            raise ValueError("angulos_meridianos no puede estar vacío.")
        if self.frames_minimos_utiles > self.frames_objetivo_por_meridiano:
            raise ValueError(
                "frames_minimos_utiles no puede superar frames_objetivo_por_meridiano."
            )
        if not (0.0 < self.fraccion_longitud_meridiano <= 1.0):
            raise ValueError("fraccion_longitud_meridiano debe estar en (0, 1].")
        if not (0.0 <= self.fraccion_borde_excluido < 0.5):
            raise ValueError("fraccion_borde_excluido debe estar en [0, 0.5).")
