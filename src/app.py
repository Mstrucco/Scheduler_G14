"""
Comprehensive Streamlit UI for University Course Scheduler MVP

Features:
- Interactive drag-and-drop schedule matrix
- Real-time constraint validation
- Multi-tab cohort views + master compilation
- Production Excel export
- Session state persistence
"""

import streamlit as st
import pandas as pd
from io import BytesIO
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
import json
import html as html_utils
from datetime import datetime

# Local imports
from src.data.loader import load_course_sections
from src.solver.scheduler import CourseScheduler
from src.models.models import (
    DayOfWeek,
    SessionType,
    ACADEMIC_BLOCKS,
    TimeSlot,
    GlobalTimeConstraints,
)


# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

def initialize_session_state() -> None:
    """Initialize all required session state keys on first app run."""
    if "sections" not in st.session_state:
        st.session_state.sections = []
    
    if "schedule_matrix" not in st.session_state:
        # Structure: {(day_val, block_idx): [(section_key, session_type, room), ...]}
        st.session_state.schedule_matrix = {}
    
    if "unassigned_blocks" not in st.session_state:
        # Structure: {section_key: [(session_type, reason), ...]}
        st.session_state.unassigned_blocks = {}
    
    if "relaxation_flags" not in st.session_state:
        st.session_state.relaxation_flags = {
            "plan_comun_1": False,
            "plan_comun_2": False,
            "plan_comun_3": False,
            "plan_comun_4": False,
        }
    
    if "drag_drop_state" not in st.session_state:
        st.session_state.drag_drop_state = {}


# ============================================================================
# SCHEDULE DATA HELPERS
# ============================================================================

def get_section_lookup() -> Dict[str, Any]:
    """Return loaded sections keyed by their stable section identifier."""
    return {section.section_key: section for section in st.session_state.sections}


def normalize_session_type(session_type: Any) -> str:
    """Normalize enum/string session labels to the values used by SessionType."""
    if isinstance(session_type, SessionType):
        return session_type.value

    raw_value = str(session_type or "").strip()
    lowered = raw_value.lower()

    aliases = {
        "clase": SessionType.CLASE.value,
        "clases": SessionType.CLASE.value,
        "ayudantia": SessionType.AYUDANTIA.value,
        "ayudantias": SessionType.AYUDANTIA.value,
        "ayudantía": SessionType.AYUDANTIA.value,
        "ayudantías": SessionType.AYUDANTIA.value,
        "laboratorio": SessionType.LABORATORIO.value,
        "laboratorios": SessionType.LABORATORIO.value,
        "lab": SessionType.LABORATORIO.value,
    }

    if lowered in aliases:
        return aliases[lowered]

    for session_enum in SessionType:
        if raw_value == session_enum.value or raw_value.upper() == session_enum.name:
            return session_enum.value

    return raw_value or SessionType.CLASE.value


def session_type_to_enum(session_type: Any) -> Optional[SessionType]:
    """Convert a session label to its enum, returning None for unknown labels."""
    normalized = normalize_session_type(session_type)
    for session_enum in SessionType:
        if normalized == session_enum.value:
            return session_enum
    return None


def get_day_value(day: Any) -> Optional[int]:
    """Convert day names/enums/integers to the app's day index."""
    if isinstance(day, DayOfWeek):
        return day.value

    if isinstance(day, int):
        return day if day in [day_enum.value for day_enum in DayOfWeek] else None

    raw_value = str(day or "").strip()
    if raw_value.isdigit():
        numeric_day = int(raw_value)
        return numeric_day if numeric_day in [day_enum.value for day_enum in DayOfWeek] else None

    normalized = raw_value.upper()
    if normalized in DayOfWeek.__members__:
        return DayOfWeek[normalized].value

    return None


def get_session_requirements(section: Any) -> Dict[str, int]:
    """Return required block counts per session type for a section."""
    return {
        SessionType.CLASE.value: section.required_clases,
        SessionType.AYUDANTIA.value: section.required_ayudantias,
        SessionType.LABORATORIO.value: section.required_laboratorios,
    }


def get_professor_for_session(section: Any, session_type: Any) -> str:
    """Return the professor token responsible for the given session type."""
    normalized = normalize_session_type(session_type)

    if normalized == SessionType.CLASE.value:
        return section.professor_1_rut
    if normalized == SessionType.AYUDANTIA.value:
        return section.professor_2_rut or section.professor_1_rut
    if normalized == SessionType.LABORATORIO.value:
        return section.lab_professor_rut or section.professor_1_rut

    return section.professor_1_rut


def get_room_for_section(section: Any, room: Optional[str] = None) -> str:
    """Prefer explicit room data, then special room requirements, then Standard."""
    if room and room != "Standard":
        return room
    return section.special_room or room or "Standard"


def get_block_label(block_idx: int) -> str:
    """Return a readable block label with its academic time range."""
    block = ACADEMIC_BLOCKS.get(block_idx)
    if not block:
        return f"Block {block_idx}"
    return f"Block {block_idx} ({block.start_time}-{block.end_time})"


def short_text(value: Any, max_length: int = 28) -> str:
    """Trim long opaque tokens and course titles for compact UI labels."""
    text = str(value or "")
    if len(text) <= max_length:
        return text
    return f"{text[:max_length - 3]}..."


def session_css_class(session_type: Any) -> str:
    """Return a stable CSS class for a session type."""
    normalized = normalize_session_type(session_type)
    if normalized == SessionType.AYUDANTIA.value:
        return "ayudantia"
    if normalized == SessionType.LABORATORIO.value:
        return "laboratorio"
    return "clase"


def session_abbreviation(session_type: Any) -> str:
    """Return a compact label for cards."""
    normalized = normalize_session_type(session_type)
    if normalized == SessionType.AYUDANTIA.value:
        return "AYU"
    if normalized == SessionType.LABORATORIO.value:
        return "LAB"
    return "CLA"


def coerce_unassigned_item(item: Any) -> Tuple[str, str]:
    """Support both old tuple entries and the richer dict entries used now."""
    if isinstance(item, dict):
        return (
            normalize_session_type(item.get("session_type")),
            str(item.get("reason") or item.get("details") or "Unassigned"),
        )

    if isinstance(item, (tuple, list)) and item:
        session_type = normalize_session_type(item[0])
        reason = str(item[1]) if len(item) > 1 else "Unassigned"
        return session_type, reason

    return SessionType.CLASE.value, "Unassigned"


def build_schedule_matrix_from_assignments(scheduled_blocks: List[Dict]) -> Dict[Tuple[int, int], List[Tuple[str, str, str]]]:
    """Convert solver assignments into the session-state matrix format."""
    matrix: Dict[Tuple[int, int], List[Tuple[str, str, str]]] = {}

    for block_info in scheduled_blocks:
        section_key = block_info.get("section_key")
        session_type = normalize_session_type(block_info.get("session_type"))
        day_val = get_day_value(block_info.get("day"))
        block_idx = block_info.get("block_index")

        if not section_key or day_val is None or block_idx is None:
            continue

        try:
            block_idx = int(block_idx)
        except (TypeError, ValueError):
            continue

        room = block_info.get("room") or block_info.get("special_room") or "Standard"
        key = (day_val, block_idx)
        matrix.setdefault(key, []).append((section_key, session_type, room))

    return matrix


def summarize_conflict_reason(conflict: Optional[Dict], session_type: str) -> str:
    """Turn solver diagnostics into compact human-readable sidebar text."""
    if not conflict:
        return f"No feasible {session_type} block was assigned."

    if conflict.get("reason"):
        return str(conflict["reason"])

    diagnosis = conflict.get("diagnosis") or {}
    bottlenecks = diagnosis.get("bottlenecks") or []
    descriptions = [
        str(bottleneck.get("description"))
        for bottleneck in bottlenecks
        if bottleneck.get("description")
    ]

    if descriptions:
        return " | ".join(descriptions[:2])

    missing = conflict.get("missing_blocks", "some")
    return f"Solver left {missing} required block(s) unassigned."


