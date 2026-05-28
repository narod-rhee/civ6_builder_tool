"""Extract Civilization VI XML mod data into a reusable JSON profile.

Sample usage:
    python xml_profile_extractor.py extract path/to/mod --out extracted_profile.json
    python xml_profile_extractor.py summarize extracted_profile.json
    python xml_profile_extractor.py copilot extracted_profile.json --out copilot_prefill.json

This module is intentionally offline-only. It never calls OpenAI, never makes
network requests, and never edits source XML files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any


PROFILE_KEYS = [
    "civilizations",
    "leaders",
    "leader_links",
    "traits",
    "units",
    "buildings",
    "districts",
    "improvements",
    "named_geography",
    "city_names",
    "icons",
    "atlases",
    "modifiers",
    "modifier_arguments",
]

TABLE_TO_KEY = {
    "Civilizations": "civilizations",
    "Leaders": "leaders",
    "CivilizationLeaders": "leader_links",
    "Traits": "traits",
    "CivilizationTraits": "traits",
    "LeaderTraits": "traits",
    "TraitModifiers": "modifiers",
    "Modifiers": "modifiers",
    "ModifierArguments": "modifier_arguments",
    "Types": "unknown_tables",
    "Units": "units",
    "Buildings": "buildings",
    "Districts": "districts",
    "Improvements": "improvements",
    "NamedRiverCivilizations": "named_geography",
    "NamedLakes": "named_geography",
    "NamedLakeCivilizations": "named_geography",
    "NamedSeas": "named_geography",
    "NamedSeaCivilizations": "named_geography",
    "NamedDeserts": "named_geography",
    "NamedDesertCivilizations": "named_geography",
    "NamedVolcanoes": "named_geography",
    "NamedVolcanoCivilizations": "named_geography",
    "NamedMountainCivilizations": "named_geography",
    "CityNames": "city_names",
    "LocalizedText": "localized_text",
    "BaseGameText": "localized_text",
    "IconDefinitions": "icons",
    "IconTextureAtlases": "atlases",
}

SUPPORTED_OPERATIONS = {"Row", "Update", "Replace", "Delete"}


class ExtractorError(RuntimeError):
    """Raised for clear CLI-facing extraction errors."""


def empty_profile(source: Path) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "source": str(source),
        "files": [],
        "warnings": [],
        "localized_text": {},
        "localized_text_variants": {},
        "unknown_tables": {},
    }
    for key in PROFILE_KEYS:
        profile[key] = []
    return profile


def extract_path(input_path: Path, out_path: Path | None = None) -> dict[str, Any]:
    source = input_path.resolve()
    if not source.exists():
        raise ExtractorError(f"Input path does not exist: {input_path}")
    files = xml_files_for_path(source)
    if not files:
        raise ExtractorError(f"No .xml files found under: {input_path}")

    profile = empty_profile(source)
    for file_path in files:
        profile["files"].append(str(file_path))
        extract_file(file_path, profile)

    profile["summary"] = summarize_profile(profile, print_output=False)
    if out_path:
        write_json(out_path, profile)
    return profile


def xml_files_for_path(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() != ".xml":
            raise ExtractorError(f"Input file is not an XML file: {path}")
        return [path.resolve()]
    if not path.is_dir():
        raise ExtractorError(f"Input path is not a file or folder: {path}")
    return sorted(item.resolve() for item in path.rglob("*.xml") if item.is_file())


def extract_file(file_path: Path, profile: dict[str, Any]) -> None:
    try:
        tree = ET.parse(file_path)
    except ET.ParseError as exc:
        profile["warnings"].append(f"{file_path}: XML parse error: {exc}")
        return
    except OSError as exc:
        profile["warnings"].append(f"{file_path}: could not read file: {exc}")
        return

    root = tree.getroot()
    root_name = strip_namespace(root.tag)
    if root_name in TABLE_TO_KEY and root_name != "GameData":
        if TABLE_TO_KEY[root_name] == "localized_text":
            extract_localized_text_table(root, file_path, profile, root_name)
        else:
            rows = extract_table_operations(root, file_path, root_name)
            if rows:
                profile[TABLE_TO_KEY[root_name]].extend(rows)
        return

    for table in list(root):
        table_name = strip_namespace(table.tag)
        target_key = TABLE_TO_KEY.get(table_name)
        if target_key is None:
            target_key = "unknown_tables"

        if target_key == "localized_text":
            extract_localized_text_table(table, file_path, profile, table_name)
            continue

        rows = extract_table_operations(table, file_path, table_name)
        if not rows:
            continue
        if target_key == "unknown_tables":
            bucket = profile["unknown_tables"].setdefault(table_name, [])
            bucket.extend(rows)
        else:
            profile[target_key].extend(rows)


def extract_table_operations(table: ET.Element, file_path: Path, table_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for child in list(table):
        operation = strip_namespace(child.tag)
        if operation not in SUPPORTED_OPERATIONS:
            continue
        record = operation_record(child, operation, file_path, table_name)
        rows.append(record)
    return rows


def operation_record(element: ET.Element, operation: str, file_path: Path, table_name: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "table": table_name,
        "operation": operation,
        "attributes": dict(element.attrib),
        "source_file": str(file_path),
    }
    children = []
    for child in list(element):
        children.append(
            {
                "tag": strip_namespace(child.tag),
                "attributes": dict(child.attrib),
                "text": text_or_empty(child),
                "children": [
                    {
                        "tag": strip_namespace(grandchild.tag),
                        "attributes": dict(grandchild.attrib),
                        "text": text_or_empty(grandchild),
                    }
                    for grandchild in list(child)
                ],
            }
        )
    if children:
        record["children"] = children
    if operation in {"Update", "Delete"}:
        where = first_child(element, "Where")
        if where is not None:
            record["where"] = dict(where.attrib)
        set_node = first_child(element, "Set")
        if set_node is not None:
            record["set"] = dict(set_node.attrib)
    return record


def extract_localized_text_table(
    table: ET.Element,
    file_path: Path,
    profile: dict[str, Any],
    table_name: str,
) -> None:
    for child in list(table):
        operation = strip_namespace(child.tag)
        if operation not in SUPPORTED_OPERATIONS:
            continue
        tag = child.attrib.get("Tag")
        text = text_from_localized_row(child)
        record = operation_record(child, operation, file_path, table_name)
        if tag and text is not None and operation in {"Row", "Replace"}:
            if tag not in profile["localized_text"]:
                profile["localized_text"][tag] = text
            language = child.attrib.get("Language", "")
            if language:
                profile["localized_text_variants"].setdefault(tag, {})[language] = text
        if operation != "Row" or not tag:
            profile["unknown_tables"].setdefault(table_name, []).append(record)


def text_from_localized_row(row: ET.Element) -> str | None:
    text_child = first_child(row, "Text")
    if text_child is not None:
        return text_or_empty(text_child)
    if row.text and row.text.strip():
        return row.text.strip()
    return None


def first_child(element: ET.Element, local_name: str) -> ET.Element | None:
    for child in list(element):
        if strip_namespace(child.tag) == local_name:
            return child
    return None


def strip_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def text_or_empty(element: ET.Element) -> str:
    return "".join(element.itertext()).strip()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    target = path.resolve()
    if target.exists() and target.is_dir():
        raise ExtractorError(f"Output path is a directory: {path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_profile(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ExtractorError(f"Profile JSON does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ExtractorError(f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ExtractorError("Profile JSON must be an object.")
    return data


def summarize_profile(profile: dict[str, Any], print_output: bool = True) -> dict[str, Any]:
    summary = {
        "civilizations": typed_values(profile.get("civilizations", []), "CivilizationType"),
        "leaders": typed_values(profile.get("leaders", []), "LeaderType"),
        "units": typed_values(profile.get("units", []), "UnitType"),
        "buildings": typed_values(profile.get("buildings", []), "BuildingType"),
        "districts": typed_values(profile.get("districts", []), "DistrictType"),
        "improvements": typed_values(profile.get("improvements", []), "ImprovementType"),
        "named_geography_count": len(profile.get("named_geography", [])),
        "localized_text_count": len(profile.get("localized_text", {})),
        "modifier_count": len(profile.get("modifiers", [])),
        "modifier_argument_count": len(profile.get("modifier_arguments", [])),
        "warnings": profile.get("warnings", []),
    }
    if print_output:
        print_summary(summary)
    return summary


def print_summary(summary: dict[str, Any]) -> None:
    print("Detected Civilization VI XML profile")
    for key in ["civilizations", "leaders", "units", "buildings", "districts", "improvements"]:
        values = summary[key]
        label = key.replace("_", " ").title()
        print(f"{label}: {len(values)}")
        for value in values[:20]:
            print(f"  - {value}")
        if len(values) > 20:
            print(f"  ... {len(values) - 20} more")
    print(f"LOC keys: {summary['localized_text_count']}")
    print(f"Named geography rows: {summary.get('named_geography_count', 0)}")
    print(f"Modifiers: {summary['modifier_count']}")
    print(f"Modifier arguments: {summary['modifier_argument_count']}")
    warnings = summary.get("warnings", [])
    print(f"Warnings: {len(warnings)}")
    for warning in warnings[:20]:
        print(f"  - {warning}")


def typed_values(rows: list[dict[str, Any]], preferred_key: str) -> list[str]:
    values = []
    for row in rows:
        attrs = row.get("attributes", {})
        value = attrs.get(preferred_key) or attrs.get("Type") or attrs.get("TraitType") or attrs.get("Name")
        if value:
            values.append(str(value))
    return unique(values)


def profile_to_copilot_prefill(profile: dict[str, Any]) -> dict[str, Any]:
    localized = profile.get("localized_text", {})
    leader_ids = detect_current_leader_ids(profile)
    if leader_ids:
        profile = prune_profile_to_leaders(profile, leader_ids)

    civilizations = build_civilization_prefill(profile, localized)
    leaders = build_leader_prefill(profile, localized)
    mod_code = infer_mod_code(civilizations, leaders)
    detected_icons = detect_icons(profile)
    localization_keys = sorted(localized.keys())

    return {
        "schema": "icon_forge_copilot_prefill_v1",
        "source_profile": profile.get("source", ""),
        "mod_code": mod_code,
        "civilization_names": [item["name"] for item in civilizations],
        "leader_names": [item["name"] for item in leaders],
        "unit_names": names_for_rows(profile.get("units", []), "UnitType", localized),
        "building_names": names_for_rows(profile.get("buildings", []), "BuildingType", localized),
        "district_names": names_for_rows(profile.get("districts", []), "DistrictType", localized),
        "improvement_names": names_for_rows(profile.get("improvements", []), "ImprovementType", localized),
        "governor_names": [],
        "named_geography": named_geography_summary(profile, localized),
        "city_names": city_names(profile, localized),
        "localization_keys": localization_keys,
        "detected_icons": detected_icons,
        "civilization_profiles": civilizations,
        "leader_bindings": leaders,
        "warnings": profile.get("warnings", []),
    }


def detect_current_leader_ids(profile: dict[str, Any]) -> set[str]:
    ids = set()
    for row in profile.get("leaders", []):
        attrs = row.get("attributes", {})
        value = attrs.get("LeaderType") or attrs.get("Type")
        if value:
            ids.add(str(value))
    for row in profile.get("leader_links", []):
        value = row.get("attributes", {}).get("LeaderType")
        if value:
            ids.add(str(value))
    return ids


def prune_profile_to_leaders(profile: dict[str, Any], leader_ids: set[str]) -> dict[str, Any]:
    pruned = dict(profile)
    pruned["leaders"] = [
        row for row in profile.get("leaders", [])
        if row_id(row, "LeaderType") in leader_ids or row_id(row, "Type") in leader_ids
    ]
    pruned["leader_links"] = [
        row for row in profile.get("leader_links", [])
        if row.get("attributes", {}).get("LeaderType") in leader_ids
    ]
    pruned["traits"] = [
        row for row in profile.get("traits", [])
        if row.get("table") != "LeaderTraits" or row.get("attributes", {}).get("LeaderType") in leader_ids
    ]
    pruned.setdefault("warnings", list(profile.get("warnings", [])))
    removed = len(profile.get("leaders", [])) - len(pruned["leaders"])
    if removed > 0:
        pruned["warnings"].append(f"Pruned {removed} leader row(s) that did not match detected current leader IDs.")
    return pruned


def build_civilization_prefill(profile: dict[str, Any], localized: dict[str, str]) -> list[dict[str, Any]]:
    profiles = []
    city_by_civ = defaultdict(list)
    for row in profile.get("city_names", []):
        attrs = row.get("attributes", {})
        civ_id = attrs.get("CivilizationType", "")
        city_key = attrs.get("CityName", "")
        if civ_id and city_key:
            city_by_civ[civ_id].append(localized.get(city_key, city_key))

    for index, row in enumerate(profile.get("civilizations", [])):
        attrs = row.get("attributes", {})
        civ_id = attrs.get("CivilizationType") or attrs.get("Type") or f"CIVILIZATION_{index + 1}"
        name_key = attrs.get("Name", "")
        adjective_key = attrs.get("Adjective", "")
        profiles.append(
            {
                "index": index,
                "id": civ_id,
                "name": localized.get(name_key, civ_id_to_name(civ_id)),
                "demonym": localized.get(adjective_key, ""),
                "city_names": city_by_civ.get(civ_id, []),
                "citizen_names": citizen_names_for_civ(profile, civ_id, localized),
                "unit_names": names_for_rows(profile.get("units", []), "UnitType", localized)[:5],
                "building_names": names_for_rows(profile.get("buildings", []), "BuildingType", localized)[:5],
                "improvement_names": names_for_rows(profile.get("improvements", []), "ImprovementType", localized)[:5],
                "district_names": names_for_rows(profile.get("districts", []), "DistrictType", localized)[:5],
                "governor_names": [],
                "named_geography": named_geography_summary(profile, localized),
            }
        )
    return profiles


def build_leader_prefill(profile: dict[str, Any], localized: dict[str, str]) -> list[dict[str, Any]]:
    leader_to_civ = {}
    for row in profile.get("leader_links", []):
        attrs = row.get("attributes", {})
        leader = attrs.get("LeaderType")
        civ = attrs.get("CivilizationType")
        if leader and civ:
            leader_to_civ[leader] = civ

    civ_names = {
        civ["id"]: civ["name"]
        for civ in build_civilization_prefill(profile, localized)
    }
    leaders = []
    for index, row in enumerate(profile.get("leaders", [])):
        attrs = row.get("attributes", {})
        leader_id = attrs.get("LeaderType") or attrs.get("Type") or f"LEADER_{index + 1}"
        name_key = attrs.get("Name") or f"LOC_{leader_id}_NAME"
        civ_id = leader_to_civ.get(leader_id, "")
        leaders.append(
            {
                "index": index,
                "name": localized.get(name_key, civ_id_to_name(leader_id.removeprefix("LEADER_"))),
                "leader_id": leader_id,
                "civilization": civ_names.get(civ_id, civ_id),
                "civilization_id": civ_id,
            }
        )
    return leaders


def row_id(row: dict[str, Any], key: str) -> str:
    return str(row.get("attributes", {}).get(key, ""))


def names_for_rows(rows: list[dict[str, Any]], type_key: str, localized: dict[str, str]) -> list[str]:
    names = []
    for row in rows:
        attrs = row.get("attributes", {})
        name_key = attrs.get("Name")
        type_value = attrs.get(type_key) or attrs.get("Type")
        if name_key and name_key in localized:
            names.append(localized[name_key])
        elif type_value:
            names.append(civ_id_to_name(str(type_value)))
    return unique(names)


def citizen_names_for_civ(profile: dict[str, Any], civ_id: str, localized: dict[str, str]) -> list[str]:
    names = []
    for row in profile.get("unknown_tables", {}).get("CivilizationCitizenNames", []):
        attrs = row.get("attributes", {})
        if attrs.get("CivilizationType") == civ_id and attrs.get("CitizenName"):
            key = attrs["CitizenName"]
            names.append(localized.get(key, key))
    return names


def city_names(profile: dict[str, Any], localized: dict[str, str]) -> list[str]:
    names = []
    for row in profile.get("city_names", []):
        key = row.get("attributes", {}).get("CityName")
        if key:
            names.append(localized.get(key, key))
    return unique(names)


def named_geography_summary(profile: dict[str, Any], localized: dict[str, str]) -> str:
    labels = {
        "NamedRiverType": "Rivers",
        "NamedLakeType": "Lakes",
        "NamedSeaType": "Seas",
        "NamedDesertType": "Deserts",
        "NamedVolcanoType": "Volcanoes",
        "NamedMountainType": "Mountains",
    }
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in profile.get("named_geography", []):
        attrs = row.get("attributes", {})
        for key, label in labels.items():
            if key in attrs:
                name_key = attrs.get("Name", "")
                value = localized.get(name_key, civ_id_to_name(str(attrs[key])))
                grouped[label].append(value)
                break
    lines = []
    for label in labels.values():
        values = unique(grouped.get(label, []))
        if values:
            lines.append(f"{label}: {', '.join(values)}")
    return "\n".join(lines)


def detect_icons(profile: dict[str, Any]) -> list[dict[str, Any]]:
    icons = []
    for row in profile.get("icons", []):
        attrs = row.get("attributes", {})
        if attrs:
            icons.append(dict(attrs))
    return icons


def infer_mod_code(civilizations: list[dict[str, Any]], leaders: list[dict[str, Any]]) -> str:
    for item in civilizations:
        civ_id = str(item.get("id", ""))
        if civ_id.startswith("CIVILIZATION_"):
            return civ_id.removeprefix("CIVILIZATION_")
    for item in leaders:
        leader_id = str(item.get("leader_id", ""))
        if leader_id.startswith("LEADER_"):
            return leader_id.removeprefix("LEADER_")
    return "IMPORTED_MOD"


def civ_id_to_name(value: str) -> str:
    cleaned = re.sub(r"^(CIVILIZATION|LEADER|UNIT|BUILDING|DISTRICT|IMPROVEMENT|GOVERNOR)_", "", value)
    return " ".join(part.capitalize() for part in cleaned.split("_") if part)


def unique(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def run_extract(args: argparse.Namespace) -> int:
    out = Path(args.out or "extracted_profile.json")
    profile = extract_path(Path(args.path), out)
    summary = profile.get("summary") or summarize_profile(profile, print_output=False)
    print_summary(summary)
    print(f"Wrote {out}")
    return 0


def run_summarize(args: argparse.Namespace) -> int:
    profile = load_profile(Path(args.profile))
    summarize_profile(profile, print_output=True)
    return 0


def run_copilot(args: argparse.Namespace) -> int:
    profile = load_profile(Path(args.profile))
    prefill = profile_to_copilot_prefill(profile)
    out = Path(args.out or "copilot_prefill.json")
    write_json(out, prefill)
    print(f"Wrote {out}")
    print(f"Civilizations: {len(prefill['civilization_names'])}")
    print(f"Leaders: {len(prefill['leader_names'])}")
    print(f"LOC keys: {len(prefill['localization_keys'])}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract Civ VI XML data into a clean JSON profile.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract", help="Extract XML files from one file or folder.")
    extract.add_argument("path", help="XML file or folder to scan recursively.")
    extract.add_argument("--out", default="extracted_profile.json", help="Output JSON path.")
    extract.set_defaults(func=run_extract)

    summarize = subparsers.add_parser("summarize", help="Print a profile summary.")
    summarize.add_argument("profile", help="extracted_profile.json path.")
    summarize.set_defaults(func=run_summarize)

    copilot = subparsers.add_parser("copilot", help="Convert extracted profile into Template Copilot prefill JSON.")
    copilot.add_argument("profile", help="extracted_profile.json path.")
    copilot.add_argument("--out", default="copilot_prefill.json", help="Output prefill JSON path.")
    copilot.set_defaults(func=run_copilot)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ExtractorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
