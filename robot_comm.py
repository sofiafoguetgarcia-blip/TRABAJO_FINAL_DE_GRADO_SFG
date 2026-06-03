# -*- coding: utf-8 -*-
"""
robot_comm.py
=============
Se encarga de toda la comunicacion entre el PC y los dos robots.

Hay dos tipos de comunicacion:
- PC -> Robot: el PC abre un socket y le manda el script URScript.
- Robot -> PC: el robot abre un socket y le manda el mensaje "LISTO"
  cuando ha terminado su parte. El PC escucha en un puerto fijo.

La sincronizacion entre los dos robots se hace a traves del PC:
el UR5e avisa al PC cuando ha dejado la pieza, el PC se entera y
entonces le manda el script al UR3e para que empiece a dibujar.
"""

import logging
import socket
import threading
import time

from config import PORT_UR5_LISTO_UR3, PORT_UR3_LISTO_UR5, SYNC_MSG_LISTO

log = logging.getLogger(__name__)


def enviar_script(ip: str, port: int, script: str, timeout: float = 10.0, pausa: float = 2.0) -> None:
    """
    Abre una conexion TCP con el robot, le manda el script y cierra.
    La pausa al final da tiempo al robot para procesar el mensaje antes
    de que el programa continúe.
    """
    log.info(f"Conectando a {ip}:{port}...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((ip, port))
        except OSError as e:
            raise ConnectionError(f"No se pudo conectar con {ip}:{port}. Error: {e}")
        s.sendall((script + "\n").encode("utf-8"))
        log.info(f"Script enviado a {ip} ({len(script)} caracteres)")
        time.sleep(pausa)


def esperar_mensaje(puerto: int, esperado: str = SYNC_MSG_LISTO, timeout: float = 1200.0, descripcion: str = "") -> None:
    """
    El PC se pone a escuchar en el puerto indicado hasta que llega
    un mensaje del robot. Si el mensaje no es el esperado o se agota
    el tiempo de espera, se lanza un error.

    El timeout es de 20 minutos por defecto para dar margen suficiente
    aunque el robot tarde en terminar su movimiento.
    """
    desc = descripcion or f"puerto {puerto}"
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", puerto))
    srv.listen(1)
    srv.settimeout(timeout)
    log.info(f"PC escuchando en {puerto}: {desc}")

    try:
        conn, addr = srv.accept()
    except socket.timeout:
        srv.close()
        raise TimeoutError(f"Timeout esperando {esperado} en {desc}")

    data = conn.recv(1024).decode("utf-8", errors="ignore").strip()
    conn.close()
    srv.close()
    log.info(f"Mensaje recibido desde {addr}: {data}")

    if esperado not in data:
        raise ConnectionError(f"Mensaje inesperado en {desc}. Esperado={esperado}, recibido={data}")


def _servidor_en_hilo(puerto: int, descripcion: str):
    """
    Arranca el servidor de escucha en un hilo separado para que el programa
    principal no se quede bloqueado esperando. Asi podemos enviar el script
    al robot y al mismo tiempo estar listos para recibir su respuesta.

    Devuelve el hilo y una lista donde se guardaran los errores si los hay.
    """
    errores = []

    def worker():
        try:
            esperar_mensaje(puerto, SYNC_MSG_LISTO, descripcion=descripcion)
        except Exception as e:
            errores.append(e)

    hilo = threading.Thread(target=worker, daemon=True)
    hilo.start()
    return hilo, errores


def _enviar_y_esperar_confirmacion(
    puerto_escucha: int,
    descripcion_escucha: str,
    ip_robot: str,
    puerto_robot: int,
    script: str,
    descripcion_envio: str,
) -> None:
    """
    Prepara la escucha del PC, envia un script al robot y espera su confirmacion.
    Este patron se repite en las tres fases del flujo completo.
    """
    log.info(f"Preparando escucha: {descripcion_escucha}")
    hilo, errores = _servidor_en_hilo(puerto_escucha, descripcion_escucha)
    time.sleep(1.0)

    log.info(f"Enviando script: {descripcion_envio}")
    enviar_script(ip_robot, puerto_robot, script)

    log.info(f"Esperando confirmacion: {descripcion_escucha}")
    hilo.join()
    if errores:
        raise errores[0]


def ejecutar_flujo_completo(
    script_ur5_recoger: str,
    script_ur3_dibujar: str,
    script_ur5_devolver: str,
    ip_ur5e: str,
    ip_ur3e: str,
    port: int
) -> None:
    """
    Ejecuta el ciclo completo de una pieza coordinando los dos robots.

    El orden es importante para que los robots no choquen ni actuen
    sobre la pieza al mismo tiempo:

    1. El UR5e recoge la pieza y la lleva a la zona compartida.
    2. El UR3e dibuja sobre la pieza.
    3. El UR5e devuelve la pieza a su posicion original.
    """
    log.info("FASE 1/3: UR5e recoge la baldosa y la deja en DROP_ZONE")
    _enviar_y_esperar_confirmacion(
        puerto_escucha=PORT_UR5_LISTO_UR3,
        descripcion_escucha="UR5e -> PC: baldosa en DROP_ZONE",
        ip_robot=ip_ur5e,
        puerto_robot=port,
        script=script_ur5_recoger,
        descripcion_envio="recogida UR5e",
    )

    log.info("FASE 2/3: UR3e dibuja sobre la baldosa")
    _enviar_y_esperar_confirmacion(
        puerto_escucha=PORT_UR3_LISTO_UR5,
        descripcion_escucha="UR3e -> PC: dibujo terminado",
        ip_robot=ip_ur3e,
        puerto_robot=port,
        script=script_ur3_dibujar,
        descripcion_envio="dibujo UR3e",
    )

    log.info("FASE 3/3: UR5e devuelve la baldosa al origen")
    _enviar_y_esperar_confirmacion(
        puerto_escucha=PORT_UR5_LISTO_UR3,
        descripcion_escucha="UR5e -> PC: baldosa devuelta al origen",
        ip_robot=ip_ur5e,
        puerto_robot=port,
        script=script_ur5_devolver,
        descripcion_envio="devolucion UR5e",
    )

    log.info("Flujo completo terminado correctamente.")
