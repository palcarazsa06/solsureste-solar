import pytest

import tools.rag_tools as rag_tools


@pytest.fixture(autouse=True)
def _cache_limpia():
    rag_tools._cache_rag.clear()
    yield
    rag_tools._cache_rag.clear()


def test_cache_rag_no_crece_mas_alla_del_limite():
    for i in range(rag_tools.CACHE_RAG_MAX_ENTRADAS + 1):
        clave = f"pregunta {i}"
        rag_tools._cache_rag[clave] = f"respuesta {i}"
        rag_tools._cache_rag.move_to_end(clave)
        if len(rag_tools._cache_rag) > rag_tools.CACHE_RAG_MAX_ENTRADAS:
            rag_tools._cache_rag.popitem(last=False)

    assert len(rag_tools._cache_rag) == rag_tools.CACHE_RAG_MAX_ENTRADAS
    assert "pregunta 0" not in rag_tools._cache_rag
    assert f"pregunta {rag_tools.CACHE_RAG_MAX_ENTRADAS}" in rag_tools._cache_rag


@pytest.mark.asyncio
async def test_buscar_informacion_usa_cache_en_hit_sin_llamar_a_openai(monkeypatch):
    rag_tools._cache_rag["ya preguntado"] = "respuesta cacheada"

    async def _embeddings_mock(*args, **kwargs):
        raise AssertionError("no debería llamar a embeddings.create en un cache hit")

    monkeypatch.setattr(rag_tools.client.embeddings, "create", _embeddings_mock)

    resultado = await rag_tools.buscar_informacion("Ya Preguntado")

    assert resultado == "respuesta cacheada"
