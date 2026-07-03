import os
import chromadb
from PyPDF2 import PdfReader
from dotenv import load_dotenv
from openai import OpenAI

# Cargamos variables de entorno (API Key de OpenAI)
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Configuramos la conexión a la base de datos vectorial
CHROMA_PATH = "./chroma_db"
DOCUMENTOS_PATH = "./documentos"

def obtener_embedding(texto):
    """Convierte un bloque de texto en un vector matemático usando OpenAI."""
    respuesta = client.embeddings.create(
        input=texto,
        model="text-embedding-3-small" # Modelo rápido y barato para embeddings
    )
    return respuesta.data[0].embedding

def trocear_texto(texto, max_caracteres=1000, solapamiento=200):
    """Corta el texto en fragmentos con un poco de solapamiento para no perder contexto."""
    fragmentos = []
    inicio = 0
    while inicio < len(texto):
        fin = inicio + max_caracteres
        fragmento = texto[inicio:fin]
        fragmentos.append(fragmento)
        inicio += (max_caracteres - solapamiento)
    return fragmentos

def procesar_pdfs():
    print("🧠 Iniciando la inyección de conocimiento en ChromaDB...")
    
    # 1. Inicializamos ChromaDB y la colección
    db_client = chromadb.PersistentClient(path=CHROMA_PATH)
    coleccion = db_client.get_or_create_collection(name="conocimiento_empresa")
    
    # 2. Buscamos todos los PDFs en la carpeta
    if not os.path.exists(DOCUMENTOS_PATH):
        os.makedirs(DOCUMENTOS_PATH)
        print(f"⚠️ Carpeta '{DOCUMENTOS_PATH}' creada. Mete algún PDF dentro y vuelve a ejecutar.")
        return

    archivos_pdf = [f for f in os.listdir(DOCUMENTOS_PATH) if f.endswith('.pdf') or f.endswith('.txt')]

    if not archivos_pdf:
        print(f"⚠️ No hay archivos PDF o TXT en la carpeta '{DOCUMENTOS_PATH}'.")
        return

    # 3. Procesamos cada documento (PDF o TXT)
    for archivo in archivos_pdf:
        ruta_completa = os.path.join(DOCUMENTOS_PATH, archivo)
        print(f"📄 Leyendo: {archivo}...")

        texto_completo = ""
        try:
            if archivo.endswith('.txt'):
                with open(ruta_completa, 'r', encoding='utf-8') as f:
                    texto_completo = f.read()
            else:
                lector = PdfReader(ruta_completa)
                for pagina in lector.pages:
                    texto_extraido = pagina.extract_text()
                    if texto_extraido:
                        texto_completo += texto_extraido + "\n"
        except Exception as e:
            print(f"❌ Error leyendo {archivo}: {e}")
            continue
            
        # 4. Troceamos y guardamos en la base de datos
        fragmentos = trocear_texto(texto_completo)
        print(f"✂️ {archivo} dividido en {len(fragmentos)} fragmentos.")
        
        for i, fragmento in enumerate(fragmentos):
            # Limpiamos el fragmento (quitamos saltos de línea excesivos)
            fragmento_limpio = " ".join(fragmento.split())
            if len(fragmento_limpio) < 50: 
                continue # Ignoramos fragmentos vacíos o muy cortos
                
            id_fragmento = f"{archivo}_frag_{i}"
            vector = obtener_embedding(fragmento_limpio)
            
            coleccion.upsert(
                ids=[id_fragmento],
                embeddings=[vector],
                documents=[fragmento_limpio],
                metadatas=[{"origen": archivo}]
            )
            
        print(f"✅ Conocimiento de '{archivo}' guardado en la base de datos.")
        
    print("🎉 ¡Proceso terminado! Tu IA ya es más lista.")

if __name__ == "__main__":
    procesar_pdfs()