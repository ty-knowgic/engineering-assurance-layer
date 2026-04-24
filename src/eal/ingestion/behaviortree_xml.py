"""
Narrow BehaviorTree XML ingestion.

Supported subset is intentionally small:
- Structural nodes: Sequence, Fallback
- Decorators: Timeout with explicit msec, Precondition with explicit expression-like attr
- Leaves: Action and Condition with ID/name, plus simple custom leaf tags

This module does not implement full BehaviorTree.CPP semantics. It extracts
review-relevant evidence only: leaf names, explicit timeout values, explicit
precondition/condition text, and simple fallback branch visibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from eal.ingestion.loaders import ModelDocument

_CONTROL_NODES = {"Sequence", "Fallback"}
_DECORATOR_NODES = {"Timeout", "Precondition"}
_TRANSPARENT_NODES = {"root", "BehaviorTree"}
_LEAF_NODES = {"Action", "Condition"}
_NAME_ATTRS = ("ID", "name")
_PRECONDITION_ATTRS = ("if", "condition", "expression", "cond")


@dataclass(frozen=True)
class BTLeaf:
    name: str
    kind: str
    attributes: dict[str, str]
    path: tuple[str, ...]


@dataclass(frozen=True)
class BTTimeout:
    msec: int
    target: str | None
    path: tuple[str, ...]


@dataclass(frozen=True)
class BTPrecondition:
    expression: str
    target: str | None
    path: tuple[str, ...]


@dataclass(frozen=True)
class BTFallback:
    name: str
    primary: str | None
    alternates: tuple[str, ...]
    path: tuple[str, ...]


@dataclass(frozen=True)
class BehaviorTreeXMLSlice:
    path: Path
    leaves: tuple[BTLeaf, ...] = field(default_factory=tuple)
    timeouts: tuple[BTTimeout, ...] = field(default_factory=tuple)
    preconditions: tuple[BTPrecondition, ...] = field(default_factory=tuple)
    fallbacks: tuple[BTFallback, ...] = field(default_factory=tuple)
    unsupported_nodes: tuple[str, ...] = field(default_factory=tuple)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _node_name(elem: ET.Element) -> str:
    for attr in _NAME_ATTRS:
        value = elem.attrib.get(attr)
        if value:
            return value
    return _local_name(elem.tag)


def _normalize_name(name: str) -> str:
    """Convert BT leaf names to stable EAL-ish snake_case symbols."""
    name = re.sub(r"[^0-9A-Za-z]+", "_", name).strip("_")
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return re.sub(r"_+", "_", name).lower()


def _first_leaf_name(elem: ET.Element) -> str | None:
    tag = _local_name(elem.tag)
    if tag in _LEAF_NODES or (not list(elem) and tag not in _TRANSPARENT_NODES):
        return _node_name(elem)
    for child in list(elem):
        found = _first_leaf_name(child)
        if found:
            return found
    return None


def _children_leaf_roots(elem: ET.Element) -> list[str]:
    roots: list[str] = []
    for child in list(elem):
        found = _first_leaf_name(child)
        if found:
            roots.append(found)
    return roots


def parse_bt_xml(path: Path) -> BehaviorTreeXMLSlice:
    """Parse a narrow BT XML slice into deterministic review evidence."""
    tree = ET.parse(path)
    root = tree.getroot()
    leaves: list[BTLeaf] = []
    timeouts: list[BTTimeout] = []
    preconditions: list[BTPrecondition] = []
    fallbacks: list[BTFallback] = []
    unsupported: list[str] = []

    def visit(elem: ET.Element, path_parts: tuple[str, ...]) -> None:
        tag = _local_name(elem.tag)
        name = _node_name(elem)
        current_path = path_parts + (f"{tag}:{name}",)
        children = list(elem)

        if tag == "Timeout":
            raw_msec = elem.attrib.get("msec")
            if raw_msec is not None:
                try:
                    timeouts.append(BTTimeout(
                        msec=int(raw_msec),
                        target=_first_leaf_name(elem),
                        path=current_path,
                    ))
                except ValueError:
                    unsupported.append("Timeout[msec=non-integer]")

        if tag == "Precondition":
            expression = next(
                (elem.attrib[attr] for attr in _PRECONDITION_ATTRS if elem.attrib.get(attr)),
                None,
            )
            if expression:
                preconditions.append(BTPrecondition(
                    expression=expression,
                    target=_first_leaf_name(elem),
                    path=current_path,
                ))
            else:
                unsupported.append("Precondition[missing expression attr]")

        if tag == "Fallback":
            roots = _children_leaf_roots(elem)
            if roots:
                fallbacks.append(BTFallback(
                    name=name,
                    primary=roots[0],
                    alternates=tuple(roots[1:]),
                    path=current_path,
                ))

        is_known_leaf = tag in _LEAF_NODES
        is_custom_leaf = not children and tag not in _TRANSPARENT_NODES | _CONTROL_NODES | _DECORATOR_NODES
        if is_known_leaf or is_custom_leaf:
            kind = tag.lower()
            leaves.append(BTLeaf(
                name=name,
                kind=kind,
                attributes={str(k): str(v) for k, v in elem.attrib.items()},
                path=current_path,
            ))

        if (
            tag not in _TRANSPARENT_NODES
            and tag not in _CONTROL_NODES
            and tag not in _DECORATOR_NODES
            and tag not in _LEAF_NODES
            and children
        ):
            unsupported.append(tag)

        for child in children:
            visit(child, current_path)

    visit(root, ())
    return BehaviorTreeXMLSlice(
        path=path,
        leaves=tuple(leaves),
        timeouts=tuple(timeouts),
        preconditions=tuple(preconditions),
        fallbacks=tuple(fallbacks),
        unsupported_nodes=tuple(dict.fromkeys(unsupported)),
    )


def bt_xml_slice_to_model_data(bt: BehaviorTreeXMLSlice) -> dict:
    """
    Convert BT evidence into the existing model-shaped ingestion plane.

    The generated model data is deliberately conservative. Conditions become
    boolean internal signals, actions become states for traceability, explicit
    Timeout[msec] values become timing parameters, and explicit preconditions /
    condition leaves / fallbacks become assumptions so current review rules can
    see the declared guard and recovery intent.
    """
    condition_names = {
        _normalize_name(leaf.name)
        for leaf in bt.leaves
        if leaf.kind.lower() == "condition"
    }
    action_names = [
        leaf.name
        for leaf in bt.leaves
        if leaf.kind.lower() != "condition"
    ]

    data: dict = {
        "entities": [
            {
                "name": "bt_xml_slice",
                "description": "Narrow BehaviorTree XML ingestion evidence",
            }
        ],
        "signals": [
            {
                "name": name,
                "kind": "internal",
                "unit": "bool",
                "bounds": {"min": 0, "max": 1},
            }
            for name in sorted(condition_names)
        ],
        "states": [
            {"name": _normalize_name(name).upper(), "description": f"BT action leaf {name}"}
            for name in sorted(set(action_names))
        ],
        "parameters": {},
        "assumptions": [],
    }

    parameters = data["parameters"]
    for timeout in bt.timeouts:
        target = _normalize_name(timeout.target or "bt_action")
        parameters[f"bt_timeout_{target}_ms"] = timeout.msec

    assumptions = data["assumptions"]
    for leaf in bt.leaves:
        if leaf.kind.lower() == "condition":
            signal = _normalize_name(leaf.name)
            assumptions.append(
                f"BT condition leaf '{leaf.name}' exposes guard intent for {signal}."
            )
    for precondition in bt.preconditions:
        target = precondition.target or "child"
        assumptions.append(
            f"BT Precondition before '{target}' explicitly requires {precondition.expression}."
        )
    for fallback in bt.fallbacks:
        alternates = ", ".join(fallback.alternates) if fallback.alternates else "none"
        assumptions.append(
            f"BT Fallback '{fallback.name}' uses primary '{fallback.primary}' with alternate recovery path(s): {alternates}."
        )

    return data


def load_bt_xml_model(path: Path) -> ModelDocument:
    """Load supported BT XML evidence as a model-shaped document."""
    bt = parse_bt_xml(path)
    data = bt_xml_slice_to_model_data(bt)
    if bt.unsupported_nodes:
        data["unsupported_bt_nodes"] = list(bt.unsupported_nodes)
    return ModelDocument(path=path, data=data)


__all__ = [
    "BTFallback",
    "BTLeaf",
    "BTPrecondition",
    "BTTimeout",
    "BehaviorTreeXMLSlice",
    "bt_xml_slice_to_model_data",
    "load_bt_xml_model",
    "parse_bt_xml",
]
