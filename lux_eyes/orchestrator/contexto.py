"""
orchestrator/contexto.py — Acumulador mutable de los datos de un tamizaje
en curso, y su validación estructural.

DECISIÓN de arquitectura:
    Tamizaje (common/tipos.py) representa un registro COMPLETO, tal como
    storage/ lo persiste. El flujo de uso construye esos datos por etapas;
    en vez de ensuciar Tamizaje con un estado "a medias", se usa este
    acumulador propio de orchestrator/, nunca expuesto a storage/. Solo al
    final, a_tamizaje() lo traduce a un Tamizaje completo e inmutable,
    listo para repo.crear_tamizaje().

ALCANCE DE LA VALIDACIÓN (decisión explícita, Fase 3 §0.4):
    Todo lo que valida este módulo es ESTRUCTURAL: campos obligatorios no
    vacíos, formatos básicos (fechas), consistencia mínima de los datos de
    formulario. NINGUNA regla clínica ni médica vive aquí — eso es
    responsabilidad exclusiva de clinical/ (Documento Maestro, 8.6). Este
    módulo no sabe qué es un riesgo alto ni qué umbrales aplican; solo sabe
    si los datos que el tecnólogo ingresó son sintácticamente válidos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lux_eyes.common.tipos import ResultadoOjo, Tamizaje

_PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ContextoInvalidoError(Exception):
    """Se intentó construir un Tamizaje sin que el contexto estuviera completo."""


@dataclass
class DatosSesion:
    colegio_nombre: str = ""
    colegio_distrito: str = ""
    tecnologo: str = ""
    fecha_sesion: str = ""


@dataclass
class DatosPaciente:
    dni: str = ""
    nombre_paciente: str = ""
    fecha_nacimiento: str = ""
    grado_seccion: str = ""
    email_padre: str | None = None
    telefono_padre: str | None = None


@dataclass
class ContextoTamizajeEnCurso:
    """Acumulador mutable de un único tamizaje mientras el flujo avanza."""

    sesion: DatosSesion | None = None
    paciente: DatosPaciente | None = None
    od: ResultadoOjo | None = None
    oi: ResultadoOjo | None = None
    riesgo: str | None = None
    requiere_derivacion: bool | None = None
    observaciones: str = ""
    duracion_segundos: float | None = None
    timestamp_captura: str | None = None

    # ── Validación estructural (nunca clínica) ──────────────────────────
    def errores_sesion(self) -> list[str]:
        if self.sesion is None:
            return ["No se ingresaron datos de sesión."]
        errores = []
        if not self.sesion.colegio_nombre.strip():
            errores.append("El nombre del colegio es obligatorio.")
        if not self.sesion.tecnologo.strip():
            errores.append("El nombre del tecnólogo es obligatorio.")
        if not _PATRON_FECHA.match(self.sesion.fecha_sesion or ""):
            errores.append("fecha_sesion debe tener formato YYYY-MM-DD.")
        return errores

    def errores_paciente(self) -> list[str]:
        if self.paciente is None:
            return ["No se ingresaron datos de paciente."]
        errores = []
        if not self.paciente.dni.strip():
            errores.append("El DNI es obligatorio.")
        if not self.paciente.nombre_paciente.strip():
            errores.append("El nombre del paciente es obligatorio.")
        if not _PATRON_FECHA.match(self.paciente.fecha_nacimiento or ""):
            errores.append("fecha_nacimiento debe tener formato YYYY-MM-DD.")
        return errores

    # ── Traducción final hacia el modelo de storage/ ────────────────────
    def a_tamizaje(self) -> Tamizaje:
        if self.errores_sesion() or self.errores_paciente():
            raise ContextoInvalidoError(
                "No se puede construir un Tamizaje con datos de sesión/"
                "paciente incompletos o inválidos."
            )
        if self.od is None or self.oi is None:
            raise ContextoInvalidoError(
                "No se puede construir un Tamizaje sin resultados de ambos ojos."
            )

        return Tamizaje(
            colegio_nombre=self.sesion.colegio_nombre,
            colegio_distrito=self.sesion.colegio_distrito,
            tecnologo=self.sesion.tecnologo,
            fecha_sesion=self.sesion.fecha_sesion,
            dni=self.paciente.dni,
            nombre_paciente=self.paciente.nombre_paciente,
            fecha_nacimiento=self.paciente.fecha_nacimiento,
            grado_seccion=self.paciente.grado_seccion,
            email_padre=self.paciente.email_padre,
            telefono_padre=self.paciente.telefono_padre,
            od=self.od,
            oi=self.oi,
            riesgo=self.riesgo,
            requiere_derivacion=self.requiere_derivacion,
            observaciones=self.observaciones,
            duracion_segundos=self.duracion_segundos,
            timestamp_captura=self.timestamp_captura,
        )
