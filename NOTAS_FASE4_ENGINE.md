# Notas de la Fase 4 (`engine/`) — qué validé yo y qué falta validar en la Pi

## ACTUALIZACIÓN 3: MediaPipe reemplazado por Haar Cascades para la Raspberry Pi

Descubrimiento real al validar en tu Pi: **Google no publica NINGÚN wheel
de `mediapipe` para Linux ARM64 en PyPI**, para ninguna versión — no era
un problema de tu versión de Python (3.13.5), sino de la plataforma en
sí (confirmado revisando los archivos publicados de mediapipe 0.10.35:
solo `win_amd64`, `manylinux_2_28_x86_64`, `macosx_11_0_arm64`).

**Decisión tomada (Opción C de tres evaluadas):** se creó
`engine/adaptador_haarcascade.py` — `DetectorPupilaHaar`, que usa los
clasificadores Haar de OpenCV (rostro + ojo) ya incluidos en el paquete
`opencv-python` que el proyecto ya usa. Cero descargas externas, cero
problemas de wheel por arquitectura. Implementa el mismo contrato
`DetectorPupila` que `DetectorPupilaMediaPipe` — cero cambios en
`motor.py`, `geometry.py` ni en el resto del pipeline.

`adaptador_mediapipe.py` NO se eliminó — sigue siendo válido para
entornos x86_64/macOS (desarrollo, pruebas fuera de la Pi). La elección
de cuál detector usar en la Pi está centralizada en
`scripts_validacion_pi/config_pi.py` (`DETECTOR_PUPILA = "haar"`), un
solo lugar a cambiar si en el futuro compilas mediapipe para ARM64
(Opción A del análisis, descartada por ahora por el costo de horas de
build en la Pi).

**Verificado por mí:** además de las pruebas con ruido/imagen negra,
descargué una foto de rostro real (la imagen estándar "Lena", desde el
propio repositorio de OpenCV en GitHub) y confirmé que el detector
encuentra ambos ojos, en el lado correcto, con radios razonables —
`test_engine_haarcascade.py`, 11/11. **No es una imagen IR**, así que
sigue pendiente que valides la exactitud real con
`scripts_validacion_pi/verificar_4_deteccion_pupila.py` sobre tus propias
capturas.

## ACTUALIZACIÓN 2: bug real encontrado al validar en hardware (capture_array/capture_metadata)

Al correr `verificar_2_camara.py` en tu Pi real, el framerate medido fue
~15fps sobre un modo nativo de 56fps (2304x1296) — una discrepancia
demasiado grande para ser solo overhead normal. La causa: `leer_frame()`
llamaba a `capture_array()` y `capture_metadata()` como **dos peticiones
separadas**, cada una esperando de forma independiente al siguiente frame
disponible. Esto no es solo un problema de rendimiento (~2x el tiempo de
espera por frame): **la imagen y los metadatos podían terminar
perteneciendo a frames físicamente distintos** — un bug de correctud, no
solo de velocidad, que podría haber corrompido silenciosamente el
`FocusFoM` usado por `temporal_aggregator.py` para ponderar calidad.

**Corregido:** ahora se usa `capture_request()`, que devuelve una única
petición ya completada; imagen y metadatos se extraen de esa misma
petición con `make_array()`/`get_metadata()`, garantizando que
correspondan al mismo frame físico. Esto también debería mejorar el
framerate real (una sola espera por frame, no dos) — **pendiente de que
confirmes el nuevo framerate en tu Pi** volviendo a correr
`verificar_2_camara.py`.

## ACTUALIZACIÓN 1: compatibilidad de mediapipe (resuelto)

Se detectó en la práctica que `mediapipe>=0.10.30` (obligatorio en Python
3.13+, que es lo que tienes) eliminó la API legacy `mp.solutions` que
usaba la primera versión de `adaptador_mediapipe.py`. Se corrigió con
detección automática de API en tiempo de construcción:

- Si tu entorno tiene `mp.solutions.face_mesh` (mediapipe <0.10.30):
  se usa esa API, sin ningún archivo adicional que descargar.
- Si no (tu caso, Python 3.14 + mediapipe 0.10.35): se usa la nueva API
  de Tasks (`mp.tasks.vision.FaceLandmarker`), que **requiere que
  descargues un archivo de modelo**:

  ```
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
  ```

  y pases su ruta local al construir el detector:
  ```python
  DetectorPupilaMediaPipe("od", ruta_modelo_tasks=r"C:\ruta\a\face_landmarker.task")
  ```

  En `motor.py`, esto significa que quien construya
  `MotorFotorrefraccionLuxEyes` debe construir el `DetectorPupila` con esa
  ruta antes de inyectarlo — no requiere ningún cambio en `motor.py` en sí.

