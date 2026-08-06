"""
orchestrator/contratos.py — Contratos contra los que se implementa
OrquestadorTamizaje.

DECISIÓN de arquitectura:
    engine/ y clinical/ (Fase 4) no existen todavía. Se usa typing.Protocol
    (tipado estructural) para no forzar que sus futuras implementaciones
    importen orchestrator/: basta con que tengan los métodos con esta
    firma. Esto respeta la regla de dependencias del proyecto (orchestrator
    depende de abstracciones; nada depende hacia orchestrator).

ObservadorDeFlujo es la contraparte formal de "reportar_progreso" y
"mostrar_resultado" que 8.8 atribuye a ui/, ampliada con eventos de alto
nivel (decisión aprobada, Fase 3 §0.7): inicio de formulario, captura
iniciada/finalizada, procesamiento iniciado/finalizado, almacenamiento
completado, error y cancelación. Se define aquí, ya, para poder probar
orchestrator/ de extremo a extremo sin esperar a PySide6 (Fase 5), y para
que la futura ui/ solo tenga que sobreescribir los eventos que le
interesan.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

from lux_eyes.common.tipos import ResultadoOjo

from .maquina_estados import EstadoFlujo


@runtime_checkable
class MotorFotorrefraccion(Protocol):
    """Contrato que engine/ deberá cumplir (Fase 4). No importa orchestrator/."""

    def medir_ojo(
        self, ojo: str, reportar_progreso: Callable[[str], None]
    ) -> ResultadoOjo:
        """
        Ejecuta el pipeline completo de fotorrefracción para un ojo
        ('od' u 'oi') y devuelve su ResultadoOjo con incertidumbre.

        Debe llamar a reportar_progreso(mensaje) durante la captura para
        que el orquestador pueda reenviar el progreso al observador
        (ObservadorDeFlujo.en_progreso_captura).

        Puede lanzar cualquier excepción para señalar un fallo de captura
        (pupila no detectada, ventana inestable, fallo de cámara/LED,
        etc.); el orquestador la atrapa y permite reintentar el mismo ojo
        sin perder los datos de sesión/paciente ya ingresados (Documento
        Maestro, 14.4).
        """
        ...


@runtime_checkable
class ReglasClinicas(Protocol):
    """Contrato que clinical/ deberá cumplir. No importa orchestrator/."""

    def clasificar(
        self, od: ResultadoOjo, oi: ResultadoOjo, edad_meses: float
    ) -> tuple[str | None, bool | None, str]:
        """
        Devuelve (riesgo, requiere_derivacion, observaciones) a partir de
        los resultados refractivos de ambos ojos y la edad del paciente
        en meses (con precisión fraccional). Firma tomada de la interfaz
        pública documentada en 8.6, ampliada con edad_meses: la tabla de
        umbrales clínicos real (clinical/configuracion.py) estratifica
        varios criterios por edad, con un corte a los 48 meses — sin este
        dato, ReglasClinicas no puede aplicar la tabla correctamente.
        """
        ...


class ObservadorDeFlujo:
    """
    Eventos de alto nivel que OrquestadorTamizaje emite durante el flujo.
    ui/ (Fase 5) implementará una subclase concreta que traduzca estos
    eventos a actualizaciones de pantalla PySide6, sin que orchestrator/
    dependa de PySide6 ni de ningún framework gráfico.

    DECISIÓN de arquitectura:
        Se implementa como clase base con métodos no-operativos (en vez de
        un Protocol puro) para que una implementación concreta solo tenga
        que sobreescribir los eventos que le interesan. El orquestador usa
        una instancia de esta clase base por defecto cuando no se le
        inyecta ninguna, de modo que nunca es obligatorio pasar un
        observador para poder usar OrquestadorTamizaje (p. ej. en scripts
        o pruebas que no necesitan reaccionar a eventos).

        Cualquier excepción que una implementación concreta lance dentro
        de estos métodos se atrapa y se registra por logging en el
        orquestador (ver orquestador._notificar): un error de la UI nunca
        debe corromper el estado de un tamizaje en curso.
    """

    def en_cambio_de_estado(
        self, estado_anterior: EstadoFlujo | None, estado_nuevo: EstadoFlujo
    ) -> None:
        """Se emite en TODA transición, además de los eventos semánticos de abajo."""

    def en_inicio_formulario(self) -> None:
        """Arrancó un tamizaje nuevo (estado: FORMULARIO_SESION)."""

    def en_captura_iniciada(self, ojo: str) -> None:
        """Comienza la captura de 'od' o 'oi'."""

    def en_progreso_captura(self, ojo: str, mensaje: str) -> None:
        """Progreso intermedio reenviado desde MotorFotorrefraccion.medir_ojo."""

    def en_captura_finalizada(self, ojo: str, resultado: ResultadoOjo) -> None:
        """La captura de ese ojo tuvo éxito."""

    def en_procesamiento_iniciado(self) -> None:
        """Arrancó la clasificación clínica (estado: REGLAS_CLINICAS)."""

    def en_procesamiento_finalizado(
        self,
        riesgo: str | None,
        requiere_derivacion: bool | None,
        observaciones: str,
    ) -> None:
        """clinical/ ya devolvió su clasificación."""

    def en_resultado_listo(self) -> None:
        """El contexto ya tiene todo listo para mostrarse (estado: MOSTRAR_RESULTADO)."""

    def en_almacenamiento_completado(self, uuid_local: str) -> None:
        """repo.crear_tamizaje() tuvo éxito (GUARDAR_LOCAL -> COMPLETADO)."""

    def en_error(self, estado: EstadoFlujo, mensaje: str) -> None:
        """
        Un paso falló de forma recuperable (validación fallida, o fallo
        de captura de un ojo). El flujo permanece en el mismo estado para
        que quien invoque corrija o reintente.
        """

    def en_cancelacion(self, estado_anterior: EstadoFlujo) -> None:
        """El flujo se canceló antes de persistirse (estado: CANCELADO)."""
