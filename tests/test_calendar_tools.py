from tools.calendar_tools import _dentro_horario_laboral

# Semana de referencia conocida (2026-07-06 = lunes ... 2026-07-12 = domingo).
LUNES = "2026-07-06"
JUEVES = "2026-07-09"
VIERNES = "2026-07-10"
SABADO = "2026-07-11"
DOMINGO = "2026-07-12"


def test_dentro_de_horario_manana_lunes_a_jueves():
    assert _dentro_horario_laboral(LUNES, "09:00")
    assert _dentro_horario_laboral(JUEVES, "13:59")


def test_limite_exacto_14_00_no_esta_incluido_lunes_a_jueves():
    # La franja de mañana es [08:30, 14:00) -- el límite superior es exclusivo.
    assert not _dentro_horario_laboral(LUNES, "14:00")
    assert _dentro_horario_laboral(LUNES, "13:59")


def test_dentro_de_horario_tarde_lunes_a_jueves():
    assert _dentro_horario_laboral(LUNES, "16:00")
    assert _dentro_horario_laboral(JUEVES, "19:29")
    assert not _dentro_horario_laboral(JUEVES, "19:30")


def test_hueco_de_comida_lunes_a_jueves_esta_fuera_de_horario():
    assert not _dentro_horario_laboral(LUNES, "15:00")


def test_viernes_solo_tiene_franja_de_manana():
    assert _dentro_horario_laboral(VIERNES, "09:00")
    assert _dentro_horario_laboral(VIERNES, "14:59")
    assert not _dentro_horario_laboral(VIERNES, "15:00")
    assert not _dentro_horario_laboral(VIERNES, "16:30")


def test_fin_de_semana_siempre_cerrado():
    assert not _dentro_horario_laboral(SABADO, "10:00")
    assert not _dentro_horario_laboral(DOMINGO, "10:00")
