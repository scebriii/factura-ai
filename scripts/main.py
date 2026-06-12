# =============================================================================
# PROYECTO 1: API de Extracción de Facturas
# =============================================================================
# Este script crea un servidor web que:
#   1. Recibe un PDF de factura por HTTP
#   2. Extrae el texto del PDF
#   3. Envía el texto a OpenAI para que identifique los datos clave
#   4. Devuelve un JSON estructurado con proveedor, importe, fecha, etc.
#
# Es el equivalente a tu pipeline de n8n, pero en Python puro.
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 1: IMPORTACIONES
# ─────────────────────────────────────────────────────────────────────────────
# En Python, "import" es como conectar un nodo externo en n8n.
# Cada librería nos da una capacidad específica.

import os                      # Para leer variables de entorno (como la API key)
import json                    # Para convertir texto JSON ↔ diccionarios Python
import sqlite3                 # Base de datos incluida en Python (no necesita instalacion)
from datetime import datetime  # Para registrar la fecha/hora de procesamiento
import fitz                    # PyMuPDF: lee PDFs y extrae su texto
from io import BytesIO         # Para manejar el PDF en memoria (sin guardarlo a disco)

from pathlib import Path         # Para manejar rutas de archivos de forma limpia

from fastapi import FastAPI, UploadFile, HTTPException, Header, Depends
# FastAPI = el framework web (crea endpoints como los webhooks de n8n)
# UploadFile = tipo especial para archivos subidos
# HTTPException = para devolver errores HTTP con codigo y mensaje
# Header = para leer headers de la peticion (donde viene la API key)
# Depends = para inyectar dependencias (funciones que se ejecutan antes del endpoint)

from fastapi.staticfiles import StaticFiles     # Para servir archivos HTML/CSS/JS
from fastapi.responses import FileResponse       # Para devolver archivos como respuesta

from dotenv import load_dotenv  # Carga las variables del archivo .env
from openai import OpenAI, RateLimitError, APITimeoutError, APIConnectionError


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 2: CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────
# Cargamos la API key y preparamos el cliente de OpenAI.
# Equivale al nodo "Credentials" en n8n.

load_dotenv()  # Lee el archivo .env y carga OPENAI_API_KEY al entorno

cliente_openai = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")  # os.getenv() lee una variable de entorno
)

# Clave para proteger la API (la que pusiste en .env)
API_KEY_APP = os.getenv("API_KEY_APP", "mi-clave-secreta-123")

# Creamos la aplicacion FastAPI (equivale a activar el webhook en n8n)
app = FastAPI(
    title="API Extraccion de Facturas",
    description="Recibe un PDF, extrae datos con OpenAI, devuelve JSON estructurado.",
    version="1.1.0"
)

# Ruta a la carpeta del frontend (HTML, CSS, JS)
RUTA_FRONTEND = Path(__file__).parent.parent / "frontend"

