"""
Comprehensive Streamlit UI for University Course Scheduler

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
import os
import html as html_utils
from datetime import datetime
from cryptography.fernet import Fernet
from dotenv import load_dotenv

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
from src.components.dnd_grid import dnd_grid as dnd_grid_component
from src.storage.saver import save_to_json, load_from_json, delete_json_file

# Load the RUT decryption key (EncryptionKey) from the local .env file, if present.
load_dotenv()


def _get_rut_cipher() -> Optional[Fernet]:
    """Build the Fernet cipher used to decrypt professor RUTs for display.

    The key lives in the gitignored .env file as EncryptionKey. If it is missing
    or invalid we return None, and RUTs fall back to their raw stored token
    rather than crashing the app (e.g. on a fresh clone without a .env)."""
    key = os.getenv("EncryptionKey")
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except Exception:
        return None

def _encrypt_rut(cipher: Optional[Fernet], value) -> Optional[str]:
    """Encrypt a professor RUT for anonymization. Falls back to the raw value for
    placeholders (e.g. UNKNOWN_PROF_1) or when the key is unavailable/invalid."""
    if value is None:
        return None
    if cipher is None:
        return value
    try:
        return cipher.encrypt(str(value).encode()).decode()
    except Exception:
        return value

def _decrypt_rut(cipher: Optional[Fernet], value) -> Optional[str]:
    """Decrypt a stored RUT token for display. Falls back to the raw value for
    placeholders (e.g. UNKNOWN_PROF_1) or when the key is unavailable/invalid."""
    if value is None:
        return None
    if cipher is None:
        return value
    try:
        return cipher.decrypt(str(value).encode()).decode()
    except Exception:
        return value

def serialize_schedule_matrix() -> dict:
    """Convierte las keys de tupla a string 'day,block' para JSON."""
    return {
        f"{day},{block}": list(blocks)
        for (day, block), blocks in st.session_state.schedule_matrix.items()
    }

def serialize_sections() -> list:
    """Convierte los objetos section a dicts para JSON."""
    result = []
    cipher = _get_rut_cipher()
    for s in st.session_state.sections:
        result.append({
            "section_key":        s.section_key,
            "course_code":        s.course_code,
            "title":              s.title,
            "plan_comun_level":   s.plan_comun_level,
            "professor_1_rut":    _decrypt_rut(cipher, s.professor_1_rut),
            "professor_2_rut":    _decrypt_rut(cipher, s.professor_2_rut),
            "lab_professor_rut":  _decrypt_rut(cipher, s.lab_professor_rut),
            "special_room":       getattr(s, "special_room", None),
            "class_distribution": getattr(s, "class_distribution", None),
            "required_clases":      s.required_clases,
            "required_ayudantias":  s.required_ayudantias,
            "required_laboratorios":s.required_laboratorios,
            "allowed_slots":      [f"{slot.day.value},{slot.block_index}" for slot in s.allowed_slots],
        })
    return result

def deserialize_sections(data: list) -> list:
    """Reconstruye los objetos section desde dicts cargados de JSON."""
    cipher = _get_rut_cipher()
    sections = []
    for s in data:
        section = type('Section', (), {})()  # Crea un objeto vacío
        section.section_key = s.get("section_key")
        section.course_code = s.get("course_code")
        section.title = s.get("title")
        section.plan_comun_level = s.get("plan_comun_level")
        section.professor_1_rut = _encrypt_rut(cipher, s.get("professor_1_rut"))
        section.professor_2_rut = _encrypt_rut(cipher, s.get("professor_2_rut"))
        section.lab_professor_rut = _encrypt_rut(cipher, s.get("lab_professor_rut"))
        section.special_room = s.get("special_room")
        section.class_distribution = s.get("class_distribution")
        section.required_clases = s.get("required_clases", 0)
        section.required_ayudantias = s.get("required_ayudantias", 0)
        section.required_laboratorios = s.get("required_laboratorios", 0)
        section.allowed_slots = frozenset(TimeSlot(DayOfWeek(int(day)), int(block)) for day, block in (slot.split(",") for slot in s.get("allowed_slots", [])))
        sections.append(section)
    return sections

def serialize_academic_blocks() -> dict:
    """Convierte ACADEMIC_BLOCKS a dict serializable."""
    return {
        str(k): {"start_time": v.start_time, "end_time": v.end_time}
        for k, v in ACADEMIC_BLOCKS.items()
    }

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
            'relax_availability': False,
            'relax_3juntas_medium': False,
            'relax_3juntas_full': False,
            'relax_block4': False,
            'relax_ayudantia_partial': False,
            'relax_ayudantia_full': False,
        }


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
        save_to_json({
            "sections": serialize_sections(),
            "schedule_matrix": st.session_state.schedule_matrix,
            "unassigned_blocks": st.session_state.unassigned_blocks
        }, file_path="schedule_state.json")
        return True
        
    except Exception as e:
        st.error(f"Error loading/scheduling data: {str(e)}")
        return False


# ============================================================================
# CONSTRAINT VALIDATION ENGINE
# ============================================================================

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

            if GlobalTimeConstraints.is_slot_globally_invalid(slot, session_enum, section.plan_comun_level):
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

            if required_blocks == 1 and not st.session_state.relaxation_flags.get('relax_block4', False):
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
    save_file_exists = os.path.exists("./src/storage/schedule_state.json")
    #Save File Manager
    if save_file_exists:
        # Load from saved state
        if st.sidebar.button(
            "Load Saved Schedule", 
            key="load_state_btn", 
            help="Carga el último estado guardado del horario"
        ):
            try:
                saved_state = load_from_json("schedule_state.json")
                st.session_state.sections = deserialize_sections(saved_state.get("sections", []))
                st.session_state.schedule_matrix = saved_state.get("schedule_matrix", {})
                st.session_state.unassigned_blocks = saved_state.get("unassigned_blocks", {})
                st.sidebar.success("✓ Loaded saved schedule state!")
            except Exception as e:
                st.sidebar.error(f"✗ Failed to load saved state: {str(e)}")
        
        # Delete the JSON file
        if st.sidebar.button(
            "Delete Saved Schedule", 
            key="delete_json_btn", 
            help="Borra el archivo de estado guardado del horario"
        ):
            try:
                delete_json_file("schedule_state.json")
                st.sidebar.success("✓ Saved state deleted!")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"✗ Failed to delete saved state: {str(e)}")
    
    if st.session_state.sections:
        # Save Current Schedule to a JSON file
        if st.sidebar.button(
            "Save Current Schedule", 
            key="save_state_btn", 
            help="Guarda el estado actual del horario en un archivo JSON"
        ):
            try:
                save_to_json({
                    "sections": serialize_sections(),
                    "schedule_matrix": st.session_state.schedule_matrix,
                    "unassigned_blocks": st.session_state.unassigned_blocks
                }, file_path="schedule_state.json")
                st.sidebar.success("✓ Current schedule state saved!")
                if not save_file_exists:
                    st.rerun()
            except Exception as e:
                st.sidebar.error(f"✗ Failed to save schedule state: {str(e)}")
    
    # Constraint relaxation framework
    st.sidebar.subheader("Constraint Relaxation")
    flags = st.session_state.relaxation_flags

    st.sidebar.markdown("**Disponibilidad de profesores**")
    flags['relax_availability'] = st.sidebar.checkbox(
        "Ignorar disponibilidad de profesores",
        value=flags['relax_availability'],
        help="Abre los bloques 0–8 de todos los días para todas las secciones, ignorando la disponibilidad declarada.",
    )

    st.sidebar.markdown("**Restricción de bloques 3-juntas**")
    relax_3juntas_full = st.sidebar.checkbox(
        "Permitir cualquier 3 bloques consecutivos en el día",
        value=flags['relax_3juntas_full'],
        help="Cursos 3-juntas pueden usar cualquier tripleta consecutiva sin restricción de bloque.",
    )
    relax_3juntas_medium = st.sidebar.checkbox(
        "Permitir cualquier 3 bloques consecutivos dentro de bloques 1–7",
        value=flags['relax_3juntas_medium'],
        disabled=relax_3juntas_full,
        help="Cursos 3-juntas pueden usar cualquier tripleta consecutiva dentro de los bloques 1–7.",
    )
    flags['relax_3juntas_full'] = relax_3juntas_full
    flags['relax_3juntas_medium'] = relax_3juntas_medium and not relax_3juntas_full

    st.sidebar.markdown("**Regla de Bloque 4 (sesión única)**")
    flags['relax_block4'] = st.sidebar.checkbox(
        "Permitir sesiones de un bloque en cualquier horario",
        value=flags['relax_block4'],
        help="Elimina la regla que obliga a las sesiones de un solo bloque a usar el Bloque 4 (12:30–13:20).",
    )

    st.sidebar.markdown("**Restricción matutina de Ayudantías**")
    relax_ayudantia_full = st.sidebar.checkbox(
        "Permitir Ayudantías en cualquier horario",
        value=flags['relax_ayudantia_full'],
        help="Elimina toda restricción matutina para las Ayudantías.",
    )
    relax_ayudantia_partial = st.sidebar.checkbox(
        "Permitir Ayudantías desde el bloque 3 (11:30) en adelante",
        value=flags['relax_ayudantia_partial'],
        disabled=relax_ayudantia_full,
        help="Solo los bloques 0–2 (08:30–11:20) quedan prohibidos para Ayudantías.",
    )
    flags['relax_ayudantia_full'] = relax_ayudantia_full
    flags['relax_ayudantia_partial'] = relax_ayudantia_partial and not relax_ayudantia_full
    
    if st.sidebar.button("Regenerate Automated Schedule", key="regen_btn"):
        if st.session_state.sections:
            with st.spinner("Re-optimizing schedule with selected relaxations..."):
                scheduler = CourseScheduler(st.session_state.sections, st.session_state.relaxation_flags)
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


# ============================================================================
# MAIN TAB VIEWS
# ============================================================================

def render_cohort_view(plan_comun_level: int) -> None:
    if not st.session_state.sections:
        st.info("No data loaded. Use the sidebar to upload a dataset.")
        return

    result = dnd_grid_component(
        schedule_matrix=serialize_schedule_matrix(),
        unassigned_blocks=st.session_state.unassigned_blocks,
        sections=serialize_sections(),
        plan_comun_level=plan_comun_level,
        academic_blocks=serialize_academic_blocks(),
        key=f"dnd_grid_{plan_comun_level}",
    )

    if result is not None:
        payload = json.loads(result) if isinstance(result, str) else result
        nonce = payload.get("nonce")
        last_nonce_key = f"_last_dnd_nonce_{plan_comun_level}"
        if st.session_state.get(last_nonce_key) != payload:
            st.session_state[last_nonce_key] = payload
            success, message = apply_schedule_action(payload)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

    # Métricas
    col1, col2, col3 = st.columns(3)
    cohort_sections = [s for s in st.session_state.sections if s.plan_comun_level == plan_comun_level]
    total_blocks_required = sum(s.required_clases + s.required_ayudantias + s.required_laboratorios for s in cohort_sections)
    section_lookup = get_section_lookup()
    scheduled_count = sum(
        1 for blocks in st.session_state.schedule_matrix.values()
        for section_key, _, _ in blocks
        if (s := section_lookup.get(section_key)) and s.plan_comun_level == plan_comun_level
    )
    with col1: 
        st.metric("Sections", len(cohort_sections))
    with col2: 
        st.metric("Blocks Required", total_blocks_required)
    with col3: 
        st.metric("Scheduled Blocks", scheduled_count)


def render_master_view() -> None:
    """Render the interactive master calendar: every scheduled block across all
    cohorts at once, colored by semester (Plan Común).

    Because all tabs share the same global schedule matrix, dragging a block here
    is applied by `apply_schedule_action` on the underlying section and therefore
    shows up automatically on that section's Plan Común tab."""
    st.subheader("Master Academic Calendar - All Courses & Cohorts")

    if not st.session_state.sections:
        st.info("No data loaded. Use the sidebar to upload a dataset.")
        return

    st.write("**Todos los bloques de todos los semestres. Cada Plan Común se distingue por color.**")
    st.caption(
        "Puede arrastrar un bloque para reubicarlo; el cambio se refleja también "
        "en la pestaña del semestre correspondiente."
    )

    result = dnd_grid_component(
        schedule_matrix=serialize_schedule_matrix(),
        unassigned_blocks=st.session_state.unassigned_blocks,
        sections=serialize_sections(),
        plan_comun_level=0,
        academic_blocks=serialize_academic_blocks(),
        master_mode=True,
        key="dnd_grid_master",
    )

    if result is not None:
        payload = json.loads(result) if isinstance(result, str) else result
        last_nonce_key = "_last_dnd_nonce_master"
        if st.session_state.get(last_nonce_key) != payload:
            st.session_state[last_nonce_key] = payload
            success, message = apply_schedule_action(payload)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

    # Summary statistics
    st.write("### Schedule Summary")
    col1, col2, col3, col4 = st.columns(4)

    total_scheduled = sum(len(blocks) for blocks in st.session_state.schedule_matrix.values())
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
        page_title="University Scheduler",
        page_icon="📅",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session state
    initialize_session_state()
    
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
    
    st.title("University Course Scheduler")
    st.write("Interactive drag-and-drop scheduling with real-time constraint validation")
    
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
