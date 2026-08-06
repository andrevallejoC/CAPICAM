"""
scripts_validacion_pi/config_pi.py — Configuración compartida para los
scripts de validación en la Raspberry Pi física.

EDITA los valores de este archivo ANTES de correr cualquier script de
esta carpeta: son los únicos parámetros que dependen de tu cableado y de
tu sesión de prueba concretos. Ningún otro script de la carpeta debería
necesitar que edites nada más.
"""

# Pines BCM reales, uno por meridiano. AJUSTA esto a tu cableado físico.
PINES_POR_MERIDIANO = {
    0: 18,
    60: 13,
    120: 19,
}

# Corrección de orientación de montaje físico de la cámara (ver docstring
# de FuenteDeVideoPicamera2.rotacion_grados). VALIDADO en esta Pi: 270°.
# Si cambias el montaje físico, revalida con verificar_2_camara.py antes
# de tocar este valor.
ROTACION_CAMARA_GRADOS = 270

# Exposición y ganancia calibradas empíricamente en esta Pi (ver docstring
# de FuenteDeVideoPicamera2 para el procedimiento de recalibración si
# cambia el hardware de iluminación).
EXPOSICION_US = 10000
GANANCIA_ANALOGA = 2.0

# Carpeta donde los scripts guardan imágenes para que las inspecciones
# visualmente. Se crea automáticamente si no existe. Ruta relativa al
# directorio desde el que ejecutes los scripts.
CARPETA_SALIDA = "salida_validacion_pi"

# ── Detector de pupila a usar ────────────────────────────────────────
# DECISIÓN (ver adaptador_haarcascade.py): mediapipe no publica wheels
# ARM64 en PyPI para ninguna versión — confirmado al validar en esta
# misma Pi. "haar" (OpenCV, sin descargas externas) es el detector por
# defecto recomendado aquí. Si en el futuro compilas mediapipe desde
# código fuente para ARM64 (Opción A del análisis), cambia esto a
# "mediapipe" sin tocar ningún script de validación.
DETECTOR_PUPILA = "haar"  # "haar" | "mediapipe"

# Ruta LOCAL (en la Raspberry Pi, en formato Linux) del modelo de
# MediaPipe Face Landmarker — SOLO se usa si DETECTOR_PUPILA="mediapipe"
# Y tu mediapipe no tiene mp.solutions. Irrelevante con "haar".
RUTA_MODELO_TASKS = None  # p. ej.: "/home/pi/LuxEyes_Project/tests/face_landmarker.task"

# ── Sincronización con la API (Fase 2, validada) ─────────────────────
# CONFIRMADO funcionando contra el servidor real (ver conversación de
# validación de sync/): url_base, endpoints y estructura del payload ya
# coinciden con lo que el backend espera.
URL_BASE_API = "https://ambliodetect-api.onrender.com"
TOKEN_API = "token-de-prueba"  # AJUSTA cuando el backend defina autenticación real (deuda D9)
DISPOSITIVO_ID = "RPi-LUXEYES-01"  # AJUSTA con un identificador único por dispositivo
VERSION_FIRMWARE = "1.0.0"  # DEBE cumplir el patrón X.Y.Z exacto (validado con el backend real)


def construir_detector_pupila(ojo: str):
    """
    Punto único de construcción del detector de pupila para todos los
    scripts de esta carpeta — cambiar DETECTOR_PUPILA arriba basta para
    que los tres scripts (4, 5, 6) usen el otro detector, sin tocarlos.
    """
    if DETECTOR_PUPILA == "haar":
        from lux_eyes.engine.adaptador_haarcascade import DetectorPupilaHaar
        return DetectorPupilaHaar(ojo)
    elif DETECTOR_PUPILA == "mediapipe":
        from lux_eyes.engine.adaptador_mediapipe import DetectorPupilaMediaPipe
        kwargs = {} if RUTA_MODELO_TASKS is None else {"ruta_modelo_tasks": RUTA_MODELO_TASKS}
        return DetectorPupilaMediaPipe(ojo, **kwargs)
    else:
        raise ValueError(
            f"DETECTOR_PUPILA debe ser 'haar' o 'mediapipe', no {DETECTOR_PUPILA!r}"
        )


def construir_fuente_video(reloj):
    """
    Punto único de construcción de FuenteDeVideoPicamera2 para todos los
    scripts de esta carpeta — cambiar ROTACION_CAMARA_GRADOS,
    EXPOSICION_US o GANANCIA_ANALOGA arriba basta para que todos los
    scripts usen los mismos valores calibrados, sin tocarlos uno por uno.
    """
    from lux_eyes.engine.adaptadores_picamera2 import FuenteDeVideoPicamera2
    return FuenteDeVideoPicamera2(
        reloj=reloj,
        rotacion_grados=ROTACION_CAMARA_GRADOS,
        exposicion_us=EXPOSICION_US,
        ganancia_analoga=GANANCIA_ANALOGA,
    )


def construir_cliente_y_config_sync():
    """
    Punto único de construcción de ClienteAPI + ConfiguracionSync — cambiar
    URL_BASE_API, TOKEN_API, DISPOSITIVO_ID o VERSION_FIRMWARE arriba basta
    para que todos los scripts que sincronizan usen los mismos valores.
    """
    from lux_eyes.sync import ClienteAPI, ConfiguracionSync
    config = ConfiguracionSync(
        dispositivo_id=DISPOSITIVO_ID, version_firmware=VERSION_FIRMWARE,
        url_base=URL_BASE_API, token=TOKEN_API,
    )
    return ClienteAPI(config), config