# Montar archivos estaticos: todo lo que haya en frontend/ se sirve en /static/
# Esto permite que el HTML cargue el CSS y JS con rutas como /static/styles.css
app.mount("/static", StaticFiles(directory=str(RUTA_FRONTEND)), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 2.1: AUTENTICACION
# ─────────────────────────────────────────────────────────────────────────────
# Esta funcion verifica que quien llama a la API tenga la clave correcta.
# Se envia en el header "X-API-Key" de cada peticion.
# En n8n seria como configurar "Header Auth" en un webhook.
#
# "Depends" es el patron de "dependencias" de FastAPI:
# le dices a un endpoint "antes de ejecutarte, ejecuta esta funcion".
# Si la funcion lanza un error, el endpoint ni se ejecuta.

async def verificar_api_key(x_api_key: str = Header(default=None)):
    """Verifica que la peticion incluya una API key valida."""
    if x_api_key is None or x_api_key != API_KEY_APP:
        raise HTTPException(
            status_code=401,
            detail="API Key invalida o no proporcionada. Envia el header X-API-Key."
        )


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 2.5: BASE DE DATOS (SQLite)
# ─────────────────────────────────────────────────────────────────────────────
# SQLite es una base de datos que vive en UN SOLO ARCHIVO (.db).
# No necesitas instalar nada, viene con Python.
# Piensa en ella como una hoja de Excel guardada en tu carpeta,
# pero que puedes consultar con codigo.
#
# En n8n seria como el nodo "Google Sheets" o "Airtable" donde guardas datos.

# Ruta donde se guardara el archivo de la base de datos
RUTA_BD = os.path.join(os.path.dirname(__file__), "..", "facturas.db")

def inicializar_bd():
    """
    Crea la tabla de facturas si no existe.
    Se ejecuta una sola vez al arrancar el servidor.
    """
    # sqlite3.connect() abre (o crea) el archivo .db
    conexion = sqlite3.connect(RUTA_BD)
    
    # Un "cursor" es lo que ejecuta comandos SQL en la base de datos
    cursor = conexion.cursor()
    
    # CREATE TABLE IF NOT EXISTS = crea la tabla solo si no existe ya
    # Cada linea define una columna: nombre, tipo de dato
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            archivo_original TEXT,
            proveedor TEXT,
            cif_nif TEXT,
            numero_factura TEXT,
            fecha_factura TEXT,
            importe_total REAL,
            moneda TEXT,
            conceptos TEXT,
            procesado_en TEXT
        )
    """)
    
    conexion.commit()  # Guarda los cambios
    conexion.close()   # Cierra la conexion

# Ejecutamos la inicializacion al importar el modulo
inicializar_bd()


def guardar_factura(nombre_archivo: str, datos: dict) -> int:
    """
    Guarda los datos extraidos de una factura en la base de datos.
    
    Args:
        nombre_archivo: Nombre del PDF original.
        datos: Diccionario con los datos extraidos por OpenAI.
        
    Returns:
        El ID de la factura guardada.
    """
    conexion = sqlite3.connect(RUTA_BD)
    cursor = conexion.cursor()
    
    # INSERT INTO = meter una fila nueva en la tabla
    # Los ? son "placeholders" que se rellenan con la tupla de valores
    # Esto previene inyeccion SQL (un tipo de ataque)
    cursor.execute("""
        INSERT INTO facturas 
        (archivo_original, proveedor, cif_nif, numero_factura, 
         fecha_factura, importe_total, moneda, conceptos, procesado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        nombre_archivo,
        datos.get("proveedor"),           # .get() busca la clave, devuelve None si no existe
        datos.get("cif_nif"),
        datos.get("numero_factura"),
        datos.get("fecha"),
        datos.get("importe_total"),
        datos.get("moneda"),
        json.dumps(datos.get("conceptos", []), ensure_ascii=False),  # Lista -> string JSON
        datetime.now().isoformat()        # Fecha/hora actual en formato ISO
    ))
    
    id_factura = cursor.lastrowid  # El ID autoincremental que SQLite le asigno
    conexion.commit()
    conexion.close()
    
    return id_factura


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 3: FUNCIÓN — Extraer texto del PDF
# ─────────────────────────────────────────────────────────────────────────────
# Esta función recibe los bytes crudos del PDF y devuelve todo su texto.
# En n8n esto sería un nodo "Extract from File" o "Read PDF".
#
# ¿Por qué una función separada? Para que el código sea modular.
# Si mañana quieres cambiar la librería de PDFs, solo tocas aquí.

def extraer_texto_pdf(contenido_pdf: bytes) -> str:
    """
    Recibe los bytes de un archivo PDF y devuelve el texto extraído.
    
    Args:
        contenido_pdf: Los bytes crudos del archivo PDF.
        
    Returns:
        El texto completo del PDF como un string.
        
    Raises:
        ValueError: Si el PDF no contiene texto extraíble.
    """
    # Abrimos el PDF desde memoria (BytesIO simula un archivo en RAM)
    documento = fitz.open(stream=BytesIO(contenido_pdf), filetype="pdf")
    
    texto_completo = ""
    
    # Recorremos cada página del PDF
    # "for pagina in documento" es un bucle: ejecuta el bloque para cada página
    for pagina in documento:
        texto_completo += pagina.get_text()  # Extrae el texto de esa página
    
    documento.close()  # Cerramos el documento (buena práctica, libera memoria)
    
    # Validación: si el PDF era una imagen escaneada, no habrá texto
    if not texto_completo.strip():  # .strip() elimina espacios en blanco
        raise ValueError(
            "El PDF no contiene texto extraíble. "
            "Puede ser un documento escaneado (imagen)."
        )
    
    return texto_completo


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 4: FUNCIÓN — Analizar factura con OpenAI
# ─────────────────────────────────────────────────────────────────────────────
# Esta función envía el texto de la factura a GPT y le pide que extraiga
# los datos clave en formato JSON.
# En n8n esto sería tu nodo "OpenAI" con el prompt y la configuración.

