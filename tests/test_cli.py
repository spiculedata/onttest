from brackenfield.cli import EXIT_BAD_INPUT, main


def test_missing_workbook_exits_with_bad_input_and_writes_nothing(tmp_path, capsys):
    db = tmp_path / "x.duckdb"

    code = main(["run", "--skip-fieldtrax", "--workbook", str(tmp_path / "missing.xlsx"), "--db", str(db)])

    assert code == EXIT_BAD_INPUT
    assert "nothing written" in capsys.readouterr().err
    assert not db.exists()
