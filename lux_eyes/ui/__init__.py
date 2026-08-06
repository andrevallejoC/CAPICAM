"""
ui/ — Interfaz gráfica PyQt5 (Fase 5).

Depende de orchestrator/ (Fase 3) exclusivamente a través de los
contratos ya definidos (ObservadorDeFlujo, y los métodos públicos de
OrquestadorTamizaje) — cero cambios en orchestrator/, engine/,
clinical/, storage/ ni sync/ para esta fase.

gestor_camara.GestorCamaraCompartida es la única pieza que depende de
hardware real (picamera2, RPi.GPIO) y no pudo probarse fuera de la
Raspberry Pi — ver la advertencia en ese archivo. El resto del paquete
(observador_qt, hilo_orquestador, pantallas/, ventana_principal) se
probó de extremo a extremo con PyQt5 real en modo offscreen y dobles
de prueba para motor/clinical/cámara, sin ningún hardware.
"""

from .hilo_orquestador import ComandosOrquestador, HiloOrquestador, OrquestadorWorker
from .hilo_sync import ComandosSync, HiloSync, SenalesSync, SyncWorker
from .observador_qt import ObservadorQt, SenalesFlujo
from .ventana_principal import VentanaPrincipal

__all__ = [
    "VentanaPrincipal",
    "HiloOrquestador",
    "ComandosOrquestador",
    "OrquestadorWorker",
    "HiloSync",
    "ComandosSync",
    "SenalesSync",
    "SyncWorker",
    "ObservadorQt",
    "SenalesFlujo",
]
