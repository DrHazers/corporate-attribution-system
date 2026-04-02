from pathlib import Path

from scripts.build_demo_visualizations import (
    DEFAULT_DEMO_DB,
    DEFAULT_SAMPLES_JSON,
    build_demo_visualizations,
)


def test_build_demo_visualizations_generates_html(tmp_path):
    raw_db = Path("company_test_analysis.db").resolve()
    raw_db_stat = raw_db.stat()

    result = build_demo_visualizations(
        database_path=DEFAULT_DEMO_DB,
        samples_json_path=DEFAULT_SAMPLES_JSON,
        output_dir=tmp_path,
        selected_categories=[
            "equity_control",
            "board_control",
            "mixed_control",
        ],
    )

    assert Path(result["database_path"]).resolve() == DEFAULT_DEMO_DB.resolve()
    index_path = Path(result["index_path"])
    assert index_path.exists()
    assert index_path.stat().st_size > 0

    generated = result["generated"]
    assert len(generated) == 3
    assert not result["missing"]

    for item in generated:
        html_path = Path(item["html_path"])
        assert html_path.exists()
        assert html_path.stat().st_size > 0
        html_text = html_path.read_text(encoding="utf-8")
        assert item["company_name"] in html_text

    raw_db_stat_after = raw_db.stat()
    assert raw_db_stat_after.st_size == raw_db_stat.st_size
    assert raw_db_stat_after.st_mtime_ns == raw_db_stat.st_mtime_ns