def analizar_factura_con_openai(texto_factura: str) -> dict:
    """
    Envía el texto de una factura a OpenAI y devuelve los datos extraídos.
    
    Args:
        texto_factura: El texto plano extraído del PDF.
        
    Returns:
        Un diccionario con los datos estructurados de la factura.
    """
    # Truncamos a 4000 caracteres por seguridad (evita exceder contexto)
    texto_truncado = texto_factura[:4000]
    
    # El prompt es CLAVE: le decimos a GPT exactamente qué queremos.
    # Fíjate en la estructura: primero el ROL (system), luego el PEDIDO (user).
    # Esto es idéntico a cómo configuras el prompt en tu nodo de n8n.
    prompt_sistema = """Eres un asistente experto en contabilidad y análisis de facturas.
Tu tarea es extraer datos estructurados de facturas.
SIEMPRE responde en formato JSON válido con esta estructura exacta:
{
    "proveedor": "nombre del proveedor o emisor",
    "cif_nif": "CIF o NIF del proveedor",
    "numero_factura": "número o código de la factura",
    "fecha": "fecha en formato YYYY-MM-DD",
    "importe_total": número decimal sin símbolo de moneda,
    "moneda": "código de moneda (EUR, USD, etc.)",
    "conceptos": ["lista", "de", "conceptos o servicios facturados"]
}
Si no encuentras algún campo, usa null."""

    prompt_usuario = f"Analiza esta factura y extrae los datos:\n\n{texto_truncado}"
    # f"..." es un f-string: permite meter variables dentro del texto con {variable}

    # Llamada a la API de OpenAI
    # Esto es equivalente al nodo "OpenAI Chat" en n8n
    try:
        respuesta = cliente_openai.chat.completions.create(
            model="gpt-4o-mini",                        # Modelo a usar (rápido y barato)
            messages=[
                {"role": "system", "content": prompt_sistema},  # Instrucción de rol
                {"role": "user", "content": prompt_usuario}      # El texto de la factura
            ],
            response_format={"type": "json_object"},     # Fuerza respuesta en JSON
            temperature=0.1,                             # Baja creatividad = más preciso
            timeout=30.0                                 # Máximo 30s de espera
        )
    except RateLimitError:
        raise ValueError("Límite de peticiones de OpenAI alcanzado. Espera unos segundos e inténtalo de nuevo.")
    except APITimeoutError:
        raise ValueError("OpenAI tardó demasiado en responder (>30s). Inténtalo de nuevo.")
    except APIConnectionError:
        raise ValueError("No se pudo conectar con OpenAI. Verifica tu conexión a Internet.")

    # Extraemos el texto de la respuesta y lo convertimos a diccionario Python
    # respuesta.choices[0].message.content es el texto que devolvió GPT
    texto_json = respuesta.choices[0].message.content
    datos = json.loads(texto_json)  # json.loads() convierte string JSON → diccionario

    return datos


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 5: ENDPOINT — POST /extraer-factura
# ─────────────────────────────────────────────────────────────────────────────
# Este es el "webhook" de tu API: el punto de entrada donde llegan las facturas.
# @app.post() dice: "cuando alguien haga POST a /extraer-factura, ejecuta esto".
# Es exactamente como configurar un Webhook Trigger en n8n.

