"""
Analysis coverage gaps — the UNKNOWN plane.

A Finding says "I analyzed this and found a problem".
A CoverageGap says "I could not analyze this, so my silence means nothing".

These are deliberately kept in separate planes. Severity is an *ordered* scale
used for gate thresholds (LOW < MEDIUM < HIGH < CRITICAL); coverage is
*orthogonal* to it. Folding UNKNOWN into FindingSeverity would corrupt
`severity_rank`, `highest_severity`, and every threshold comparison built on
them, and would let an unanalyzable input masquerade as a graded result.

The rule this module exists to enforce:

    When EAL was asked to analyze an input and could not, it must not report
    PASS in any machine-readable plane.

Categories:
  UNSUPPORTED_INPUT_CONSTRUCT — input contained constructs the importer does
      not model. Whatever was in those constructs was not checked.
  INPUT_YIELDED_NO_CONTENT    — an input file was explicitly provided but
      contributed nothing to the IR. Nothing about it was checked.
  NO_ANALYZABLE_CONTENT       — the merged IR has no signals, constraints, or
      transitions, so no rule or solver check could have fired at all.
  AMBIGUOUS_INPUT             — the same fact is declared more than once with
      conflicting values. The parser's reading may differ from what a human
      reading the file would conclude, so neither can be relied on.
  INCOMPLETE_COMPARISON       — a cross-artifact check ran but could not cover
      every quantity, because one side of the comparison is absent.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CoverageGapCategory(str, Enum):
    UNSUPPORTED_INPUT_CONSTRUCT = "UNSUPPORTED_INPUT_CONSTRUCT"
    INPUT_YIELDED_NO_CONTENT = "INPUT_YIELDED_NO_CONTENT"
    NO_ANALYZABLE_CONTENT = "NO_ANALYZABLE_CONTENT"
    AMBIGUOUS_INPUT = "AMBIGUOUS_INPUT"
    INCOMPLETE_COMPARISON = "INCOMPLETE_COMPARISON"


class AnalysisStatus(str, Enum):
    """
    Whether every supplied input could be read.

    Deliberately not named COMPLETE/INCOMPLETE. "Analysis complete" reads as
    "the analysis is finished and nothing is left to worry about", when all it
    ever meant was that the parser managed to consume its inputs. The names say
    what is actually being reported.
    """

    INPUTS_FULLY_READ = "INPUTS_FULLY_READ"
    INPUTS_NOT_FULLY_READ = "INPUTS_NOT_FULLY_READ"


class CoverageGap(BaseModel):
    """A region of the input that EAL did not analyze."""

    id: str = Field(description="Stable ID, e.g. U-001")
    category: CoverageGapCategory
    title: str
    summary: str
    affected_input: str = Field(default="", description="Path of the input not fully analyzed")
    unanalyzed_constructs: list[str] = Field(
        default_factory=list,
        description="Named constructs that were seen but not modelled",
    )
    suggested_fix: str = ""


def assign_gap_ids(gaps: list[CoverageGap]) -> list[CoverageGap]:
    """Re-assign stable U-NNN IDs in deterministic category order."""
    order = [c.value for c in CoverageGapCategory]
    ordered = sorted(gaps, key=lambda g: (order.index(g.category.value), g.affected_input, g.title))
    for i, g in enumerate(ordered, start=1):
        g.id = f"U-{i:03d}"
    return ordered


def analysis_status(gaps: list[CoverageGap]) -> AnalysisStatus:
    return (
        AnalysisStatus.INPUTS_NOT_FULLY_READ if gaps
        else AnalysisStatus.INPUTS_FULLY_READ
    )


def detect_coverage_gaps(
    ir,
    *,
    bt_xml_path=None,
    bt_unsupported_nodes: list[str] | None = None,
    bt_contributed: bool = True,
    model_path=None,
    model_contributed: bool = True,
    code_paths: list | None = None,
    nav2_params_path=None,
    nav2_unsupported: list[str] | None = None,
    nav2_contributed: bool = True,
    nav2_duplicate_keys: list[str] | None = None,
    nav2_unchecked_roles: list[str] | None = None,
) -> list[CoverageGap]:
    """
    Determine what EAL was asked to analyze but did not.

    Detection is intentionally conservative: a false UNKNOWN destroys trust in
    the gate just as surely as a false PASS does. Each rule below fires only on
    an unambiguous signal — an importer that named the constructs it dropped, an
    input that produced literally nothing, or an IR with nothing checkable in it.
    """
    gaps: list[CoverageGap] = []
    bt_unsupported_nodes = bt_unsupported_nodes or []
    nav2_unsupported = nav2_unsupported or []
    nav2_duplicate_keys = nav2_duplicate_keys or []
    nav2_unchecked_roles = nav2_unchecked_roles or []
    code_paths = code_paths or []

    # U1 — the importer told us what it threw away.
    if bt_xml_path is not None and bt_unsupported_nodes:
        gaps.append(CoverageGap(
            id="U-000",
            category=CoverageGapCategory.UNSUPPORTED_INPUT_CONSTRUCT,
            title=f"BehaviorTree XML contains {len(bt_unsupported_nodes)} unmodelled node type(s)",
            summary=(
                "The BehaviorTree importer skipped node types it does not model: "
                + ", ".join(bt_unsupported_nodes)
                + ". Control flow expressed through these nodes was not analyzed, so the "
                "absence of findings for those branches is not evidence of their correctness."
            ),
            affected_input=str(bt_xml_path),
            unanalyzed_constructs=list(bt_unsupported_nodes),
            suggested_fix=(
                "Express the affected behaviour in a supported construct, or treat this "
                "tree as outside EAL's current analysis envelope."
            ),
        ))

    if nav2_params_path is not None and nav2_unsupported:
        gaps.append(CoverageGap(
            id="U-000",
            category=CoverageGapCategory.UNSUPPORTED_INPUT_CONSTRUCT,
            title=f"Nav2 config uses {len(nav2_unsupported)} unmodelled construct(s)",
            summary=(
                "The Nav2 importer has no validated parameter mapping for: "
                + ", ".join(nav2_unsupported)
                + ". Its motion limits were not extracted and therefore not checked."
            ),
            affected_input=str(nav2_params_path),
            unanalyzed_constructs=list(nav2_unsupported),
            suggested_fix=(
                "Add a validated role mapping for this plugin, backed by a real "
                "upstream params file, before relying on results for this config."
            ),
        ))

    if nav2_params_path is not None and nav2_duplicate_keys:
        gaps.append(CoverageGap(
            id="U-000",
            category=CoverageGapCategory.AMBIGUOUS_INPUT,
            title=f"Nav2 config declares {len(nav2_duplicate_keys)} key(s) more than once",
            summary=(
                "These keys appear multiple times in the same mapping: "
                + ", ".join(nav2_duplicate_keys)
                + ". YAML silently keeps the last occurrence, so the file may say one "
                "thing to a human reading it and another to the parser. No result "
                "derived from these keys can be relied on."
            ),
            affected_input=str(nav2_params_path),
            unanalyzed_constructs=list(nav2_duplicate_keys),
            suggested_fix="Remove the duplicate declarations so the file has one reading.",
        ))

    if nav2_params_path is not None and nav2_unchecked_roles:
        gaps.append(CoverageGap(
            id="U-000",
            category=CoverageGapCategory.INCOMPLETE_COMPARISON,
            title=f"{len(nav2_unchecked_roles)} motion limit(s) declared on only one side",
            summary=(
                "These limits are declared by the controller or the velocity_smoother "
                "but not both, so their coherence was not checked: "
                + ", ".join(nav2_unchecked_roles)
                + ". Absence of a mismatch finding for them means they were not "
                "compared, not that they agree."
            ),
            affected_input=str(nav2_params_path),
            unanalyzed_constructs=list(nav2_unchecked_roles),
            suggested_fix=(
                "Declare the limit on both sides, or accept that this quantity is "
                "outside the checked set."
            ),
        ))

    # U2 — an input was provided and contributed nothing.
    if bt_xml_path is not None and not bt_contributed:
        gaps.append(CoverageGap(
            id="U-000",
            category=CoverageGapCategory.INPUT_YIELDED_NO_CONTENT,
            title="BehaviorTree XML contributed no IR content",
            summary=(
                "A BehaviorTree XML file was supplied but produced no signals, states, "
                "constraints, or assumptions. Nothing in this file was checked."
            ),
            affected_input=str(bt_xml_path),
            suggested_fix="Verify the file is a BehaviorTree XML in a supported dialect.",
        ))

    if nav2_params_path is not None and not nav2_contributed:
        gaps.append(CoverageGap(
            id="U-000",
            category=CoverageGapCategory.INPUT_YIELDED_NO_CONTENT,
            title="Nav2 params file contributed no IR content",
            summary=(
                "A Nav2 parameter file was supplied but no motion limits, frequencies, "
                "or costmap values were extracted from it. Nothing in this file was checked."
            ),
            affected_input=str(nav2_params_path),
            suggested_fix=(
                "Verify the file declares controller_server / velocity_smoother / "
                "local_costmap sections in the standard Nav2 layout."
            ),
        ))

    if model_path is not None and not model_contributed:
        gaps.append(CoverageGap(
            id="U-000",
            category=CoverageGapCategory.INPUT_YIELDED_NO_CONTENT,
            title="Model YAML contributed no IR content",
            summary=(
                "A model YAML file was supplied but contained no recognized top-level "
                "keys. Nothing in this file was checked."
            ),
            affected_input=str(model_path),
            suggested_fix="Check the model against the schema documented in the README.",
        ))

    if code_paths and not ir.code_constants and not ir.code_comparisons:
        gaps.append(CoverageGap(
            id="U-000",
            category=CoverageGapCategory.INPUT_YIELDED_NO_CONTENT,
            title=f"Code analysis extracted nothing from {len(code_paths)} file(s)",
            summary=(
                "Code files were supplied but no numeric constants or comparisons were "
                "extracted. No code/spec/model consistency check could run, so these "
                "files are unverified rather than consistent."
            ),
            affected_input=", ".join(str(p) for p in code_paths),
            suggested_fix=(
                "Confirm the files contain module-level numeric constants or simple "
                "numeric comparisons; EAL's static pass covers only those forms."
            ),
        ))

    # U3 — nothing checkable survived extraction.
    if not ir.signals and not ir.constraints and not ir.transitions:
        gaps.append(CoverageGap(
            id="U-000",
            category=CoverageGapCategory.NO_ANALYZABLE_CONTENT,
            title="No analyzable content in merged IR",
            summary=(
                "The merged IR contains no signals, constraints, or transitions. No "
                "deterministic rule or solver check could have fired. A zero-finding "
                "result here carries no assurance information."
            ),
            affected_input=str(getattr(ir, "spec_file", "") or ""),
            suggested_fix=(
                "Provide a spec with Signals/Constraints/Transitions sections, or a model "
                "YAML supplying them."
            ),
        ))

    return assign_gap_ids(gaps)
