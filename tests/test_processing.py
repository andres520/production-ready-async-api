from pathlib import Path

from app.tasks import process_file


def test_process_csv_returns_rows_and_numeric_summary(tmp_path: Path):
    report = tmp_path / "report.csv"
    report.write_text("name,value\nalpha,10\nbeta,20\n", encoding="utf-8")

    result = process_file(report, "report.csv")

    assert result["kind"] == "csv_analysis"
    assert result["rows"] == 2
    assert result["columns"] == ["name", "value"]
    assert result["numeric_values"] == 2
    assert result["numeric_average"] == 15
