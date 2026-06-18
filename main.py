# -*- coding: utf-8 -*-
"""
main.py
=======
Punto de entrada del sistema UR5e + UR3e.

Lee un JSON generado por el sistema de vision artificial, procesa cada
baldosa y coordina los dos robots para que el UR5e recoja la pieza,
el UR3e dibuje encima y el UR5e la devuelva a su sitio.

Flujo completo para cada pieza:
  1. Lee las coordenadas y dimensiones del JSON.
  2. Calcula el tamano de dibujo en funcion del tamano real de esa baldosa.
  3. Preprocesa la imagen del dibujo y extrae los trazos.
  4. Genera los tres scripts URScript (recoger, dibujar, devolver).
  5. Si no es dry-run, los envia a los robots y espera que cada uno termine.

Uso rapido:
  python main.py                          # procesa todas las piezas
  python main.py --pieza 3               # solo la pieza numero 3
  python main.py --pieza 1 --dry-run     # genera scripts pero no envia nada
"""

import argparse
import logging
import sys
import json
import os
from typing import Any, Dict, List, Tuple

from config import (
    UR3E_IP,
    UR5E_IP,
    PORT,
)

from vision import cargar_deteccion_json
from image_processing import cargar_imagen, preprocesar_imagen, guardar_debug
from trajectory import extraer_trayectorias
from urscript_generator import (
    generar_script_ur5e_recoger,
    generar_script_ur3e_dibujar,
    generar_script_ur5e_devolver,
    guardar_script,
)
from drawing_scale import calcular_ancho_dibujo_por_baldosa, resumen_escala
from robot_comm import ejecutar_flujo_completo


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger(__name__)


# Rutas por defecto. Pueden ser sobreescritas por linea de comandos.
DEFAULT_DIBUJO = r"..\..\codigosPythonUR\imagenes\flor_simple.jpg"
DEFAULT_JSON = r"..\..\codigosPythonUR\dibujo_colab\v13\Robot\resultados\datos_robot.json"


def parse_args():
    p = argparse.ArgumentParser(
        description="Demo UR5e + UR3e usando JSON directo de vision"
    )

    p.add_argument("--dibujo", default=DEFAULT_DIBUJO,
                   help="Ruta a la imagen del dibujo que hara el UR3e")
    p.add_argument("--json", default=DEFAULT_JSON,
                   help="Ruta al JSON generado por vision artificial")
    p.add_argument(
        "--pieza",
        default=0,
        type=int,
        help="Numero de pieza a procesar. Con 0 se procesan todas."
    )
    p.add_argument("--ip3", default=UR3E_IP, help="IP del UR3e")
    p.add_argument("--ip5", default=UR5E_IP, help="IP del UR5e")
    p.add_argument("--port", default=PORT, type=int, help="Puerto URScript")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Genera los scripts pero no los envia a los robots"
    )
    p.add_argument("--debug-edges", default="debug_edges.png",
                   help="Ruta donde guardar la imagen de bordes para debug")

    return p.parse_args()


