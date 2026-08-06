# Notas de la Fase 5 (`ui/`) — qué validé yo y qué falta validar en la Pi

## ACTUALIZACIÓN: PySide6 → PyQt5 (cambio real de framework, no solo de nombre)

Se descubrió que la Raspberry Pi tiene el **espacio de usuario en 32 bits**
(`armhf`/`armv7l`) corriendo sobre un **kernel de 64 bits** (`aarch64`) — una
combinación real que confunde a primera vista (`uname -m` dice `aarch64`,
pero `getconf LONG_BIT` da `32`). PySide6 (y `mediapipe`, y cualquier paquete
moderno) solo publica wheels de 64 bits en PyPI — instalación imposible por
`pip` en ese sistema, sin importar la versión que se pida.

**Solución aplicada:** todo `ui/` se portó de `PySide6` a `PyQt5`, que sí
tiene paquete oficial de Debian para `armhf` (`sudo apt install
python3-pyqt5` — compilado por Debian, no depende de wheels de PyPI). Se
verificó en un entorno con `PyQt5==5.15.11` / `Qt 5.15.14` — la MISMA versión
exacta que trae Debian Trixie — y las 18 pruebas de `test_ui.py` pasan
igual, de forma determinista, en 3 corridas seguidas.

**Diferencias reales de API entre PySide6 y PyQt5** (no solo el nombre del
paquete):
- `Signal`/`Slot` se llaman `pyqtSignal`/`pyqtSlot` en PyQt5 — se resolvió
  con un alias en el import (`from PyQt5.QtCore import pyqtSignal as
  Signal`), así que el resto del código no tuvo que tocarse.
- Licencia: PyQt5 es **GPL** por defecto (Riverbank Computing), a diferencia
  de PySide6 (LGPL, Qt Company). Para un proyecto académico/no comercial
  como este no debería ser un problema, pero es una diferencia real que
  vale la pena tener presente si el proyecto se comercializa después.
- Verificado que `QImage.Format.Format_Grayscale8` (estilo de enum anidado)
  y `app.exec()` (sin guion bajo) funcionan igual en PyQt5 5.15 — no hizo
  falta cambiar esas partes.

**RESTRICCIÓN-ACTUAL** (la causa de fondo sigue sin resolverse): el sistema
de 32 bits va a seguir dando fricción con cualquier paquete futuro que deje
de publicar wheels de 32 bits — este parche resuelve `PySide6`/`ui/`
específicamente, no la causa raíz. La solución de fondo (reflashear a
Raspberry Pi OS de 64 bits) sigue siendo la recomendación a mediano plazo,
documentada aparte en la conversación de validación de hardware.

## Qué se probó de forma automática (18/18, con PyQt5 REAL, no un mock del framework)

- **`observador_qt.py`, `hilo_orquestador.py`** — cruce de hilos real (main ↔
  QThread del orquestador) verificado con `QTest.qWait` y esperas activas por
  condición, no tiempos fijos. Confirmé empíricamente, con un experimento
  aparte antes de construir encima, que las señales Qt cruzan hilos de forma
  correcta y seguían llegando incluso con el orquestador real (no un mock).
- **Las 4 pantallas** (`formulario_sesion`, `formulario_paciente`, `captura`,
  `resultado`) — widgets reales de PyQt5, renderizados en modo `offscreen`
  (sin pantalla física, pero es Qt de verdad ejecutándose).
- **`ventana_principal.py`** — flujo completo de extremo a extremo: sesión →
  paciente → captura OD → captura OI → resultado → guardar → "siguiente niño,
  mismo colegio" (sin repetir el formulario de sesión) → "cambiar de colegio"
  → error de captura con reintento y reinicio de vista previa → cierre limpio.
  Todo con `MotorFalso` y `GestorCamaraFalso` (dobles de prueba), igual que
  `engine/` se probó con dobles antes de la validación en hardware real.

## Qué NO se pudo probar aquí (requiere la Raspberry Pi física)

- **`gestor_camara.py`** (`GestorCamaraCompartida`) — la única pieza de `ui/`
  que importa `picamera2`/`RPi.GPIO`. Sigue la misma disciplina de
  `engine/adaptadores_picamera2.py`: escrito con cuidado, pero sin ejecutar
  ni una sola vez. Coordina que la vista previa y la captura real nunca usen
  la cámara al mismo tiempo — la misma causa exacta del error "Device or
  resource busy" que ya viste al validar `engine/`.
- **La vista previa real sobre la pantalla táctil de 5 pulgadas** — el
  `QT_QPA_PLATFORM=offscreen` que usé aquí no dice nada sobre cómo se ve o
  responde al tacto en la pantalla real.

## Qué te toca hacer en el dispositivo

1. Instalar PyQt5 vía `apt`, NO `pip` (recuerda: el sistema es de 32 bits,
   sin wheels de PyPI disponibles para casi nada moderno):
   ```
   sudo apt update
   sudo apt install python3-pyqt5 -y
   ```
2. Construir `GestorCamaraCompartida` con tus pines reales
   (`scripts_validacion_pi/config_pi.py` ya tiene `PINES_POR_MERIDIANO`,
   `ROTACION_CAMARA_GRADOS`, `EXPOSICION_US`, `GANANCIA_ANALOGA` — reutilízalos).
3. Confirmar visualmente que la vista previa se ve fluida y útil para
   posicionar al paciente (no hay forma de medir esto sin la pantalla real).
4. Probar el flujo completo con el motor y la cámara REALES (no los dobles
   de prueba) — un script de arranque simple: construir
   `GestorCamaraCompartida`, `RepositorioTamizajes`, `ReglasClinicasAAPOS`,
   `gestor.construir_motor()`, y `VentanaPrincipal(...)`.
5. Validar el teclado físico + mouse (ya confirmaste que no habrá teclado en
   pantalla) — los campos de texto (`QLineEdit`) ya aceptan entrada de
   teclado físico sin ningún cambio adicional necesario.
