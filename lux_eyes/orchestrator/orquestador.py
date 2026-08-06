"""
orchestrator/orquestador.py — OrquestadorTamizaje: coordina el flujo de
UN tamizaje de extremo a extremo (Fase 3).

Es el único componente del sistema que conoce storage/ y, por contrato
(nunca por import directo), engine/ y clinical/ a la vez — exactamente el
rol que 8.7 del Documento Maestro le asigna: "Único punto que conoce el
flujo completo".

No gestiona hilos ni concurrencia (decisión aprobada, Fase 3 §0.5): todos
los métodos son síncronos y deterministas. Quien lo invoque en un contexto
real (ui/ PySide6, Fase 5) decide cómo ejecutarlo fuera del hilo principal
para no bloquear la interfaz durante la captura — ese es exactamente el
principio 2.1 ("la interfaz nunca se bloquea"), pero su cumplimiento es
responsabilidad de quien llama, no de este módulo.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Callable

from lux_eyes.common.tipos import ResultadoOjo, ahora_utc_iso
from lux_eyes.storage.repositorio import RepositorioTamizajes

from .contexto import ContextoTamizajeEnCurso, DatosPaciente, DatosSesion
from .contratos import MotorFotorrefraccion, ObservadorDeFlujo, ReglasClinicas
from .excepciones import EstadoInvalidoError
from .maquina_estados import ESTADOS_CANCELABLES, ESTADOS_TERMINALES, EstadoFlujo

logger = logging.getLogger("lux_eyes.orchestrator")

# Días promedio por mes calendario (365.2425 / 12), usado para convertir
# una diferencia de fechas en meses con precisión fraccional — necesario
# porque clinical/ estratifica varios umbrales exactamente en 48 meses,
# no en años enteros. No se usa dateutil.relativedelta para no añadir una
# dependencia externa solo para este cálculo.
_DIAS_POR_MES_PROMEDIO = 30.436875


def _calcular_edad_meses(fecha_nacimiento: str, fecha_sesion: str) -> float:
    """
    Edad del paciente en meses (fraccional), a partir de fecha_nacimiento
    (DatosPaciente) y fecha_sesion (DatosSesion) — ambas ya validadas por
    ContextoTamizajeEnCurso en formato YYYY-MM-DD antes de llegar aquí.
    """
    nacimiento = date.fromisoformat(fecha_nacimiento)
    sesion = date.fromisoformat(fecha_sesion)
    dias = (sesion - nacimiento).days
    return dias / _DIAS_POR_MES_PROMEDIO


class OrquestadorTamizaje:
    """
    Coordina el flujo de uso de un tamizaje: sesión -> paciente -> captura
    OD -> captura OI -> reglas clínicas -> resultado -> guardado local.

    No llama a sync/: la sincronización es asíncrona e independiente
    (Documento Maestro, 13.2 y diagrama de secuencia 7.4, "en segundo
    plano"). Este orquestador solo garantiza que, al terminar
    confirmar_guardado(), el tamizaje quede PENDIENTE en storage/; que se
    sincronice es responsabilidad de quien opere SincronizadorWeb.
    """

    def __init__(
        self,
        repo: RepositorioTamizajes,
        motor: MotorFotorrefraccion,
        clinical: ReglasClinicas,
        observador: ObservadorDeFlujo | None = None,
    ):
        self._repo = repo
        self._motor = motor
        self._clinical = clinical
        self._observador = observador or ObservadorDeFlujo()
        self._estado: EstadoFlujo | None = None
        self._contexto: ContextoTamizajeEnCurso | None = None
        # [CORRECCIÓN — bug real: la primera versión medía desde el
        # primer intento de captura de 'od' hasta el final, INCLUYENDO el
        # tiempo humano entre terminar un ojo y presionar el botón del
        # otro (reposicionar al paciente, etc.) — un tamizaje real dio
        # 254s, rechazado por el servidor (máximo 180s). Se corrige
        # acumulando SOLO el tiempo que motor.medir_ojo() pasa realmente
        # ejecutando (ambos ojos, incluidos reintentos fallidos — un
        # intento fallido sí consume tiempo real del dispositivo), sin
        # contar la espera humana entre capturas.
        self._duracion_acumulada_captura: float = 0.0

    @property
    def estado(self) -> EstadoFlujo | None:
        """None significa que no hay ningún tamizaje en curso todavía."""
        return self._estado

    # ── Utilidades internas ─────────────────────────────────────────────
    def _exigir_estado(self, *permitidos: EstadoFlujo) -> None:
        if self._estado not in permitidos:
            raise EstadoInvalidoError(
                f"Operación no válida en el estado actual ({self._estado}); "
                f"se esperaba uno de {[e.value for e in permitidos]}."
            )

    def _transicionar(self, nuevo: EstadoFlujo) -> None:
        anterior = self._estado
        self._estado = nuevo
        self._notificar(lambda o: o.en_cambio_de_estado(anterior, nuevo))

    def _notificar(self, accion: Callable[[ObservadorDeFlujo], None]) -> None:
        """
        Ejecuta un callback del observador protegido de excepciones: un
        error en la implementación de ui/ nunca debe corromper el flujo de
        un tamizaje en curso (ver contratos.ObservadorDeFlujo).
        """
        try:
            accion(self._observador)
        except Exception:
            logger.exception(
                "El observador de flujo lanzó una excepción; se ignora "
                "para no interrumpir el tamizaje en curso."
            )

    # ── Ciclo de vida del flujo ──────────────────────────────────────────
    def iniciar_nuevo_tamizaje(self) -> None:
        """Arranca un tamizaje nuevo. Solo válido si no hay uno en curso."""
        if self._estado is not None and self._estado not in ESTADOS_TERMINALES:
            raise EstadoInvalidoError(
                "Ya hay un tamizaje en curso; cancélalo con cancelar() "
                "antes de iniciar uno nuevo."
            )
        self._contexto = ContextoTamizajeEnCurso()
        self._duracion_acumulada_captura = 0.0
        self._transicionar(EstadoFlujo.FORMULARIO_SESION)
        self._notificar(lambda o: o.en_inicio_formulario())

    def cancelar(self) -> None:
        """
        Cancela el tamizaje en curso en cualquier etapa anterior a su
        persistencia. Por construcción del flujo (ver maquina_estados.
        ESTADOS_CANCELABLES), repo.crear_tamizaje() nunca se ha llamado
        todavía en ninguno de esos estados, así que cancelar nunca deja un
        registro inconsistente en storage/: no hay nada que limpiar allí,
        solo se descarta el contexto en memoria.
        """
        if self._estado not in ESTADOS_CANCELABLES:
            raise EstadoInvalidoError(
                f"No se puede cancelar desde el estado actual ({self._estado})."
            )
        anterior = self._estado
        self._contexto = None
        self._estado = EstadoFlujo.CANCELADO
        self._notificar(lambda o: o.en_cancelacion(anterior))
        self._notificar(
            lambda o: o.en_cambio_de_estado(anterior, EstadoFlujo.CANCELADO)
        )

    # ── Paso 1: datos de sesión ──────────────────────────────────────────
    def recibir_datos_sesion(
        self, colegio_nombre: str, colegio_distrito: str,
        tecnologo: str, fecha_sesion: str,
    ) -> None:
        self._exigir_estado(EstadoFlujo.FORMULARIO_SESION)
        self._contexto.sesion = DatosSesion(
            colegio_nombre=colegio_nombre, colegio_distrito=colegio_distrito,
            tecnologo=tecnologo, fecha_sesion=fecha_sesion,
        )
        errores = self._contexto.errores_sesion()
        if errores:
            self._notificar(
                lambda o: o.en_error(EstadoFlujo.FORMULARIO_SESION, "; ".join(errores))
            )
            return  # permanece en FORMULARIO_SESION para corregir
        self._transicionar(EstadoFlujo.FORMULARIO_PACIENTE)

    # ── Paso 2: datos de paciente + validación estructural ──────────────
    def recibir_datos_paciente(
        self, dni: str, nombre_paciente: str, fecha_nacimiento: str,
        grado_seccion: str, email_padre: str | None = None,
        telefono_padre: str | None = None,
    ) -> None:
        self._exigir_estado(EstadoFlujo.FORMULARIO_PACIENTE)
        self._contexto.paciente = DatosPaciente(
            dni=dni, nombre_paciente=nombre_paciente,
            fecha_nacimiento=fecha_nacimiento, grado_seccion=grado_seccion,
            email_padre=email_padre, telefono_padre=telefono_padre,
        )
        errores = self._contexto.errores_paciente()
        if errores:
            self._notificar(
                lambda o: o.en_error(EstadoFlujo.FORMULARIO_PACIENTE, "; ".join(errores))
            )
            return  # permanece en FORMULARIO_PACIENTE para corregir
        self._transicionar(EstadoFlujo.CAPTURA_OD)
        self._notificar(lambda o: o.en_captura_iniciada("od"))

    # ── Paso 3: captura de cada ojo, con reintento ──────────────────────
    def ejecutar_captura(self, ojo: str) -> None:
        """
        Ejecuta la captura de 'od' o 'oi' mediante MotorFotorrefraccion.
        Un fallo deja el flujo en el mismo estado de captura (reintento
        sin pérdida de datos, 14.4); un éxito avanza al siguiente paso.
        """
        if ojo not in ("od", "oi"):
            raise ValueError(f"ojo debe ser 'od' u 'oi', no {ojo!r}")

        estado_esperado = EstadoFlujo.CAPTURA_OD if ojo == "od" else EstadoFlujo.CAPTURA_OI
        self._exigir_estado(estado_esperado)

        def _reenviar_progreso(mensaje: str) -> None:
            self._notificar(lambda o: o.en_progreso_captura(ojo, mensaje))

        # Se cronometra SOLO la llamada real a medir_ojo() — no el tiempo
        # entre que el tecnólogo termina un ojo y presiona el botón del
        # otro (eso es espera humana, no tiempo del dispositivo). Se
        # acumula tanto en éxito como en fallo: un intento fallido
        # (PupilaNoDetectadaError, etc.) sí consumió tiempo real del
        # dispositivo intentando medir.
        _inicio = time.monotonic()
        try:
            resultado: ResultadoOjo = self._motor.medir_ojo(ojo, _reenviar_progreso)
        except Exception as error:
            self._duracion_acumulada_captura += time.monotonic() - _inicio
            self._notificar(lambda o: o.en_error(estado_esperado, str(error)))
            return  # permanece en el mismo estado: reintentar el mismo ojo
        self._duracion_acumulada_captura += time.monotonic() - _inicio

        if ojo == "od":
            self._contexto.od = resultado
        else:
            self._contexto.oi = resultado
        self._notificar(lambda o: o.en_captura_finalizada(ojo, resultado))

        if ojo == "od":
            self._transicionar(EstadoFlujo.CAPTURA_OI)
            self._notificar(lambda o: o.en_captura_iniciada("oi"))
        else:
            self._transicionar(EstadoFlujo.REGLAS_CLINICAS)
            self._clasificar()

    # ── Paso 4: reglas clínicas (interno; disparado tras ambas capturas) ─
    def _clasificar(self) -> None:
        self._notificar(lambda o: o.en_procesamiento_iniciado())
        # [CORRECCIÓN — bug real: campos NUNCA se llenaban en el flujo
        # real, solo en fixtures de prueba manuales] duracion_segundos y
        # timestamp_captura del contexto quedaban en None hasta ahora —
        # confirmado por un 422 real del servidor (exige ambos como
        # obligatorios, no null). timestamp_captura se toma AQUÍ (al
        # terminar de clasificar, con ambos ojos ya medidos), no antes.
        #
        # [CORRECCIÓN 2 — segundo bug real, distinto del anterior]: la
        # primera versión de esta corrección medía desde el primer
        # intento de 'od' hasta aquí, incluyendo la espera humana entre
        # capturar un ojo y el otro. Un tamizaje real dio 254s (rechazado
        # por el servidor, máximo 180s). self._duracion_acumulada_captura
        # (ver ejecutar_captura) ya excluye esa espera — ver docstring
        # del __init__.
        self._contexto.duracion_segundos = self._duracion_acumulada_captura
        self._contexto.timestamp_captura = ahora_utc_iso()
        edad_meses = _calcular_edad_meses(
            self._contexto.paciente.fecha_nacimiento, self._contexto.sesion.fecha_sesion
        )
        riesgo, requiere_derivacion, observaciones = self._clinical.clasificar(
            self._contexto.od, self._contexto.oi, edad_meses
        )
        self._contexto.riesgo = riesgo
        self._contexto.requiere_derivacion = requiere_derivacion
        self._contexto.observaciones = observaciones
        self._notificar(
            lambda o: o.en_procesamiento_finalizado(
                riesgo, requiere_derivacion, observaciones
            )
        )
        self._transicionar(EstadoFlujo.MOSTRAR_RESULTADO)
        self._notificar(lambda o: o.en_resultado_listo())

    # ── Paso 5: confirmar y persistir en storage/ ───────────────────────
    def confirmar_guardado(self) -> str:
        """
        Traduce el contexto acumulado a un Tamizaje completo y lo persiste
        vía repo.crear_tamizaje() — único punto de contacto con storage/
        en todo este módulo. No llama a sync/ (ver docstring de la clase).
        Devuelve el uuid_local asignado.
        """
        self._exigir_estado(EstadoFlujo.MOSTRAR_RESULTADO)
        self._transicionar(EstadoFlujo.GUARDAR_LOCAL)

        tamizaje = self._contexto.a_tamizaje()
        uuid_local = self._repo.crear_tamizaje(tamizaje)

        self._notificar(lambda o: o.en_almacenamiento_completado(uuid_local))
        self._contexto = None
        self._transicionar(EstadoFlujo.COMPLETADO)
        return uuid_local
