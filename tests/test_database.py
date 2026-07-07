import threading

import pytest

import database as db


@pytest.fixture
def bd_temporal(tmp_path, monkeypatch):
    """BD SQLite aislada por test, para no interferir ni con la BD compartida de la
    sesión de tests ni entre tests."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_NAME", str(db_path))
    db.init_db()
    return db_path


def test_init_db_crea_tablas_vacias(bd_temporal):
    assert db.get_all_conversaciones() == []
    assert db.get_coste_historico() == 0.0


def test_get_conversacion_crea_la_fila_si_no_existe(bd_temporal):
    estado, historial = db.get_conversacion("nuevo_usuario")
    assert estado == "INICIO"
    assert historial == []


def test_update_datos_cliente_guarda_los_campos(bd_temporal):
    user_id = "user_datos"
    db.get_conversacion(user_id)
    db.update_datos_cliente(user_id, "Ana Garcia", "ana@test.com", "666123456", "Murcia")

    lead = next(l for l in db.get_all_conversaciones() if l["user_id"] == user_id)
    assert lead["nombre"] == "Ana Garcia"
    assert lead["correo"] == "ana@test.com"
    assert lead["telefono"] == "666123456"
    assert lead["ciudad"] == "Murcia"


def test_crm_ya_enviado_y_marcar_crm_enviado(bd_temporal):
    user_id = "user_crm"
    db.get_conversacion(user_id)

    assert db.crm_ya_enviado(user_id) is False
    db.marcar_crm_enviado(user_id)
    assert db.crm_ya_enviado(user_id) is True

    lead = next(l for l in db.get_all_conversaciones() if l["user_id"] == user_id)
    assert lead["crm_enviado"] is True


def test_reset_conversacion_limpia_historial_y_datos_pero_no_el_coste(bd_temporal):
    user_id = "user_reset"
    db.get_conversacion(user_id)
    db.append_mensaje(user_id, "user", "hola")
    db.update_datos_cliente(user_id, "Ana", "ana@test.com", "666123456", "Murcia")
    db.marcar_crm_enviado(user_id)
    db.acumular_tokens(user_id, 1000, 500)

    coste_antes = db.get_coste_sesion(user_id)
    assert coste_antes > 0

    db.reset_conversacion(user_id)

    estado, historial = db.get_conversacion(user_id)
    assert estado == "INICIO"
    assert historial == []
    lead = next(l for l in db.get_all_conversaciones() if l["user_id"] == user_id)
    assert lead["nombre"] == ""
    assert lead["crm_enviado"] is False
    # El coste acumulado persiste a través de un reset (documentado en CLAUDE.md).
    assert db.get_coste_sesion(user_id) == coste_antes


def test_purgar_conversaciones_antiguas_borra_solo_las_viejas_y_rescata_el_coste(bd_temporal):
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO conversaciones (user_id, created_at, coste_usd) VALUES (?, ?, ?)",
        ("user_viejo", "2000-01-01 00:00:00", 2.5),
    )
    conn.commit()
    conn.close()

    db.get_conversacion("user_reciente")

    coste_historico_antes = db.get_coste_historico()
    filas_borradas = db.purgar_conversaciones_antiguas(dias=730)

    assert filas_borradas == 1
    ids_restantes = {l["user_id"] for l in db.get_all_conversaciones()}
    assert "user_viejo" not in ids_restantes
    assert "user_reciente" in ids_restantes
    assert db.get_coste_historico() == pytest.approx(coste_historico_antes + 2.5)


def test_append_mensaje_concurrente_no_pierde_mensajes(bd_temporal):
    """Auditoría de robustez: append_mensaje hacía SELECT->modificar en Python->UPDATE
    como dos sentencias sin transacción explícita. Dos escrituras concurrentes para el
    mismo user_id (doble clic, retry del frontend) podían pisarse un mensaje: ambas
    leen el mismo historial "viejo" antes de que la otra escriba. Con BEGIN IMMEDIATE
    las escrituras se serializan y no se pierde ninguna.

    Sin el fix este test es intermitente (a veces pasa por suerte de scheduling); con
    el fix es determinista."""
    user_id = "user_concurrencia"
    db.get_conversacion(user_id)

    N_POR_HILO = 30
    barrera = threading.Barrier(2)

    def escribir(prefijo):
        barrera.wait()
        for i in range(N_POR_HILO):
            db.append_mensaje(user_id, "user", f"{prefijo}-{i}")

    hilo_a = threading.Thread(target=escribir, args=("A",))
    hilo_b = threading.Thread(target=escribir, args=("B",))
    hilo_a.start()
    hilo_b.start()
    hilo_a.join()
    hilo_b.join()

    _, historial = db.get_conversacion(user_id)
    assert len(historial) == N_POR_HILO * 2
