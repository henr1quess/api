"""Tests for services/validators.py"""

import pytest
from pydantic import ValidationError

from services.validators import MarcacaoFrequencia, normalize_nota


class TestNormalizeNota:
    def test_comma_decimal(self):
        assert normalize_nota("8,5") == "8.50"

    def test_dot_decimal(self):
        assert normalize_nota("8.5") == "8.50"

    def test_integer(self):
        assert normalize_nota("10") == "10.00"

    def test_zero(self):
        assert normalize_nota("0") == "0.00"

    def test_empty_string(self):
        assert normalize_nota("") is None

    def test_whitespace_only(self):
        assert normalize_nota("   ") is None

    def test_nan_string(self):
        assert normalize_nota("nan") is None

    def test_none_string(self):
        assert normalize_nota("None") is None

    def test_invalid_text(self):
        assert normalize_nota("abc") is None

    def test_leading_trailing_spaces(self):
        assert normalize_nota("  7,0  ") == "7.00"


class TestMarcacaoFrequencia:
    def test_valid_entrada(self):
        m = MarcacaoFrequencia(
            data_hora="2025-03-15T08:30:00",
            tipo_entrada_saida="E",
            matricula="12345",
        )
        assert m.tipo_entrada_saida == "E"

    def test_tipo_lowercase_uppercased(self):
        m = MarcacaoFrequencia(
            data_hora="2025-03-15T08:30:00",
            tipo_entrada_saida="s",
            matricula="12345",
        )
        assert m.tipo_entrada_saida == "S"

    def test_invalid_tipo(self):
        with pytest.raises(ValidationError):
            MarcacaoFrequencia(
                data_hora="2025-03-15T08:30:00",
                tipo_entrada_saida="X",
                matricula="12345",
            )

    def test_comentario_max_length(self):
        with pytest.raises(ValidationError):
            MarcacaoFrequencia(
                data_hora="2025-03-15T08:30:00",
                tipo_entrada_saida="E",
                matricula="12345",
                comentario="A" * 51,
            )

    def test_comentario_exactly_50(self):
        m = MarcacaoFrequencia(
            data_hora="2025-03-15T08:30:00",
            tipo_entrada_saida="E",
            matricula="12345",
            comentario="A" * 50,
        )
        assert len(m.comentario) == 50

    def test_optional_fields_default_none(self):
        m = MarcacaoFrequencia(
            data_hora="2025-03-15T08:30:00",
            tipo_entrada_saida="E",
            matricula="12345",
        )
        assert m.comentario is None
        assert m.id_responsavel_acompanhante is None
