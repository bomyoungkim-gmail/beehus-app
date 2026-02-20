from core.services.file_processor import FileProcessorService


def _context():
    return {
        "original_dir": "/tmp/original",
        "processed_dir": "/tmp/processed",
        "carteira": "ABC",
        "metadata": {"k": "v"},
        "run_id": "run-1",
        "credential_label": "cred",
        "selected_filename": "arquivo.xlsx",
        "selected_sheet": "Plan1",
        "source_excel_path": "/tmp/original/arquivo.xlsx",
    }


def test_build_wrapped_script_low_code_mode_includes_auto_wrapper():
    script = "df = pd.DataFrame({'a': [1]})\nreturn df"
    wrapped = FileProcessorService._build_wrapped_script(script, _context())

    assert "def _load_input_dataframe(arquivo, aba):" in wrapped
    assert "def process_auto_generated(arquivo, aba, carteira, df_input):" in wrapped
    assert "df_input = _load_input_dataframe(arquivo, aba)" in wrapped
    assert "resultado = process_auto_generated(arquivo, aba, carteira, df_input)" in wrapped
    assert "resultado.to_csv(caminho_saida, index=False, sep=';', decimal=',')" in wrapped
    assert "# Aliases em portugues" in wrapped
    assert "arquivo = selected_filename" in wrapped


def test_build_wrapped_script_advanced_mode_keeps_original_script():
    script = "import math\nprint(math.sqrt(4))\n"
    wrapped = FileProcessorService._build_wrapped_script(script, _context())

    assert "# User script (advanced mode)" in wrapped
    assert "import math" in wrapped
    assert "def process_auto_generated(arquivo, aba, carteira, df_input):" not in wrapped


def test_normalize_processed_names_uses_positions_pattern(tmp_path):
    source = tmp_path / "processed_any.csv"
    source.write_text("a;b\n1;2\n", encoding="utf-8")

    renamed = FileProcessorService._normalize_processed_names([str(source)], job_name="ignored")
    assert len(renamed) == 1

    output_name = renamed[0].split("\\")[-1].split("/")[-1]
    assert output_name.startswith("positions_processado-")
    assert output_name.endswith(".csv")
