import os
import json
from collections import OrderedDict
import chromadb
from openai import AsyncOpenAI
from dotenv import load_dotenv

from logging_config import get_logger
logger = get_logger(__name__)

load_dotenv()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 1. Iniciar ChromaDB (persistido en DATA_DIR/chroma_db; DATA_DIR=. en local)
DATA_DIR = os.getenv("DATA_DIR", ".")
chroma_client = chromadb.PersistentClient(path=os.path.join(DATA_DIR, "chroma_db"))
collection = chroma_client.get_or_create_collection(name="conocimiento_empresa")

# Caché LRU en memoria: clave = pregunta normalizada, valor = resultado completo.
# Límite para que no crezca sin cota durante la vida del proceso — al superarlo,
# se descarta la entrada usada hace más tiempo (menos probable que se repita).
_cache_rag: "OrderedDict[str, str]" = OrderedDict()
CACHE_RAG_MAX_ENTRADAS = 500

async def buscar_informacion(pregunta: str) -> str:
    """Busca en ChromaDB los documentos más relevantes para la pregunta."""
    clave = pregunta.strip().lower()
    if clave in _cache_rag:
        logger.info(f"[RAG TOOL] Cache hit para: '{pregunta}' — sin llamada a OpenAI.")
        _cache_rag.move_to_end(clave)
        return _cache_rag[clave]

    logger.info(f"[RAG TOOL] Buscando en manuales la respuesta a: '{pregunta}'")

    try:
        # Convertimos la pregunta del usuario en un vector
        respuesta_emb = await client.embeddings.create(
            input=pregunta,
            model="text-embedding-3-small"
        )
        vector_pregunta = respuesta_emb.data[0].embedding

        # Umbral L2: con embeddings normalizados de text-embedding-3-small,
        # distancia 1.2 ≈ cosine_sim 0.28 — filtra fragmentos claramente irrelevantes.
        RAG_MAX_DISTANCE = 1.35

        resultados = collection.query(
            query_embeddings=[vector_pregunta],
            n_results=9
        )

        documentos_raw = resultados['documents'][0]
        distancias = resultados['distances'][0]

        documentos_encontrados = [
            doc for doc, dist in zip(documentos_raw, distancias)
            if dist <= RAG_MAX_DISTANCE
        ]

        if not documentos_encontrados:
            resultado = "No he encontrado información sobre esto en los manuales de la empresa."
        else:
            contexto = "\n---\n".join(documentos_encontrados)
            logger.info("[RAG TOOL] Información encontrada y enviada al Agente.")
            resultado = f"Información de los manuales:\n{contexto}"

        _cache_rag[clave] = resultado
        _cache_rag.move_to_end(clave)
        if len(_cache_rag) > CACHE_RAG_MAX_ENTRADAS:
            _cache_rag.popitem(last=False)
        return resultado

    except Exception as e:
        logger.error(f"[RAG TOOL ERROR]: {e}", exc_info=True)
        return "Hubo un problema técnico al consultar los manuales."

# El esquema de la herramienta (tool_consultar_dudas) se queda exactamente igual
tool_consultar_dudas = {
    "type": "function",
    "function": {
        "name": "buscar_informacion",
        "description": "Busca en la base de datos de conocimiento oficial de Solsureste. DEBES usar esta herramienta para CUALQUIER pregunta del cliente sobre: precios, baterías, inversores, marcas, zonas de cobertura, ciudades, financiación, garantías, plazos de instalación, subcontratas, amortización, subvenciones, IBI, deducciones fiscales, proceso de trabajo, o cualquier duda sobre la empresa. NUNCA respondas preguntas sobre Solsureste sin llamar primero a esta herramienta.",
        "parameters": {
            "type": "object",
            "properties": {
                "pregunta": {
                    "type": "string",
                    "description": "La duda específica del usuario resumida de forma clara."
                }
            },
            "required": ["pregunta"]
        }
    }
}