from validadores import email_valido, telefono_valido


def test_telefono_valido_acepta_formatos_espanoles_comunes():
    assert telefono_valido("666123456")
    assert telefono_valido("+34 666 123 456")
    assert telefono_valido("0034666123456")
    assert telefono_valido("666-123-456")
    assert telefono_valido("722123456")  # prefijo 7, también móvil válido en España


def test_telefono_valido_rechaza_formatos_invalidos():
    assert not telefono_valido("N/A")
    assert not telefono_valido("Desconocido")
    assert not telefono_valido("123")
    assert not telefono_valido("")
    assert not telefono_valido(None)
    assert not telefono_valido("512345678")  # el primer dígito debe ser 6, 7, 8 o 9


def test_email_valido_acepta_correos_bien_formados():
    assert email_valido("cliente@example.com")
    assert email_valido("nombre.apellido@dominio.es")


def test_email_valido_rechaza_correos_mal_formados():
    assert not email_valido("Desconocido")
    assert not email_valido("no-es-un-correo")
    assert not email_valido("")
    assert not email_valido(None)
