from pathlib import Path
from typing import Any, Dict, List, Optional
import streamlit.components.v1 as components

_component_func = components.declare_component(
    "dnd_grid",
    path=str(Path(__file__).parent),
)


def dnd_grid(
    schedule_matrix: Dict,
    unassigned_blocks: Dict,
    sections: List[Dict],
    plan_comun_level: int,
    academic_blocks: Optional[Dict] = None,
    key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    return _component_func(
        schedule_matrix=schedule_matrix,
        unassigned_blocks=unassigned_blocks,
        sections=sections,
        plan_comun_level=plan_comun_level,
        academic_blocks=academic_blocks or {},
        key=key,
        default=None,
        height=1100,
    )
