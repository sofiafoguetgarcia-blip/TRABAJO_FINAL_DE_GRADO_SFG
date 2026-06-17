# -*- coding: utf-8 -*-
"""
config.py
=========
Aqui van todos los parametros que usa el sistema. Si hay que cambiar
algo (una IP, una velocidad, un pin), se toca aqui y ya esta.

Nota importante sobre las coordenadas:
El JSON de vision ya da robot_x y robot_y en coordenadas del UR5e,
en milimetros. El modulo vision.py simplemente divide entre 1000
para pasar a metros.
"""

# -----------------------------------------------------------------------------
# IPs y puertos de los robots y el PC
# -----------------------------------------------------------------------------
UR3E_IP = "192.168.56.101"
UR5E_IP = "192.168.56.102"
PORT = 30002          # puerto estandar de URScript en robots Universal Robots
PC_IP = "192.168.56.2"

# Puertos que usa el PC para escuchar los avisos de los robots
PORT_UR5_LISTO_UR3 = 50001   # el UR5e avisa aqui cuando ha dejado la pieza
PORT_UR3_LISTO_UR5 = 50002   # el UR3e avisa aqui cuando ha terminado de dibujar
SYNC_MSG_LISTO = "LISTO"     # texto exacto que manda el robot al PC


# -----------------------------------------------------------------------------
# Poses de los robots
# -----------------------------------------------------------------------------

# Posicion de reposo del UR5e. Se va aqui antes y despues de cada movimiento.
UR5E_HOME_POSE = [0.54216, -0.32723, 0.38191, 3.066, -0.685, 0.0]

# Orientacion de la muneca para coger y dejar piezas.
# Se midio directamente sobre la tablet con el robot en posicion real.
# Coordenadas de referencia: [167.95, -394.41, Z, 2.979, -0.997, 0.0]
# Esta orientacion se usa siempre, sin importar el angulo que diga el JSON.
UR5E_PICK_ORIENTATION = [2.79604, -1.43234, 0.00003]

# Posicion de reposo del UR3e.
UR3E_HOME_POSE = [0.31875, -0.05563, 0.07194, 2.974, -1.013, 0.0]

# Zona compartida donde el UR5e deja la pieza para que el UR3e la dibuje.
# Como los robots estan en mesas distintas y enfrentados, el mismo punto fisico
# tiene coordenadas distintas segun quien lo mida.
DROP_ZONE_UR5E = [-0.04511, 0.51128, -0.0102, 1.9626, 2.482, 0.0]
DROP_ZONE_UR3E = [0.0573, 0.34812, -0.00126, 2.84, 1.344, 0.0]

# Punto alto sobre la zona compartida. Se usa para entrar y salir sin chocar.
UR5E_DROP_APPROACH_POSE = [-0.04511, 0.51128, 0.2987, 1.9626, 2.482, 0.0]


# -----------------------------------------------------------------------------
# Alturas de trabajo y umbral de fuerza para detectar superficie (UR5e)
# -----------------------------------------------------------------------------
Z_APROX_UR5 = 0.250      # altura a la que el robot se pone encima de la pieza antes de bajar
Z_SUBIDA_UR5 = 0.080     # cuanto sube el robot despues de coger o dejar la pieza
Z_PIEZA_OFFSET = 0.003   # margen que se deja por encima del punto de contacto real
F_UMBRAL_UR5 = 1.2       # fuerza en N a partir de la cual se considera que hay contacto


# -----------------------------------------------------------------------------
# Configuracion de la ventosa
# -----------------------------------------------------------------------------

# Mientras no este conectada la ventosa fisica, poner True para simular.
# Cuando este lista, cambiar a False y ajustar tipo y pin.
SIMULAR_VENTOSA = False

# Tipo de salida digital:
#   "DO_CONTROLADOR"  ->  set_digital_out(pin, estado)
#                         Salida del controlador (conector trasero del armario).
#   "TOOL_DO"         ->  set_tool_digital_out(pin, estado)
#                         Salida digital del conector de herramienta.
VENTOSA_TIPO_SALIDA = "DO_CONTROLADOR"

# Numero de pin segun el cableado:
#   DO_CONTROLADOR: de 0 a 7
#   TOOL_DO: 0 o 1 (solo hay dos salidas en el conector de muneca)
VENTOSA_DO_PIN = 0

# Tiempos de espera tras activar o desactivar la ventosa
VENTOSA_DELAY_ON = 0.4     # segundos que se espera para que haga vacio y agarre bien
VENTOSA_DELAY_OFF = 0.3    # segundos que se espera para liberar el vacio


# -----------------------------------------------------------------------------
# Velocidades y aceleraciones del UR5e
# -----------------------------------------------------------------------------
V_APROX = 0.080      # velocidad al acercarse a la pieza (m/s)
V_BAJA_UR5 = 0.008   # velocidad al bajar buscando la superficie
V_TRASLADO = 0.125   # velocidad al moverse entre puntos (sin pieza)
V_DEPOSITO = 0.008   # velocidad al depositar la pieza
A_LENTO = 0.030      # aceleracion para movimientos delicados
A_RAPIDO = 0.120     # aceleracion para movimientos rapidos
V_HOME = 0.8         # velocidad para ir al home
A_HOME = 0.030       # aceleracion para ir al home


# -----------------------------------------------------------------------------
# Velocidades y aceleraciones del UR3e (movimientos de dibujo)
# -----------------------------------------------------------------------------
V_BAJA_UR3 = 0.006   # velocidad al bajar buscando el papel
V_DIBUJO = 0.010     # velocidad mientras dibuja (lento para que quede bien)
V_SUBIDA = 0.020     # velocidad al levantar el lapiz entre trazos
A_DIBUJO = 0.004     # aceleracion durante el dibujo
Z_PAPEL = 0.0010     # margen que se deja sobre el papel una vez detectado el contacto
Z_SUBIDA = 0.025     # cuanto sube el lapiz entre tramo y tramo
F_UMBRAL_UR3 = 1.2   # fuerza en N para detectar el papel


# -----------------------------------------------------------------------------
# Escala del dibujo sobre la baldosa
# -----------------------------------------------------------------------------

# El dibujo ocupa esta fraccion del lado menor de la baldosa.
DRAWING_SCALE_ON_TILE = 0.75

# Limites de seguridad para el ancho del dibujo (en metros).
# Si el calculo por baldosa diera un valor fuera de este rango, se ajusta.
MAX_DRAWING_WIDTH_M = 0.115
MIN_DRAWING_WIDTH_M = 0.020


# -----------------------------------------------------------------------------
# Parametros para el procesado de imagen y extraccion de contornos
# -----------------------------------------------------------------------------
EPSILON_PX = 0.2        # tolerancia de aproximacion de contornos (cv2.approxPolyDP)
DECIMATE_STEP = 1      # se coge un punto de cada N para reducir la densidad
MIN_PUNTOS_CONTORNO = 3   # minimo de puntos para que un contorno sea valido
MIN_LONGITUD_PX =  2     # longitud minima de un contorno en pixeles
MAX_PUNTOS_TOTAL = 5000   # limite total de puntos entre todos los trazos

# Umbrales de Canny para detectar bordes finos y gruesos
CANNY_FINO_LOW = 30
CANNY_FINO_HIGH = 90
CANNY_GRUESO_LOW = 80
CANNY_GRUESO_HIGH = 160
