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

    Paso 1 - Preparamos el servidor para escuchar al UR5e (antes de mandarle nada)
    Paso 2 - Mandamos al UR5e el script para recoger la pieza y llevarla a la zona compartida
    Paso 3 - Esperamos a que el UR5e confirme que ha dejado la pieza
    Paso 4 - Preparamos el servidor para escuchar al UR3e
    Paso 5 - Mandamos al UR3e el script de dibujo
    Paso 6 - Esperamos a que el UR3e confirme que ha terminado de dibujar
    Paso 7 - Preparamos el servidor para escuchar al UR5e de nuevo
    Paso 8 - Mandamos al UR5e el script para devolver la pieza a su sitio
    Paso 9 - Esperamos a que el UR5e confirme que ha devuelto la pieza
    """
    log.info("PASO 1/9: preparando escucha para el aviso del UR5e")
    hilo5, err5 = _servidor_en_hilo(PORT_UR5_LISTO_UR3, "UR5e -> PC: baldosa en DROP_ZONE")
    time.sleep(1.0)

    log.info("PASO 2/9: enviando script de recogida al UR5e")
    enviar_script(ip_ur5e, port, script_ur5_recoger)

    log.info("PASO 3/9: esperando confirmacion del UR5e")
    hilo5.join()
    if err5:
        raise err5[0]

    log.info("PASO 4/9: preparando escucha para el aviso del UR3e")
    hilo3, err3 = _servidor_en_hilo(PORT_UR3_LISTO_UR5, "UR3e -> PC: dibujo terminado")
    time.sleep(1.0)

    log.info("PASO 5/9: enviando script de dibujo al UR3e")
    enviar_script(ip_ur3e, port, script_ur3_dibujar)

    log.info("PASO 6/9: esperando confirmacion del UR3e")
    hilo3.join()
    if err3:
        raise err3[0]

    log.info("PASO 7/9: preparando escucha para el aviso final del UR5e")
    hilo5_fin, err5_fin = _servidor_en_hilo(
        PORT_UR5_LISTO_UR3,
        "UR5e -> PC: baldosa devuelta al origen"
    )
    time.sleep(1.0)

    log.info("PASO 8/9: enviando script de devolucion al UR5e")
    enviar_script(ip_ur5e, port, script_ur5_devolver)

    log.info("PASO 9/9: esperando a que el UR5e termine de devolver la pieza")
    hilo5_fin.join()

    if err5_fin:
        raise err5_fin[0]

    log.info("Flujo completo terminado correctamente.")
