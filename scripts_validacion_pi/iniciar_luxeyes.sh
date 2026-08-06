#!/bin/bash
# iniciar_luxeyes.sh — Script de arranque automático de la app real.
#
# Se ejecuta desde el autoarranque del escritorio (ver
# ~/.config/autostart/luxeyes.desktop) al iniciar sesión gráfica.
# Guarda toda la salida (normal y de error) en un log con fecha, para
# poder diagnosticar sin necesidad de estar viendo una terminal en el
# momento del arranque — nadie va a estar mirando la pantalla cuando el
# dispositivo se enciende solo en un colegio.

# AJUSTA esta ruta a donde tengas el proyecto en tu Pi.
RUTA_PROYECTO="/home/theluxeyes/Desktop/lux_eyes_ui_rediseno"
CARPETA_LOGS="$RUTA_PROYECTO/logs_arranque"

mkdir -p "$CARPETA_LOGS"
ARCHIVO_LOG="$CARPETA_LOGS/arranque_$(date +%Y%m%d_%H%M%S).log"

cd "$RUTA_PROYECTO" || exit 1

# Pequeña espera: justo al arrancar el escritorio, la cámara y la red a
# veces todavía no están completamente listas (picamera2 puede fallar si
# se le pide la cámara demasiado pronto tras el arranque del kernel).
sleep 5

echo "=== Arranque de Lux Eyes: $(date) ===" >> "$ARCHIVO_LOG"
python3 -m scripts_validacion_pi.verificar_7_interfaz_completa >> "$ARCHIVO_LOG" 2>&1
CODIGO_SALIDA=$?
echo "=== Terminó con código $CODIGO_SALIDA: $(date) ===" >> "$ARCHIVO_LOG"

exit $CODIGO_SALIDA