def build_unassigned_registry(
    sections: List[Any],
    matrix: Dict[Tuple[int, int], List[Tuple[str, str, str]]],
    conflict_report: Optional[List[Dict]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Build a per-section registry of missing blocks by exact session type."""
    scheduled_counts: Dict[Tuple[str, str], int] = defaultdict(int)
    conflicts_by_section = {
        conflict.get("section_key"): conflict
        for conflict in (conflict_report or [])
        if conflict.get("section_key")
    }

    for blocks in matrix.values():
        for section_key, session_type, _ in blocks:
            scheduled_counts[(section_key, normalize_session_type(session_type))] += 1

    registry: Dict[str, List[Dict[str, Any]]] = {}
    for section in sections:
        missing_items: List[Dict[str, Any]] = []
        requirements = get_session_requirements(section)
        conflict = conflicts_by_section.get(section.section_key)

        for session_type, required_blocks in requirements.items():
            if required_blocks <= 0:
                continue

            scheduled_blocks = scheduled_counts[(section.section_key, session_type)]
            missing_blocks = max(required_blocks - scheduled_blocks, 0)
            reason = summarize_conflict_reason(conflict, session_type)

            for _ in range(missing_blocks):
                missing_items.append({
                    "session_type": session_type,
                    "reason": reason,
                    "required": required_blocks,
                    "scheduled": scheduled_blocks,
                })

        if missing_items:
            registry[section.section_key] = missing_items

    return registry


def remove_unassigned_block(section_key: str, session_type: str) -> bool:
    """Remove one matching unassigned block after a manual drop into the grid."""
    items = list(st.session_state.unassigned_blocks.get(section_key, []))
    normalized = normalize_session_type(session_type)

    for index, item in enumerate(items):
        item_session_type, _ = coerce_unassigned_item(item)
        if item_session_type == normalized:
            del items[index]
            if items:
                st.session_state.unassigned_blocks[section_key] = items
            else:
                st.session_state.unassigned_blocks.pop(section_key, None)
            return True

    return False


def add_unassigned_block(section_key: str, session_type: str, reason: str = "Manually unassigned") -> None:
    """Add one unassigned block back into the sidebar bank."""
    st.session_state.unassigned_blocks.setdefault(section_key, []).append({
        "session_type": normalize_session_type(session_type),
        "reason": reason,
    })


def remove_scheduled_block(day_val: int, block_idx: int, section_key: str, session_type: str) -> Optional[Tuple[str, str, str]]:
    """Remove and return one scheduled block from a source cell."""
    source_key = (day_val, block_idx)
    blocks = list(st.session_state.schedule_matrix.get(source_key, []))
    normalized = normalize_session_type(session_type)

    for index, block in enumerate(blocks):
        current_section_key, current_session_type, _ = block
        if current_section_key == section_key and normalize_session_type(current_session_type) == normalized:
            removed = block
            del blocks[index]
            if blocks:
                st.session_state.schedule_matrix[source_key] = blocks
            else:
                st.session_state.schedule_matrix.pop(source_key, None)
            return removed

    return None


def schedule_block_at(day_val: int, block_idx: int, block: Tuple[str, str, str]) -> None:
    """Place a scheduled block in the target cell unless it already exists there."""
    target_key = (day_val, block_idx)
    existing_blocks = st.session_state.schedule_matrix.setdefault(target_key, [])
    section_key, session_type, _ = block
    normalized = normalize_session_type(session_type)

    duplicate = any(
        existing_section_key == section_key and normalize_session_type(existing_session_type) == normalized
        for existing_section_key, existing_session_type, _ in existing_blocks
    )
    if not duplicate:
        existing_blocks.append((section_key, normalized, block[2]))


def is_scheduled_at(day_val: int, block_idx: int, section_key: str, session_type: str) -> bool:
    """Return True if the target cell already has this section/session pair."""
    normalized = normalize_session_type(session_type)
    return any(
        existing_section_key == section_key and normalize_session_type(existing_session_type) == normalized
        for existing_section_key, existing_session_type, _ in st.session_state.schedule_matrix.get((day_val, block_idx), [])
    )


def apply_schedule_action(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Apply a drag/drop action sent from the embedded HTML grid."""
    action = payload.get("action")
    section_key = str(payload.get("section_key") or "").strip()
    session_type = normalize_session_type(payload.get("session_type"))
    section_lookup = get_section_lookup()
    section = section_lookup.get(section_key)

    if action not in {"move_block", "unassign_block"}:
        return False, "Unsupported schedule action."
    if not section:
        return False, "The dragged course was not found in the loaded dataset."

    source_day = get_day_value(payload.get("source_day"))
    source_block = payload.get("source_block")
    if source_block not in (None, ""):
        try:
            source_block = int(source_block)
        except (TypeError, ValueError):
            return False, "The source block could not be read."

    if action == "unassign_block":
        if source_day is None or source_block is None:
            return False, "Only scheduled blocks can be moved back to unassigned."

        removed = remove_scheduled_block(source_day, source_block, section_key, session_type)
        if not removed:
            return False, "The source block was no longer scheduled."

        add_unassigned_block(section_key, session_type)
        return True, f"{section.course_code} was moved back to unassigned."

    target_day = get_day_value(payload.get("target_day"))
    target_block = payload.get("target_block")
    try:
        target_block = int(target_block)
    except (TypeError, ValueError):
        return False, "The target block could not be read."

    if target_day is None or target_block not in ACADEMIC_BLOCKS:
        return False, "The target slot is outside the academic calendar."

    source = payload.get("source")
    if source == "scheduled":
        if source_day is None or source_block is None:
            return False, "The source slot could not be read."
        if source_day == target_day and source_block == target_block:
            return True, "No change needed."
        if is_scheduled_at(target_day, target_block, section_key, session_type):
            return False, "The target slot already contains that block."

        removed = remove_scheduled_block(source_day, source_block, section_key, session_type)
        if not removed:
            return False, "The source block was no longer scheduled."

        schedule_block_at(target_day, target_block, removed)
        return True, f"{section.course_code} moved to {DayOfWeek(target_day).name} {get_block_label(target_block)}."

    if source == "unassigned":
        if is_scheduled_at(target_day, target_block, section_key, session_type):
            return False, "The target slot already contains that block."
        if not remove_unassigned_block(section_key, session_type):
            return False, "That unassigned block was already placed."

        room = get_room_for_section(section)
        schedule_block_at(target_day, target_block, (section_key, session_type, room))
        return True, f"{section.course_code} was scheduled on {DayOfWeek(target_day).name} {get_block_label(target_block)}."

    return False, "The drag source could not be read."


def process_pending_drag_drop_action() -> None:
    """Read one pending drag/drop action from query params and apply it once."""
    params = st.experimental_get_query_params()
    raw_payload_values = params.get("schedule_move")
    if not raw_payload_values:
        return

    raw_payload = raw_payload_values[-1] if isinstance(raw_payload_values, list) else raw_payload_values
    try:
        payload = json.loads(raw_payload)
        success, message = apply_schedule_action(payload)
    except Exception as exc:
        success = False
        message = f"Could not apply drag/drop change: {exc}"

    st.session_state.drag_drop_state["last_feedback"] = {
        "success": success,
        "message": message,
    }

    cleaned_params = {
        key: value
        for key, value in params.items()
        if key not in {"schedule_move", "schedule_move_nonce"}
    }
    st.experimental_set_query_params(**cleaned_params)
    st.experimental_rerun()


def render_drag_drop_feedback() -> None:
    """Show the result of the latest drag/drop change once."""
    feedback = st.session_state.drag_drop_state.pop("last_feedback", None)
    if not feedback:
        return

    if feedback.get("success"):
        st.success(feedback.get("message", "Schedule updated."))
    else:
        st.error(feedback.get("message", "Schedule update failed."))


def load_and_schedule_data(file_path: str) -> bool:
    """
    Load course data and run initial automated scheduling.
    Returns True if successful, False otherwise.
    """
    try:
        # Load sections from file
        sections = load_course_sections(file_path)
        if not sections:
            st.error("Failed to load sections from file")
            return False
        
        st.session_state.sections = sections
        
        # Run automated scheduler
        scheduler = CourseScheduler(sections)
        scheduled_blocks, conflict_report = scheduler.solve(timeout_seconds=60)
        
        # Build schedule matrix from scheduled blocks
        matrix = build_schedule_matrix_from_assignments(scheduled_blocks)
        st.session_state.schedule_matrix = matrix
        
        # Build unassigned blocks registry
        st.session_state.unassigned_blocks = build_unassigned_registry(
            sections,
            matrix,
            conflict_report,
        )
        return True
        
    except Exception as e:
        st.error(f"Error loading/scheduling data: {str(e)}")
        return False


# ============================================================================
# CONSTRAINT VALIDATION ENGINE
# ============================================================================

def _legacy_validate_schedule() -> Dict:
    """
    Run constraint validation sweep over active schedule matrix.
    Returns report dict with violations list.
    """
    report = {
        "valid": True,
        "violations": [],
        "stats": {
            "total_slots_used": 0,
            "total_sections": len(st.session_state.sections),
            "scheduled_blocks": 0,
            "unscheduled_blocks": sum(len(v) for v in st.session_state.unassigned_blocks.values()),
        }
    }
    
    # Track professors by (day, block) to detect double-booking
    professor_bookings: Dict[Tuple, List] = {}
    
    # Track rooms by (day, block) to detect room conflicts
    room_bookings: Dict[Tuple, List] = {}
    
    # Iterate through schedule matrix
    for (day_val, block_idx), blocks in st.session_state.schedule_matrix.items():
        report["stats"]["total_slots_used"] += 1
        report["stats"]["scheduled_blocks"] += len(blocks)
        
        for section_key, session_type, room in blocks:
            # Find section details
            section = next((s for s in st.session_state.sections if s.section_key == section_key), None)
            if not section:
                continue
            
            # Determine professor based on session type
            if session_type == SessionType.CLASE.value:
                professor = section.professor_1_rut
            elif session_type == SessionType.AYUDANTIA.value:
                professor = section.professor_2_rut or section.professor_1_rut
            else:  # LABORATORIO
                professor = section.lab_professor_rut or section.professor_1_rut
            
            # Check professor double-booking
            prof_key = (day_val, block_idx, professor)
            if prof_key not in professor_bookings:
                professor_bookings[prof_key] = []
            professor_bookings[prof_key].append((section_key, session_type))
            
            # Check room conflicts (if special room specified)
            if section.special_room and section.special_room.strip():
                room_key = (day_val, block_idx, section.special_room)
                if room_key not in room_bookings:
                    room_bookings[room_key] = []
                room_bookings[room_key].append((section_key, session_type))
    
    # Report professor double-bookings
    for (day_val, block_idx, prof), sections in professor_bookings.items():
        if len(sections) > 1:
            report["valid"] = False
            day_name = DayOfWeek(day_val).name
            block_time = ACADEMIC_BLOCKS[block_idx]
            report["violations"].append({
                "type": "PROFESSOR_DOUBLE_BOOKING",
                "day": day_name,
                "block": f"{block_idx} ({block_time.start_time}-{block_time.end_time})",
                "professor": prof[:20] + "..." if len(prof) > 20 else prof,
                "sections": len(sections),
                "details": f"Professor booked {len(sections)} times on {day_name} Block {block_idx}"
            })
    
    # Report room conflicts
    for (day_val, block_idx, room), sections in room_bookings.items():
        if len(sections) > 1:
            report["valid"] = False
            day_name = DayOfWeek(day_val).name
            report["violations"].append({
                "type": "ROOM_CONFLICT",
                "day": day_name,
                "block": block_idx,
                "room": room,
                "sections": len(sections),
                "details": f"Room '{room}' booked {len(sections)} times on {day_name} Block {block_idx}"
            })
    
    # Report cohort overlaps
    for (day_val, block_idx, plan_comun), sections in {}.items():
        if len(sections) > 1:
            report["valid"] = False
            day_name = DayOfWeek(day_val).name
            report["violations"].append({
                "type": "COHORT_OVERLAP",
                "day": day_name,
                "block": block_idx,
                "plan_comun_level": plan_comun,
                "sections": len(sections),
                "details": f"Plan Común {plan_comun} has {len(sections)} courses on {day_name} Block {block_idx}"
            })
    
    # Check for isolated single blocks outside block 4
    for section in st.session_state.sections:
        blocks_scheduled = sum(
            1 for (day_val, block_idx), blocks in st.session_state.schedule_matrix.items()
            if any(sk == section.section_key for sk, _, _ in blocks)
        )
        
        total_required = section.required_clases + section.required_ayudantias + section.required_laboratorios
        if total_required == 1 and blocks_scheduled == 1:
            # Find which block was scheduled
            for (day_val, block_idx), blocks in st.session_state.schedule_matrix.items():
                if any(sk == section.section_key for sk, _, _ in blocks):
                    if block_idx != 4:  # Block 4 is lunch hour
                        report["valid"] = False
                        day_name = DayOfWeek(day_val).name
                        report["violations"].append({
                            "type": "INVALID_SINGLE_BLOCK",
                            "section": section.section_key[:20] + "...",
                            "block": block_idx,
                            "day": day_name,
                            "details": f"Single-block courses must use Block 4 (lunch hour), not Block {block_idx}"
                        })
                    break
    
    return report


def validate_schedule() -> Dict:
    """
    Run constraint validation over the editable schedule matrix.

    The checks here mirror the solver's current contract and also catch manual
    edits that can be introduced through drag/drop.
    """
    report = {
        "valid": True,
        "violations": [],
        "stats": {
            "total_slots_used": 0,
            "total_sections": len(st.session_state.sections),
            "scheduled_blocks": 0,
            "unscheduled_blocks": sum(len(v) for v in st.session_state.unassigned_blocks.values()),
        }
    }

    section_lookup = get_section_lookup()
    professor_bookings: Dict[Tuple[int, int, str], List[Tuple[str, str]]] = defaultdict(list)
    room_bookings: Dict[Tuple[int, int, str], List[Tuple[str, str]]] = defaultdict(list)
    course_bookings: Dict[Tuple[int, int, str], List[Tuple[str, str]]] = defaultdict(list)
    exact_bookings: Dict[Tuple[int, int, str, str], List[str]] = defaultdict(list)
    scheduled_counts: Dict[Tuple[str, str], int] = defaultdict(int)
    scheduled_locations: Dict[Tuple[str, str], List[Tuple[int, int]]] = defaultdict(list)
    lecture_blocks_by_day: Dict[Tuple[str, int], List[int]] = defaultdict(list)

    def add_violation(violation_type: str, details: str, **fields: Any) -> None:
        report["valid"] = False
        violation = {"type": violation_type, "details": details}
        violation.update(fields)
        report["violations"].append(violation)

    for (day_val, block_idx), blocks in st.session_state.schedule_matrix.items():
        report["stats"]["total_slots_used"] += 1
        report["stats"]["scheduled_blocks"] += len(blocks)

        if day_val not in [day.value for day in DayOfWeek] or block_idx not in ACADEMIC_BLOCKS:
            add_violation(
                "INVALID_SLOT",
                f"Schedule contains an invalid slot ({day_val}, {block_idx})",
                day=day_val,
                block=block_idx,
            )
            continue

        day_name = DayOfWeek(day_val).name
        slot = TimeSlot(DayOfWeek(day_val), block_idx)

        for section_key, session_type, room in blocks:
            section = section_lookup.get(section_key)
            if not section:
                add_violation(
                    "UNKNOWN_SECTION",
                    f"Scheduled block references unknown section '{section_key}'",
                    day=day_name,
                    block=get_block_label(block_idx),
                    section=section_key,
                )
                continue

            normalized_session_type = normalize_session_type(session_type)
            session_enum = session_type_to_enum(normalized_session_type)
            scheduled_counts[(section_key, normalized_session_type)] += 1
            scheduled_locations[(section_key, normalized_session_type)].append((day_val, block_idx))
            exact_bookings[(day_val, block_idx, section_key, normalized_session_type)].append(room)

            if normalized_session_type == SessionType.CLASE.value:
                lecture_blocks_by_day[(section_key, day_val)].append(block_idx)

            if session_enum is None:
                add_violation(
                    "UNKNOWN_SESSION_TYPE",
                    f"{section.course_code} has unknown session type '{session_type}'",
                    day=day_name,
                    block=get_block_label(block_idx),
                    section=section.section_key,
                    session_type=session_type,
                )
                continue

            if GlobalTimeConstraints.is_slot_globally_invalid(slot, session_enum):
                add_violation(
                    "GLOBAL_TIME_CONSTRAINT",
                    f"{section.course_code} {normalized_session_type} is in a globally forbidden slot",
                    day=day_name,
                    block=get_block_label(block_idx),
                    section=section.section_key,
                    session_type=normalized_session_type,
                )

            if slot not in section.allowed_slots:
                add_violation(
                    "PROFESSOR_AVAILABILITY",
                    f"{section.course_code} is scheduled outside the professor's allowed slots",
                    day=day_name,
                    block=get_block_label(block_idx),
                    section=section.section_key,
                    professor=short_text(get_professor_for_session(section, normalized_session_type)),
                )

            professor = get_professor_for_session(section, normalized_session_type)
            professor_bookings[(day_val, block_idx, professor)].append((section_key, normalized_session_type))

            if section.special_room and section.special_room.strip():
                room_bookings[(day_val, block_idx, get_room_for_section(section, room))].append(
                    (section_key, normalized_session_type)
                )

            course_bookings[(day_val, block_idx, section.course_code)].append(
                (section_key, normalized_session_type)
            )

    for (day_val, block_idx, professor), sections in professor_bookings.items():
        if len(sections) > 1:
            day_name = DayOfWeek(day_val).name
            add_violation(
                "PROFESSOR_DOUBLE_BOOKING",
                f"Professor booked {len(sections)} times on {day_name} Block {block_idx}",
                day=day_name,
                block=get_block_label(block_idx),
                professor=short_text(professor, 20),
                sections=", ".join(f"{section_key} ({session_type})" for section_key, session_type in sections),
            )

    for (day_val, block_idx, room), sections in room_bookings.items():
        if len(sections) > 1:
            day_name = DayOfWeek(day_val).name
            add_violation(
                "ROOM_CONFLICT",
                f"Room '{room}' booked {len(sections)} times on {day_name} Block {block_idx}",
                day=day_name,
                block=get_block_label(block_idx),
                room=room,
                sections=", ".join(f"{section_key} ({session_type})" for section_key, session_type in sections),
            )

    for (day_val, block_idx, section_key, session_type), rooms in exact_bookings.items():
        if len(rooms) > 1:
            section = section_lookup.get(section_key)
            day_name = DayOfWeek(day_val).name
            course_code = section.course_code if section else section_key
            add_violation(
                "DUPLICATE_ASSIGNMENT",
                f"{course_code} has duplicate {session_type} blocks in the same slot",
                day=day_name,
                block=get_block_label(block_idx),
                section=section_key,
                session_type=session_type,
            )

    for (day_val, block_idx, course_code), sections in course_bookings.items():
        if len(sections) > 1:
            day_name = DayOfWeek(day_val).name
            add_violation(
                "COURSE_OVERLAP",
                f"{course_code} appears {len(sections)} times on {day_name} Block {block_idx}",
                day=day_name,
                block=get_block_label(block_idx),
                course_code=course_code,
                sections=", ".join(f"{section_key} ({session_type})" for section_key, session_type in sections),
            )

    for section in st.session_state.sections:
        for session_type, required_blocks in get_session_requirements(section).items():
            scheduled_count = scheduled_counts[(section.section_key, session_type)]

            if scheduled_count > required_blocks:
                add_violation(
                    "OVER_REQUIRED_BLOCKS",
                    f"{section.course_code} has {scheduled_count} {session_type} blocks scheduled but requires {required_blocks}",
                    section=section.section_key,
                    session_type=session_type,
                    required=required_blocks,
                    scheduled=scheduled_count,
                )

            if required_blocks == 1:
                for day_val, block_idx in scheduled_locations[(section.section_key, session_type)]:
                    if block_idx != 4:
                        add_violation(
                            "INVALID_SINGLE_BLOCK",
                            f"Single-block {session_type} sessions must use Block 4, not Block {block_idx}",
                            section=section.section_key,
                            day=DayOfWeek(day_val).name,
                            block=get_block_label(block_idx),
                            session_type=session_type,
                        )

        distribution = (section.class_distribution or "").strip().lower()

        if distribution.startswith("2+1"):
            for (section_key, day_val), blocks in lecture_blocks_by_day.items():
                if section_key != section.section_key:
                    continue
                unique_blocks = sorted(set(blocks))
                if len(unique_blocks) == 1 and unique_blocks[0] != 4:
                    add_violation(
                        "INVALID_2_PLUS_1_SINGLE",
                        f"{section.course_code} has an isolated lecture outside Block 4",
                        section=section.section_key,
                        day=DayOfWeek(day_val).name,
                        block=get_block_label(unique_blocks[0]),
                    )

        if distribution == "3-juntas":
            for (section_key, day_val), blocks in lecture_blocks_by_day.items():
                if section_key != section.section_key:
                    continue
                unique_blocks = sorted(set(blocks))
                if len(unique_blocks) not in {0, 3}:
                    add_violation(
                        "INVALID_3_JUNTAS_COUNT",
                        f"{section.course_code} must place 3-juntas lectures in groups of exactly 3",
                        section=section.section_key,
                        day=DayOfWeek(day_val).name,
                        blocks=", ".join(str(block) for block in unique_blocks),
                    )
                elif len(unique_blocks) == 3 and unique_blocks != list(range(unique_blocks[0], unique_blocks[0] + 3)):
                    add_violation(
                        "INVALID_3_JUNTAS_SEQUENCE",
                        f"{section.course_code} has 3-juntas lectures that are not consecutive",
                        section=section.section_key,
                        day=DayOfWeek(day_val).name,
                        blocks=", ".join(str(block) for block in unique_blocks),
                    )

    return report


# ============================================================================
# HTML/JAVASCRIPT DRAG-AND-DROP SCHEDULER
# ============================================================================

def _legacy_generate_dnd_grid_html(plan_comun_level: int) -> str:
    """
    Generate HTML/CSS/JavaScript for drag-and-drop schedule grid.
    """
    days = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]
    
    html = """
    <style>
        .dnd-container {
            font-family: Arial, sans-serif;
            padding: 10px;
            background: #f5f5f5;
            border-radius: 8px;
        }
        
        .schedule-grid {
            border-collapse: collapse;
            width: 100%;
            background: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .schedule-grid th, .schedule-grid td {
            border: 1px solid #ddd;
            padding: 12px;
            text-align: center;
            min-width: 120px;
            min-height: 60px;
            vertical-align: top;
        }
        
        .schedule-grid th {
            background: #2c3e50;
            color: white;
            font-weight: bold;
            position: sticky;
            top: 0;
        }
        
        .block-label {
            background: #ecf0f1;
            font-weight: bold;
            color: #2c3e50;
            width: 100px;
        }
        
        .drop-zone {
            background: #ffffff;
            border: 2px dashed #bdc3c7;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        
        .drop-zone:hover {
            background: #f0f0f0;
            border-color: #3498db;
        }
        
        .drop-zone.drag-over {
            background: #e8f4f8;
            border-color: #2980b9;
            box-shadow: inset 0 0 10px rgba(52, 152, 219, 0.2);
        }
        
        .course-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 8px;
            margin: 4px 0;
            border-radius: 6px;
            cursor: move;
            font-size: 12px;
            font-weight: bold;
            box-shadow: 0 2px 6px rgba(0,0,0,0.2);
            transition: transform 0.2s ease;
            user-select: none;
        }
        
        .course-card:hover {
            transform: scale(1.05);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        
        .course-card.clase {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        
        .course-card.ayudantia {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        
        .course-card.laboratorio {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }
        
        .unassigned-zone {
            background: #fff3cd;
            border: 2px solid #ffc107;
            border-radius: 8px;
            padding: 12px;
            margin: 10px 0;
        }
        
        .unassigned-card {
            background: white;
            border-left: 4px solid #ff6b6b;
            padding: 8px;
            margin: 4px 0;
            border-radius: 4px;
            font-size: 12px;
        }
    </style>
    
    <div class="dnd-container">
        <h3>Schedule for Plan Común Level """ + str(plan_comun_level) + """</h3>
        
        <table class="schedule-grid">
            <thead>
                <tr>
                    <th class="block-label">Block</th>
    """
    
    for day in days:
        html += f"<th>{day}</th>"
    
    html += """
                </tr>
            </thead>
            <tbody>
    """
    
    # Generate rows for each block
    for block_idx in range(13):
        block = ACADEMIC_BLOCKS[block_idx]
        html += f"""
                <tr>
                    <td class="block-label">
                        <div>{block_idx}</div>
                        <div style="font-size: 10px; margin-top: 4px;">{block.start_time}-{block.end_time}</div>
                    </td>
        """
        
        for day_idx, day in enumerate(days):
            key = (day_idx, block_idx)
            html += f"""
                    <td class="drop-zone" data-day="{day_idx}" data-block="{block_idx}" 
                        ondragover="event.preventDefault(); this.classList.add('drag-over')"
                        ondragleave="this.classList.remove('drag-over')"
                        ondrop="dropHandler(event, {plan_comun_level})">
            """
            
            # Add scheduled courses for this slot
            if key in st.session_state.schedule_matrix:
                for section_key, session_type, room in st.session_state.schedule_matrix[key]:
                    section = next((s for s in st.session_state.sections if s.section_key == section_key), None)
                    if section and section.plan_comun_level == plan_comun_level:
                        session_class = session_type.lower().replace("ía", "ia")
                        html += f"""
                        <div class="course-card {session_class}" draggable="true" 
                             data-section-key="{section_key}" data-session-type="{session_type}"
                             ondragstart="dragStartHandler(event)">
                            {section.course_code[:10]}... | {session_type[:3]}
                        </div>
                        """
            
            html += "</td>"
        
        html += "</tr>"
    
    html += """
            </tbody>
        </table>
    </div>
    
    <script>
    function dragStartHandler(event) {
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/html', event.currentTarget.innerHTML);
        event.dataTransfer.setData('section-key', event.currentTarget.dataset.sectionKey);
        event.dataTransfer.setData('session-type', event.currentTarget.dataset.sessionType);
        event.currentTarget.style.opacity = '0.5';
    }
    
    function dropHandler(event, planComunLevel) {
        event.preventDefault();
        event.currentTarget.classList.remove('drag-over');
        
        const sectionKey = event.dataTransfer.getData('section-key');
        const sessionType = event.dataTransfer.getData('session-type');
        const day = event.currentTarget.dataset.day;
        const block = event.currentTarget.dataset.block;
        
        // Send update to Streamlit
        const updateData = {
            action: 'move_block',
            section_key: sectionKey,
            session_type: sessionType,
            day: parseInt(day),
            block: parseInt(block),
            plan_comun: planComunLevel
        };
        
        // Store in browser session for Streamlit to read
        window.parent.postMessage(updateData, '*');
        
        // Simulate successful drop
        event.currentTarget.innerHTML += `<div class="course-card" style="opacity: 0.8;">${sectionKey.substring(0, 12)}...</div>`;
    }
    </script>
    """
    
    return html


def generate_dnd_grid_html(plan_comun_level: int) -> str:
    """
    Generate the editable schedule grid and unassigned bank.

    Streamlit's built-in HTML component is one-way, so drops are persisted by
    writing a small JSON payload into the parent page's query params. The app
    consumes that payload on the next rerun and updates session_state.
    """
    days = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]
    section_lookup = get_section_lookup()

    def esc(value: Any) -> str:
        return html_utils.escape(str(value or ""), quote=True)

    def render_course_card(
        section: Any,
        session_type: Any,
        room: Optional[str],
        source: str,
        source_day: Optional[int] = None,
        source_block: Optional[int] = None,
        item_index: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> str:
        normalized_session_type = normalize_session_type(session_type)
        css_class = session_css_class(normalized_session_type)
        professor = get_professor_for_session(section, normalized_session_type)
        room_label = get_room_for_section(section, room)
        requirements = get_session_requirements(section)
        required_count = requirements.get(normalized_session_type, 0)

        tooltip_lines = [
            ("Course", f"{section.course_code} - {section.title}"),
            ("Section", section.section_key),
            ("Session", normalized_session_type),
            ("Plan Comun", section.plan_comun_level),
            ("Required", f"{required_count} block(s)"),
            ("Professor", professor),
            ("Room", room_label),
        ]
        if section.class_distribution:
            tooltip_lines.append(("Distribution", section.class_distribution))
        if reason:
            tooltip_lines.append(("Reason", reason))

        tooltip_html = "".join(
            f"<div><strong>{esc(label)}:</strong> {esc(value)}</div>"
            for label, value in tooltip_lines
        )
        title_attr = esc(" | ".join(f"{label}: {value}" for label, value in tooltip_lines))
        reason_html = ""
        if reason:
            reason_html = f'<div class="course-reason">{esc(short_text(reason, 64))}</div>'

        source_day_attr = "" if source_day is None else str(source_day)
        source_block_attr = "" if source_block is None else str(source_block)
        item_index_attr = "" if item_index is None else str(item_index)

        return f"""
            <div class="course-card {css_class}" draggable="true"
                 data-source="{esc(source)}"
                 data-section-key="{esc(section.section_key)}"
                 data-session-type="{esc(normalized_session_type)}"
                 data-source-day="{esc(source_day_attr)}"
                 data-source-block="{esc(source_block_attr)}"
                 data-item-index="{esc(item_index_attr)}"
                 title="{title_attr}"
                 ondragstart="dragStartHandler(event)"
                 ondragend="dragEndHandler(event)">
                <div class="course-card-top">
                    <span class="course-code">{esc(section.course_code)}</span>
                    <span class="session-pill">{esc(session_abbreviation(normalized_session_type))}</span>
                </div>
                <div class="course-title">{esc(short_text(section.title, 42))}</div>
                <div class="course-meta">Sec {esc(short_text(section.section_key, 14))} | Prof {esc(short_text(professor, 18))}</div>
                {reason_html}
                <div class="course-tooltip">{tooltip_html}</div>
            </div>
        """

    unassigned_cards: List[str] = []
    for section_key, items in sorted(st.session_state.unassigned_blocks.items()):
        section = section_lookup.get(section_key)
        if not section or section.plan_comun_level != plan_comun_level:
            continue

        for item_index, item in enumerate(items):
            session_type, reason = coerce_unassigned_item(item)
            unassigned_cards.append(
                render_course_card(
                    section=section,
                    session_type=session_type,
                    room=section.special_room or "Standard",
                    source="unassigned",
                    item_index=item_index,
                    reason=reason,
                )
            )

    parts: List[str] = ["""
    <style>
        .dnd-container {
            font-family: Arial, Helvetica, sans-serif;
            color: #1f2937;
            background: #f7f8fa;
            padding: 12px;
        }

        .dnd-header {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 10px;
        }

        .dnd-header h3 {
            margin: 0;
            font-size: 18px;
            font-weight: 700;
        }

        .dnd-count {
            color: #4b5563;
            font-size: 12px;
        }

        .unassigned-bank {
            background: #fff8e6;
            border: 1px solid #e5b94f;
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 14px;
            max-height: 230px;
            overflow-y: auto;
            transition: background 0.15s ease, border-color 0.15s ease;
        }

        .unassigned-bank.drag-over {
            background: #fff0c2;
            border-color: #b7791f;
        }

        .bank-title {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 8px;
            font-size: 13px;
            font-weight: 700;
        }

        .bank-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
            gap: 8px;
        }

        .empty-bank {
            color: #6b7280;
            font-size: 12px;
            padding: 6px 0;
        }

        .schedule-wrap {
            overflow: auto;
            border: 1px solid #d5dae1;
            border-radius: 8px;
            background: white;
        }

        .schedule-grid {
            border-collapse: separate;
            border-spacing: 0;
            width: 100%;
            min-width: 880px;
            background: white;
        }

        .schedule-grid th,
        .schedule-grid td {
            border-right: 1px solid #e5e7eb;
            border-bottom: 1px solid #e5e7eb;
            vertical-align: top;
        }

        .schedule-grid th {
            position: sticky;
            top: 0;
            z-index: 20;
            background: #243447;
            color: white;
            padding: 10px;
            font-size: 12px;
            font-weight: 700;
            text-align: center;
        }

        .block-label {
            width: 95px;
            min-width: 95px;
            background: #eef1f5;
            color: #243447;
            text-align: center;
            font-weight: 700;
            padding: 10px 6px;
        }

        .block-time {
            margin-top: 4px;
            color: #4b5563;
            font-size: 11px;
            font-weight: 500;
        }

        .drop-zone {
            position: relative;
            width: 18%;
            min-width: 145px;
            height: 92px;
            background: #ffffff;
            transition: background 0.15s ease, box-shadow 0.15s ease;
        }

        .drop-zone:hover {
            background: #f5f9fc;
        }

        .drop-zone.drag-over {
            background: #e8f3f7;
            box-shadow: inset 0 0 0 2px #2f7d95;
        }

        .cell-stack {
            min-height: 76px;
            padding: 6px;
        }

        .course-card {
            position: relative;
            background: #ffffff;
            border: 1px solid #d9dee7;
            border-left: 5px solid #245c7a;
            border-radius: 8px;
            color: #172033;
            cursor: move;
            font-size: 12px;
            margin-bottom: 6px;
            padding: 7px 8px;
            text-align: left;
            user-select: none;
            box-shadow: 0 1px 3px rgba(31, 41, 55, 0.12);
        }

        .course-card.ayudantia {
            border-left-color: #a16207;
        }

        .course-card.laboratorio {
            border-left-color: #2f6b43;
        }

        .course-card:hover {
            box-shadow: 0 6px 16px rgba(31, 41, 55, 0.18);
            z-index: 100;
        }

        .course-card.dragging {
            opacity: 0.55;
        }

        .course-card-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 6px;
            margin-bottom: 3px;
        }

        .course-code {
            overflow-wrap: anywhere;
            font-weight: 700;
        }

        .session-pill {
            flex: 0 0 auto;
            border-radius: 6px;
            background: #e7edf4;
            color: #243447;
            font-size: 10px;
            font-weight: 700;
            padding: 2px 5px;
        }

        .course-title {
            color: #374151;
            font-size: 11px;
            line-height: 1.25;
            overflow-wrap: anywhere;
        }

        .course-meta,
        .course-reason {
            color: #6b7280;
            font-size: 10px;
            line-height: 1.25;
            margin-top: 4px;
            overflow-wrap: anywhere;
        }

        .course-tooltip {
            display: none;
            position: absolute;
            left: calc(100% + 8px);
            top: 0;
            width: 280px;
            max-width: 280px;
            background: #111827;
            border-radius: 8px;
            box-shadow: 0 12px 32px rgba(17, 24, 39, 0.28);
            color: #f9fafb;
            font-size: 12px;
            font-weight: 400;
            line-height: 1.35;
            padding: 10px;
            z-index: 5000;
        }

        .course-tooltip div + div {
            margin-top: 5px;
        }

        .course-tooltip strong {
            color: #c7d2fe;
        }

        .course-card:hover .course-tooltip {
            display: block;
        }
    </style>
    """]

    parts.append(f"""
    <div class="dnd-container">
        <div class="dnd-header">
            <h3>Plan Comun {plan_comun_level}</h3>
            <div class="dnd-count">{len(unassigned_cards)} unassigned block(s)</div>
        </div>

        <div class="unassigned-bank"
             ondragover="event.preventDefault(); this.classList.add('drag-over')"
             ondragleave="this.classList.remove('drag-over')"
             ondrop="unassignDropHandler(event, {plan_comun_level})">
            <div class="bank-title">
                <span>Unassigned Blocks</span>
                <span>{len(unassigned_cards)}</span>
            </div>
            <div class="bank-grid">
    """)

    if unassigned_cards:
        parts.extend(unassigned_cards)
    else:
        parts.append('<div class="empty-bank">No unassigned blocks for this level.</div>')

    parts.append("""
            </div>
        </div>

        <div class="schedule-wrap">
            <table class="schedule-grid">
                <thead>
                    <tr>
                        <th class="block-label">Block</th>
    """)

    for day in days:
        parts.append(f"<th>{esc(day)}</th>")

    parts.append("""
                    </tr>
                </thead>
                <tbody>
    """)

    for block_idx in range(13):
        block = ACADEMIC_BLOCKS[block_idx]
        parts.append(f"""
                    <tr>
                        <td class="block-label">
                            <div>{block_idx}</div>
                            <div class="block-time">{esc(block.start_time)}-{esc(block.end_time)}</div>
                        </td>
        """)

        for day_idx, _ in enumerate(days):
            key = (day_idx, block_idx)
            parts.append(f"""
                        <td class="drop-zone"
                            data-day="{day_idx}"
                            data-block="{block_idx}"
                            ondragover="event.preventDefault(); this.classList.add('drag-over')"
                            ondragleave="this.classList.remove('drag-over')"
                            ondrop="dropHandler(event, {plan_comun_level})">
                            <div class="cell-stack">
            """)

            for section_key, session_type, room in st.session_state.schedule_matrix.get(key, []):
                section = section_lookup.get(section_key)
                if section and section.plan_comun_level == plan_comun_level:
                    parts.append(
                        render_course_card(
                            section=section,
                            session_type=session_type,
                            room=room,
                            source="scheduled",
                            source_day=day_idx,
                            source_block=block_idx,
                        )
                    )

            parts.append("""
                            </div>
                        </td>
            """)

        parts.append("</tr>")

    parts.append("""
                </tbody>
            </table>
        </div>
    </div>

    <script>
    function dragStartHandler(event) {
        const card = event.currentTarget;
        const payload = {
            source: card.dataset.source,
            section_key: card.dataset.sectionKey,
            session_type: card.dataset.sessionType,
            source_day: card.dataset.sourceDay || null,
            source_block: card.dataset.sourceBlock || null,
            item_index: card.dataset.itemIndex || null
        };

        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('application/json', JSON.stringify(payload));
        event.dataTransfer.setData('text/plain', JSON.stringify(payload));
        card.classList.add('dragging');
    }

    function dragEndHandler(event) {
        event.currentTarget.classList.remove('dragging');
    }

    function getDragPayload(event) {
        const raw = event.dataTransfer.getData('application/json') ||
            event.dataTransfer.getData('text/plain');
        if (!raw) {
            return null;
        }

        try {
            return JSON.parse(raw);
        } catch (error) {
            return null;
        }
    }

    function sendScheduleAction(payload) {
        payload.nonce = Date.now();
        const parentWindow = window.parent || window.top;
        const url = new URL(parentWindow.location.href);
        url.searchParams.set('schedule_move', JSON.stringify(payload));
        url.searchParams.set('schedule_move_nonce', String(payload.nonce));
        parentWindow.location.href = url.toString();
    }

    function dropHandler(event, planComunLevel) {
        event.preventDefault();
        event.currentTarget.classList.remove('drag-over');

        const payload = getDragPayload(event);
        if (!payload) {
            return;
        }

        const targetDay = event.currentTarget.dataset.day;
        const targetBlock = event.currentTarget.dataset.block;
        if (
            payload.source === 'scheduled' &&
            String(payload.source_day) === String(targetDay) &&
            String(payload.source_block) === String(targetBlock)
        ) {
            return;
        }

        payload.action = 'move_block';
        payload.target_day = parseInt(targetDay, 10);
        payload.target_block = parseInt(targetBlock, 10);
        payload.plan_comun = planComunLevel;
        sendScheduleAction(payload);
    }

    function unassignDropHandler(event, planComunLevel) {
        event.preventDefault();
        event.currentTarget.classList.remove('drag-over');

        const payload = getDragPayload(event);
        if (!payload || payload.source !== 'scheduled') {
            return;
        }

        payload.action = 'unassign_block';
        payload.plan_comun = planComunLevel;
        sendScheduleAction(payload);
    }
    </script>
    """)

    return "".join(parts)


# ============================================================================
# SIDEBAR CONTROLS
# ============================================================================

def render_unassigned_sidebar() -> None:
    """Render a detailed, filterable unassigned-block sidebar."""
    st.sidebar.subheader("Unassigned Blocks")

    if not st.session_state.sections:
        st.sidebar.info("No dataset loaded.")
        return

    total_unassigned = sum(len(items) for items in st.session_state.unassigned_blocks.values())
    if total_unassigned == 0:
        st.sidebar.success("All required blocks are scheduled.")
        return

    metric_col1, metric_col2 = st.sidebar.columns(2)
    with metric_col1:
        st.metric("Blocks", total_unassigned)
    with metric_col2:
        st.metric("Courses", len(st.session_state.unassigned_blocks))

    plan_options = ["All"] + [
        str(plan_level)
        for plan_level in sorted({section.plan_comun_level for section in st.session_state.sections})
    ]
    selected_plan = st.sidebar.selectbox("Plan Comun", plan_options, key="unassigned_plan_filter")
    search_text = st.sidebar.text_input("Filter unassigned", key="unassigned_search").strip().lower()

    section_lookup = get_section_lookup()
    filtered_sections: List[Tuple[Any, List[Any]]] = []

    for section_key, items in sorted(st.session_state.unassigned_blocks.items()):
        section = section_lookup.get(section_key)
        if not section:
            continue

        if selected_plan != "All" and str(section.plan_comun_level) != selected_plan:
            continue

        searchable_text = " ".join([
            section.section_key,
            section.course_code,
            section.title,
            str(section.plan_comun_level),
        ]).lower()
        if search_text and search_text not in searchable_text:
            continue

        filtered_sections.append((section, items))

    filtered_blocks = sum(len(items) for _, items in filtered_sections)
    st.sidebar.caption(f"{filtered_blocks} block(s) across {len(filtered_sections)} course(s)")

    for section, items in filtered_sections:
        requirements = get_session_requirements(section)
        scheduled_count = sum(
            1
            for blocks in st.session_state.schedule_matrix.values()
            for section_key, _, _ in blocks
            if section_key == section.section_key
        )
        required_count = sum(requirements.values())
        label = f"{section.course_code} | PC{section.plan_comun_level} | {len(items)} missing"

        with st.sidebar.expander(label, expanded=False):
            st.markdown(f"**{section.title}**")
            st.caption(f"Section {section.section_key}")
            st.caption(f"Scheduled {scheduled_count}/{required_count} required blocks")
            if section.special_room:
                st.caption(f"Room: {section.special_room}")
            if section.class_distribution:
                st.caption(f"Distribution: {section.class_distribution}")

            for item_index, item in enumerate(items, start=1):
                session_type, reason = coerce_unassigned_item(item)
                st.markdown(f"**{item_index}. {session_type}**")
                st.caption(reason)


def render_sidebar() -> None:
    """Render the control panel in the sidebar."""
    st.sidebar.title("Control Panel")
    
    # File uploader
    st.sidebar.subheader("Load Dataset")
    uploaded_file = st.sidebar.file_uploader(
        "Upload course schedule Excel/CSV",
        type=["xlsx", "csv"],
        help="Select your course data file"
    )
    
    if uploaded_file:
        # Save uploaded file temporarily
        file_path = f"temp_{uploaded_file.name}"
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        if st.sidebar.button("Load and Schedule", key="load_btn"):
            with st.spinner("Loading and scheduling courses..."):
                if load_and_schedule_data(file_path):
                    st.sidebar.success("✓ Data loaded and scheduled successfully!")
                else:
                    st.sidebar.error("✗ Failed to load data")
    
    # Constraint relaxation framework
    st.sidebar.subheader("Constraint Relaxation")
    st.sidebar.write("Relax cohort overlap constraints by Plan Común level:")
    
    st.session_state.relaxation_flags["plan_comun_1"] = st.sidebar.checkbox(
        "Relax Plan Común 1",
        value=st.session_state.relaxation_flags["plan_comun_1"]
    )
    st.session_state.relaxation_flags["plan_comun_2"] = st.sidebar.checkbox(
        "Relax Plan Común 2",
        value=st.session_state.relaxation_flags["plan_comun_2"]
    )
    st.session_state.relaxation_flags["plan_comun_3"] = st.sidebar.checkbox(
        "Relax Plan Común 3",
        value=st.session_state.relaxation_flags["plan_comun_3"]
    )
    st.session_state.relaxation_flags["plan_comun_4"] = st.sidebar.checkbox(
        "Relax Plan Común 4",
        value=st.session_state.relaxation_flags["plan_comun_4"]
    )
    
    if st.sidebar.button("Regenerate Automated Schedule", key="regen_btn"):
        if st.session_state.sections:
            with st.spinner("Re-optimizing schedule with selected relaxations..."):
                scheduler = CourseScheduler(st.session_state.sections)
                scheduled_blocks, conflict_report = scheduler.solve(timeout_seconds=60)
                
                matrix = build_schedule_matrix_from_assignments(scheduled_blocks)
                
                st.session_state.schedule_matrix = matrix
                st.session_state.unassigned_blocks = build_unassigned_registry(
                    st.session_state.sections,
                    matrix,
                    conflict_report,
                )
                st.sidebar.success("✓ Schedule regenerated!")
                st.rerun()
        else:
            st.sidebar.warning("No data loaded yet")

    render_unassigned_sidebar()
    return
    
    # Unassigned blocks bank
    st.sidebar.subheader("Unassigned Blocks")
    if st.session_state.unassigned_blocks:
        for section_key, reasons in list(st.session_state.unassigned_blocks.items())[:3]:
            section = next((s for s in st.session_state.sections if s.section_key == section_key), None)
            if section:
                with st.sidebar.expander(f"{section.course_code[:15]}...", expanded=False):
                    for session_type, reason in reasons[:2]:
                        st.write(f"- **{session_type}**: {reason[:40]}...")
        
        if len(st.session_state.unassigned_blocks) > 3:
            st.sidebar.info(f"... and {len(st.session_state.unassigned_blocks) - 3} more unassigned")
    else:
        st.sidebar.success("✓ All courses scheduled!")


# ============================================================================
# MAIN TAB VIEWS
# ============================================================================

def render_cohort_view(plan_comun_level: int) -> None:
    """Render drag-and-drop schedule for a specific cohort level."""
    
    
    if not st.session_state.sections:
        st.info("No data loaded. Use the sidebar to upload a dataset.")
        return
    
    # Generate and render the drag-and-drop grid
    html_content = generate_dnd_grid_html(plan_comun_level)
    st.components.v1.html(html_content, height=1100, scrolling=True)
    
    # Summary statistics
    col1, col2, col3 = st.columns(3)
    
    # Count sections for this cohort
    cohort_sections = [s for s in st.session_state.sections if s.plan_comun_level == plan_comun_level]
    total_blocks_required = sum(s.required_clases + s.required_ayudantias + s.required_laboratorios for s in cohort_sections)
    
    section_lookup = get_section_lookup()
    scheduled_count = 0
    for blocks in st.session_state.schedule_matrix.values():
        for section_key, _, _ in blocks:
            section = section_lookup.get(section_key)
            if section and section.plan_comun_level == plan_comun_level:
                scheduled_count += 1
    
    with col1:
        st.metric("Sections", len(cohort_sections))
    with col2:
        st.metric("Blocks Required", total_blocks_required)
    with col3:
        st.metric("Scheduled Blocks", scheduled_count)


def render_master_view() -> None:
    """Render master compilation view with all cohorts and concurrent courses."""
    st.subheader("Master Academic Calendar - All Courses & Cohorts")
    
    if not st.session_state.sections:
        st.info("No data loaded. Use the sidebar to upload a dataset.")
        return
    
    st.write("**Showing all concurrent courses across all cohort levels**")
    st.info("Cells display multiple courses running in parallel (separated by |).")
    
    # Create master grid
    days = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]
    
    # Build data for display
    display_data = []
    for block_idx in range(13):
        block = ACADEMIC_BLOCKS[block_idx]
        row = {"Block": f"{block_idx}\n({block.start_time}-{block.end_time})"}
        
        for day_idx, day in enumerate(days):
            key = (day_idx, block_idx)
            courses = []
            if key in st.session_state.schedule_matrix:
                for section_key, session_type, room in st.session_state.schedule_matrix[key]:
                    section = next((s for s in st.session_state.sections if s.section_key == section_key), None)
                    if section:
                        # Format: CourseCode (PC_Level) SessionType [Room]
                        course_str = f"{section.course_code[:10]} (PC{section.plan_comun_level}) {session_type[:3]}"
                        if section.special_room:
                            course_str += f" [{section.special_room[:15]}]"
                        courses.append(course_str)
            
            # Join multiple courses with newlines for better readability
            row[day] = "\n".join(courses) if courses else "—"
        
        display_data.append(row)
    
    df = pd.DataFrame(display_data)
    
    # Display with custom styling
    st.dataframe(
        df, 
        use_container_width=True,
        height=500
    )
    
    # Summary statistics
    st.write("### Schedule Summary")
    col1, col2, col3, col4 = st.columns(4)
    
    total_scheduled = sum(len(blocks) for blocks in st.session_state.schedule_matrix.values())
    total_slots_used = len(st.session_state.schedule_matrix)
    total_sections = len(st.session_state.sections)
    total_required = sum(s.required_clases + s.required_ayudantias + s.required_laboratorios for s in st.session_state.sections)
    
    with col1:
        st.metric("Total Sections", total_sections)
    with col2:
        st.metric("Total Blocks Required", total_required)
    with col3:
        st.metric("Blocks Scheduled", total_scheduled)
    with col4:
        utilization = f"{100 * total_scheduled / total_required:.1f}%" if total_required > 0 else "—"
        st.metric("Utilization", utilization)


