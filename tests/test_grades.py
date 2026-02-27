"""Tests for services/grades.py"""

import pandas as pd
import pytest

from services.grades import build_payloads, parse_notas_csv


def _csv(content: str) -> bytes:
    return content.encode("utf-8-sig")


class TestParseNotasCsv:
    def test_valid_csv(self):
        csv = _csv("matricula;nota01;nota02\n001;8,5;7,0\n002;9,0;\n")
        df = parse_notas_csv(csv)
        assert list(df.columns) == ["matricula", "nota01", "nota02"]
        assert len(df) == 2
        assert df.iloc[0]["matricula"] == "001"

    def test_missing_matricula_column(self):
        csv = _csv("nome;nota01\nJoao;8,5\n")
        with pytest.raises(ValueError, match="matricula"):
            parse_notas_csv(csv)

    def test_columns_stripped_lowercased(self):
        csv = _csv("  Matricula ;  Nota01 \n001;8,5\n")
        df = parse_notas_csv(csv)
        assert "matricula" in df.columns
        assert "nota01" in df.columns


class TestBuildPayloads:
    def _make_validated_df(self, rows):
        return pd.DataFrame(rows)

    def test_only_ok_rows_included(self):
        df = self._make_validated_df([
            {"matricula": "001", "nota01": "8,5", "_status": "OK", "_msg": ""},
            {"matricula": "002", "nota01": "",    "_status": "ERRO", "_msg": "Nota invalida"},
            {"matricula": "003", "nota01": "7,0", "_status": "OK", "_msg": ""},
        ])
        payloads = build_payloads(df, turma_id=1, disciplina_id=2, fase_nota_id=3)
        assert len(payloads) == 1
        notas = payloads[0]["notas"]
        matriculas = [n["matricula"] for n in notas]
        assert "001" in matriculas
        assert "003" in matriculas
        assert "002" not in matriculas

    def test_chunking(self):
        rows = [
            {"matricula": str(i), "nota01": "8,0", "_status": "OK", "_msg": ""}
            for i in range(3)
        ]
        df = self._make_validated_df(rows)
        payloads = build_payloads(df, turma_id=1, disciplina_id=2, fase_nota_id=3, batch_size=2)
        assert len(payloads) == 2
        assert len(payloads[0]["notas"]) == 2
        assert len(payloads[1]["notas"]) == 1

    def test_nota_normalized(self):
        df = self._make_validated_df([
            {"matricula": "001", "nota01": "8,5", "_status": "OK", "_msg": ""},
        ])
        payloads = build_payloads(df, turma_id=1, disciplina_id=2, fase_nota_id=3)
        nota = payloads[0]["notas"][0]
        assert nota["nota01"] == "8.50"

    def test_empty_ok_rows(self):
        df = self._make_validated_df([
            {"matricula": "001", "nota01": "8,5", "_status": "ERRO", "_msg": "err"},
        ])
        payloads = build_payloads(df, turma_id=1, disciplina_id=2, fase_nota_id=3)
        assert payloads == []
