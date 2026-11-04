"""
Utility functions for the structural benchmark suite
====================================================

1. Geometry-derived concrete volume (no silent fallbacks in strict mode).
2. Numerical claim extraction from free-text agent responses, converted to the case's units.
3. Prompt-to-Schema Fidelity (PSFR): does the configuration's structural model match ``spec``?
4. Design-check currency: did a run's design check use an analysis of the model it delivered?
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from itertools import accumulate
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from struct_agent.tools.model_state import model_fingerprint
from struct_core import conversion_factor, parse_units

try:
    from .case_schema import REPO_ROOT, BenchmarkCase
except ImportError:
    from research_paper.benchmarks.case_schema import REPO_ROOT, BenchmarkCase


def _get(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        value = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        if value is not None:
            return value
    return default


def calculate_concrete_volume(project: Any, strict: bool = False) -> float:
    """
    Total concrete volume sum(A_e * L_e) in model length units cubed.

    Section area comes from ``A``/``area`` or ``b * h``. With ``strict=True`` an element without a
    positive area or with missing end nodes raises ``ValueError`` instead of being skipped.
    """
    model = getattr(project, "model", None)
    if model is None:
        return 0.0

    def _items(container: Any) -> List[Any]:
        return list(container.values()) if isinstance(container, dict) else list(container or [])

    nodes = {_get(n, "id"): n for n in _items(_get(model, "nodes", default=[]))}
    sections = {_get(s, "id"): s for s in _items(_get(model, "sections", default=[]))}

    total = 0.0
    for elem in _items(_get(model, "elements", default=[])):
        eid = _get(elem, "id", default="?")
        sec = sections.get(_get(elem, "section_id"))
        area = 0.0
        if sec is not None:
            area = float(_get(sec, "A", "area", default=0.0) or 0.0)
            if area <= 0.0:
                b = float(_get(sec, "b", "width", default=0.0) or 0.0)
                h = float(_get(sec, "h", "height", "depth", default=0.0) or 0.0)
                area = b * h
        if area <= 0.0:
            area = float(_get(elem, "area", default=0.0) or 0.0)
        ni = nodes.get(_get(elem, "start_node", "node_i"))
        nj = nodes.get(_get(elem, "end_node", "node_j"))
        if area <= 0.0 or ni is None or nj is None:
            if strict:
                raise ValueError(f"Element '{eid}' has no positive cross-section area or references missing nodes.")
            continue
        length = math.dist(
            [float(_get(ni, c, default=0.0)) for c in ("x", "y", "z")],
            [float(_get(nj, c, default=0.0)) for c in ("x", "y", "z")],
        )
        total += area * length
    return round(total, 3)


# ----------------------------------------------------------------------------
# Claim extraction
# ----------------------------------------------------------------------------
_NUM = r"(-?\d+(?:,\d{3})*(?:\.\d+)?)"
_FORCE_UNITS = {"kn": "kN", "mn": "MN", "kip": "kip", "kips": "kip", "n": "N", "lb": "lbf", "lbs": "lbf", "lbf": "lbf"}
_KN_PER = {"MN": 1000.0}  # force units struct_core does not convert (gpt-oss: "W ≈ 4.14 MN")
_LENGTH_UNITS = {"mm": "mm", "cm": "cm", "m": "m", "in": "in", "inch": "in", "inches": "in", "ft": "ft"}

# Label patterns per metric, most specific first (a "total ..." label wins over a bare "dead load")
_PATTERNS: Dict[str, Tuple[str, ...]] = {
    # A final-design DCR wins over the trial DCR that resizing cases also report
    "governing_dcr": (
        r"\b(?:governing\s+)?(?:dcr|demand[\s-]*(?:to[\s-]*)?capacity\s+ratio)\s*[(,]?\s*(?:of\s+(?:the\s+)?)?final(?:\s+design)?\)?",
        r"\bfinal\s+(?:design\s+)?(?:governing\s+)?(?:dcr|demand[\s-]*(?:to[\s-]*)?capacity\s+ratio)\b",
        # a 'governing' DCR wins over a bare one (e.g. the DCR of a single check or an earlier iteration);
        # minimax C02: 'Governing member-level DCR: 0.987' after a frame check's 'DCR = 0.7548'
        r"\bgoverning\s+(?:(?:member|element|overall)(?:[\s-]level)?\s+)?(?:dcr|demand[\s-]*(?:to[\s-]*)?capacity\s+ratio)\b",
        r"\b(?:dcr|demand[\s-]*(?:to[\s-]*)?capacity\s+ratio)(?:_[a-z]+)?\b",  # also DCR_gov
    ),
    "total_weight": (
        r"\btotal\s+(?:(?:dead\s+(?:load|weight)|structural\s+weight|weight)\s*(?:\(?\s*w\s*\)?)?|w\b)",  # also 'Total W'
        r"(?-i:\bW)(?:_dead)?\s*=",  # "W = 288.96 + 700.00 = 988.96 kN" (capital W only), "W_dead = 3261.9 kN"
        # the symbol with its meaning (minimax A02, A03: '| **W (total dead)** | **1,533.0** |')
        r"(?-i:\bW)\s*\(\s*(?:total\s+)?dead(?:\s+(?:load|weight))?\s*\)",
        # not a component's weight (minimax A02: 'member self-weight (γ = 23.54 kN/m³). Total LL applied = 702.0 kN')
        r"(?<![-\w])(?<!partition\s)(?:dead\s+(?:load|weight)|structural\s+weight|weight)\s*(?:\(?\s*w\s*\)?)?",
    ),
    # not a coefficient (minimax C01: 'a base shear coefficient C_s ≈ 0.13'); 'V_base = 132.37 kN' is one
    "base_shear": (r"\b(?:peak\s+)?(?:base\s+shear(?!\s+(?:coefficient|ratio|factor)\b)|v[_\s]?b(?:,?\s*x)?|v_?base)\b",),
    "fundamental_period": (r"\b(?:fundamental\s+(?:natural\s+)?period|t[_\s]?1|first[\s-]mode\s+period)\b",),
    "period_t2": (r"\b(?:second[\s-]mode\s+period|mode\s+2\s+period|t[_\s]?2)\b",),
    "period_t3": (r"\b(?:third[\s-]mode\s+period|mode\s+3\s+period|t[_\s]?3)\b",),
    # a bare 'mass ratio' is not modal (minimax B03: 'a mass ratio of 1.055', of two seismic masses)
    "modal_mass_ratio": (r"\b(?:(?:cumulative\s+)?(?:modal\s+)?(?:effective\s+)?mass\s+participation(?:\s+ratio)?|"
                         r"(?:cumulative|modal|effective)\s+(?:modal\s+)?(?:effective\s+)?mass\s+ratio)\b",
                         # the cumulative value of a list under a mass participation heading (deepseek A03:
                         # '- Mode 1: 90.21 %' / '- Modes 1–2: 98.64 %' / '- **Modes 1–3: 100.0 %**'); a percentage
                         # only, so that a list of periods ('modes 1-3: 0.52, 0.16, 0.09 s') is not read
                         r"\bmodes\s+1\s*-\s*3\s*(?=[:=]\s*\d+(?:\.\d+)?\s*%)",
                         # the mode-3 item of a list marked cumulative (qwen B03: '- Mode 3: 0.8977 (89.77% cumulative)')
                         r"\bmode\s+3\s*(?=[:=]\s*\d+(?:\.\d+)?[^\n]{0,30}\bcumulative\b)"),
    "peak_roof_displacement": (r"\b(?:peak\s+)?roof\s+(?:lateral\s+)?displacement\b",),
    "max_base_reaction": (r"\b(?:max(?:imum)?|largest|peak)\s+(?:vertical\s+)?(?:base|support|column)\s+reaction\b",),
}
# The symbol of each force or period metric, for a label whose value follows as an equation on the next line
_METRIC_SYMBOLS = {"total_weight": "W", "base_shear": "V", "max_base_reaction": "R", "fundamental_period": "T_?1"}
# Units a claimed value may carry ('' = no unit written, e.g. a table cell with the unit in another column)
_FORCE_METRICS = ("total_weight", "base_shear", "max_base_reaction")
_ALLOWED_UNITS: Dict[str, Tuple[str, ...]] = {
    "governing_dcr": ("",),
    "fundamental_period": ("", "s", "sec", "seconds"),
    "period_t2": ("", "s", "sec", "seconds"),
    "period_t3": ("", "s", "sec", "seconds"),
    "modal_mass_ratio": ("", "%"),
    "peak_roof_displacement": ("", *_LENGTH_UNITS),
    **{m: ("", *_FORCE_UNITS) for m in _FORCE_METRICS},
}
_KNOWN_UNITS = {*_FORCE_UNITS, *_LENGTH_UNITS, "s", "sec", "seconds", "%", "kpa", "mpa", "gpa", "psf", "ksf", "psi",
                "ksi", "pcf", "hz", "kg"}
_WINDOW = 300  # characters after a label searched for its value, on the label's own line (or the next one)
# A number followed by an operator is a term of a calculation or a dimension pair, not the value:
# "W = 288.96 + 700.00 = 988.96 kN", "0.30 × 0.45 m"; but a number before '=' that no operator precedes is the
# label's value followed by its derivation (minimax C05: 'Total dead load W = 7 555.6 kN = floor dead load ...')
_OPERAND = re.compile(r"\s*(?:[+×*/=]|x\s)")
_TERM_BEFORE = re.compile(r"(?:[+×*/-]|\bx)\s*$")


def _is_citation(text: str, start: int, end: int) -> bool:
    """Numbers that are not values: code references (ACI 318-25, §22.4, Eq. 12.8-7, Table 6.6.3.1.1) and
    identifiers (Node 13, Story 2, Mode 1, Grid 4, Column C3)."""
    before, after = text[max(0, start - 12):start], text[end:end + 2]
    if re.search(r"(?:§|\b(?:aci|asce|eq|eqs|table|tables|section|sec|chapter|ch)\.?)\s*$", before, re.IGNORECASE):
        return True
    if re.search(r"\b(?:node|joint|story|storey|level|floor|mode|element|member|beam|column|grid|bay|case|"
                 r"combination|combo|step|item|no|id)\.?\s*#?\s*$", before, re.IGNORECASE):
        return True
    # Limits and comparisons, not values: "exceeds 1.0", "DCR <= 1.0", "below 1.00"
    if re.search(r"(?:\bexceed(?:s|ed|ing)?|\bbelow|\babove|\bthan|\blimit(?:\s+of)?|\btarget(?:\s+of)?|\bwithin|"
                 r"≤|≥|<=|>=|<|>)\s*$", text[max(0, start - 14):start], re.IGNORECASE):
        return True
    if re.match(r"[-.]\d", after):  # 318-25, 12.8-7, 6.6.3.1.1
        return True
    if re.match(r"(?:st|nd|rd|th)\b", text[end:end + 3], re.IGNORECASE):  # ordinals: '2nd mode', '3rd floor'
        return True
    # Counts, an integer next to its noun: "of the first 3 modes is 98.6%", "W of the 2 stories is 1,516 kN",
    # "a 3-story building" (not a table value followed by the next cell: '| 0.998 | Beam flexure')
    if re.fullmatch(r"\d+", text[start:end]) and re.match(
            r"[ -]?(?:modes?|stor(?:e)?ys?|stories|floors?|levels?|bays?|spans?|columns?|beams?|frames?|seeds?|"
            r"iterations?|cycles?)\b", text[end:end + 12], re.IGNORECASE):
        return True
    if re.match(r"\s?(?:D|L|Lr|E|Ex|Ey|EX|EY|W|S|H)\b", text[end:end + 4]):  # load factors: 1.2D + 1.6L
        return True
    return bool(re.search(r"\d[-.]$", before))  # the 25 of 318-25, the 3.1 of 6.6.3.1


_NOT_GOVERNING = re.compile(r"\b(?:drift|stability|joint|footing|foundation|bearing|punching)\s*$", re.IGNORECASE)
# A DCR on the line of a frame second-order check is that check's (deepseek C02: 'Governing second-order condition:
# ACI 318-25 §6.2.5.3 — second-order end moment ≤ 1.4 × first-order moment, DCR 0.755'), not the members' governing DCR
# or on a row about it (minimax A05: '| Second order | Q = 0.026–0.030; ... all 15 analysis frame checks ... passed
# (governing DCR 0.756) |')
_SECOND_ORDER_CHECK = re.compile(r"\bsecond-order\s+(?:condition|check|limit|end\s+moment|moment\s+ratio)\b|"
                                 r"^\W*second[\s-]order\b", re.IGNORECASE)
# Footings are designed but not scored: a DCR on a line about them is theirs (qwen B06: 'All footings pass with DCR
# between 0.85 and 1.00')
_FOOTING_LINE = re.compile(r"\b(?:footings?|foundations?)\b", re.IGNORECASE)
# A period symbol after another one is an item of a list whose values follow in order (minimax A03: 'T2/T3 (0.163 s,
# 0.093 s)'); the first value is not T3's
_LISTED_SYMBOL = re.compile(r"\bT_?\d\s*(?:[/,&]|and)\s*$", re.IGNORECASE)
# An unscaled response spectrum base shear is not the design base shear Vb (deepseek B09: 'Modal base shear | 676.8 kN'
# above 'ELF base shear V (design) | 816.4 kN' and 'Base shear Vb, X direction | 816 kN')
_NOT_DESIGN_SHEAR = re.compile(r"\b(?:modal|unscaled|elastic)\s*$", re.IGNORECASE)


_HEADING = re.compile(r"\s*(?:#{1,6}\s.*|\*\*[^*\n]{1,80}\*\*\s*:?\s*|[^:\n]{0,80}:\s*)")
_MARKDOWN_HEADING = re.compile(r"\s*#{1,6}\s")


def _design_state(heading: str) -> Optional[str]:
    """'final', 'other' (trial, initial, first pass, a revision not carried out, ...), or None for a heading that
    names neither."""
    if re.search(r"\bfinal\b", heading, re.IGNORECASE):
        return "final"
    return "other" if _OTHER_STATE.search(heading) or _UNBUILT.search(heading) else None


def _line_states(text: str) -> List[Tuple[str, Optional[str]]]:
    """Each raw line with the design state of its section. A markdown '#' heading sets the state of its
    section; a bold-only or colon sub-heading inherits it unless the sub-heading names its own."""
    lines, section, state = [], None, None
    for line in text.splitlines():
        if _HEADING.fullmatch(line):
            own = _design_state(line)
            if _MARKDOWN_HEADING.match(line):
                section = state = own
            else:
                state = own if own is not None else section
        lines.append((line, state))
    return lines


def _final_sections(text: str) -> str:
    """Raw text of the sections about the final design."""
    return "\n".join(line for line, state in _line_states(text) if state == "final")


# A value the response says it does not have ("not available", "n/a") ends the search: no claim
_WITHHELD_MARK = re.compile(
    r"\b(?:not\s+(?:directly\s+|yet\s+)?(?:available|obtained|computed|calculated|determined|reported|provided)|"
    r"n/a|unavailable)\b", re.IGNORECASE)
_WITHHELD: Tuple[float, str] = (math.nan, "withheld")
# Occurrences that describe another design state, not the delivered one ("DCR of the trial sections")
_OTHER_STATE = re.compile(r"\b(?:trial|initial|first\s+(?:design\s+check|pass|iteration)|previous|earlier|original)\b",
                          re.IGNORECASE)
# A section heading about a revision the run did not carry out (minimax ablated A08: '5. Revision required — not
# executable in this run', whose hand calculation of a proposed beam gives 'DCR ≈ 0.56')
_UNBUILT = re.compile(r"\bnot\s+(?:executable|executed|implemented|applied|built)\b|"
                      r"\b(?:revision|changes?)\s+required\b|\brequired\s+(?:revision|changes?)\b", re.IGNORECASE)
# Parenthetical qualifiers after a label ("V_b (ASCE 7-22 ELF, R = 5)") and formulas in braces hold no value
_QUALIFIER = re.compile(r"\((?!\s*[-\d.])[^()]*\)|\{[^{}]*\}")


def _without_other_states(text: str) -> str:
    """Raw text without the sections about another design state ('Initial Trial Sections')."""
    return "\n".join(line for line, state in _line_states(text) if state != "other")


def _claimed_value(metric: str, scopes: Sequence[str]) -> Optional[Tuple[float, str]]:
    """The first number after a label of ``metric``, skipping code references; None if its unit does not fit
    or the response withholds the value. A more specific label wins in any scope; for one label, the first
    scope that has it wins (values under a 'final' heading come first: resizing cases also report the trial
    design)."""
    for pattern in _PATTERNS[metric]:
        for scope in scopes:
            found = _first_claim(metric, pattern, scope)
            if found is _WITHHELD:
                return None
            if found is not None:
                return found
    return None


def _value_window(text: str, start: int, symbol: Optional[str] = None) -> Tuple[str, Optional[int], bool]:
    """Text after a label on its own line, None and False; a label that ends its line ('Governing DCR of the final
    design:') takes the next line too, and the offset where that line starts. So does a sentence that announces
    its value on the next line (gemma A03: '... participation ratio for the first three modes is:' over the
    bullet '- Sum MPR_x = 1.00'); True marks such an announcement, whose bullet is the value, not a sub-item.
    A label line without a number whose next line is an equation of the metric's own ``symbol`` takes that line
    too (minimax C01: the bold line '**Base shear, load case EQx**' over 'V = **132.37 kN**')."""
    window = text[start:start + _WINDOW]
    cut = window.find("\n")
    if cut == -1:
        return window, None, False
    first = window[:cut]
    if symbol is not None and not re.search(r"\d", first):
        nxt = cut + 1
        while blank := re.match(r"[ \t]*\n", window[nxt:]):
            nxt += blank.end()
        if re.match(rf"\s*(?:-\s+)?(?-i:{symbol})(?:_[\w,-]+)?\s*=\s*-?\d", window[nxt:]):
            end = window.find("\n", nxt)
            return (window if end == -1 else window[:end]), nxt, False
    # a heading whose label ends with a qualifier only (deepseek B03: '3. Cumulative X-direction modal mass
    # participation (first three modes)' over '$$M_{X,1-3} = 0.0005 + 0.8880 + 0.0092 = 89.77 %$$')
    bare = _QUALIFIER.sub("", first)
    announced = not re.search(r"\d", first) and bool(re.search(r"\b(?:is|are|equals?)\s*:\s*$", first))
    # A label whose numbers are load factors or code references ends its line too (minimax B01: 'Maximum vertical
    # support reaction under 1.2D + 1.6L:' over '$$R_{max} = 1149.7 \text{ kN}$$')
    label_only = first.rstrip(" *").endswith(":") and all(
        _is_citation(text, start + m.start(), start + m.end()) for m in re.finditer(r"\d+(?:\.\d+)?", first))
    if bare.strip(" :-") == "" or announced or label_only:
        nxt = cut + 1
        while blank := re.match(r"[ \t]*\n", window[nxt:]):  # blank lines around a display equation
            nxt += blank.end()
        if _MARKDOWN_HEADING.match(window[nxt:]):  # a new section holds no value of this label (deepseek B05:
            return first, None, False  # '... scaled to ELF base shear (§12.9.1.4)' over '## 2. Final member sizes')
        end = window.find("\n", nxt)
        return (window if end == -1 else window[:end]), nxt, announced
    return first, None, False


def _first_claim(metric: str, pattern: str, text: str) -> Optional[Tuple[float, str]]:
    for label in re.finditer(pattern, text, re.IGNORECASE):
        if metric == "governing_dcr" and _NOT_GOVERNING.search(text[max(0, label.start() - 20):label.start()]):
            continue  # a drift, stability, joint or footing DCR is not the members' governing DCR
        line_start = text.rfind("\n", 0, label.start()) + 1
        if metric == "governing_dcr" and (_SECOND_ORDER_CHECK.search(text[line_start:label.start()])
                                          or _FOOTING_LINE.search(text[line_start:label.start()])):
            continue
        if metric == "base_shear" and _NOT_DESIGN_SHEAR.search(text[max(0, label.start() - 20):label.start()]):
            continue
        if metric in _PERIOD_ORDER and _LISTED_SYMBOL.search(text[line_start:label.start()]):
            continue
        # A label ends at its line (qwen C02: the '\s*' of 'Total Dead Load' crossed the end of the heading
        # '### Total Dead Load', so its sub-item '- DEAD load case: 288.96 kN' was read as the label's value)
        newline = label.group().find("\n")
        window_start = label.start() + newline if newline != -1 else label.end()
        window, next_line, announced = _value_window(text, window_start, _METRIC_SYMBOLS.get(metric))
        window = _QUALIFIER.sub(lambda m: " " * len(m.group(0)), window)  # same length: offsets kept
        symbol_equation = False  # the next line is the label's symbol equation: its terms and result follow
        for num in re.finditer(r"(?<![\w.])" + _NUM + r"(?:\s*([A-Za-z%]+)(/?))?", window):
            start, end = window_start + num.start(1), window_start + num.end(1)
            if _is_citation(text, start, end):
                continue
            if next_line is not None and num.start(1) >= next_line and not announced and not symbol_equation:
                named = window[next_line:num.start(1)]
                if not named.strip() and re.match(r"[.)]\s", window[num.end(1):]):
                    break  # the marker of a numbered list ('... you would need to:' over '1. Run ...')
                if re.fullmatch(r"\s*(?:\$\$?\s*)?[A-Za-z](?:_\{?[\w,-]+\}?)?\s*=\s*", named):
                    # the label's value as an equation of its symbol ('$$R_{max} = 1149.7 ...', and deepseek B03's
                    # '$$M_{X,1-3} = 0.0005 + 0.8880 + 0.0092 = 89.77 %$$'), not a sub-item
                    symbol_equation = True
                elif re.match(r"\s*(?:-|\d+[.)])\s", named) or (
                        re.search(r"[A-Za-z]", named)
                        and not any(re.search(p, named, re.IGNORECASE) for p in _PATTERNS[metric])):
                    break  # a sub-item or another quantity ('- DEAD = 288.96 kN' under 'Total dead load:')
            word = (num.group(2) or "").lower()
            unit = word if word in _KNOWN_UNITS else ""  # a following ordinary word is not a unit
            # An operator after the unit ('0.30 m × 0.45 m'), not after an ordinary word: deepseek C01's table row
            # '| T3 | 0.3874 | torsional / 2nd mode |' is the value, not a term divided by something. Qualifiers are
            # blanked (gemma C01: '288.96 kN (DEAD) + 700.00 kN (SuperDead) = 988.96 kN' has terms before '=')
            operand = _OPERAND.match(window, num.end(1)) or _OPERAND.match(window, num.end() if unit else num.end(1))
            if operand and (operand.group().strip() != "=" or _TERM_BEFORE.search(text[line_start:start])):
                continue  # a term of a calculation or one dimension of a pair; the value follows
            context = text[line_start:start]
            if _OTHER_STATE.search(context) and not re.search(r"\bfinal\b", context, re.IGNORECASE):
                break  # a trial or earlier design state; the delivered value comes elsewhere
            if _WITHHELD_MARK.search(window[:num.start(1)]):
                return _WITHHELD
            if unit and num.group(3):
                break  # composite unit such as kN/m
            if unit in _ALLOWED_UNITS[metric]:
                return float(num.group(1).replace(",", "")), unit
            break  # the label's value has a unit of another quantity (e.g. a pressure)
        else:
            if _WITHHELD_MARK.search(window):
                return _WITHHELD
    return None


def _normalize(text: str) -> str:
    """Plain text for claim parsing: markdown, HTML, and LaTeX markup removed, thousands separators unified."""
    norm = unicodedata.normalize("NFKD", text)  # also turns narrow and thin spaces into plain spaces
    norm = re.sub(r"[‐-―−]", "-", norm)  # typographic dashes
    norm = re.sub(r"<sub>\s*([^<]*?)\s*</sub>", r"_\1", norm, flags=re.IGNORECASE)  # V<sub>b</sub>
    norm = re.sub(r"</?[A-Za-z][^>]*>", " ", norm)  # other HTML tags
    norm = re.sub(r"\\[()\[\]]", " ", norm)  # LaTeX math delimiters \( \) \[ \]
    norm = re.sub(r"(\d)\{,\}(?=\d{3})", r"\1,", norm)  # LaTeX thousands separator: 4{,}772.5
    # LaTeX wrappers (\text{ mm}, \boxed{0.99}), innermost first: \boxed{W = 4,135.8\ \text{kN}}
    previous = None
    while previous != norm:
        previous = norm
        norm = re.sub(r"\\(?:text|mathrm|mathbf|rm|mbox|boxed)\s*\{([^{}]*)\}", r" \1", norm)
    norm = re.sub(r"_\{([^{}]*)\}", r"_\1", norm)  # subscripts: T_{1}
    norm = re.sub(r"\\[,;:! ]|\$", " ", norm)
    norm = re.sub(r"(?m)^(\s*)[*+•]\s+", r"\1- ", norm)  # list bullets kept as '- ' before '*' is removed
    norm = re.sub(r"[*`|]", " ", norm)  # markdown emphasis and table pipes
    # Space-separated thousands (1 393.5 kN): digit groups joined by single spaces
    return re.sub(r"(?<![\d.,])(\d{1,3})((?: \d{3})+)(?!\d)",
                  lambda m: m.group(1) + m.group(2).replace(" ", ","), norm)


# "T1, T2, T3 = 0.52 s, 0.16 s, 0.09 s": listed periods map to their values by position; so do slash-separated
# lists (minimax C01: 'T1/T2/T3 = 0.4577 / 0.4167 / 0.3874 s', whose values are not a division)
_PERIOD_VALUE = _NUM + r"\s*(?:s|sec|seconds)?"
_PERIOD_LIST = re.compile(
    r"\bT_?1\s*[,/]\s*T_?2\s*[,/]?\s*(?:and\s+)?T_?3\b[^\d\n]{0,40}?"
    + _PERIOD_VALUE + r"\s*[,/]?\s*" + _PERIOD_VALUE + r"\s*[,/]?\s*(?:and\s+)?" + _PERIOD_VALUE,
    re.IGNORECASE,
)
_PERIOD_ORDER = ("fundamental_period", "period_t2", "period_t3")


def _listed_period(metric: str, scopes: Sequence[str]) -> Optional[Tuple[float, str]]:
    if metric not in _PERIOD_ORDER:
        return None
    for scope in scopes:
        listed = _PERIOD_LIST.search(scope)
        if listed is not None:
            return float(listed.group(_PERIOD_ORDER.index(metric) + 1).replace(",", "")), "s"
    return None


def _cells(line: str) -> List[str]:
    return [_normalize(c).strip() for c in line.strip().strip("|").split("|")]


def _mode_table_value(
    raw_scopes: Sequence[str],
    header: str,
    mode: int,
    parse: Callable[[str], Optional[Tuple[float, str]]],
    prefer: Optional[str] = None,
    cumulative: bool = False,
) -> Optional[Tuple[float, str]]:
    """The value in the row of ``mode`` of a markdown table of modes (a 'Mode' column), in the column whose header
    matches ``header`` (the first that also matches ``prefer``, if one does); the first such table of the first
    scope that has one. A ``cumulative`` table may label the row of modes 1 to ``mode`` as a range (minimax B03:
    '| Modes 1–3 | 89.77% |' under '| Modes | Cumulative X |')."""
    for scope in raw_scopes:
        columns = None
        for line in scope.splitlines():
            if not line.lstrip().startswith("|"):
                columns = None
                continue
            cells = _cells(line)
            if columns is None:
                mode_col = next((i for i, c in enumerate(cells) if re.fullmatch(r"modes?(?:\s*(?:#|no\.?))?", c, re.I)), None)
                matching = [i for i, c in enumerate(cells) if re.search(header, c, re.I)]
                if prefer:
                    matching = [i for i in matching if re.search(prefer, cells[i], re.I)] or matching
                if mode_col is not None and matching:
                    columns = (mode_col, matching[0])
                continue
            row = re.fullmatch(r"(?:modes?\s*)?(?:(1)\s*-\s*)?(\d+)", cells[columns[0]], re.I) \
                if len(cells) > max(columns) else None
            if row is None or (row.group(1) and not cumulative):
                continue  # the separator row, or a row of several modes ('4-12')
            found = parse(cells[columns[1]]) if int(row.group(2)) == mode else None
            if found is not None:
                return found
    return None


def _tabled_period(metric: str, raw_scopes: Sequence[str]) -> Optional[Tuple[float, str]]:
    """A period from a markdown table of modes: minimax B03 wrote '| **1** | **0.4267** | 2.344 | ...' under the
    header '| Mode | Period T (s) | Freq. (Hz) |' and no labeled T1. The row of mode 1, 2 or 3."""
    if metric not in _PERIOD_ORDER:
        return None

    def parse(cell: str) -> Optional[Tuple[float, str]]:
        value = re.match(_NUM + r"\s*(?:s|sec|seconds)?$", cell)
        return None if value is None else (float(value.group(1).replace(",", "")), "s")
    return _mode_table_value(raw_scopes, r"\bperiod\b|^T\s*\(\s*s(?:ec)?\s*\)$", _PERIOD_ORDER.index(metric) + 1, parse)


def _tabled_mass_ratio(metric: str, raw_scopes: Sequence[str]) -> Optional[Tuple[float, str]]:
    """The cumulative X mass ratio of the first three modes (as A03 and B03 ask) from a table of modes: minimax A03
    wrote '| 3 | 0.0136 | **1.0000 (100%)** |' under '| Mode | Individual | Cumulative (first 3) |'."""
    if metric != "modal_mass_ratio":
        return None

    def parse(cell: str) -> Optional[Tuple[float, str]]:
        value = re.match(_NUM + r"\s*(%)?", cell)
        return None if value is None else (float(value.group(1).replace(",", "")), value.group(2) or "")
    return _mode_table_value(raw_scopes, r"\bcum(?:ul|\.)|Σ|\bsum\b", 3, parse, prefer=r"\bx\b|_x\b|\bux\b",
                             cumulative=True)


def _final_table_columns(text: str) -> str:
    """Tables that compare design states keep only their final column (gemma A07: '| Parameter | Trial Design | Final
    Design |' gave '| **Governing DCR** | **1.311** | **0.985** |', and the trial value came first)."""
    out, drop = [], None
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            drop = None
        else:
            cells = line.strip().strip("|").split("|")
            if drop is None:  # the header row
                states = [_design_state(c) for c in cells]
                drop = [i for i, s in enumerate(states) if s == "other"] if "final" in states else []
            if drop:
                line = "|" + "|".join(c for i, c in enumerate(cells) if i not in drop) + "|"
        out.append(line)
    return "\n".join(out)


def parse_numerical_claims_from_text(text: str, units: str = "kN, m") -> Dict[str, float]:
    """Extract claimed metric values from free text, converted to ``units`` (forces, lengths)."""
    if not text:
        return {}
    text = _final_table_columns(text)
    final = _final_sections(text)
    norm = _normalize(_without_other_states(text))
    scopes = (_normalize(final), norm) if final else (norm,)
    raw_scopes = (final, _without_other_states(text)) if final else (_without_other_states(text),)
    target = parse_units(units)
    claims: Dict[str, float] = {}
    for metric in _PATTERNS:
        found = (_listed_period(metric, scopes) or _claimed_value(metric, scopes)
                 or _tabled_period(metric, raw_scopes) or _tabled_mass_ratio(metric, raw_scopes)
                 # only sections about the trial design state the value: the delivered design is the trial one
                 # (minimax ablated A08, which could not resize, reported 'Governing DCR = 1.488' under '4. ACI 318-25
                 # design check of the trial sections')
                 or _claimed_value(metric, (_normalize(text),)))
        if found is None:
            continue
        value, unit = found
        if metric in ("total_weight", "base_shear", "max_base_reaction"):
            src = _FORCE_UNITS.get(unit)
            if src in _KN_PER:
                value, src = value * _KN_PER[src], "kN"
            if src is not None:
                value *= conversion_factor(f"{src}, m", target, "force")
        elif metric == "peak_roof_displacement":
            src = _LENGTH_UNITS.get(unit)
            if src is not None:
                value *= conversion_factor(f"kN, {src}", target, "length")
        elif metric == "modal_mass_ratio" and (unit == "%" or value > 1.0):
            value /= 100.0
        claims[metric] = value
    return claims


# ----------------------------------------------------------------------------
# Prompt-to-Schema Fidelity
# ----------------------------------------------------------------------------
def _coords(values: List[float], tol: float) -> List[float]:
    out: List[float] = []
    for v in sorted(values):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _matches(actual: List[float], expected: List[float], tol: float) -> bool:
    if len(actual) != len(expected):
        return False
    shift = actual[0] - expected[0]
    return all(abs(a - shift - e) <= tol for a, e in zip(actual, expected))


def _grid_matches(actual: List[float], spacings: List[float], tol: float) -> bool:
    """Grid lines at the given bay spacings, in either order (a mirrored plan is the same structure)."""
    return any(_matches(actual, [0.0, *accumulate(order)], tol) for order in (spacings, spacings[::-1]))


LOAD_TOTAL_TOLERANCE = 0.02  # relative, on the dead / live / partition resultants
S1_LOWER_BOUND_THRESHOLD = 0.6  # g; ASCE 7-22 Eq. 12.8-7 applies where S1 >= 0.6 g
MATERIAL_TOLERANCE = 0.01  # relative, on f'c, fy and the allowable bearing pressure
# relative, on the concrete unit weight: the conventional 24 kN/m3 for 2,400 kg/m3 (g taken as 10 m/s2) is 1.97 % high
UNIT_WEIGHT_TOLERANCE = 0.025
STANDARD_GRAVITY = 9.80665  # m/s2: the spec's concrete density (kg/m3) as a unit weight


def gravity_load_totals(project: Any, units: str) -> Dict[str, float]:
    """Resultants of the dead-type, live, and partition load cases of a project, in the force unit of ``units``."""
    from struct_agent.tools.loads import _case_total

    model = project.model
    scale = conversion_factor(getattr(project.metadata, "units", None) or "kN, m", units, "force")
    totals = {"dead": 0.0, "live": 0.0, "partition": 0.0}
    for lc in model.load_cases:
        cid = str(lc.id).lower()
        if "partition" in cid:
            group = "partition"
        elif "dead" in cid or "sdl" in cid:
            group = "dead"
        elif "live" in cid and "roof" not in cid:
            group = "live"
        else:
            continue
        totals[group] += _case_total(project, lc.id) * scale
    return totals


def lateral_load_totals(project: Any, units: str) -> Dict[str, float]:
    """Resultant horizontal force of each ELF seismic case ('eq_x', 'eq_y'), in the force unit of ``units``."""
    model = project.model
    scale = conversion_factor(getattr(project.metadata, "units", None) or "kN, m", units, "force")
    totals: Dict[str, float] = {}
    for lc in model.load_cases:
        cid = str(lc.id).lower()
        if cid in ("eq_x", "eq_y"):
            attr = "fx" if cid == "eq_x" else "fy"
            totals[cid] = abs(sum(getattr(p, attr, 0.0) for p in lc.point_loads)) * scale
    return totals


def _horizontal_load_cases(model: Any, is_3d: bool) -> List[str]:
    """Load cases carrying a horizontal force (global X, and Y in 3D): seismic, wind, or notional loads."""
    tiny = 1e-9
    found = []
    for lc in model.load_cases:
        point = any(abs(p.fx) > tiny or (is_3d and abs(p.fy) > tiny) for p in lc.point_loads)
        line = any(not w.is_local and (abs(w.wx) > tiny or (is_3d and abs(w.wy) > tiny)) for w in lc.element_loads)
        if point or line:
            found.append(lc.id)
    return found


_FULL_ENVELOPE = ("ENVELOPE", "ALL", "TOTAL")  # run_analysis load_case_id values that envelope every combination


# Tools that change the model, its loads, or its load combinations: a design check before the last of them is of an
# earlier model
MODEL_CHANGING_TOOLS = ("create_project", "create_frame_model", "create_model_from_plan_draft", "import_from_etabs",
                        "modify_project", "preliminary_sizing", "apply_gravity_loads", "apply_lateral_loads",
                        "apply_self_weight", "generate_load_combinations", "set_project_units")


def _design_checks(calls: List[Tuple[str, Dict[str, Any]]]
                   ) -> List[Tuple[int, Dict[str, Any], Optional[Tuple[str, Dict[str, Any]]]]]:
    """Every ``run_design`` call as (call index, its arguments, the analysis it checked as (kind, arguments of the
    analysis call)).

    ``calls`` are the successful tool calls. ``run_design`` uses its ``analysis_case_id``, else the active
    case. A response spectrum call with ``envelope_to_design`` (the default) stores and activates the
    gravity-combined envelope '<analysis_case_id>_design', reported here as kind 'rsa_envelope'. The tools'
    aliases resolve as they do in the tools: 'envelope' is the latest static envelope (the first one before
    the tools were fixed; both are static envelopes), 'dynamic_envelope' the latest spectrum design envelope.
    """
    by_id: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    active = None
    checks = []
    for i, (name, args) in enumerate(calls):
        if name in ("run_analysis", "run_response_spectrum", "run_time_history"):
            cid = args.get("analysis_case_id")
            active = (name, args)
            if cid:
                by_id[cid] = active
            if name == "run_analysis" and args.get("analysis_type", "static") == "static" \
                    and str(args.get("load_case_id") or "envelope").upper() in _FULL_ENVELOPE:
                by_id["envelope"] = active
            if name == "run_response_spectrum" and args.get("envelope_to_design", True) and cid:
                active = by_id[f"{cid}_design"] = by_id["dynamic_envelope"] = ("rsa_envelope", args)
        elif name == "run_design":
            cid = args.get("analysis_case_id")
            checks.append((i, args, by_id.get(cid) if cid else active))
    return checks


def _final_design_basis(calls: List[Tuple[str, Dict[str, Any]]]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Analysis the last ``run_design`` call checked, as (kind, arguments of the analysis call)."""
    checks = _design_checks(calls)
    return checks[-1][2] if checks else None


def _final_model_design_checks(calls: List[Tuple[str, Dict[str, Any]]]
                               ) -> List[Tuple[int, Dict[str, Any], Optional[Tuple[str, Dict[str, Any]]]]]:
    """The design checks of the final model: the ``run_design`` calls after the last model-changing call, or the last
    check alone when the model changed after it. A diagnostic check after the final design (one combination, another
    bearing pressure) does not displace a check of the final model on the specified basis."""
    checks = _design_checks(calls)
    last_change = max((i for i, (name, _) in enumerate(calls) if name in MODEL_CHANGING_TOOLS), default=-1)
    final = [c for c in checks if c[0] > last_change]
    return final or checks[-1:]


def _close(value: Optional[float], target: float, tol: float = MATERIAL_TOLERANCE) -> bool:
    return value is not None and abs(value - target) <= tol * abs(target)


def materials_match(project: Any, case: BenchmarkCase) -> Tuple[bool, Dict[str, Any]]:
    """The frame's concrete and reinforcement are the prompt's: every concrete of a frame section has the spec f'c and
    unit weight, and every longitudinal and transverse rebar the spec fy (within 1 %; the unit weight within 2.5 %, so
    the conventional 24 kN/m3 for 2,400 kg/m3 passes). Values reported in MPa and kN/m3."""
    from struct_load.engine.self_weight import material_weight_density

    model = project.model
    units = getattr(getattr(project, "metadata", None), "units", None) or "kN, m"
    to_mpa = conversion_factor(units, "N, mm", "stress")
    to_kn_m3 = conversion_factor(units, "kN, m", "weight_density")
    spec = case.spec.materials
    used = {e.section_id for e in model.elements}
    sections = [s for s in model.sections if s.id in used]
    concrete, rebar = [], []
    for sec in sections:
        mat = model.get_material(sec.material_id)
        concrete.append(mat)
        rebar += [model.get_material(getattr(sec, k, None))
                  for k in ("rebar_material_id", "transverse_rebar_material_id")]
    found = {
        "fc_mpa": sorted({round(getattr(m, "fc", None) * to_mpa, 2) if getattr(m, "fc", None) else None
                          for m in concrete}, key=str),
        "fy_mpa": sorted({round(getattr(m, "fy", None) * to_mpa, 1) if getattr(m, "fy", None) else None
                          for m in rebar}, key=str),
    }
    weights = []
    for m in concrete:
        try:
            weights.append(round(material_weight_density(m, parse_units(units)) * to_kn_m3, 3))
        except (ValueError, AttributeError, TypeError):
            weights.append(None)
    found["unit_weight_kn_m3"] = sorted(set(weights), key=str)
    unit_weight = spec.density_kg_m3 * STANDARD_GRAVITY / 1000.0
    ok = (bool(sections)
          and all(_close(v, spec.fc_mpa) for v in found["fc_mpa"])
          and all(_close(v, spec.fy_mpa) for v in found["fy_mpa"])
          and all(_close(v, unit_weight, UNIT_WEIGHT_TOLERANCE) for v in found["unit_weight_kn_m3"]))
    return ok, found


def bearing_pressure_match(case: BenchmarkCase, project: Any,
                           tool_calls: List[Tuple[str, Dict[str, Any]]]) -> Tuple[bool, Optional[float]]:
    """A design check of the final model (``_final_model_design_checks``) used the prompt's allowable soil bearing
    pressure (spec pressure units). Returns the verdict and that pressure, else the last check's."""
    checks = _final_model_design_checks(tool_calls)
    if not checks:
        return False, None
    units = getattr(getattr(project, "metadata", None), "units", None) or "kN, m"
    target = case.spec.foundation.allowable_bearing_pressure
    values: List[Optional[float]] = []
    for k, (_, args, _) in enumerate(checks):
        try:
            if args.get("allowable_bearing_pressure") is not None:
                value = float(args["allowable_bearing_pressure"])
            elif k == len(checks) - 1:  # the stored design result is the last check's
                inputs = getattr(getattr(project, "design_result", None), "inputs", None)
                value = getattr(inputs, "allowable_bearing_pressure", None)
                value = None if value is None else float(value)
            else:
                value = None
            values.append(None if value is None else value * conversion_factor(units, case.spec.units, "pressure"))
        except (TypeError, ValueError):
            values.append(None)
    match = next((v for v in values if _close(v, target)), None)
    if match is not None:
        return True, round(match, 3)
    return False, None if values[-1] is None else round(values[-1], 3)


def evaluate_prompt_to_schema_fidelity(
    project: Any,
    case: BenchmarkCase,
    tool_calls: Optional[List[Tuple[str, Dict[str, Any]]]] = None,
    reference_load_totals: Optional[Dict[str, float]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Check that the configuration's model reproduces the case specification.

    Geometry is compared in spec units after converting the model's own units, so a model built in
    metres for a prompt stated in feet still passes when it is the same structure. ``tool_calls``
    (name, arguments of the successful calls) supply seismic and ground-motion parameters that are not
    stored on the model, and the analysis basis of the final design check.
    ``reference_load_totals`` (``gravity_load_totals`` of the oracle's model with the configuration's
    sections, spec units) checks the magnitude of the applied dead, live, and partition loads.
    """
    model = getattr(project, "model", None)
    if model is None or not getattr(model, "nodes", None):
        return False, {"error": "No structural model was produced."}
    spec = case.spec
    details: Dict[str, Any] = {}

    if spec.cae is not None:
        from struct_link import read_project

        fixture = read_project(REPO_ROOT / spec.cae.file).model
        details["node_count_match"] = len(model.nodes) == len(fixture.nodes)
        details["element_count_match"] = len(model.elements) == len(fixture.elements)
        details["support_count_match"] = len(model.supports) == len(fixture.supports)
        if case.deliverables.design != "none":
            details["materials_match"], details["materials"] = materials_match(project, case)
            details["bearing_pressure_match"], details["bearing_pressure"] = bearing_pressure_match(
                case, project, tool_calls or [])
            fixture_cases = {f.id.lower() for f in fixture.load_cases}
            details["no_unspecified_load_cases"] = not any(
                lc.id.lower() not in fixture_cases for lc in model.load_cases
            )
        return all(v for v in details.values() if isinstance(v, bool)), details

    geo = spec.geometry
    model_units = getattr(getattr(project, "metadata", None), "units", None) or "kN, m"
    scale = conversion_factor(model_units, spec.units, "length")
    tol = case.evaluation.geometry_tolerance
    xs = [n.x * scale for n in model.nodes]
    ys = [n.y * scale for n in model.nodes]
    zs = [getattr(n, "z", 0.0) * scale for n in model.nodes]
    is_3d = any(abs(z) > tol for z in zs)
    details["dimension_match"] = is_3d == (geo.dimension == "3d")

    vertical = zs if is_3d else ys
    elevations = _coords(vertical, tol)
    withheld = set(case.evaluation.withheld)
    if "story_heights" in withheld:
        details["story_count_match"] = len(elevations) == len(geo.story_heights) + 1
    else:
        details["story_heights_match"] = _matches(elevations, [0.0, *accumulate(geo.story_heights)], tol)
    if "bay_widths_x" not in withheld:
        details["grid_x_match"] = _grid_matches(_coords(xs, tol), list(geo.bay_widths_x), tol)
    if geo.dimension == "3d":
        details["grid_y_match"] = _grid_matches(_coords(ys, tol), list(geo.bay_widths_y), tol)

    plan_lines = len(geo.bay_widths_x) + 1
    if geo.dimension == "3d":
        plan_lines *= len(geo.bay_widths_y) + 1
    expected_columns = (plan_lines - len(geo.omitted_columns)) * len(geo.story_heights)
    node_by_id = {n.id: n for n in model.nodes}

    def _is_column(e: Any) -> bool:
        a, b = node_by_id.get(e.start_node), node_by_id.get(e.end_node)
        if a is None or b is None:
            return False
        if is_3d:
            return abs(a.x - b.x) * scale <= tol and abs(a.y - b.y) * scale <= tol
        return abs(a.x - b.x) * scale <= tol
    details["column_count_match"] = sum(1 for e in model.elements if _is_column(e)) == expected_columns

    if spec.sections is not None:
        # Prescribed sections (analysis cases) on every column and beam: gemma B01 left out the beam size, and the
        # tool's default 0.30 x 0.50 m beam replaced the prompt's 0.30 x 0.55 m (seen only as 2.3% more dead load)
        dims = {s.id: (getattr(s, "b", None), getattr(s, "h", None)) for s in model.sections}

        def _has(e: Any, want: Tuple[float, float]) -> bool:
            got = dims.get(e.section_id, (None, None))
            return None not in got and all(abs(g * scale - w) <= 0.01 * w for g, w in zip(got, want))
        details["sections_match"] = all(
            _has(e, spec.sections.column if _is_column(e) else spec.sections.beam) for e in model.elements)

    base = min(vertical)
    base_ids = {n.id for n, v in zip(model.nodes, vertical) if abs(v - base) <= tol}
    supports = {s.node_id: s for s in model.supports}
    rot = ("rx", "ry", "rz") if is_3d else ("rz",)
    want_fixed = geo.support == "fixed"
    details["supports_match"] = bool(base_ids) and all(
        nid in supports and all(bool(getattr(supports[nid], r, False)) == want_fixed for r in rot) for nid in base_ids
    )

    case_ids = [lc.id.lower() for lc in model.load_cases]
    details["gravity_cases_present"] = any("dead" in c for c in case_ids) and any("live" in c for c in case_ids)
    # The final model's loading, not only earlier tool calls (nemotron rebuilt models without them): static
    # design cases need load combinations, and ELF cases a loaded seismic case in every specified direction
    if spec.analysis == "static" and (case.deliverables.design != "none" or spec.initial_sections is not None):
        details["load_combinations_present"] = bool(getattr(model, "load_combinations", None))
    if spec.seismic is not None and spec.seismic.procedure == "elf":
        loaded = {lc.id.lower() for lc in model.load_cases if lc.point_loads or lc.element_loads}
        details["seismic_loads_present"] = all(f"eq_{d}" in loaded for d in spec.seismic.directions)
    # Gravity-only cases: no lateral loads and no seismic design basis the prompt does not state (qwen added
    # ELF loads with invented SDS to A01, B02 and D02, which adds seismic combinations and Chapter 18 checks)
    if spec.seismic is None:
        details["no_unspecified_lateral_loads"] = (
            not _horizontal_load_cases(model, is_3d) and getattr(project, "seismic_basis", None) is None)
    if reference_load_totals is not None:
        # Magnitudes, not just the presence of the cases: a unit slip (e.g. 0.105 entered as psf) changes them
        actual = gravity_load_totals(project, spec.units)
        # The partition weight enters only the seismic weight (no load combination uses it), so it is
        # compared only where the case states one or has a seismic analysis
        uses_partition = spec.loads.partition_weight is not None or spec.seismic is not None
        details["gravity_load_magnitudes_match"] = all(
            abs(actual[g] - ref) <= LOAD_TOTAL_TOLERANCE * max(abs(ref), 1e-9) if ref > 0 else actual[g] <= 1e-9
            for g, ref in reference_load_totals.items() if g in actual and (g != "partition" or uses_partition)
        )
        details["gravity_load_totals"] = {g: round(v, 3) for g, v in actual.items()}
        # ELF force applied, whatever produced it: minimax A04 passed an invented TL = 0.36 s (below its period),
        # which cut the base shear by 11% while SDS, SD1, R and Ie all matched
        lateral_ref = {g: v for g, v in reference_load_totals.items() if g.startswith("eq_")}
        if lateral_ref:
            lateral = lateral_load_totals(project, spec.units)
            details["seismic_load_magnitudes_match"] = all(
                abs(lateral.get(g, 0.0) - ref) <= LOAD_TOTAL_TOLERANCE * max(abs(ref), 1e-9)
                for g, ref in lateral_ref.items())
            details["seismic_load_totals"] = {g: round(v, 3) for g, v in lateral.items()}

    seis = spec.seismic
    if seis is not None:
        calls = tool_calls or []
        target_tool = {"elf": "apply_lateral_loads", "rsa_code": "run_response_spectrum",
                       "rsa_record": "run_response_spectrum", "tha": "run_time_history"}[seis.procedure]
        args_list = [a for name, a in calls if name == target_tool]

        def _ok(args: Dict[str, Any]) -> bool:
            if seis.sds is not None and abs(float(args.get("sds") or 0.0) - seis.sds) > 1e-3:
                return False
            if seis.sd1 is not None and abs(float(args.get("sd1") or 0.0) - seis.sd1) > 1e-3:
                return False
            if seis.r_factor is not None and seis.procedure != "tha":
                # r_factor is R; Ie and the system type are separate arguments of both seismic tools. The ELF tool
                # takes R from the system (ASCE 7-22 Table 12.2-1) when it is not given (a response spectrum
                # without R stays elastic); both take Ie from the Risk Category (Table 1.5-2, default II)
                from struct_load import seismic_importance_factor, seismic_system_coefficients

                default_system = "rc_smf" if target_tool == "apply_lateral_loads" else None
                r_factor = args.get("r_factor")
                if r_factor is None and target_tool == "apply_lateral_loads":
                    try:
                        r_factor = seismic_system_coefficients(args.get("system_type") or default_system)[0]
                    except ValueError:
                        return False
                importance = args.get("importance_factor")
                if importance is None:
                    try:
                        importance = seismic_importance_factor(args.get("risk_category") or "II")
                    except ValueError:
                        return False
                if r_factor is None or abs(float(r_factor) - seis.r_factor) > 1e-3:
                    return False
                if abs(float(importance) - seis.importance_factor) > 1e-3:
                    return False
                if seis.system is not None and args.get("system_type", default_system) != seis.system:
                    return False
            # S1 enters only through the Cs lower bound of Eq. 12.8-7 (and SDC E/F), which apply when S1 >= 0.6
            if seis.s1 is not None and seis.s1 >= S1_LOWER_BOUND_THRESHOLD \
                    and abs(float(args.get("s1") or 0.0) - seis.s1) > 1e-3:
                return False
            if seis.ground_motion is not None:
                gm = str(args.get("ground_motion") or "").replace("\\", "/")
                if not gm.endswith(seis.ground_motion.file.split("/")[-1]):
                    return False
            return True
        details["seismic_parameters_match"] = any(_ok(a) for a in args_list)

        # RSA designs: a design check of the final model uses the gravity-combined envelope of a matching spectrum
        # analysis in the specified directions (gemma B05 designed on a static ELF envelope instead, and
        # one-direction analyses lack the orthogonal combination of direction='both')
        if spec.analysis == "rsa" and (case.deliverables.design != "none" or spec.initial_sections is not None):
            want = "both" if len(seis.directions) > 1 else seis.directions[0]
            details["design_on_spectrum_envelope"] = any(
                basis is not None and basis[0] == "rsa_envelope" and _ok(basis[1])
                and basis[1].get("direction", "x") == want
                for _, _, basis in _final_model_design_checks(calls)
            )

        # ELF combinations are generated by the agent: Ev = 0.2 SDS D (§12.4.2.2) and the 100-30 rule (§12.5)
        # must follow the spec. (The RSA tool builds its own combinations from its sds argument.)
        if seis.procedure == "elf":
            combo_calls = [a for name, a in calls if name == "generate_load_combinations"]

            def _combo_ok(args: Dict[str, Any]) -> bool:
                sds = args.get("sds")
                if seis.vertical_effect:
                    ev_ok = sds is not None and abs(float(sds) - seis.sds) <= 1e-3
                else:
                    ev_ok = not sds
                orth_ok = True
                if len(seis.directions) > 1:
                    orth_ok = bool(args.get("orthogonal_seismic", True)) == bool(seis.orthogonal_combination)
                return ev_ok and orth_ok

            details["load_combinations_match"] = bool(combo_calls) and _combo_ok(combo_calls[-1])

    # The prompt's concrete and reinforcement, and the allowable bearing pressure of a design
    details["materials_match"], details["materials"] = materials_match(project, case)
    if spec.foundation is not None:
        details["bearing_pressure_match"], details["bearing_pressure"] = bearing_pressure_match(
            case, project, tool_calls or [])

    if spec.loads is not None and spec.loads.partition_weight is not None:
        partition_case = next((lc for lc in model.load_cases if lc.id == "PartitionWeight"), None)
        details["partition_weight_present"] = partition_case is not None and bool(partition_case.element_loads)

    # Static design cases (gravity, ELF): a design check of the final model uses the envelope of all load
    # combinations of a static analysis (qwen designed the ELF case C06 on a response spectrum envelope instead)
    if spec.analysis == "static" and (case.deliverables.design != "none" or spec.initial_sections is not None):
        details["design_on_static_envelope"] = any(
            basis is not None and basis[0] == "run_analysis"
            and basis[1].get("analysis_type", "static") == "static"
            and str(basis[1].get("load_case_id") or "envelope").upper() in _FULL_ENVELOPE
            for _, _, basis in _final_model_design_checks(tool_calls or [])
        )

    # A design check of the final model uses an analysis with cracked sections (Table 6.6.3.1.1) and slenderness
    # (§6.6.4)
    if case.deliverables.design != "none" or spec.initial_sections is not None:
        details["design_analysis_basis_match"] = any(
            basis is not None and bool(basis[1].get("cracked_sections")) and bool(basis[1].get("second_order"))
            for _, _, basis in _final_model_design_checks(tool_calls or [])
        )

    return all(v for v in details.values() if isinstance(v, bool)), details


# ----------------------------------------------------------------------------
# Design-check currency
# ----------------------------------------------------------------------------
ANALYSIS_TOOLS = ("run_analysis", "run_response_spectrum", "run_time_history")


class DesignCheckTracker:
    """Follows a run's tool calls to tell whether its design checks used an analysis of the model as it stood.

    Before struct_agent stamped analysis results (``model_state``), ``run_design`` checked whichever stored
    result it was given: after a model change (resized sections, new loads) without a new analysis, a check
    combined the new section capacities with the old demands (nemotron B04 resized and re-checked that way).
    Runs logged with those tools are judged here, and a model changed after the final check is caught. Each
    analysis result is fingerprinted when an analysis tool creates it; static results include the model's load
    combinations, response-spectrum and time-history results do not (they build their own combinations).
    """

    def __init__(self) -> None:
        self._stamps: Dict[str, Tuple[Any, bool, str]] = {}  # case id -> (result object, with combos, fingerprint)
        self._last_check: Optional[Tuple[Any, bool, str]] = None
        self.checks_current: List[bool] = []  # per successful run_design: was its analysis current then?

    def record(self, tool: str, project: Any, ok: bool) -> None:
        """Call after every tool call, with the runner's project after the call."""
        if not ok or project is None or getattr(project, "model", None) is None:
            return
        if tool in ANALYSIS_TOOLS:
            combos = tool == "run_analysis"
            fp = model_fingerprint(project, combos)
            for cid, res in project.analysis_results.items():
                stamp = self._stamps.get(cid)
                if stamp is None or stamp[0] is not res:  # new or replaced result; an unchanged alias keeps its stamp
                    self._stamps[cid] = (res, combos, fp)
        elif tool == "run_design":
            cid = project.active_analysis_case  # run_design activates the case it checked
            stamp = self._stamps.get(cid)
            if stamp is not None and project.analysis_results.get(cid) is not stamp[0]:
                stamp = None  # a result no analysis tool of this run produced
            self._last_check = stamp
            self.checks_current.append(self._current(stamp, project))

    @staticmethod
    def _current(stamp: Optional[Tuple[Any, bool, str]], project: Any) -> bool:
        return stamp is not None and model_fingerprint(project, stamp[1]) == stamp[2]

    def design_current(self, project: Any) -> bool:
        """The last design check used an analysis of ``project`` as it now stands."""
        return project is not None and getattr(project, "model", None) is not None \
            and self._current(self._last_check, project)


def tool_calls_from_messages(messages: List[Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any]]]:
    """Extract (tool name, arguments) pairs from an OpenAI-style message log."""
    calls: List[Tuple[str, Dict[str, Any]]] = []
    for msg in messages or []:
        for tc in msg.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            raw = fn.get("arguments", {})
            try:
                args = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
            except (TypeError, ValueError):
                args = {}
            calls.append((fn.get("name", ""), args))
    return calls
