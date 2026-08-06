# Scripts de validación en la Raspberry Pi física

Estos scripts **no son pruebas automáticas** como las de `tests/` — dependen de
hardware real (cámara, LEDs, un ojo real frente a la cámara) y varios de ellos
requieren que **tú** inspecciones visualmente una imagen o confirmes que un LED
se encendió. Donde es posible, además, se auto-verifican programáticamente
contra los criterios de aceptación que el propio proyecto documenta (16.2 del
Documento Maestro / Pipeline Architecture).

## Antes de empezar

1. Edita `config_pi.py`: pon tus pines BCM reales y, si tu `mediapipe` en la Pi
   usa la API de Tasks (no tiene `mp.solutions`), la ruta al modelo `.task`.
2. Corre todo desde la **raíz del proyecto** (donde están `lux_eyes/` y
   `tests/`), con `python -m scripts_validacion_pi.<nombre>`, igual que ya
   corres `python -m tests.test_engine_mediapipe`.

## Orden recomendado

| # | Script | Qué valida | Requiere ojo real |
|---|---|---|---|
| 1 | `verificar_1_leds` | `ControladorLEDGPIO` enciende/apaga el LED correcto en el pin correcto | No |
| 2 | `verificar_2_camara` | `FuenteDeVideoPicamera2` captura frames con timestamps monótonos y parámetros fijos | No |
| 3 | `verificar_3_sincronizacion` | **El más importante**: criterio del Paso 1, "0 frames mal asignados", con hardware real | No |
| 4 | `verificar_4_deteccion_pupila` | Criterio del Paso 3: dispersión del centro pupilar entre frames | Sí |
| 5 | `verificar_5_mascara_reflejo` | Criterio del Paso 4: la máscara cubre el reflejo sin invadir el gradiente (inspección visual) | Sí |
| 6 | `verificar_6_medir_ojo_completo` | Medición real de extremo a extremo con `MotorFotorrefraccionLuxEyes` | Sí |
| 7 | `verificar_7_interfaz_completa` | La app real completa: `VentanaPrincipal` + cámara + motor + reglas clínicas + `storage/` + `sync/` | Sí |
| 8 | `verificar_8_sync_real` | Solo conectividad con la API real, con un tamizaje de prueba explícito (no un paciente real) | No |

Corre en este orden: si el 1 o el 2 fallan, no tiene sentido seguir — el
problema está en el hardware básico, no en la lógica de más arriba. El script 3
es el que de verdad certifica que la sincronización LED-frame funciona con tu
cámara y tu cableado reales (la lógica en sí ya está probada sin hardware en
`tests/test_engine.py`, sección 4).

## Qué hacer con los resultados

- Las imágenes que se guardan quedan en `salida_validacion_pi/` (configurable
  en `config_pi.py`) — ábrelas y revísalas, no asumas que "no crasheó" es
  suficiente.
- Si `verificar_3_sincronizacion` reporta frames mal asignados (>0), no sigas
  con el 4/5/6 hasta resolverlo — es la base de todo lo demás.
- `verificar_6_medir_ojo_completo` es una primera medición, no una validación
  clínica: los valores absolutos de esfera/cilindro dependen de la calibración
  (deuda D3, aún la de Agarwala et al.). Lo que sí puedes empezar a evaluar ya
  es **repetibilidad** — repite la medición varias veces y compara.

## Arranque automático (`verificar_7` al encender la Pi)

Dos archivos para esto: `iniciar_luxeyes.sh` (el script que arranca la app,
con log de errores) y `luxeyes.desktop` (le dice al escritorio que lo corra
solo). Pasos:

1. **Auto-login al escritorio**: `sudo raspi-config` → `1 System Options` →
   `S5 Boot / Auto Login` → `B4 Desktop Autologin`.
2. **Edita `iniciar_luxeyes.sh`**: cambia `RUTA_PROYECTO` a la ruta real donde
   tengas el proyecto en tu Pi.
3. **Hazlo ejecutable** (si no lo es ya): `chmod +x iniciar_luxeyes.sh`.
4. **Edita `luxeyes.desktop`**: cambia la línea `Exec=` a la misma ruta que
   pusiste en el paso 2.
5. **Copia `luxeyes.desktop`** a la carpeta de autoarranque del escritorio:
   ```bash
   mkdir -p ~/.config/autostart
   cp scripts_validacion_pi/luxeyes.desktop ~/.config/autostart/
   ```
6. **Reinicia** (`sudo reboot`) y confirma que la app aparece sola, en
   pantalla completa, sin que toques nada.

Si algo falla en el arranque automático (la app no aparece), revisa
`logs_arranque/arranque_<fecha>.log` dentro de la carpeta del proyecto — ahí
queda el error real, exactamente igual que si lo hubieras corrido a mano por
SSH.

