"""
Merge a YAML model document into an existing IRSnapshot.

The YAML model can define or refine: signals (with bounds), states, modes,
transitions, entities, parameters, and invariants.
Model entries override/extend spec entries — they don't replace them.
"""

from __future__ import annotations

from eal.ingestion.loaders import ModelDocument
from eal.ir.schema import (
    Bounds, Constraint, ConstraintType, Entity, IRSnapshot,
    Mode, Signal, SignalKind, SourceRef, State, Transition,
)


def _src(model: ModelDocument, section: str) -> SourceRef:
    return SourceRef(file=str(model.path), section=section)


def merge_model_into_ir(ir: IRSnapshot, model: ModelDocument) -> IRSnapshot:
    """Merge model YAML into ir in-place; return the same ir for chaining."""
    data = model.data
    ir.model_file = str(model.path)

    existing_signals = {s.name: s for s in ir.signals}
    existing_states  = {s.name: s for s in ir.states}
    existing_modes   = {m.name: m for m in ir.modes}

    # ── Signals ───────────────────────────────────────────────────────────────
    for entry in data.get("signals", []):
        name = entry.get("name", "")
        if not name:
            continue
        kind_raw = entry.get("kind", "unknown")
        try:
            kind = SignalKind(kind_raw)
        except ValueError:
            kind = SignalKind.UNKNOWN

        bounds_data = entry.get("bounds")
        bounds: Bounds | None = None
        if isinstance(bounds_data, dict):
            bounds = Bounds(
                min=bounds_data.get("min"),
                max=bounds_data.get("max"),
                unit=entry.get("unit"),
            )

        if name in existing_signals:
            s = existing_signals[name]
            # Model bounds always take precedence — model is more authoritative than spec text
            if bounds is not None:
                s.bounds = bounds
            elif s.bounds is None and bounds is not None:
                s.bounds = bounds
            if kind != SignalKind.UNKNOWN and s.kind == SignalKind.UNKNOWN:
                s.kind = kind
            if entry.get("unit") and not s.unit:
                s.unit = entry["unit"]
        else:
            sig = Signal(
                name=name,
                kind=kind,
                unit=entry.get("unit"),
                bounds=bounds,
                source_ref=_src(model, "signals"),
            )
            ir.signals.append(sig)
            existing_signals[name] = sig

    # ── States ────────────────────────────────────────────────────────────────
    for entry in data.get("states", []):
        name = entry.get("name", "")
        if not name:
            continue
        if name not in existing_states:
            s = State(
                name=name,
                description=entry.get("description"),
                source_ref=_src(model, "states"),
            )
            ir.states.append(s)
            existing_states[name] = s

    # ── Modes ─────────────────────────────────────────────────────────────────
    for entry in data.get("modes", []):
        name = entry.get("name", "")
        if not name:
            continue
        if name not in existing_modes:
            m = Mode(
                name=name,
                description=entry.get("description"),
                source_ref=_src(model, "modes"),
            )
            ir.modes.append(m)
            existing_modes[name] = m

    # ── Entities ──────────────────────────────────────────────────────────────
    existing_entities = {e.name for e in ir.entities}
    for entry in data.get("entities", []):
        name = entry.get("name", "")
        if name and name not in existing_entities:
            ir.entities.append(Entity(
                name=name,
                description=entry.get("description"),
                source_ref=_src(model, "entities"),
            ))
            existing_entities.add(name)

    # ── Transitions ───────────────────────────────────────────────────────────
    existing_transitions = {(t.from_state, t.to_state) for t in ir.transitions}
    for entry in data.get("transitions", []):
        from_s = entry.get("from", "")
        to_s = entry.get("to", "")
        if not from_s or not to_s:
            continue
        if (from_s, to_s) not in existing_transitions:
            ir.transitions.append(Transition(
                from_state=from_s,
                to_state=to_s,
                guard_condition=entry.get("guard"),
                forbidden=bool(entry.get("forbidden", False)),
                source_ref=_src(model, "transitions"),
            ))
            existing_transitions.add((from_s, to_s))

    # ── Parameters → synthetic Constraints ───────────────────────────────────
    params = data.get("parameters", {})
    existing_con_ids = {c.id for c in ir.constraints}
    for param_name, param_val in params.items():
        if not isinstance(param_val, (int, float)):
            continue
        cid = f"PARAM-{param_name.upper()}"
        if cid not in existing_con_ids:
            ir.constraints.append(Constraint(
                id=cid,
                expression_text=f"{param_name} = {param_val}",
                constraint_type=ConstraintType.BOUND,
                numeric_value=float(param_val),
                source_ref=_src(model, "parameters"),
            ))
            existing_con_ids.add(cid)

    # ── Invariants → Constraints ──────────────────────────────────────────────
    for i, inv in enumerate(data.get("invariants", []), start=1):
        if not isinstance(inv, str):
            continue
        cid = f"INV-{i:03d}"
        if cid not in existing_con_ids:
            ir.constraints.append(Constraint(
                id=cid,
                expression_text=inv,
                constraint_type=ConstraintType.INVARIANT,
                source_ref=_src(model, "invariants"),
            ))
            existing_con_ids.add(cid)

    return ir
