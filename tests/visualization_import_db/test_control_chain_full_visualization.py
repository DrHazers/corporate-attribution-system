from __future__ import annotations

from pathlib import Path


def _pick_sample(sample_selection, *, category: str | None = None, mixed: bool = False):
    for item in sample_selection:
        if category is not None and item["category"] == category:
            return item
        if mixed and item["summary"].get("mixed_path_visible"):
            return item
    return None


def test_build_edge_label_formats_control_types_and_percentages(visualization_module):
    assert visualization_module.build_edge_label("equity", holding_ratio="35") == "equity 35%"
    assert visualization_module.build_edge_label("equity", holding_ratio="27.5") == "equity 27.5%"
    assert visualization_module.build_edge_label("agreement") == "agreement"
    assert visualization_module.build_edge_label("board_control", holding_ratio="0") == "board_control"
    assert visualization_module.build_edge_label(None, holding_ratio="51.23") == "equity 51.23%"
    assert visualization_module.build_edge_label(None) == "unknown"
    assert (
        visualization_module.build_edge_label(
            "agreement",
            remarks="[import] original_control_type=board_control",
        )
        == "board_control"
    )


def test_sample_selection_covers_mixed_and_non_equity_patterns(sample_selection):
    categories = {item["category"] for item in sample_selection}
    assert len(sample_selection) == 5
    assert "mixed_path" in categories
    assert any(
        item["category"] in {"voting_right", "board_control", "non_equity"}
        or item["summary"].get("has_non_equity")
        for item in sample_selection
    )
    assert any(item["summary"].get("max_depth", 0) >= 3 for item in sample_selection)


def test_mixed_path_company_uses_shareholder_structures_and_preserves_labels(
    db_session,
    visualization_module,
    sample_selection,
):
    mixed_sample = _pick_sample(sample_selection, mixed=True)
    assert mixed_sample is not None

    context = visualization_module.load_visualization_context(db_session)
    data = visualization_module.load_company_visualization_data(
        db_session,
        mixed_sample["company_id"],
        context=context,
    )
    assert data is not None
    assert data["raw_edge_count"] > 0
    assert data["mixed_path_visible"] is True
    assert data["mixed_path_examples"]

    display_types = {edge["display_control_type"] for edge in data["raw_edges"]}
    assert any(visualization_module.is_equity_like(control_type) for control_type in display_types)
    assert any(
        control_type not in {"unknown", ""}
        and not visualization_module.is_equity_like(control_type)
        for control_type in display_types
    )
    assert any(edge["label"].startswith("equity ") for edge in data["raw_edges"])
    assert any(
        edge["label"] in {"agreement", "voting_right", "board_control", "nominee", "vie", "other"}
        or edge["label"].startswith("agreement")
        or edge["label"].startswith("voting_right")
        or edge["label"].startswith("board_control")
        for edge in data["raw_edges"]
    )


def test_visual_graph_uses_entity_type_categories_and_multiline_labels(
    db_session,
    visualization_module,
):
    context = visualization_module.load_visualization_context(db_session)
    data = visualization_module.load_company_visualization_data(
        db_session,
        3,
        context=context,
    )
    assert data is not None

    graph = visualization_module.build_visual_graph(data, context=context)
    nodes_by_name = {
        attrs["display_name"]: attrs
        for _, attrs in graph.nodes(data=True)
    }

    assert nodes_by_name["Joe Tsai"]["visual_category"] == "person"
    assert nodes_by_name["Public Float - Greater China"]["visual_category"] == "public_float"
    assert nodes_by_name["Alibaba Partnership"]["visual_category"] == "company"
    assert "\n" in nodes_by_name["JPMorgan Chase & Co."]["label"]


def test_batch_generation_outputs_five_html_files_and_report(
    db_session,
    visualization_module,
    sample_selection,
    tmp_path: Path,
):
    context = visualization_module.load_visualization_context(db_session)
    company_ids = [item["company_id"] for item in sample_selection]

    report = visualization_module.generate_visualization_batch(
        db_session,
        company_ids,
        context=context,
        output_dir=tmp_path,
        selection_metadata=sample_selection,
    )

    assert report["database_url"].endswith("company_import_test.db")
    assert report["success_count"] == 5
    assert report["failure_count"] == 0

    html_files = sorted(tmp_path.glob("*.html"))
    json_files = sorted(tmp_path.glob("*.json"))
    assert len(html_files) == 5
    assert len(json_files) >= 6
    assert (tmp_path / "control_chain_full_visualization_report.json").exists()

    combined_html = "\n".join(
        html_file.read_text(encoding="utf-8") for html_file in html_files
    )
    assert "equity" in combined_html
    assert any(
        marker in combined_html
        for marker in ["agreement", "voting_right", "board_control", "nominee", "vie"]
    )
    assert any(item["mixed_path_visible"] for item in report["results"])


