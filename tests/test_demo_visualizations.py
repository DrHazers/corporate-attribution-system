import shutil
import sqlite3
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
    assert result["refreshed_company_ids"] == []

    for item in generated:
        html_path = Path(item["html_path"])
        assert html_path.exists()
        assert html_path.stat().st_size > 0
        html_text = html_path.read_text(encoding="utf-8")
        assert item["company_name"] in html_text

    raw_db_stat_after = raw_db.stat()
    assert raw_db_stat_after.st_size == raw_db_stat.st_size
    assert raw_db_stat_after.st_mtime_ns == raw_db_stat.st_mtime_ns


def test_build_demo_visualizations_refreshes_specific_company_id_and_persists(tmp_path):
    temp_db = tmp_path / "demo_copy.db"
    shutil.copy2(DEFAULT_DEMO_DB, temp_db)

    conn = sqlite3.connect(temp_db)
    before_control = conn.execute(
        "select count(*) from control_relationships where company_id = 15"
    ).fetchone()[0]
    before_country = conn.execute(
        "select count(*) from country_attributions where company_id = 15"
    ).fetchone()[0]
    conn.close()

    result = build_demo_visualizations(
        database_path=temp_db,
        samples_json_path=DEFAULT_SAMPLES_JSON,
        output_dir=tmp_path / "graphs",
        selected_company_ids=[15],
    )

    assert result["refreshed_company_ids"] == [15]
    assert not result["missing"]
    assert len(result["generated"]) == 1

    item = result["generated"][0]
    assert item["company_id"] == 15
    assert item["file_name"] == "company_15_shengda_semiconductor_industrial_group_co_ltd.html"

    html_path = Path(item["html_path"])
    assert html_path.exists()
    html_text = html_path.read_text(encoding="utf-8")
    assert "Shengda Semiconductor Industrial Group Co., Ltd." in html_text

    conn = sqlite3.connect(temp_db)
    after_control = conn.execute(
        "select count(*) from control_relationships where company_id = 15"
    ).fetchone()[0]
    after_country = conn.execute(
        "select count(*) from country_attributions where company_id = 15"
    ).fetchone()[0]
    conn.close()

    assert after_control > 0
    assert after_control >= before_control
    assert after_country >= 1

    index_path = Path(result["index_path"])
    assert index_path.exists()
    index_text = index_path.read_text(encoding="utf-8")
    assert item["file_name"] in index_text
