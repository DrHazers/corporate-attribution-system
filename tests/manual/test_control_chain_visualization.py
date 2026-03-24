from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import networkx as nx
from pyvis.network import Network

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.analysis.control_chain import analyze_control_chain
from backend.crud.company import get_company_by_id
from backend.database import SessionLocal
from backend.models.company import Company  # noqa: F401
from backend.models.control_relationship import ControlRelationship  # noqa: F401
from backend.models.country_attribution import CountryAttribution  # noqa: F401
from backend.models.shareholder import ShareholderEntity

OUTPUT_DIR = PROJECT_ROOT / "tests" / "output"
MANUAL_COMPANY_ID: int | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an interactive control-chain visualization HTML file.",
    )
    parser.add_argument(
        "--company-id",
        type=int,
        help="Target company_id from the companies table.",
    )
    return parser.parse_args()


def _serialize_company(company) -> dict[str, Any]:
    return {
        "id": company.id,
        "name": company.name,
        "stock_code": company.stock_code,
        "incorporation_country": company.incorporation_country,
        "listing_country": company.listing_country,
        "headquarters": company.headquarters,
        "description": company.description,
    }


def load_company_analysis_data(db, company_id: int) -> dict[str, Any] | None:
    company = get_company_by_id(db, company_id)
    if company is None:
        return None

    control_chain_data = analyze_control_chain(db, company_id)
    control_relationships = control_chain_data["control_relationships"]
    actual_controllers = [
        relationship
        for relationship in control_relationships
        if relationship["is_actual_controller"]
    ]

    return {
        "company": _serialize_company(company),
        "control_relationships": control_relationships,
        "actual_controllers": actual_controllers,
        "actual_controller": control_chain_data["actual_controller"],
    }


def _make_virtual_node_id(
    relationship: dict[str, Any],
    index: int,
    node_name: str,
) -> str:
    safe_name = node_name.strip() or f"unknown_{index}"
    return f"virtual:{relationship['id']}:{index}:{safe_name}"


