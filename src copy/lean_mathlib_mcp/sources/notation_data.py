"""Curated Mathlib 4 notation registry.

The docgen master index does not ship a machine-readable notation table, so we
bundle a curated, high-coverage registry of the most common Mathlib symbols. Each
entry binds a symbol to the *real* Mathlib entity it denotes and records its LaTeX
form, precedence, and associativity — exactly the fields the spec (2.1 Notation /
3.1 symbol search) requires. This is intentionally a data file: extending coverage
is a pure data edit, no code change.

Ambiguous symbols (e.g. ``*`` meaning ``Mul.mul`` vs ``HMul.hMul``) are recorded
with their primary binding and a ``conflicts_with`` list so disambiguation can list
the alternatives explicitly instead of guessing.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from ..models import NotationEntity

# symbol, latex, precedence, associativity, binds_to, type_constraint, category, conflicts
_RECORDS: List[Dict[str, Any]] = [
    {"symbol": "ℕ", "latex": r"\N", "precedence": 0, "associativity": "none",
     "binds_to": "Nat", "type_constraint": "Type", "syntax_category": "number-type", "contexts": ["Mathlib.Data.Nat.Basic"]},
    {"symbol": "ℤ", "latex": r"\Z", "precedence": 0, "associativity": "none",
     "binds_to": "Int", "type_constraint": "Type", "syntax_category": "number-type", "contexts": ["Mathlib.Data.Int.Basic"]},
    {"symbol": "ℚ", "latex": r"\Q", "precedence": 0, "associativity": "none",
     "binds_to": "Rat", "type_constraint": "Type", "syntax_category": "number-type", "contexts": ["Mathlib.Data.Rat.Basic"]},
    {"symbol": "ℝ", "latex": r"\R", "precedence": 0, "associativity": "none",
     "binds_to": "Real", "type_constraint": "Type", "syntax_category": "number-type", "contexts": ["Mathlib.Data.Real.Basic"]},
    {"symbol": "ℂ", "latex": r"\C", "precedence": 0, "associativity": "none",
     "binds_to": "Complex", "type_constraint": "Type", "syntax_category": "number-type", "contexts": ["Mathlib.Analysis.Complex.Basic"]},
    {"symbol": "≤", "latex": r"\le", "precedence": 50, "associativity": "none",
     "binds_to": "LE.le", "type_constraint": "α → α → Prop", "syntax_category": "relation", "conflicts_with": ["LE.le", "NNReal.le"]},
    {"symbol": "<", "latex": r"\lt", "precedence": 50, "associativity": "none",
     "binds_to": "LT.lt", "type_constraint": "α → α → Prop", "syntax_category": "relation"},
    {"symbol": "≥", "latex": r"\ge", "precedence": 50, "associativity": "none",
     "binds_to": "GE.ge", "type_constraint": "α → α → Prop", "syntax_category": "relation"},
    {"symbol": ">", "latex": r"\gt", "precedence": 50, "associativity": "none",
     "binds_to": "GT.gt", "type_constraint": "α → α → Prop", "syntax_category": "relation"},
    {"symbol": "≠", "latex": r"\ne", "precedence": 50, "associativity": "none",
     "binds_to": "Ne.ne", "type_constraint": "α → α → Prop", "syntax_category": "relation"},
    {"symbol": "=", "latex": r"\=", "precedence": 50, "associativity": "none",
     "binds_to": "Eq", "type_constraint": "α → α → Prop", "syntax_category": "relation"},
    {"symbol": "+", "latex": "+", "precedence": 65, "associativity": "left",
     "binds_to": "Add.add", "type_constraint": "α → α → α", "syntax_category": "operator", "conflicts_with": ["Add.add", "HMul.hMul"]},
    {"symbol": "*", "latex": "*", "precedence": 70, "associativity": "left",
     "binds_to": "Mul.mul", "type_constraint": "α → α → α", "syntax_category": "operator", "conflicts_with": ["Mul.mul", "HMul.hMul"]},
    {"symbol": "⁻¹", "latex": r"\⁻¹", "precedence": 90, "associativity": "none",
     "binds_to": "Inv.inv", "type_constraint": "α → α", "syntax_category": "operator"},
    {"symbol": "/", "latex": "/", "precedence": 70, "associativity": "left",
     "binds_to": "Div.div", "type_constraint": "α → α → α", "syntax_category": "operator"},
    {"symbol": "0", "latex": "0", "precedence": 0, "associativity": "none",
     "binds_to": "Zero.zero", "type_constraint": "α", "syntax_category": "literal"},
    {"symbol": "1", "latex": "1", "precedence": 0, "associativity": "none",
     "binds_to": "One.one", "type_constraint": "α", "syntax_category": "literal"},
    {"symbol": "∑", "latex": r"\sum", "precedence": 0, "associativity": "none",
     "binds_to": "Finset.sum", "type_constraint": "(i : ι) → α", "syntax_category": "binder", "contexts": ["Mathlib.Data.Finset.BigOperators.Basic"]},
    {"symbol": "∏", "latex": r"\prod", "precedence": 0, "associativity": "none",
     "binds_to": "Finset.prod", "type_constraint": "(i : ι) → α", "syntax_category": "binder", "contexts": ["Mathlib.Data.Finset.BigOperators.Basic"]},
    {"symbol": "∧", "latex": r"\and", "precedence": 35, "associativity": "left",
     "binds_to": "And", "type_constraint": "Prop → Prop → Prop", "syntax_category": "logic"},
    {"symbol": "∨", "latex": r"\or", "precedence": 30, "associativity": "left",
     "binds_to": "Or", "type_constraint": "Prop → Prop → Prop", "syntax_category": "logic"},
    {"symbol": "¬", "latex": r"\not", "precedence": 40, "associativity": "none",
     "binds_to": "Not", "type_constraint": "Prop → Prop", "syntax_category": "logic"},
    {"symbol": "→", "latex": r"\to", "precedence": 25, "associativity": "right",
     "binds_to": "", "type_constraint": "α → β", "syntax_category": "arrow"},
    {"symbol": "↦", "latex": r"\fun", "precedence": 25, "associativity": "right",
     "binds_to": "", "type_constraint": "α → β", "syntax_category": "arrow"},
    {"symbol": "∘", "latex": r"\circ", "precedence": 80, "associativity": "left",
     "binds_to": "Function.comp", "type_constraint": "(β → γ) → (α → β) → α → γ", "syntax_category": "operator", "contexts": ["Mathlib.Function.Basic"]},
    {"symbol": "‖·‖", "latex": r"\norm", "precedence": 90, "associativity": "none",
     "binds_to": "Norm.norm", "type_constraint": "α → ℝ", "syntax_category": "operator", "contexts": ["Mathlib.Analysis.Normed.Norm.Basic"]},
    {"symbol": "∣", "latex": r"\mid", "precedence": 50, "associativity": "none",
     "binds_to": "Dvd.dvd", "type_constraint": "α → α → Prop", "syntax_category": "relation", "contexts": ["Mathlib.Algebra.Divisibility.Basic"]},
    {"symbol": "⌊·⌋", "latex": r"\lfloor \rfloor", "precedence": 0, "associativity": "none",
     "binds_to": "Int.floor", "type_constraint": "α → ℤ", "syntax_category": "operator", "contexts": ["Mathlib.Data.Int.Basic"]},
    {"symbol": "⌈·⌉", "latex": r"\lceil \rceil", "precedence": 0, "associativity": "none",
     "binds_to": "Int.ceil", "type_constraint": "α → ℤ", "syntax_category": "operator", "contexts": ["Mathlib.Data.Int.Basic"]},
    {"symbol": "√", "latex": r"\sqrt", "precedence": 90, "associativity": "none",
     "binds_to": "Real.sqrt", "type_constraint": "ℝ → ℝ", "syntax_category": "operator", "contexts": ["Mathlib.Analysis.SpecialFunctions.Pow"]},
    {"symbol": "π", "latex": r"\pi", "precedence": 0, "associativity": "none",
     "binds_to": "Real.pi", "type_constraint": "ℝ", "syntax_category": "literal", "contexts": ["Mathlib.Analysis.SpecialFunctions.Trigonometric"]},
    {"symbol": "abs", "latex": r"\abs", "precedence": 0, "associativity": "none",
     "binds_to": "Abs.abs", "type_constraint": "α → α", "syntax_category": "operator"},
    {"symbol": "•", "latex": r"\•", "precedence": 70, "associativity": "left",
     "binds_to": "SMul.smul", "type_constraint": "M → α → α", "syntax_category": "operator", "contexts": ["Mathlib.Algebra.GroupAction.Defs"]},
    {"symbol": "⊆", "latex": r"\subseteq", "precedence": 50, "associativity": "none",
     "binds_to": "HasSubset.subset", "type_constraint": "α → α → Prop", "syntax_category": "relation", "contexts": ["Mathlib.Data.Set.Basic"]},
    {"symbol": "∪", "latex": r"\cup", "precedence": 60, "associativity": "left",
     "binds_to": "Union.union", "type_constraint": "α → α → α", "syntax_category": "operator", "contexts": ["Mathlib.Data.Set.Basic"]},
    {"symbol": "∩", "latex": r"\cap", "precedence": 60, "associativity": "left",
     "binds_to": "Inter.inter", "type_constraint": "α → α → α", "syntax_category": "operator", "contexts": ["Mathlib.Data.Set.Basic"]},
    {"symbol": "∅", "latex": r"\emptyset", "precedence": 0, "associativity": "none",
     "binds_to": "EmptyCollection.emptyCollection", "type_constraint": "α", "syntax_category": "literal", "contexts": ["Mathlib.Data.Set.Basic"]},
]


def load_notations() -> List[NotationEntity]:
    out: List[NotationEntity] = []
    for r in _RECORDS:
        sid = "not:" + hashlib.md5(r["symbol"].encode("utf-8")).hexdigest()[:12]
        out.append(
            NotationEntity(
                id=sid,
                symbol=r["symbol"],
                latex=r.get("latex"),
                precedence=r.get("precedence"),
                associativity=r.get("associativity"),
                binds_to=r.get("binds_to") or None,
                type_constraint=r.get("type_constraint"),
                syntax_category=r.get("syntax_category"),
                contexts=list(r.get("contexts", [])),
                conflicts_with=list(r.get("conflicts_with", [])),
            )
        )
    return out