# ============================================================================
# VALIDATION & EXPORT
# ============================================================================

def render_validation_section() -> None:
    """Render constraint validation section."""
    st.subheader("Check Restrictions")
    
    if st.button("Run Validation", key="validate_btn", use_container_width=True):
        with st.spinner("Validating schedule..."):
            validation_report = validate_schedule()
        
        if validation_report["valid"]:
            st.success("Schedule is valid! All constraints satisfied.")
        else:
            st.warning(f"Found {len(validation_report['violations'])} violations")
            
            for violation in validation_report["violations"]:
                with st.expander(f"{violation['type']}", expanded=False):
                    st.write(violation["details"])
                    for key, val in violation.items():
                        if key not in ["type", "details"]:
                            st.write(f"- **{key}**: {val}")
        
        # Display statistics
        st.write("### Statistics")
        stats_col1, stats_col2, stats_col3, stats_col4 = st.columns(4)
        
        with stats_col1:
            st.metric("Total Sections", validation_report["stats"]["total_sections"])
        with stats_col2:
            st.metric("Scheduled Blocks", validation_report["stats"]["scheduled_blocks"])
        with stats_col3:
            st.metric("Unscheduled Blocks", validation_report["stats"]["unscheduled_blocks"])
        with stats_col4:
            st.metric("Slots Used", validation_report["stats"]["total_slots_used"])


