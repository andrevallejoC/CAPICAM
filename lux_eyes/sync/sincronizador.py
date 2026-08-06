"""
sync/sincronizador.py — Orquesta un ciclo de sincronización de la cola de
pendientes de storage/ contra la API web externa.

Es el único componente de sync/ que conoce storage/, cliente_api.py y
politica_reintentos.py a la vez. Deliberadamente delgado: no reimplementa
nada que ya resuelvan sus colaboradores.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from lux_eyes.common.tipos import EstadoImagenes, EstadoSync, Tamizaje
from lux_eyes.storage.repositorio import RepositorioTamizajes

from .cliente_api import ClienteAPI
from .configuracion import ConfiguracionSync
from .excepciones import ErrorAutenticacion, ErrorConectividad, ErrorSincronizacion
from .politica_reintentos import ClasificadorErrores, DecisionReintento, RegistroBackoff
from .serializacion import tamizaje_a_payload

logger = logging.getLogger("lux_eyes.sync")


@dataclass(frozen=True)
class ResumenSincronizacion:
    """
    Resultado de un ejecutar_ciclo(). No es necesario inspeccionar
    storage/ para saber qué pasó en el ciclo: este resumen ya lo dice.
    """
    sincronizados: int = 0
    reintentables: int = 0
    permanentes: int = 0
    ambientales: int = 0
    saltados_por_backoff: int = 0
    ciclo_abortado_por_autenticacion: bool = False


class SincronizadorWeb:
    """
    Orquesta un ciclo de sincronización sobre la cola de storage/.

    RESTRICCIÓN/PRINCIPIO DE USO (backoff en memoria, Fase 2 aprobada):
        Esta clase mantiene estado en memoria (la tabla de backoff dentro
        de RegistroBackoff). DEBE instanciarse UNA sola vez por proceso y
        reutilizarse en cada llamada a ejecutar_ciclo(). Crear una
        instancia nueva en cada ciclo pierde el backoff acumulado, tal
        como se perdería ante un reinicio del dispositivo — pero aquí
        ocurriría sin que la Raspberry se haya reiniciado, solo por un
        error de uso de este componente.

    PRECONDICIÓN DE USO:
        Antes del primer ejecutar_ciclo() de una sesión del dispositivo,
        quien construya este objeto debe haber llamado ya a
        repo.recuperar_envios_interrumpidos(). No es responsabilidad de
        SincronizadorWeb decidir cuándo el dispositivo "arrancó"; storage/
        ya resuelve la recuperación tras corte de energía por su cuenta.
    """

    def __init__(
        self,
        repo: RepositorioTamizajes,
        cliente: ClienteAPI,
        config: ConfiguracionSync,
        clasificador: ClasificadorErrores | None = None,
        registro_backoff: RegistroBackoff | None = None,
    ):
        self._repo = repo
        self._cliente = cliente
        self._config = config
        self._clasificador = clasificador or ClasificadorErrores()
        self._backoff = registro_backoff or RegistroBackoff(config)

    def ejecutar_ciclo(self) -> ResumenSincronizacion:
        """
        Una sola pasada sobre la cola de pendientes. No es un bucle
        infinito ni bloquea con sleep(): la cadencia con la que se llama a
        este método es responsabilidad de quien lo invoque (hoy: pruebas o
        un script; mañana: el orquestador), igual que storage/ no decide
        cuándo se le llama.
        """
        pendientes = self._repo.listar_pendientes(max_intentos=self._config.max_intentos)

        sincronizados = reintentables = permanentes = 0
        ambientales = saltados = 0

        for t in pendientes:
            if not self._backoff.listo_para_intentar(t.uuid_local):
                saltados += 1
                continue

            resultado = self._procesar_uno(t)

            if resultado is DecisionReintento.ABORTAR_CICLO:
                return ResumenSincronizacion(
                    sincronizados=sincronizados,
                    reintentables=reintentables,
                    permanentes=permanentes,
                    ambientales=ambientales,
                    saltados_por_backoff=saltados,
                    ciclo_abortado_por_autenticacion=True,
                )
            if resultado is None:
                sincronizados += 1
            elif resultado is DecisionReintento.REINTENTAR_AMBIENTAL:
                ambientales += 1
            elif resultado is DecisionReintento.REINTENTAR_CON_BACKOFF:
                reintentables += 1
            elif resultado is DecisionReintento.PERMANENTE:
                permanentes += 1

        return ResumenSincronizacion(
            sincronizados=sincronizados,
            reintentables=reintentables,
            permanentes=permanentes,
            ambientales=ambientales,
            saltados_por_backoff=saltados,
            ciclo_abortado_por_autenticacion=False,
        )

    # ── Internos ─────────────────────────────────────────────────────────
    def _procesar_uno(self, t: Tamizaje) -> DecisionReintento | None:
        """
        Procesa un único tamizaje pendiente. Devuelve None si terminó
        SINCRONIZADO, o la DecisionReintento aplicada en caso contrario.
        """
        self._repo.marcar_estado_sync(t.uuid_local, EstadoSync.ENVIANDO)

        try:
            payload = tamizaje_a_payload(t, self._config)
            registro_id = self._cliente.enviar_datos(payload)
        except ErrorSincronizacion as error:
            return self._manejar_fallo(t, error)

        # Éxito del Paso 1: esto es lo único que determina SINCRONIZADO
        # (13.1, 13.2). Los pasos 2 y 3 son best-effort a continuación.
        self._repo.marcar_estado_sync(
            t.uuid_local, EstadoSync.SINCRONIZADO, registro_id_servidor=registro_id
        )
        self._backoff.olvidar(t.uuid_local)
        self._intentar_pasos_opcionales(t, registro_id)
        return None

    def _manejar_fallo(self, t: Tamizaje, error: ErrorSincronizacion) -> DecisionReintento:
        decision = self._clasificador.clasificar(error)

        if decision is DecisionReintento.REINTENTAR_AMBIENTAL:
            # No llegó al servidor: fallo del dispositivo, no del registro.
            # No incrementa intentos_sync (13.2: "Sin Wi-Fi -> PENDIENTE").
            self._repo.marcar_estado_sync(
                t.uuid_local, EstadoSync.PENDIENTE, error=str(error)
            )

        elif decision is DecisionReintento.REINTENTAR_CON_BACKOFF:
            self._repo.marcar_estado_sync(
                t.uuid_local, EstadoSync.ERROR_REINTENTABLE,
                error=str(error), incrementar_intentos=True,
            )
            # intentos_sync ya reflejaba t.intentos_sync antes de este
            # fallo; el incremento que acabamos de aplicar en storage/ lo
            # deja en +1 respecto a lo que teníamos en memoria.
            self._backoff.programar_siguiente(t.uuid_local, t.intentos_sync + 1)

        elif decision is DecisionReintento.PERMANENTE:
            self._repo.marcar_estado_sync(
                t.uuid_local, EstadoSync.ERROR_PERMANENTE, error=str(error)
            )
            self._backoff.olvidar(t.uuid_local)

        elif decision is DecisionReintento.ABORTAR_CICLO:
            # No dejamos el registro colgado en ENVIANDO: vuelve a
            # PENDIENTE sin penalizar su presupuesto de reintentos, ya que
            # el fallo es de configuración del dispositivo (token), no del
            # tamizaje en sí.
            self._repo.marcar_estado_sync(
                t.uuid_local, EstadoSync.PENDIENTE, error=str(error)
            )
            logger.error(
                "Ciclo de sincronización abortado por fallo de autenticación "
                "(token inválido o expirado). uuid_local=%s. %s",
                t.uuid_local, error,
            )

        return decision

    def _intentar_pasos_opcionales(self, t: Tamizaje, registro_id: str) -> None:
        """
        Pasos 2 (imágenes) y 3 (PDF) del contrato: best-effort. Un fallo
        aquí NUNCA revierte el estado SINCRONIZADO ya confirmado (13.2:
        "Falla imagen (opcional) -> no afecta el estado SINCRONIZADO").
        Se registran solo por logging: no son transiciones del ciclo de
        vida del tamizaje en el sentido de storage/, son un intento
        secundario y no bloqueante.
        """
        if t.ruta_imagen_od or t.ruta_imagen_oi:
            try:
                self._cliente.subir_imagenes(
                    registro_id, t.ruta_imagen_od, t.ruta_imagen_oi
                )
                self._repo.marcar_estado_imagenes(t.uuid_local, EstadoImagenes.SUBIDAS)
            except ErrorSincronizacion as error:
                logger.warning(
                    "Fallo al subir imágenes (no crítico) para uuid_local=%s: %s",
                    t.uuid_local, error,
                )
                self._repo.marcar_estado_imagenes(t.uuid_local, EstadoImagenes.ERROR)

        try:
            self._cliente.generar_pdf(
                registro_id, t.colegio_nombre, self._config.dispositivo_id, t.email_padre
            )
        except ErrorSincronizacion as error:
            logger.warning(
                "Fallo al solicitar generación de PDF (no crítico) para "
                "uuid_local=%s: %s", t.uuid_local, error,
            )