**Verificado por mí:** construí un entorno virtual aislado con
`mediapipe==0.10.35` (tu misma versión) y confirmé que la rama "tasks" (a)
detecta correctamente que `mp.solutions` no existe, (b) exige
`ruta_modelo_tasks` con un mensaje claro si no se provee, y (c) con una
ruta de archivo inexistente, llega hasta el intento real de carga del
modelo y falla con `FileNotFoundError` — es decir, la cadena de llamadas a
la API de Tasks (`BaseOptions`, `FaceLandmarkerOptions`, `RunningMode`,
`create_from_options`) es estructuralmente correcta.

**NO pude verificar:** el resultado de una detección real sobre una foto
de un rostro con la rama "tasks", porque no pude descargar el modelo en mi
entorno (sin acceso a `storage.googleapis.com`). Cuando descargues el
modelo, corre `test_engine_mediapipe.py` con `RUTA_MODELO_TASKS` apuntando
a tu archivo — ese script ya detecta automáticamente qué rama está activa
en tu entorno y prueba la que corresponda.

---

## Qué se probó de forma automática (48+11+5 = 64 pruebas, 0 fallidas)

- **Toda la lógica científica pura** (`synchronizer`, `geometry`, `reflex_mask`,
  `slope_estimator` con los 4 estimadores, `temporal_aggregator`, `refraction`,
  `incertidumbre`) — sin ningún hardware, con datos sintéticos.
- **`illumination.SecuenciadorIluminacion`** — máquina de estados completa, con
  `Reloj` y `ControladorLED` falsos (sin `sleep()` real).
- **`MotorFotorrefraccionLuxEyes` de extremo a extremo** — con cámara y LEDs
  simulados, incluida una imagen sintética con gradiente de intensidad real.
- **Integración con `orchestrator/` (Fase 3)** — confirmado que el motor se
  conecta sin ningún cambio en `orchestrator/`, tal como estaba previsto desde
  que se diseñó el `Protocol MotorFotorrefraccion`.
- **`DetectorPupilaMediaPipe`** — ambas ramas (`solutions` y `tasks`) probadas
  estructuralmente en sus respectivos entornos reales (ver arriba).

## Qué NO se pudo probar aquí (requiere la Raspberry Pi física)

- **`adaptadores_gpio.ControladorLEDGPIO`** — `RPi.GPIO` se instala pero lanza
  `RuntimeError` fuera de una Raspberry Pi real. El código sigue la API pública
  documentada de `RPi.GPIO`, pero no se ejecutó ni una sola vez.
- **`adaptadores_picamera2.FuenteDeVideoPicamera2`** — `picamera2` ni siquiera
  instala fuera de la Raspberry Pi (depende de `libcamera` del sistema
  operativo). El código sigue la API pública documentada de Picamera2 (incluida
  la selección de canal R, rotación 180°, parámetros manuales fijos de 17.6),
  pero tampoco se ejecutó.
- **Exactitud real de `DetectorPupilaMediaPipe`** sobre fotografías de ojos —
  solo se verificó que no crashea y que es seguro (`None` ante ausencia de
  rostro). La exactitud real solo se puede juzgar con imágenes de ojos
  capturadas por la cámara real, y el propio criterio de aceptación del Paso 3
  del Pipeline Architecture lo define como "inspección visual", no como prueba
  unitaria.

## Qué te toca hacer en el dispositivo

1. Instalar dependencias del sistema para `picamera2` (viene con Raspberry Pi
   OS normalmente; si no, `sudo apt install python3-picamera2`).
2. Verificar los pines BCM reales en `pines_por_meridiano` al construir
   `ControladorLEDGPIO` — no hay ninguna validación de que coincidan con tu
   cableado físico.
3. Descargar el modelo de Face Landmarker (ver arriba) y confirmar
   `test_engine_mediapipe.py` con `RUTA_MODELO_TASKS` configurada.
4. Ejecutar el **Paso 1** documentado (16.2 del Maestro): captura continua con
   parámetros fijos, verificar que cada frame se asigna a su LED por timestamp
   — criterio: 0 frames mal asignados en una secuencia conocida. La lógica de
   `synchronizer.py` ya está probada; lo que falta validar es que
   `FuenteDeVideoPicamera2` entrega `SensorTimestamp` real y consistente.
5. Ejecutar el **Paso 2**: verificar que el LED en DC no produce banding
   inter-frame (deuda D4, ya resuelta en el diseño — falta la confirmación
   empírica).
6. Ejecutar el **plan experimental de estimadores** (3.2 del Pipeline
   Architecture) con datos reales, ahora que los 4 estimadores están
   implementados e intercambiables — esta fue la razón original del patrón
   Strategy.

## Dependencias nuevas de esta fase

```
numpy
scikit-learn
opencv-python-headless   # o opencv-python si necesitas GUI de depuración
mediapipe                 # cualquier versión; el adaptador se ajusta solo.
                           # Si tu versión NO tiene mp.solutions (0.10.30+,
                           # obligatorio en Python 3.13+), necesitas además
                           # descargar face_landmarker.task (ver arriba).
# En la Raspberry Pi, además:
picamera2                 # normalmente preinstalado en Raspberry Pi OS
RPi.GPIO
```

