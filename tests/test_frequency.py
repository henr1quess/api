"""Tests for services/frequency.py"""

import pandas as pd
import pytest

from services.frequency import (
    parse_marcacao_csv,
    summarize_frequencia,
    validate_marcacoes,
)


def _csv(content: str) -> bytes:
    return content.encode("utf-8-sig")


class TestSummarizeFrequencia:
    def test_counts_presence_and_faults(self):
        df = pd.DataFrame([
            {
                "matricula": "001",
                "nome": "Aluno A",
                "presenca_falta_01": "\u2022",  # bullet = Presenca
                "presenca_falta_02": "F",
                "presenca_falta_03": "D",
            }
        ])
        summary = summarize_frequencia(df)
        assert len(summary) == 1
        row = summary.iloc[0]
        assert row["Presenca"] == 1
        assert row["Falta"] == 1
        assert row["Dispensa"] == 1
        assert row["Total_aulas"] == 3

    def test_empty_dataframe_returns_empty(self):
        df = pd.DataFrame()
        result = summarize_frequencia(df)
        assert result.empty

    def test_no_presenca_falta_columns_returns_unchanged(self):
        df = pd.DataFrame([{"matricula": "001", "nome": "A"}])
        result = summarize_frequencia(df)
        assert list(result.columns) == ["matricula", "nome"]

    def test_multiple_students(self):
        df = pd.DataFrame([
            {"matricula": "001", "presenca_falta_01": "P", "presenca_falta_02": "F"},
            {"matricula": "002", "presenca_falta_01": "F", "presenca_falta_02": "F"},
        ])
        summary = summarize_frequencia(df)
        assert len(summary) == 2
        row1 = summary[summary["matricula"] == "001"].iloc[0]
        assert row1["Presenca"] == 1
        assert row1["Falta"] == 1


class TestParseMarcacaoCsv:
    def test_valid_csv(self):
        csv = _csv("data_hora;tipo_entrada_saida;matricula\n2025-03-15T08:30:00;E;001\n")
        df = parse_marcacao_csv(csv)
        assert len(df) == 1
        assert df.iloc[0]["matricula"] == "001"

    def test_missing_required_column(self):
        csv = _csv("data_hora;matricula\n2025-03-15T08:30:00;001\n")
        with pytest.raises(ValueError, match="tipo_entrada_saida"):
            parse_marcacao_csv(csv)

    def test_columns_lowercased(self):
        csv = _csv("Data_Hora;Tipo_Entrada_Saida;Matricula\n2025-03-15T08:30:00;E;001\n")
        df = parse_marcacao_csv(csv)
        assert "data_hora" in df.columns
        assert "tipo_entrada_saida" in df.columns


class TestValidateMarcacoes:
    def _df(self, rows):
        return pd.DataFrame(rows)

    def test_valid_row_is_ok(self):
        df = self._df([{
            "matricula": "001",
            "tipo_entrada_saida": "E",
            "data_hora": "2025-03-15T08:30:00",
            "comentario": "",
        }])
        result = validate_marcacoes(df)
        assert result.iloc[0]["_status"] == "OK"

    def test_empty_matricula_is_error(self):
        df = self._df([{
            "matricula": "",
            "tipo_entrada_saida": "E",
            "data_hora": "2025-03-15T08:30:00",
            "comentario": "",
        }])
        result = validate_marcacoes(df)
        assert result.iloc[0]["_status"] == "ERRO"
        assert "Matricula vazia" in result.iloc[0]["_msg"]

    def test_invalid_tipo_is_error(self):
        df = self._df([{
            "matricula": "001",
            "tipo_entrada_saida": "X",
            "data_hora": "2025-03-15T08:30:00",
            "comentario": "",
        }])
        result = validate_marcacoes(df)
        assert result.iloc[0]["_status"] == "ERRO"
        assert "tipo_entrada_saida invalido" in result.iloc[0]["_msg"]

    def test_non_iso_data_hora_is_error(self):
        df = self._df([{
            "matricula": "001",
            "tipo_entrada_saida": "E",
            "data_hora": "15/03/2025 08:30",
            "comentario": "",
        }])
        result = validate_marcacoes(df)
        assert result.iloc[0]["_status"] == "ERRO"
        assert "data_hora formato invalido" in result.iloc[0]["_msg"]

    def test_empty_data_hora_is_error(self):
        df = self._df([{
            "matricula": "001",
            "tipo_entrada_saida": "E",
            "data_hora": "",
            "comentario": "",
        }])
        result = validate_marcacoes(df)
        assert result.iloc[0]["_status"] == "ERRO"
        assert "data_hora vazia" in result.iloc[0]["_msg"]