@app.post("/extraer-factura", dependencies=[Depends(verificar_api_key)])
async def extraer_factura(archivo: UploadFile):
    """
    Endpoint principal. Recibe un PDF y devuelve los datos extraídos.
    
    - **archivo**: El PDF de la factura (enviado como form-data).
    """
    
    # --- Paso 1: Validar que sea un PDF ---
    # En n8n harías esto con un nodo IF para filtrar archivos no válidos
    if not archivo.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,  # 400 = Bad Request
            detail="Solo se aceptan archivos PDF."
        )
    
    # --- Paso 2: Leer los bytes del archivo ---
    # await = "espera a que termine" (necesario porque leer archivos es asíncrono)
    contenido = await archivo.read()
    
    # --- Paso 3: Extraer texto del PDF ---
    # try/except es el manejo de errores de Python.
    # Si algo falla dentro de "try", salta a "except" en vez de crashear.
    try:
        texto = extraer_texto_pdf(contenido)
    except ValueError as error:
        # Si el PDF no tiene texto, devolvemos error 422
        raise HTTPException(status_code=422, detail=str(error))
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar el PDF: {str(error)}"
        )
    
    # --- Paso 4: Analizar con OpenAI ---
    try:
        datos_factura = analizar_factura_con_openai(texto)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error al analizar con OpenAI: {str(error)}"
        )
    
    # --- Paso 5: Guardar en base de datos ---
    # Guardamos los datos extraidos para tener un historial
    # En n8n esto seria un nodo "Insert Row" hacia Google Sheets o Airtable
    try:
        id_factura = guardar_factura(archivo.filename, datos_factura)
    except Exception as error:
        # Si falla el guardado, aun devolvemos los datos (no es critico)
        id_factura = None
    
    # --- Paso 6: Devolver JSON estructurado ---
    # Esto es lo que recibe quien llamo al endpoint.
    # Equivale al nodo "Respond to Webhook" en n8n.
    return {
        "exito": True,
        "id_factura": id_factura,
        "archivo_original": archivo.filename,
        "datos": datos_factura
    }


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 6: ENDPOINT — GET /facturas (NUEVO)
# ─────────────────────────────────────────────────────────────────────────────
# Este endpoint devuelve el historial de todas las facturas procesadas.
# Es como consultar tu hoja de Google Sheets desde n8n.
# No recibe nada, solo devuelve la lista.

@app.get("/facturas", dependencies=[Depends(verificar_api_key)])
def listar_facturas():
    """Devuelve el historial de todas las facturas procesadas."""
    conexion = sqlite3.connect(RUTA_BD)
    
    # row_factory = sqlite3.Row hace que cada fila sea un diccionario
    # en vez de una tupla. Asi podemos acceder por nombre de columna.
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()
    
    # SELECT * = dame todas las columnas, ORDER BY = ordena por ID descendente
    cursor.execute("SELECT * FROM facturas ORDER BY id DESC")
    filas = cursor.fetchall()  # fetchall() = dame TODAS las filas
    conexion.close()
    
    # Convertimos cada fila a diccionario y los conceptos de string JSON a lista
    facturas = []
    for fila in filas:
        factura = dict(fila)  # sqlite3.Row -> diccionario normal
        # Los conceptos se guardaron como string JSON, los reconvertimos a lista
        if factura["conceptos"]:
            factura["conceptos"] = json.loads(factura["conceptos"])
        facturas.append(factura)
    
    return {"total": len(facturas), "facturas": facturas}


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 6.1: ENDPOINT — DELETE /facturas/{id}
# ─────────────────────────────────────────────────────────────────────────────
# Elimina una factura por su ID.
# En n8n seria un nodo "Delete Row" en Google Sheets.

@app.delete("/facturas/{factura_id}", dependencies=[Depends(verificar_api_key)])
def eliminar_factura(factura_id: int):
    """Elimina una factura por su ID."""
    conexion = sqlite3.connect(RUTA_BD)
    cursor = conexion.cursor()

    # Primero verificamos que existe
    cursor.execute("SELECT id FROM facturas WHERE id = ?", (factura_id,))
    if cursor.fetchone() is None:
        conexion.close()
        raise HTTPException(status_code=404, detail="Factura no encontrada.")

    cursor.execute("DELETE FROM facturas WHERE id = ?", (factura_id,))
    conexion.commit()
    conexion.close()

    return {"exito": True, "mensaje": f"Factura {factura_id} eliminada."}


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 6.2: ENDPOINT — GET /estadisticas
# ─────────────────────────────────────────────────────────────────────────────
# Devuelve datos agregados para el dashboard y graficos.
# Equivale a un nodo "Aggregate" o "Summarize" en n8n.

