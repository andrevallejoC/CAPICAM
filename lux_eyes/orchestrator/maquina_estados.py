"""
orchestrator/maquina_estados.py — Estados del flujo de un tamizaje.

Cubre únicamente el flujo de UN tamizaje (FORMULARIO_SESION -> COMPLETADO
o CANCELADO), no la navegación completa de la aplicación (ENCENDIDO,
BIENVENIDA, VERIFICAR_WIFI, MENU) — decisión aprobada en el diseño de la
Fase 3 (§0.1): esos estados son navegación pura, sin lógica de dominio
verificable sin ui/ real. Si en el futuro se necesita coordinarlos, se
añaden como una capa fina encima de este módulo, sin rediseñarlo.
"""

from __future__ import annotations

from enum import Enum


class EstadoFlujo(str, Enum):
    FORMULARIO_SESION = "FORMULARIO_SESION"
    FORMULARIO_PACIENTE = "FORMULARIO_PACIENTE"
    CAPTURA_OD = "CAPTURA_OD"
    CAPTURA_OI = "CAPTURA_OI"
    REGLAS_CLINICAS = "REGLAS_CLINICAS"
    MOSTRAR_RESULTADO = "MOSTRAR_RESULTADO"
    GUARDAR_LOCAL = "GUARDAR_LOCAL"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"


# Estados terminales: desde aquí ya no se puede reanudar el tamizaje
# actual, solo iniciar uno nuevo con iniciar_nuevo_tamizaje().
ESTADOS_TERMINALES = frozenset({EstadoFlujo.COMPLETADO, EstadoFlujo.CANCELADO})

# Estados desde los que cancelar() está permitido: cualquiera que no sea ya
# terminal. Como repo.crear_tamizaje() SOLO se invoca dentro de
# confirmar_guardado() (estado GUARDAR_LOCAL, ejecución síncrona de un solo
# método), cancelar antes de eso nunca deja un registro a medias en
# storage/ — es seguro por construcción del flujo, no por una verificación
# adicional de storage/.
ESTADOS_CANCELABLES = frozenset(EstadoFlujo) - ESTADOS_TERMINALES
