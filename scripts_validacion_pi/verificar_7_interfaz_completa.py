"""
scripts_validacion_pi/verificar_7_interfaz_completa.py — Lanza la
aplicación REAL completa: VentanaPrincipal + GestorCamaraCompartida +
MotorFotorrefraccionLuxEyes + ReglasClinicasAAPOS + storage real, todo
con hardware físico (cámara, LEDs).

A diferencia de verificar_1 a verificar_6 (que prueban piezas sueltas de
engine/), este script es la primera vez que corres el flujo COMPLETO tal
como lo usaría el tecnólogo: formulario de sesión → paciente → captura OD
→ captura OI → resultado → guardar → siguiente niño.

Los datos se guardan en una base real (tamizaje_validacion.db), separada
de cualquier dato de prueba anterior — bórrala si quieres empezar de cero.

Ejecutar: python -m scripts_validacion_pi.verificar_7_interfaz_completa
"""

import sys

from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QApplication, QShortcut

from lux_eyes.clinical import ReglasClinicasAAPOS
from lux_eyes.engine.slope_estimator import EstimadorOLS
from lux_eyes.storage import RepositorioTamizajes
from lux_eyes.ui import VentanaPrincipal
from lux_eyes.ui.gestor_camara import GestorCamaraCompartida
from scripts_validacion_pi.config_pi import (
    DETECTOR_PUPILA, EXPOSICION_US, GANANCIA_ANALOGA, PINES_POR_MERIDIANO,
    ROTACION_CAMARA_GRADOS, construir_cliente_y_config_sync, construir_detector_pupila,
)


def main():
    print(f"Detector de pupila configurado: {DETECTOR_PUPILA}")
    print(f"Rotación de cámara: {ROTACION_CAMARA_GRADOS}°, "
          f"exposición: {EXPOSICION_US}us, ganancia: {GANANCIA_ANALOGA}")

    # Un DetectorPupilaHaar/MediaPipe POR OJO — cada instancia está fija
    # a un lado de la cara (ver adaptador_haarcascade.py /
    # adaptador_mediapipe.py). GestorCamaraCompartida ya exige los dos
    # por separado desde la corrección aplicada en engine/motor.py.
    gestor = GestorCamaraCompartida(
        pines_por_meridiano=PINES_POR_MERIDIANO,
        detector_pupila_od=construir_detector_pupila("od"),
        detector_pupila_oi=construir_detector_pupila("oi"),
        estimador=EstimadorOLS(),
        rotacion_grados=ROTACION_CAMARA_GRADOS,
        exposicion_us=EXPOSICION_US,
        ganancia_analoga=GANANCIA_ANALOGA,
    )
    motor = gestor.construir_motor()
    clinical = ReglasClinicasAAPOS()
    repo = RepositorioTamizajes("tamizaje_validacion.db", "capturas_validacion")
    cliente_sync, config_sync = construir_cliente_y_config_sync()

    app = QApplication(sys.argv)
    ventana = VentanaPrincipal(
        repo=repo, motor=motor, clinical=clinical, gestor_camara=gestor,
        cliente_sync=cliente_sync, config_sync=config_sync,
    )
    # Pantalla completa, sin bordes ni barra de título: en una pantalla de
    # solo 480px de alto, las decoraciones de ventana del gestor de
    # ventanas pueden comerse pixeles que no sobran. Un dispositivo
    # dedicado como este no necesita esos elementos de todas formas.
    ventana.showFullScreen()

    # En pantalla completa no hay botón de cerrar visible — Escape cierra
    # la app de forma limpia (dispara closeEvent, que ya libera cámara/GPIO
    # e hilo del orquestador). Solo para esta validación; en producción,
    # la salida normal sería apagar el dispositivo.
    atajo_salir = QShortcut(QKeySequence("Esc"), ventana)
    atajo_salir.activated.connect(ventana.close)

    codigo_salida = app.exec()

    gestor.liberar()
    repo.cerrar()
    sys.exit(codigo_salida)


if __name__ == "__main__":
    main()
