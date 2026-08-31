#!/usr/bin/env python3
"""Canonical OpenShift Edge workstream -> Jira component map.

This is the single in-repo source of truth for the six workstreams and the Jira
OCPEDGE components that belong to each. It is intentionally a code constant so the
plugin works without waiting on an edge-context documentation PR.

The map is list-valued because live OCPEDGE components are not 1:1 with
workstreams: TNF owns both ``TNF`` and ``Two Node Fencing``; TOPO owns both
``Topology Transitions`` and ``Mutable Topology``. The ``Planning`` component is
not a workstream and is intentionally absent, so it resolves to ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Workstream:
    """A long-lived stream of Edge engineering work and its Jira components."""

    acronym: str
    name: str
    components: Tuple[str, ...]


# Order here defines the canonical column order used by metrics and renderers.
_WORKSTREAMS: Tuple[Workstream, ...] = (
    Workstream("SNO", "Single Node", ("SNO",)),
    Workstream("TNA", "Two Node with Arbiter", ("Two Node with Arbiter",)),
    Workstream("TNF", "Two Node Fencing", ("TNF", "Two Node Fencing")),
    Workstream("LVMS", "Logical Volume Manager Storage", ("Logical Volume Manager Storage",)),
    Workstream("USHIFT", "MicroShift", ("MicroShift",)),
    Workstream("TOPO", "Topology Transitions", ("Topology Transitions", "Mutable Topology")),
)

# Jira components that exist in OCPEDGE but are deliberately not workstreams.
# Kept for documentation; they resolve to None like any other unmapped component.
NON_WORKSTREAM_COMPONENTS: Tuple[str, ...] = ("Planning",)


def _normalize(component_name: str) -> str:
    return component_name.strip().lower()


_COMPONENT_INDEX: Dict[str, str] = {
    _normalize(component): stream.acronym
    for stream in _WORKSTREAMS
    for component in stream.components
}


def workstreams() -> Tuple[Workstream, ...]:
    """Return the six workstreams in canonical order."""
    return _WORKSTREAMS


def workstream_acronyms() -> List[str]:
    """Return the six workstream acronyms in canonical order."""
    return [stream.acronym for stream in _WORKSTREAMS]


def component_to_workstream(component_name: Optional[str]) -> Optional[str]:
    """Map a Jira component name to a workstream acronym.

    Returns ``None`` for a genuine miss: unknown components, non-workstream
    components such as ``Planning``, and empty/``None`` input. Lookup is
    case-insensitive and ignores surrounding whitespace.
    """
    if component_name is None:
        return None
    key = _normalize(component_name)
    if not key:
        return None
    return _COMPONENT_INDEX.get(key)