def _normalize_path_item(
    company: dict[str, Any],
    relationship: dict[str, Any],
    raw_path: Any,
    path_index: int,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(raw_path, dict):
        return (
            None,
            (
                f"Relationship {relationship['id']} path item {path_index} "
                "is not a JSON object and was skipped."
            ),
        )

    path_entity_names = raw_path.get("path_entity_names")
    if not isinstance(path_entity_names, list) or len(path_entity_names) < 2:
        return (
            None,
            (
                f"Relationship {relationship['id']} path item {path_index} "
                "missing usable path_entity_names and was skipped."
            ),
        )

    path_entity_ids = raw_path.get("path_entity_ids")
    if not isinstance(path_entity_ids, list) or len(path_entity_ids) != len(
        path_entity_names
    ):
        rebuilt_entity_ids: list[int | str] = []
        for node_index, node_name in enumerate(path_entity_names):
            if node_index == 0 and relationship["controller_entity_id"] is not None:
                rebuilt_entity_ids.append(relationship["controller_entity_id"])
            elif node_index == len(path_entity_names) - 1:
                rebuilt_entity_ids.append(company["id"])
            else:
                rebuilt_entity_ids.append(
                    _make_virtual_node_id(relationship, node_index, node_name)
                )
        path_entity_ids = rebuilt_entity_ids

    edge_holding_ratio_pct = raw_path.get("edge_holding_ratio_pct")
    if not isinstance(edge_holding_ratio_pct, list):
        edge_holding_ratio_pct = []

    path_ratio_pct = raw_path.get("path_ratio_pct") or raw_path.get("ratio_pct")

    return (
        {
            "relationship_id": relationship["id"],
            "controller_entity_id": relationship["controller_entity_id"],
            "controller_name": relationship["controller_name"],
            "controller_type": relationship["controller_type"],
            "control_ratio": relationship["control_ratio"],
            "is_actual_controller": relationship["is_actual_controller"],
            "source": "control_path_json",
            "path_entity_ids": path_entity_ids,
            "path_entity_names": path_entity_names,
            "edge_holding_ratio_pct": [str(item) for item in edge_holding_ratio_pct],
            "path_ratio_pct": str(path_ratio_pct) if path_ratio_pct is not None else None,
        },
        None,
    )


def parse_control_paths(
    company: dict[str, Any],
    control_relationships: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    parsed_paths: list[dict[str, Any]] = []
    warnings: list[str] = []

    for relationship in control_relationships:
        raw_control_path = relationship.get("control_path")
        if raw_control_path in (None, ""):
            warnings.append(
                f"Relationship {relationship['id']} has empty control_path and was skipped."
            )
            continue

        payload = raw_control_path
        if isinstance(raw_control_path, str):
            try:
                payload = json.loads(raw_control_path)
            except json.JSONDecodeError as exc:
                warnings.append(
                    (
                        f"Relationship {relationship['id']} control_path JSON parse "
                        f"failed: {exc}"
                    )
                )
                continue

        path_items: list[Any] = []
        if isinstance(payload, dict):
            best_path = payload.get("best_path")
            paths_top_k = payload.get("paths_top_k")
            if best_path is not None:
                path_items.append(best_path)
            if isinstance(paths_top_k, list):
                path_items.extend(paths_top_k)
            if not path_items and "path_entity_names" in payload:
                path_items.append(payload)
        elif isinstance(payload, list):
            path_items.extend(payload)
        else:
            warnings.append(
                (
                    f"Relationship {relationship['id']} control_path JSON shape is "
                    "unsupported and was skipped."
                )
            )
            continue

        if not path_items:
            warnings.append(
                (
                    f"Relationship {relationship['id']} has no usable path items and "
                    "was skipped."
                )
            )
            continue

        for path_index, raw_path in enumerate(path_items):
            normalized_path, warning_message = _normalize_path_item(
                company,
                relationship,
                raw_path,
                path_index,
            )
            if warning_message is not None:
                warnings.append(warning_message)
            if normalized_path is not None:
                parsed_paths.append(normalized_path)

    return parsed_paths, warnings


def _load_entity_type_map(
    db,
    parsed_paths: list[dict[str, Any]],
) -> dict[int, str]:
    entity_ids: set[int] = set()
    for path in parsed_paths:
        for node_id in path["path_entity_ids"]:
            if isinstance(node_id, int):
                entity_ids.add(node_id)

    if not entity_ids:
        return {}

    entities = (
        db.query(ShareholderEntity)
        .filter(ShareholderEntity.id.in_(sorted(entity_ids)))
        .all()
    )
    return {entity.id: entity.entity_type for entity in entities}


def build_visual_graph(
    company: dict[str, Any],
    control_relationships: list[dict[str, Any]],
    parsed_paths: list[dict[str, Any]],
    entity_type_map: dict[int, str],
) -> nx.DiGraph:
    graph = nx.DiGraph()
    target_node_key = f"company:{company['id']}"
    max_path_length = max(
        (len(path["path_entity_names"]) for path in parsed_paths),
        default=1,
    )

    graph.add_node(
        target_node_key,
        label=company["name"],
        level=max_path_length - 1,
        node_role="target_company",
        entity_id=company["id"],
        entity_type="company",
        title=(
            f"<b>{company['name']}</b><br/>"
            f"Entity ID: {company['id']}<br/>"
            "Role: Target Company<br/>"
            f"Stock Code: {company['stock_code']}"
        ),
    )

    relationship_lookup = {
        relationship["id"]: relationship for relationship in control_relationships
    }

    for path in parsed_paths:
        relationship = relationship_lookup[path["relationship_id"]]
        path_length = len(path["path_entity_names"])
        offset = max_path_length - path_length
        node_chain: list[str] = []

        for index, node_name in enumerate(path["path_entity_names"]):
            raw_node_id = path["path_entity_ids"][index]
            is_target = index == path_length - 1

            if is_target:
                node_key = target_node_key
                node_role = "target_company"
                entity_id = company["id"]
                entity_type = "company"
                title = (
                    f"<b>{company['name']}</b><br/>"
                    f"Entity ID: {company['id']}<br/>"
                    "Role: Target Company<br/>"
                    f"Stock Code: {company['stock_code']}"
                )
            else:
                if isinstance(raw_node_id, int):
                    node_key = f"entity:{raw_node_id}"
                    entity_id = raw_node_id
                else:
                    node_key = str(raw_node_id)
                    entity_id = None

                if index == 0 and relationship["is_actual_controller"]:
                    node_role = "actual_controller"
                    role_label = "Actual Controller"
                elif index == 0:
                    node_role = "significant_controller"
                    role_label = "Significant Controller"
                else:
                    node_role = "intermediate"
                    role_label = "Intermediate Holder"

                if index == 0:
                    entity_type = relationship["controller_type"]
                elif isinstance(raw_node_id, int):
                    entity_type = entity_type_map.get(raw_node_id, "unknown")
                else:
                    entity_type = "unknown"

                entity_id_label = entity_id if entity_id is not None else "N/A"
                title = (
                    f"<b>{node_name}</b><br/>"
                    f"Entity ID: {entity_id_label}<br/>"
                    f"Entity Type: {entity_type}<br/>"
                    f"Role: {role_label}<br/>"
                    f"Relationship ID: {relationship['id']}"
                )

            level = index + offset
            if graph.has_node(node_key):
                graph.nodes[node_key]["level"] = min(
                    graph.nodes[node_key]["level"],
                    level,
                )
            else:
                graph.add_node(
                    node_key,
                    label=node_name if not is_target else company["name"],
                    level=level,
                    node_role=node_role,
                    entity_id=entity_id,
                    entity_type=entity_type,
                    title=title,
                )

            node_chain.append(node_key)

        for edge_index in range(len(node_chain) - 1):
            source = node_chain[edge_index]
            target = node_chain[edge_index + 1]
            edge_ratios = path["edge_holding_ratio_pct"]
            ratio_label = None
            if edge_index < len(edge_ratios):
                ratio_label = edge_ratios[edge_index]
            if ratio_label is None:
                ratio_label = path["path_ratio_pct"] or relationship["control_ratio"]

            edge_title = (
                f"Relationship ID: {relationship['id']}<br/>"
                f"Controller: {relationship['controller_name']}<br/>"
                f"Control Ratio: {relationship['control_ratio'] or 'N/A'}<br/>"
                f"Path Contribution: {path['path_ratio_pct'] or 'N/A'}<br/>"
                f"Source: {path['source']}"
            )

            if graph.has_edge(source, target):
                graph[source][target]["labels"].add(f"{ratio_label}%")
                graph[source][target]["titles"].append(edge_title)
            else:
                graph.add_edge(
                    source,
                    target,
                    labels={f"{ratio_label}%"},
                    titles=[edge_title],
                )

    return graph


def export_html_graph(
    graph: nx.DiGraph,
    company: dict[str, Any],
    html_path: Path,
) -> None:
    html_path.parent.mkdir(parents=True, exist_ok=True)

    net = Network(
        height="900px",
        width="100%",
        directed=True,
        bgcolor="#f8fafc",
        font_color="#111827",
        notebook=False,
        cdn_resources="remote",
    )
    net.heading = f"Control Chain Visualization - {company['name']}"

    role_styles = {
        "target_company": {
            "color": {"background": "#f59e0b", "border": "#b45309"},
            "shape": "box",
            "size": 36,
        },
        "actual_controller": {
            "color": {"background": "#ef4444", "border": "#991b1b"},
            "shape": "ellipse",
            "size": 28,
        },
        "significant_controller": {
            "color": {"background": "#2563eb", "border": "#1d4ed8"},
            "shape": "ellipse",
            "size": 24,
        },
        "intermediate": {
            "color": {"background": "#94a3b8", "border": "#475569"},
            "shape": "dot",
            "size": 18,
        },
    }

    for node_key, attrs in graph.nodes(data=True):
        style = role_styles.get(attrs["node_role"], role_styles["intermediate"])
        net.add_node(
            node_key,
            label=attrs["label"],
            title=attrs["title"],
            level=attrs["level"],
            color=style["color"],
            shape=style["shape"],
            size=style["size"],
        )

    for source, target, attrs in graph.edges(data=True):
        labels = sorted(attrs["labels"])
        label = labels[0] if len(labels) == 1 else " / ".join(labels[:3])
        title = "<br/><br/>".join(attrs["titles"])
        net.add_edge(
            source,
            target,
            label=label,
            title=title,
            arrows="to",
            color="#64748b",
        )

    net.set_options(
        """
        {
          "layout": {
            "hierarchical": {
              "enabled": true,
              "direction": "UD",
              "sortMethod": "directed",
              "levelSeparation": 150,
              "nodeSpacing": 220
            }
          },
          "physics": {
            "enabled": true,
            "hierarchicalRepulsion": {
              "nodeDistance": 180
            },
            "solver": "hierarchicalRepulsion"
          },
          "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true
          },
          "edges": {
            "smooth": {
              "enabled": true,
              "type": "cubicBezier",
              "roundness": 0.35
            },
            "font": {
              "align": "middle"
            }
          }
        }
        """
    )
    net.write_html(str(html_path), open_browser=False, notebook=False)


def export_debug_json(
    json_path: Path,
    company_data: dict[str, Any],
    actual_controllers: list[dict[str, Any]],
    control_relationships: list[dict[str, Any]],
    parsed_paths: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "company": company_data,
        "actual_controllers": actual_controllers,
        "all_control_relationships": control_relationships,
        "parsed_paths": parsed_paths,
        "warnings": warnings,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    company_id = args.company_id or MANUAL_COMPANY_ID
    if company_id is None:
        print(
            "Please provide --company-id, or set MANUAL_COMPANY_ID in the file.",
        )
        return 1

    db = SessionLocal()
    try:
        analysis_data = load_company_analysis_data(db, company_id)
        if analysis_data is None:
            print(f"Company with company_id={company_id} was not found.")
            return 1

        company = analysis_data["company"]
        control_relationships = analysis_data["control_relationships"]

        if not control_relationships:
            print(
                f"Company '{company['name']}' exists, but has no control_relationships.",
            )

        parsed_paths, warnings = parse_control_paths(company, control_relationships)
        entity_type_map = _load_entity_type_map(db, parsed_paths)
        graph = build_visual_graph(
            company,
            control_relationships,
            parsed_paths,
            entity_type_map,
        )

        html_path = OUTPUT_DIR / f"control_chain_company_{company_id}.html"
        json_path = OUTPUT_DIR / f"control_chain_company_{company_id}.json"

        export_html_graph(graph, company, html_path)
        export_debug_json(
            json_path,
            company,
            analysis_data["actual_controllers"],
            control_relationships,
            parsed_paths,
            warnings,
        )

        for warning in warnings:
            print(f"[WARN] {warning}")

        print(f"Company: {company['name']}")
        print(f"Control relationships: {len(control_relationships)}")
        print(f"Parsed paths: {len(parsed_paths)}")
        print(f"HTML output: {html_path.resolve()}")
        print(f"JSON output: {json_path.resolve()}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