@app.get("/estadisticas", dependencies=[Depends(verificar_api_key)])
def obtener_estadisticas():
    """Devuelve KPIs y datos para graficos del dashboard."""
    conexion = sqlite3.connect(RUTA_BD)
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()

    # --- KPIs ---
    cursor.execute("SELECT COUNT(*) as total FROM facturas")
    total = cursor.fetchone()["total"]

    cursor.execute("SELECT COALESCE(SUM(importe_total), 0) as suma FROM facturas")
    importe_total = cursor.fetchone()["suma"]

    cursor.execute("SELECT COALESCE(AVG(importe_total), 0) as media FROM facturas")
    importe_medio = round(cursor.fetchone()["media"], 2)

    cursor.execute("SELECT COUNT(DISTINCT proveedor) as unicos FROM facturas WHERE proveedor IS NOT NULL")
    proveedores_unicos = cursor.fetchone()["unicos"]

    # --- Gasto por mes (ultimos 12 meses) ---
    cursor.execute("""
        SELECT 
            substr(fecha_factura, 1, 7) as mes,
            SUM(importe_total) as total_mes,
            COUNT(*) as num_facturas
        FROM facturas
        WHERE fecha_factura IS NOT NULL
        GROUP BY mes
        ORDER BY mes DESC
        LIMIT 12
    """)
    gasto_mensual = [dict(r) for r in cursor.fetchall()]
    gasto_mensual.reverse()  # Orden cronologico

    # --- Top 5 proveedores por gasto ---
    cursor.execute("""
        SELECT 
            proveedor,
            SUM(importe_total) as total_gasto,
            COUNT(*) as num_facturas
        FROM facturas
        WHERE proveedor IS NOT NULL
        GROUP BY proveedor
        ORDER BY total_gasto DESC
        LIMIT 5
    """)
    top_proveedores = [dict(r) for r in cursor.fetchall()]

    conexion.close()

    return {
        "kpis": {
            "total_facturas": total,
            "importe_total": round(importe_total, 2),
            "importe_medio": importe_medio,
            "proveedores_unicos": proveedores_unicos
        },
        "gasto_mensual": gasto_mensual,
        "top_proveedores": top_proveedores
    }


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 7: ENDPOINT AUXILIAR — GET /salud
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/salud")
def verificar_salud():
    """Endpoint de salud. Devuelve OK si el servidor esta activo. No requiere API key."""
    return {"estado": "activo", "version": "2.0.0"}


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 8: FRONTEND — Servir la pagina web
# ─────────────────────────────────────────────────────────────────────────────
# Este endpoint sirve el archivo index.html cuando alguien abre http://localhost:8000
# Es como tener un nodo "Respond with HTML" en n8n.
# IMPORTANTE: Este endpoint debe ir AL FINAL, despues de todos los demas,
# para que no intercepte las rutas de la API.

@app.get("/")
def pagina_principal():
    """Sirve la interfaz web del frontend."""
    return FileResponse(str(RUTA_FRONTEND / "index.html"))


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 9: ARRANQUE DEL SERVIDOR
# ─────────────────────────────────────────────────────────────────────────────
# Este bloque solo se ejecuta cuando corres el script directamente.
# "if __name__ == '__main__'" es un patron estandar de Python:
# significa "si este archivo es el principal (no importado por otro)".

if __name__ == "__main__":
    import uvicorn
    print("[*] Iniciando servidor de extraccion de facturas...")
    print("[i] Frontend en: http://localhost:8000")
    print("[i] Documentacion API en: http://localhost:8000/docs")
    uvicorn.run(
        "scripts.main:app",  # Ruta al objeto "app" dentro de este modulo
        host="0.0.0.0",      # Escucha en todas las interfaces de red
        port=8000,            # Puerto 8000 (puedes cambiarlo)
        reload=True           # Recarga automatica al guardar cambios (modo desarrollo)
    )
