#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[MEDIDO] Diagnóstico y optimización de velocidad de una platina piezoelectrica E-545
Versión CORREGIDA para macOS arm64 + pipython

COPIA ESTE ARCHIVO A: ~/Desktop/LABORATORIO 7/diagnostico_CORREGIDO.py
REEMPLAZA el anterior si tiene errores de sintaxis
"""

import json
import time
from datetime import datetime
import os
import sys

# [MEDIDO] Configurar librerías PI antes de importar pipython
lib_path = os.path.expanduser("~/.pi_libs")
if os.path.exists(lib_path):
    os.environ['DYLD_LIBRARY_PATH'] = lib_path
    sys.path.insert(0, lib_path)

from pipython import GCSDevice, GCSError


# ============================================================================
# 0. Documentacion de parametros y comandos relevantes
# ============================================================================

PARAMETROS_INFO = {
    "CSV?": {
        "nombre": "Version de sintaxis GCS",
        "descripcion": (
            "Version del PI General Command Set que interpreta el modulo "
            "E-517. Debe ser 2.0 para el E-545."
        ),
        "valores_posibles": "2.0 (esperado) / 1.0 (sintaxis antigua E-516, no aplica)",
    },
    "ONL": {
        "nombre": "Modo de control del canal (ONLINE / OFFLINE)",
        "descripcion": (
            "Determina si el E-517 controla el canal o espera voltaje analogico externo."
        ),
        "valores_posibles": "0 = OFFLINE, 1 = ONLINE (requerido para control remoto)",
    },
    "SVO": {
        "nombre": "Estado del servo (lazo abierto / lazo cerrado)",
        "descripcion": (
            "Activa el lazo P-I analogico. SVO=1 usa posicion en um; SVO=0 usa voltaje directo."
        ),
        "valores_posibles": "0 = lazo abierto, 1 = lazo cerrado",
    },
    "VCO": {
        "nombre": "Modo de control por velocidad",
        "descripcion": "Activa rampa de velocidad controlada (perfil trapezoidal).",
        "valores_posibles": "0 = maxima velocidad, 1 = limitada por VEL",
    },
    "VEL": {
        "nombre": "Velocidad de la rampa",
        "descripcion": "Velocidad en um/s para movimientos con VCO=1.",
        "valores_posibles": "Numero real positivo (um/s)",
    },
    "POS?": {
        "nombre": "Posicion real del eje",
        "descripcion": "Posicion actual medida por el sensor, en micrometros.",
        "valores_posibles": "Numero real dentro del rango de viaje",
    },
}


# ============================================================================
# 1. Funciones auxiliares de conexión y manejo de errores
# ============================================================================

def _comando_crudo(pidevice, comando, etiqueta=""):
    """
    [MEDIDO] Ejecuta comando GCS crudo y retorna respuesta.
    etiqueta: identificador para trazabilidad en logs.
    """
    try:
        respuesta = pidevice.read(comando)
        if etiqueta:
            print(f"  ✓ {etiqueta}: {respuesta.strip()}")
        return respuesta
    except GCSError as e:
        print(f"  ✗ {etiqueta}: GCSError {e}")
        return None
    except Exception as e:
        print(f"  ✗ {etiqueta}: {type(e).__name__} {e}")
        return None


def _seguro(func, *args, etiqueta="", **kwargs):
    """
    [MEDIDO] Ejecuta función con manejo de excepciones.
    Retorna resultado o None si hay error.
    """
    try:
        result = func(*args, **kwargs)
        if etiqueta and result is not None:
            print(f"  ✓ {etiqueta}: {result}")
        return result
    except GCSError as e:
        if etiqueta:
            print(f"  ✗ {etiqueta}: GCSError {e}")
        return None
    except Exception as e:
        if etiqueta:
            print(f"  ✗ {etiqueta}: {type(e).__name__} {e}")
        return None


def conectar(metodo, **kwargs):
    """
    [MEDIDO] Conecta al E-545 por USB, TCPIP o RS232.
    
    Argumentos:
        metodo: "usb", "tcpip", o "rs232"
        **kwargs: parámetros específicos del método
            - USB: serialnum="" (opcional, si hay un solo dispositivo)
            - TCPIP: ipaddress="192.168.1.10", ipport=50000 (default)
            - RS232: comport=3, baudrate=115200
    
    Ejemplos:
        pidevice = conectar("usb")
        pidevice = conectar("tcpip", ipaddress="192.168.168.10")
        pidevice = conectar("rs232", comport=3, baudrate=115200)
    """
    pidevice = GCSDevice()
    
    try:
        if metodo == "usb":
            serialnum = kwargs.get("serialnum", "")
            pidevice.ConnectUSB(serialnum=serialnum)
            print(f"✓ Conectado por USB (serial: {serialnum if serialnum else 'automático'})")
            
        elif metodo == "tcpip":
            ipaddress = kwargs["ipaddress"]
            ipport = kwargs.get("ipport", 50000)
            pidevice.ConnectTCPIP(ipaddress=ipaddress, ipport=ipport)
            print(f"✓ Conectado por TCPIP ({ipaddress}:{ipport})")
            
        elif metodo == "rs232":
            comport = kwargs["comport"]
            baudrate = kwargs.get("baudrate", 115200)
            pidevice.ConnectRS232(comport=comport, baudrate=baudrate)
            print(f"✓ Conectado por RS232 (puerto {comport}, {baudrate} baud)")
            
        else:
            raise ValueError(f"Método desconocido: {metodo}")
            
        return pidevice
        
    except Exception as e:
        print(f"✗ Error de conexión: {type(e).__name__}: {e}")
        raise


# ============================================================================
# 2. Diagnóstico de estado
# ============================================================================

def diagnosticar_estado(pidevice):
    """
    [MEDIDO] Realiza diagnóstico completo del E-545.
    Retorna diccionario con estado de todos los parámetros.
    """
    print("\n" + "="*70)
    print("DIAGNÓSTICO DE ESTADO DEL E-545")
    print("="*70)
    
    datos = {
        "timestamp": datetime.now().isoformat(),
        "ejes": {},
    }
    
    # Versión de sintaxis GCS
    csv = _seguro(_comando_crudo, pidevice, "CSV?\n", etiqueta="CSV? (versión GCS)")
    datos["csv"] = csv.strip() if csv else None
    
    # Obtener ejes disponibles
    ejes = _seguro(lambda: list(pidevice.axes), etiqueta="Ejes disponibles") or ["A", "B", "C"]
    
    for eje in ejes:
        print(f"\n--- Eje {eje} ---")
        estado_eje = {}
        
        # Estado ON/OFF
        online = _seguro(lambda: _comando_crudo(pidevice, f"ONL? {eje}\n"), etiqueta=f"ONL? {eje}")
        estado_eje["online"] = online.strip() if online else None
        
        # Servo ON/OFF
        svo = _seguro(lambda: _comando_crudo(pidevice, f"SVO? {eje}\n"), etiqueta=f"SVO? {eje}")
        estado_eje["servo"] = svo.strip() if svo else None
        
        # Velocidad controlada
        vco = _seguro(lambda: _comando_crudo(pidevice, f"VCO? {eje}\n"), etiqueta=f"VCO? {eje}")
        estado_eje["vco"] = vco.strip() if vco else None
        
        # Velocidad
        vel = _seguro(lambda: _comando_crudo(pidevice, f"VEL? {eje}\n"), etiqueta=f"VEL? {eje}")
        estado_eje["vel"] = vel.strip() if vel else None
        
        # Posición actual
        pos = _seguro(pidevice.qPOS, eje, etiqueta=f"POS? {eje}")
        estado_eje["pos"] = pos
        
        # En objetivo
        ont = _seguro(pidevice.qONT, eje, etiqueta=f"ONT? {eje}")
        estado_eje["ont"] = ont
        
        datos["ejes"][eje] = estado_eje
    
    return datos


def mostrar_diagnostico(datos):
    """[MEDIDO] Imprime diagnóstico en formato legible."""
    print("\n" + "="*70)
    print("RESUMEN DEL DIAGNÓSTICO")
    print("="*70)
    
    print(f"\nFecha: {datos.get('timestamp')}")
    print(f"Versión GCS: {datos.get('csv', 'N/A')}")
    
    for eje, estado in datos.get("ejes", {}).items():
        print(f"\nEje {eje}:")
        for param, valor in estado.items():
            print(f"  {param:15s}: {valor}")


def mostrar_documentacion_parametros():
    """[MEDIDO] Imprime referencia de parámetros disponibles."""
    print("\n" + "="*70)
    print("REFERENCIA DE PARÁMETROS E COMANDOS GCS 2.0")
    print("="*70)
    
    for param, info in PARAMETROS_INFO.items():
        print(f"\n{param}: {info['nombre']}")
        print(f"  {info['descripcion']}")
        print(f"  Valores: {info['valores_posibles']}")


def respaldar_parametros(pidevice, archivo_salida):
    """[MEDIDO] Guarda estado actual de parámetros en JSON."""
    datos = diagnosticar_estado(pidevice)
    
    try:
        with open(archivo_salida, 'w') as f:
            json.dump(datos, f, indent=2)
        print(f"\n✓ Respaldo guardado: {archivo_salida}")
    except Exception as e:
        print(f"✗ Error al guardar respaldo: {e}")


# ============================================================================
# 3. Optimización de velocidad
# ============================================================================

def optimizar_velocidad(pidevice, modo="maxima", velocidad_um_s=None, ejes=None):
    """
    [MEDIDO] Configura parámetros para máxima velocidad o velocidad controlada.
    
    Argumentos:
        modo: "maxima" o "controlada"
        velocidad_um_s: requerido si modo="controlada"
        ejes: lista de ejes (default: ["A", "B", "C"])
    """
    if ejes is None:
        ejes = _seguro(lambda: list(pidevice.axes), etiqueta="qSAI") or ["A", "B", "C"]

    if modo not in ("maxima", "controlada"):
        raise ValueError("modo debe ser 'maxima' o 'controlada'")
    if modo == "controlada" and not velocidad_um_s:
        raise ValueError("modo 'controlada' requiere indicar velocidad_um_s")

    # 1) Canales físicos en ONLINE
    for canal in range(1, len(ejes) + 1):
        _seguro(
            _comando_crudo,
            pidevice,
            f"ONL {canal} 1\n",
            etiqueta=f"ONL {canal} 1",
        )

    for eje in ejes:
        # 2) Lazo cerrado
        _seguro(pidevice.SVO, eje, True, etiqueta=f"SVO {eje} 1")

        # 3) Compensación de deriva
        _seguro(_comando_crudo, pidevice, f"DCO {eje} 1\n", etiqueta=f"DCO {eje} 1")

        if modo == "maxima":
            _seguro(_comando_crudo, pidevice, f"VCO {eje} 0\n", etiqueta=f"VCO {eje} 0")
        else:
            _seguro(_comando_crudo, pidevice, f"VCO {eje} 1\n", etiqueta=f"VCO {eje} 1")
            _seguro(
                pidevice.VEL, eje, velocidad_um_s, etiqueta=f"VEL {eje} {velocidad_um_s}"
            )

    print(f"\n✓ Configuración aplicada (modo='{modo}')")


def probar_tiempo_de_movimiento(
    pidevice, eje, posicion_destino_um, timeout_s=2.0, intervalo_sondeo_s=0.002
):
    """[MEDIDO] Mueve el eje y mide tiempo hasta 'en objetivo'."""
    inicio = time.perf_counter()
    _seguro(pidevice.MOV, eje, posicion_destino_um, etiqueta=f"MOV {eje} {posicion_destino_um}")

    while (time.perf_counter() - inicio) < timeout_s:
        en_objetivo = _seguro(pidevice.qONT, eje, etiqueta=f"ONT? {eje}")
        if isinstance(en_objetivo, dict):
            en_objetivo = en_objetivo.get(eje)
        if en_objetivo in (True, "1", 1):
            transcurrido = time.perf_counter() - inicio
            posicion_final = _seguro(pidevice.qPOS, eje, etiqueta=f"POS? {eje}")
            print(
                f"\n✓ Eje {eje}: llegó a objetivo en {transcurrido * 1000:.1f} ms "
                f"(posición final: {posicion_final})"
            )
            return transcurrido
        time.sleep(intervalo_sondeo_s)

    print(f"\n✗ Eje {eje}: timeout sin alcanzar objetivo en {timeout_s} s")
    return None


# ============================================================================
# 7. FLUJO PRINCIPAL
# ============================================================================

if __name__ == "__main__":
    pidevice = None
    
    try:
        print("\n[INICIO] Conectando al E-545...")
        pidevice = conectar("usb")
        
        print("\n[PASO 1] Mostrando documentación de parámetros...")
        mostrar_documentacion_parametros()

        print("\n[PASO 2] Diagnóstico inicial...")
        datos = diagnosticar_estado(pidevice)
        mostrar_diagnostico(datos)

        print("\n[PASO 3] Respaldando parámetros...")
        respaldar_parametros(pidevice, "respaldo_e545.json")

        # Descomentar si deseas optimizar velocidad:
        #
        # print("\n[PASO 4] Optimizando velocidad...")
        # optimizar_velocidad(pidevice, modo="maxima")
        # datos_post = diagnosticar_estado(pidevice)
        # mostrar_diagnostico(datos_post)
        #
        # print("\n[PASO 5] Probando tiempos de movimiento...")
        # for eje in datos["ejes"]:
        #     probar_tiempo_de_movimiento(pidevice, eje, 50)
        #     probar_tiempo_de_movimiento(pidevice, eje, 100)

        print("\n[ÉXITO] Diagnóstico completado")

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if pidevice is not None:
            try:
                pidevice.CloseConnection()
                print("\n[LISTO] Conexión cerrada")
            except Exception as e:
                print(f"\n[ADVERTENCIA] Error al cerrar: {e}")
