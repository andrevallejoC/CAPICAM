"""
storage/esquema.py — Definición del esquema SQLite y su inicialización.

Aísla todo el SQL de creación de tablas. El resto de storage/ no escribe DDL;
solo este módulo conoce la estructura física de la base de datos.
"""

from __future__ import annotations
import sqlite3

# Versión del esquema. Permite migraciones futuras sin perder datos.
VERSION_ESQUEMA = 1

# ── DDL ──────────────────────────────────────────────────────────────────────
# Notas de diseño:
#  - uuid_local es la CLAVE PRIMARIA: identidad propia del dispositivo, nunca nula.
#  - registro_id_servidor es NULLABLE: se rellena cuando el servidor confirma.
#  - Los estados se guardan como texto (enum.str) para legibilidad y auditoría.
#  - Se separan conceptualmente identificadores del paciente y datos del tamizaje
#    (facilita anonimización/retención futura), aunque vivan en la misma tabla.
_DDL_TAMIZAJES = """
CREATE TABLE IF NOT EXISTS tamizajes (
    uuid_local            TEXT PRIMARY KEY NOT NULL,
    registro_id_servidor  TEXT,

    -- Sesión
    colegio_nombre        TEXT,
    colegio_distrito      TEXT,
    tecnologo             TEXT,
    fecha_sesion          TEXT,

    -- Paciente (DNI en claro SOLO local; se hashea antes de sincronizar)
    dni                   TEXT,
    nombre_paciente       TEXT,
    fecha_nacimiento      TEXT,
    grado_seccion         TEXT,
    email_padre           TEXT,
    telefono_padre        TEXT,

    -- Resultados OD
    od_esfera             REAL,
    od_cilindro           REAL,
    od_eje                REAL,
    od_esfera_sd          REAL,
    od_cilindro_sd        REAL,
    od_eje_sd             REAL,
    od_reflejo_rojo       INTEGER,   -- 0/1/NULL (NULL = no evaluado)

    -- Resultados OI
    oi_esfera             REAL,
    oi_cilindro           REAL,
    oi_eje                REAL,
    oi_esfera_sd          REAL,
    oi_cilindro_sd        REAL,
    oi_eje_sd             REAL,
    oi_reflejo_rojo       INTEGER,

    -- Clasificación clínica
    riesgo                TEXT,
    requiere_derivacion   INTEGER,   -- 0/1/NULL
    observaciones         TEXT,

    -- Metadatos de captura
    duracion_segundos     REAL,
    timestamp_captura     TEXT,

    -- Imágenes (opcionales)
    ruta_imagen_od        TEXT,
    ruta_imagen_oi        TEXT,
    hash_imagen_od        TEXT,
    hash_imagen_oi        TEXT,

    -- Ciclo de vida
    estado_sync           TEXT NOT NULL DEFAULT 'PENDIENTE',
    estado_imagenes       TEXT NOT NULL DEFAULT 'NO_APLICA',
    intentos_sync         INTEGER NOT NULL DEFAULT 0,
    ultimo_error          TEXT,

    creado_en             TEXT NOT NULL,
    actualizado_en        TEXT NOT NULL
);
"""

# Índice para que el sincronizador encuentre pendientes con rapidez.
_DDL_INDICE_SYNC = """
CREATE INDEX IF NOT EXISTS idx_estado_sync ON tamizajes (estado_sync);
"""

# Registro de auditoría: toda transición relevante del ciclo de vida queda
# trazada. Clave para un dispositivo biomédico reproducible y depurable.
_DDL_AUDITORIA = """
CREATE TABLE IF NOT EXISTS auditoria (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid_local    TEXT,               -- nullable: los eventos de sistema no
                                      -- refieren a un tamizaje concreto
    evento        TEXT NOT NULL,
    detalle       TEXT,
    creado_en     TEXT NOT NULL,
    FOREIGN KEY (uuid_local) REFERENCES tamizajes (uuid_local)
);
"""

_DDL_META = """
CREATE TABLE IF NOT EXISTS meta (
    clave  TEXT PRIMARY KEY,
    valor  TEXT
);
"""


def inicializar_esquema(conn: sqlite3.Connection) -> None:
    """Crea las tablas si no existen y registra la versión del esquema."""
    conn.execute("PRAGMA foreign_keys = ON;")
    # WAL: mejora la resiliencia ante cortes y permite lecturas concurrentes
    # mientras se escribe (útil cuando el sincronizador lee y la UI escribe).
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute(_DDL_TAMIZAJES)
    conn.execute(_DDL_INDICE_SYNC)
    conn.execute(_DDL_AUDITORIA)
    conn.execute(_DDL_META)
    conn.execute(
        "INSERT OR IGNORE INTO meta (clave, valor) VALUES ('version_esquema', ?);",
        (str(VERSION_ESQUEMA),),
    )
    conn.commit()