def cargar_json_vision(path_json: str) -> Dict[str, Any]:
    """Carga el JSON de vision una sola vez y valida que contenga piezas."""
    with open(path_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    piezas = data.get("piezas", [])
    if not piezas:
        raise ValueError("El JSON no contiene piezas.")

    return data


def seleccionar_piezas(piezas: List[Dict[str, Any]], pieza_arg: int) -> List[Dict[str, Any]]:
    """
    Filtra la lista de piezas segun lo indicado por linea de comandos.
    Si pieza_arg es 0, se procesan todas las piezas del JSON.
    """
    if pieza_arg == 0:
        return piezas

    seleccion = [p for p in piezas if int(p.get("numero", -1)) == int(pieza_arg)]
    if not seleccion:
        disponibles = [p.get("numero") for p in piezas]
        raise ValueError(f"No existe la pieza {pieza_arg}. Disponibles: {disponibles}")

    return seleccion


def cargar_y_preprocesar_dibujo(path_dibujo: str, path_debug_edges: str):
    """Carga la imagen del dibujo, extrae sus bordes y guarda la imagen de debug."""
    img = cargar_imagen(path_dibujo)
    edges = preprocesar_imagen(img)
    guardar_debug(edges, path_debug_edges)
    return img, edges


def generar_scripts_pieza(
    numero: int,
    x_baldosa_ur5: float,
    y_baldosa_ur5: float,
    angulo_baldosa: float,
    trayectorias,
) -> Tuple[str, str, str]:
    """Genera y guarda los tres scripts URScript de una pieza."""
    script_recoger = generar_script_ur5e_recoger(
        x_baldosa_ur5,
        y_baldosa_ur5,
        angulo_baldosa,
    )
    script_dibujar = generar_script_ur3e_dibujar(trayectorias)
    script_devolver = generar_script_ur5e_devolver(
        x_baldosa_ur5,
        y_baldosa_ur5,
    )

    os.makedirs("Resultados", exist_ok=True)

    guardar_script(
        script_recoger,
        os.path.join("Resultados", f"pieza_{numero}_ur5_recoger.urscript")
    )

    guardar_script(
        script_dibujar,
        os.path.join("Resultados", f"pieza_{numero}_ur3_dibujar.urscript")
    )

    guardar_script(
        script_devolver,
        os.path.join("Resultados", f"pieza_{numero}_ur5_devolver.urscript")
    )

    return script_recoger, script_dibujar, script_devolver


def procesar_pieza(pieza: Dict[str, Any], args, img, edges) -> None:
    """
    Procesa una pieza completa: lectura de datos, calculo de escala,
    extraccion de trayectorias, generacion de scripts y ejecucion opcional.
    """
    numero = int(pieza["numero"])

    log.info("")
    log.info("=" * 60)
    log.info(f"             PIEZA {numero}")
    log.info("=" * 60)

    det = cargar_deteccion_json(args.json, numero_pieza=numero)

    x_baldosa_ur5 = det.x_robot
    y_baldosa_ur5 = det.y_robot
    angulo_baldosa = det.angulo_deg

    log.warning(
        f"SE VA A ENVIAR AL UR5e EXACTAMENTE: "
        f"x={x_baldosa_ur5:.5f} m, y={y_baldosa_ur5:.5f} m"
    )

    ancho_mm = float(pieza.get("ancho_mm", 0))
    alto_mm = float(pieza.get("alto_mm", 0))
    ancho_dibujo_m = calcular_ancho_dibujo_por_baldosa(ancho_mm, alto_mm)

    log.info(
        f"Baldosa {numero}: {ancho_mm:.1f} x {alto_mm:.1f} mm "
        f"-> dibujo: {ancho_dibujo_m*1000:.1f} mm"
    )

    trayectorias = extraer_trayectorias(
        edges,
        img.shape,
        ancho_dibujo_m=ancho_dibujo_m,
    )

    script_recoger, script_dibujar, script_devolver = generar_scripts_pieza(
        numero=numero,
        x_baldosa_ur5=x_baldosa_ur5,
        y_baldosa_ur5=y_baldosa_ur5,
        angulo_baldosa=angulo_baldosa,
        trayectorias=trayectorias,
    )

    if args.dry_run:
        log.info(f"Dry-run pieza {numero}: scripts generados, no se envian")
        return

    ejecutar_flujo_completo(
        script_ur5_recoger=script_recoger,
        script_ur3_dibujar=script_dibujar,
        script_ur5_devolver=script_devolver,
        ip_ur5e=args.ip5,
        ip_ur3e=args.ip3,
        port=args.port,
    )

    log.info(f"PIEZA {numero} TERMINADA")


def main():
    args = parse_args()

    log.info("=" * 70)
    log.info(" DEMO UR5e + UR3e CON JSON DIRECTO ")
    log.info("=" * 70)

    try:
        datos_json = cargar_json_vision(args.json)
        todas_las_piezas = datos_json["piezas"]
        piezas_a_procesar = seleccionar_piezas(todas_las_piezas, args.pieza)
    except Exception as e:
        log.error(f"Error leyendo JSON: {e}")
        sys.exit(1)

    log.info(resumen_escala(todas_las_piezas))
    log.info(f"Piezas a procesar: {[p.get('numero') for p in piezas_a_procesar]}")

    try:
        img, edges = cargar_y_preprocesar_dibujo(args.dibujo, args.debug_edges)
    except Exception as e:
        log.error(f"Error procesando dibujo: {e}")
        sys.exit(1)

    for pieza in piezas_a_procesar:
        try:
            procesar_pieza(pieza, args, img, edges)
        except Exception as e:
            log.error(f"Error en pieza {pieza}: {e}")
            continue  # si falla una pieza, intentamos con la siguiente

    log.info("")
    log.info("PROCESO TERMINADO")


if __name__ == "__main__":
    main()