def render_export_section() -> None:
    """Render Excel export section."""
    st.subheader("Export Schedule")
    
    if st.button("Download Production Schedule", key="export_btn", use_container_width=True):
        if not st.session_state.sections:
            st.warning("No data to export")
            return
        
        with st.spinner("Generating Excel workbook..."):
            output = BytesIO()
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                days = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]
                
                # Export each cohort level + master view
                for plan_comun in range(1, 5):
                    display_data = []
                    for block_idx in range(13):
                        block = ACADEMIC_BLOCKS[block_idx]
                        row = {"Block": f"{block_idx} ({block.start_time}-{block.end_time})"}
                        
                        for day_idx, day in enumerate(days):
                            key = (day_idx, block_idx)
                            courses = []
                            if key in st.session_state.schedule_matrix:
                                for section_key, session_type, room in st.session_state.schedule_matrix[key]:
                                    section = next((s for s in st.session_state.sections if s.section_key == section_key), None)
                                    if section and section.plan_comun_level == plan_comun:
                                        courses.append(f"{section.course_code} ({session_type[:3]})")
                            
                            row[day] = " | ".join(courses) if courses else ""
                        
                        display_data.append(row)
                    
                    df = pd.DataFrame(display_data)
                    df.to_excel(writer, sheet_name=f"Plan Común {plan_comun}", index=False)
                
                # Master view
                display_data = []
                for block_idx in range(13):
                    block = ACADEMIC_BLOCKS[block_idx]
                    row = {"Block": f"{block_idx} ({block.start_time}-{block.end_time})"}
                    
                    for day_idx, day in enumerate(days):
                        key = (day_idx, block_idx)
                        courses = []
                        if key in st.session_state.schedule_matrix:
                            for section_key, session_type, room in st.session_state.schedule_matrix[key]:
                                section = next((s for s in st.session_state.sections if s.section_key == section_key), None)
                                if section:
                                    courses.append(f"{section.course_code} (PC{section.plan_comun_level})")
                        
                        row[day] = " | ".join(courses) if courses else ""
                    
                    display_data.append(row)
                
                df_master = pd.DataFrame(display_data)
                df_master.to_excel(writer, sheet_name="Master View", index=False)
            
            output.seek(0)
            st.download_button(
                label="Download Excel File",
                data=output,
                file_name=f"schedule_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point."""
    st.set_page_config(
        page_title="University Scheduler MVP",
        page_icon="📅",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session state
    initialize_session_state()
    process_pending_drag_drop_action()
    
    # Configure page styling
    st.markdown("""
    <style>
        .main { max-width: 1400px; }
        .metric-box { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
        }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("University Course Scheduler MVP")
    st.write("Interactive drag-and-drop scheduling with real-time constraint validation")
    render_drag_drop_feedback()
    
    # Render sidebar controls
    render_sidebar()
    
    # Main content tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Plan Común 1",
        "Plan Común 2", 
        "Plan Común 3",
        "Plan Común 4",
        "Master View",
        "Validation & Export"
    ])
    
    with tab1:
        render_cohort_view(1)
    
    with tab2:
        render_cohort_view(2)
    
    with tab3:
        render_cohort_view(3)
    
    with tab4:
        render_cohort_view(4)
    
    with tab5:
        render_master_view()
    
    with tab6:
        col1, col2 = st.columns(2)
        with col1:
            render_validation_section()
        with col2:
            render_export_section()


if __name__ == "__main__":
    main()
