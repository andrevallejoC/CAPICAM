"""
common/tipos.py — Tipos, enumeraciones y estructuras compartidas de Lux Eyes.

Este módulo no depende de ningún otro subsistema. Define el vocabulario común
(estados, estructuras de datos) que usan storage, sync y el orquestador, de modo
que ninguno de ellos necesite importar a los otros para hablar el mismo idioma.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import uuid


class EstadoSync(str, Enum):
    """
    Estado de sincronización de un tamizaje con la plataforma web.

    Corresponde a la máquina de estados de sincronización del documento maestro
    (sección 5.2). Hereda de str para que se serialice de forma legible en SQLite
    y en JSON sin conversiones adicionales.
    """
    PENDIENTE = "PENDIENTE"              # Guardado local; aún no enviado
    ENVIANDO = "ENVIANDO"               # Envío en curso
    SINCRONIZADO = "SINCRONIZADO"       # Confirmado por el servidor (paso 1 OK)
    ERROR_REINTENTABLE = "ERROR_REINTENTABLE"   # Falló, pero se puede reintentar
    ERROR_PERMANENTE = "ERROR_PERMANENTE"       # Superó el límite de reintentos


class EstadoImagenes(str, Enum):
    """
    Estado de subida de las imágenes IR (funcionalidad OPCIONAL).

    RESTRICCIÓN-ACTUAL:
        Las imágenes no son obligatorias para considerar un tamizaje completo
        (decisión del equipo). Su subida no condiciona EstadoSync.
    ARQUITECTURA IDEAL:
        En un dispositivo biomédico, las imágenes son evidencia clínica y su
        subida formaría parte del criterio de "tamizaje completo".
    MEJORA FUTURA:
        Reevaluar si las imágenes deben volverse obligatorias y unificar su
        estado con EstadoSync.
    """
    NO_APLICA = "NO_APLICA"             # No se capturaron / no se subirán
    PENDIENTE = "PENDIENTE"
    SUBIDAS = "SUBIDAS"
    ERROR = "ERROR"


def ahora_utc_iso() -> str:
    """Marca de tiempo actual en UTC, formato ISO 8601. Fuente única de tiempo."""
    return datetime.now(timezone.utc).isoformat()


def nuevo_uuid_local() -> str:
    """
    Genera el identificador local permanente de un tamizaje.

    ARQUITECTURA IDEAL / PRINCIPIO:
        Cada tamizaje nace con un identificador único generado por el propio
        dispositivo, con total independencia del servidor. Este uuid_local es la
        columna vertebral de la autonomía del dispositivo: con él se organizan el
        paciente, los resultados, los archivos, el estado de sincronización y la
        auditoría. El registro_id_servidor se asocia después, si y cuando el
        servidor confirma el paso 1.
    """
    return str(uuid.uuid4())


@dataclass
class ResultadoOjo:
    """Resultados refractivos de un ojo, con su incertidumbre asociada."""
    esfera: Optional[float] = None
    cilindro: Optional[float] = None
    eje: Optional[float] = None

    # Incertidumbre (desviación estándar entre frames). El motor de vídeo la
    # produce; puede ser None si aún no se ha medido.
    esfera_sd: Optional[float] = None
    cilindro_sd: Optional[float] = None
    eje_sd: Optional[float] = None

    # RESTRICCIÓN-ACTUAL:
    #   reflejo_rojo es un placeholder exigido por el contrato de la API.
    #   No existe algoritmo de detección; se guarda como None ("no evaluado").
    # ARQUITECTURA IDEAL:
    #   No inventar datos clínicos. Un valor nulo/"no evaluado" es honesto;
    #   un valor aleatorio sería peligroso (podría confundirse con medición real).
    # MEJORA FUTURA:
    #   Incorporar un módulo de detección de reflejo rojo que rellene este campo.
    reflejo_rojo: Optional[bool] = None


@dataclass
class Tamizaje:
    """
    Registro completo de un tamizaje. Es la unidad de dato del dispositivo.

    El almacenamiento local es la FUENTE DE VERDAD mientras el tamizaje no se haya
    sincronizado. El servidor es persistencia remota, no origen de los datos.
    """
    # ── Identidad ──
    uuid_local: str = field(default_factory=nuevo_uuid_local)
    registro_id_servidor: Optional[str] = None   # Lo asigna la API en el paso 1

    # ── Sesión ──
    colegio_nombre: str = ""
    colegio_distrito: str = ""
    tecnologo: str = ""
    fecha_sesion: str = ""

    # ── Paciente ──
    # RESTRICCIÓN/PRIVACIDAD:
    #   El DNI se almacena aquí en claro SOLO localmente para operación del
    #   dispositivo. NUNCA se envía en claro: sync lo hashea (SHA-256) antes de
    #   salir. El cifrado en reposo de esta base es MEJORA FUTURA (ver deuda).
    dni: str = ""
    nombre_paciente: str = ""
    fecha_nacimiento: str = ""
    grado_seccion: str = ""
    email_padre: Optional[str] = None
    telefono_padre: Optional[str] = None

    # ── Resultados ──
    od: ResultadoOjo = field(default_factory=ResultadoOjo)
    oi: ResultadoOjo = field(default_factory=ResultadoOjo)

    # ── Clasificación clínica (módulo de reglas, aún con umbrales por definir) ──
    riesgo: Optional[str] = None
    requiere_derivacion: Optional[bool] = None
    observaciones: str = ""

    # ── Metadatos de captura ──
    duracion_segundos: Optional[float] = None
    timestamp_captura: Optional[str] = None

    # ── Imágenes (opcionales) ──
    ruta_imagen_od: Optional[str] = None
    ruta_imagen_oi: Optional[str] = None
    hash_imagen_od: Optional[str] = None
    hash_imagen_oi: Optional[str] = None

    # ── Estado interno del ciclo de vida ──
    estado_sync: EstadoSync = EstadoSync.PENDIENTE
    estado_imagenes: EstadoImagenes = EstadoImagenes.NO_APLICA
    intentos_sync: int = 0
    ultimo_error: Optional[str] = None

    creado_en: str = field(default_factory=ahora_utc_iso)
    actualizado_en: str = field(default_factory=ahora_utc_iso)

    def to_dict(self) -> dict:
        """Serializa a dict plano (para logging/depuración)."""
        return asdict(self)
