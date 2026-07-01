"""
University course scheduling system models tailored to Chilean academic calendar.

Core Components:
- DayOfWeek: Days of the week (Chilean academic week)
- SessionType: Types of academic sessions (Clase, Ayudantía, Laboratorio)
- TimeBlock: Standardized 13-block daily matrix (08:30 to 21:20)
- TimeSlot: Immutable day + block_index representation
- CourseSection: Complete course section definition with Chilean requirements
- ConstraintValidator: Institutional constraint checking
- GlobalTimeConstraints: Centralized Chilean academic rules

All models use frozen dataclasses for immutability and deterministic constraint solving.
Designed for OR-Tools CP-SAT integration.
"""

from dataclasses import dataclass
from typing import FrozenSet, Optional, Dict, Tuple
from enum import Enum


# ============================================================================
# ENUMERATIONS
# ============================================================================

class DayOfWeek(Enum):
    """Chilean academic week days"""
    LUNES = 0
    MARTES = 1
    MIERCOLES = 2
    JUEVES = 3
    VIERNES = 4


class SessionType(Enum):
    """Types of academic sessions in Chilean universities"""
    CLASE = "Clase"
    AYUDANTIA = "Ayudantía"
    LABORATORIO = "Laboratorio"


# ============================================================================
# TIME BLOCK DEFINITIONS (13-BLOCK DAILY MATRIX)
# ============================================================================

@dataclass(frozen=True)
class TimeBlock:
    """Immutable representation of a single academic block with times"""
    block_index: int  # 0-12
    start_time: str  # HH:MM format (e.g., "08:30")
    end_time: str    # HH:MM format (e.g., "09:20")
    
    def __post_init__(self) -> None:
        if not 0 <= self.block_index <= 12:
            raise ValueError(f"block_index must be 0-12, got {self.block_index}")
        if len(self.start_time) != 5 or len(self.end_time) != 5:
            raise ValueError("Times must be in HH:MM format")


# Standard Chilean academic 13-block schedule
ACADEMIC_BLOCKS: Dict[int, TimeBlock] = {
    0: TimeBlock(0, "08:30", "09:20"),
    1: TimeBlock(1, "09:30", "10:20"),
    2: TimeBlock(2, "10:30", "11:20"),
    3: TimeBlock(3, "11:30", "12:20"),
    4: TimeBlock(4, "12:30", "13:20"),
    5: TimeBlock(5, "13:30", "14:20"),
    6: TimeBlock(6, "14:30", "15:20"),
    7: TimeBlock(7, "15:30", "16:20"),
    8: TimeBlock(8, "16:30", "17:20"),
    9: TimeBlock(9, "17:30", "18:20"),
    10: TimeBlock(10, "18:30", "19:20"),
    11: TimeBlock(11, "19:30", "20:20"),
    12: TimeBlock(12, "20:30", "21:20"),
}


# ============================================================================
# IMMUTABLE DATA STRUCTURES (FROZEN DATACLASSES)
# ============================================================================

@dataclass(frozen=True)
class TimeSlot:
    """
    Immutable representation of a schedulable time slot.
    
    Uniquely identifies a day and academic block.
    Hashable for use in sets and dictionaries.
    """
    day: DayOfWeek
    block_index: int
    
    def __post_init__(self) -> None:
        if not 0 <= self.block_index <= 12:
            raise ValueError(f"block_index must be 0-12, got {self.block_index}")
    
    @property
    def block_times(self) -> TimeBlock:
        """Get the TimeBlock info for this slot"""
        return ACADEMIC_BLOCKS[self.block_index]
    
    def __str__(self) -> str:
        block = self.block_times
        return f"{self.day.name} Block {self.block_index} ({block.start_time}-{block.end_time})"
    
    def __hash__(self) -> int:
        return hash((self.day, self.block_index))


@dataclass(frozen=True)
class CourseSection:
    """
    Immutable representation of a specific course section.
    
    Maps to Excel columns: LLAVE Código-Sec, TITULO, CUPOS, Clases, Ayudantías,
    Laboratorios, RUT PROFESOR 1, RUT PROFESOR 2, RUT PROFESOR LAB
    
    Attributes:
        section_key: Unique identifier (e.g., "ING12011" = ING1201 Section 1)
        course_code: Course code (e.g., "ING1201")
        title: Course title (e.g., "Cálculo I")
        plan_comun_level: Academic year in plan común (e.g., 1, 2, 3)
        required_clases: Weekly blocks needed for lectures
        required_ayudantias: Weekly blocks needed for workshops
        required_laboratorios: Weekly blocks needed for labs
        special_room: Special room requirement if any (e.g., "ComputerLab", "Lab")
        professor_1_rut: Main professor RUT (Chilean national ID)
        professor_2_rut: Secondary professor RUT (optional)
        lab_professor_rut: Lab professor RUT (optional)
        class_distribution: Format string like "2+1" (2 classes of X blocks, 1 of Y)
        allowed_slots: Set of TimeSlots where this section can be scheduled
    """
    section_key: str
    course_code: str
    title: str
    plan_comun_level: int
    required_clases: int
    required_ayudantias: int
    required_laboratorios: int
    professor_1_rut: str
    professor_2_rut: Optional[str]
    lab_professor_rut: Optional[str]
    special_room: Optional[str]
    class_distribution: Optional[str]
    allowed_slots: FrozenSet[TimeSlot]
    
    def __post_init__(self) -> None:
        if not self.section_key.strip():
            raise ValueError("section_key cannot be empty")
        if not self.course_code.strip():
            raise ValueError("course_code cannot be empty")
        if not self.title.strip():
            raise ValueError("title cannot be empty")
        if self.plan_comun_level < 1:
            raise ValueError(f"plan_comun_level must be >= 1, got {self.plan_comun_level}")
        if self.required_clases < 0:
            raise ValueError(f"required_clases must be >= 0, got {self.required_clases}")
        if self.required_ayudantias < 0:
            raise ValueError(f"required_ayudantias must be >= 0, got {self.required_ayudantias}")
        if self.required_laboratorios < 0:
            raise ValueError(f"required_laboratorios must be >= 0, got {self.required_laboratorios}")
        if not self.professor_1_rut.strip():
            raise ValueError("professor_1_rut cannot be empty")
    
    def __hash__(self) -> int:
        return hash(self.section_key)
    
    def __str__(self) -> str:
        return f"{self.section_key}: {self.title} (Plan Común: {self.plan_comun_level})"


# ============================================================================
# CONSTRAINT VALIDATION
# ============================================================================

class GlobalTimeConstraints:
    """
    Centralized validation of Chilean institutional time constraints.
    All constraints are based on academic regulations.
    """
    
    FORBIDDEN_MARTES_MIERCOLES_BLOCKS = frozenset([9, 10, 11])
    FORBIDDEN_VIERNES_BLOCKS = frozenset([2, 3])
    FORBIDDEN_AYUDANTIA_BLOCKS = frozenset([0, 1, 2, 3])
    
    @staticmethod
    def is_slot_globally_invalid(
        timeslot: TimeSlot,
        session_type: SessionType,
        plan_comun_level: Optional[int] = None,
    ) -> bool:
        """
        Check if a TimeSlot violates any global institutional constraints.

        Rules 1 (Tue/Wed evening) and 2 (Friday morning) only apply to Plan Común
        levels 3 and 4. Pass plan_comun_level=None to apply them unconditionally
        (backward-compatible default for callers that don't know the level).

        Args:
            timeslot: The TimeSlot to validate
            session_type: Type of session (Clase, Ayudantía, Laboratorio)
            plan_comun_level: Optional semester level (1–4)

        Returns:
            True if the slot is invalid (violates a constraint), False otherwise
        """
        # Rules 1 & 2 do not apply to Plan Común 1 and 2
        if plan_comun_level not in (1, 2):
            if timeslot.day in (DayOfWeek.MARTES, DayOfWeek.MIERCOLES):
                if timeslot.block_index in GlobalTimeConstraints.FORBIDDEN_MARTES_MIERCOLES_BLOCKS:
                    return True

            if timeslot.day == DayOfWeek.VIERNES:
                if timeslot.block_index in GlobalTimeConstraints.FORBIDDEN_VIERNES_BLOCKS:
                    return True

        if session_type == SessionType.AYUDANTIA:
            if timeslot.block_index in GlobalTimeConstraints.FORBIDDEN_AYUDANTIA_BLOCKS:
                return True

        return False
    
    @staticmethod
    def get_valid_slots_for_session(
        session_type: SessionType,
        preferred_days: Optional[FrozenSet[DayOfWeek]] = None
    ) -> FrozenSet[TimeSlot]:
        """
        Generate all valid TimeSlots for a given session type, optionally filtered by days.
        
        Args:
            session_type: Type of session
            preferred_days: Optional set of days to restrict to
        
        Returns:
            Frozenset of all valid TimeSlots
        """
        valid_slots = []
        days_to_check = preferred_days if preferred_days else frozenset(DayOfWeek)
        
        for day in DayOfWeek:
            if preferred_days and day not in preferred_days:
                continue
            
            for block_idx in range(13):
                slot = TimeSlot(day, block_idx)
                if not GlobalTimeConstraints.is_slot_globally_invalid(slot, session_type):
                    valid_slots.append(slot)
        
        return frozenset(valid_slots)
    
    @staticmethod
    def validate_slot_constraints(
        timeslot: TimeSlot,
        session_type: SessionType,
        allowed_slots: FrozenSet[TimeSlot]
    ) -> Tuple[bool, str]:
        """
        Comprehensive validation of a slot assignment.
        
        Args:
            timeslot: The TimeSlot to validate
            session_type: Type of session
            allowed_slots: Set of professor-available slots
        
        Returns:
            Tuple of (is_valid, reason_if_invalid)
        """
        if GlobalTimeConstraints.is_slot_globally_invalid(timeslot, session_type):
            return False, f"Slot {timeslot} violates global time constraint for {session_type.value}"
        
        if timeslot not in allowed_slots:
            return False, f"Slot {timeslot} not in professor's allowed slots"
        
        return True, "Valid"


# ============================================================================
# VALIDATION UTILITIES
# ============================================================================

def parse_class_distribution(distribution_str: Optional[str]) -> Optional[Tuple[int, ...]]:
    """
    Parse class distribution string like "2+1" into tuple (2, 1).
    
    Args:
        distribution_str: String like "2+1" or "3" or None
    
    Returns:
        Tuple of integers, or None if input is None
    """
    if distribution_str is None:
        return None
    
    try:
        parts = distribution_str.split("+")
        return tuple(int(p.strip()) for p in parts if p.strip())
    except ValueError:
        raise ValueError(f"Invalid class distribution format: {distribution_str}")


def create_professor_available_slots(
    availability_dict: Dict[DayOfWeek, FrozenSet[int]]
) -> FrozenSet[TimeSlot]:
    """
    Create TimeSlots from professor availability data.
    
    Args:
        availability_dict: Mapping of day to set of available block indices
    
    Returns:
        Frozenset of valid TimeSlots
    """
    slots = []
    for day, blocks in availability_dict.items():
        for block_idx in blocks:
            if 0 <= block_idx <= 12:
                slots.append(TimeSlot(day, block_idx))
    return frozenset(slots)


# ============================================================================
# DEMONSTRATION AND VALIDATION
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("UNIVERSITY SCHEDULING MODELS - CHILEAN ACADEMIC CALENDAR")
    print("=" * 80)
    
    print("\n[1] STANDARD 13-BLOCK ACADEMIC SCHEDULE")
    print("-" * 80)
    for idx, block in ACADEMIC_BLOCKS.items():
        print(f"  Block {idx:2d}: {block.start_time}-{block.end_time}")
    
    print("\n[2] TIME SLOT CREATION")
    print("-" * 80)
    slot_lunes_0 = TimeSlot(DayOfWeek.LUNES, 0)
    slot_martes_9 = TimeSlot(DayOfWeek.MARTES, 9)
    slot_viernes_2 = TimeSlot(DayOfWeek.VIERNES, 2)
    print(f"  • {slot_lunes_0}")
    print(f"  • {slot_martes_9}")
    print(f"  • {slot_viernes_2}")
    
    print("\n[3] COURSE SECTION CREATION")
    print("-" * 80)
    
    prof_availability = {
        DayOfWeek.LUNES: frozenset([0, 1, 2, 3, 4, 5, 6, 7, 8]),
        DayOfWeek.MARTES: frozenset([0, 1, 2, 3, 4, 5, 6, 7, 8]),
        DayOfWeek.MIERCOLES: frozenset([0, 1, 2, 3, 4, 5, 6, 7, 8]),
        DayOfWeek.JUEVES: frozenset([0, 1, 2, 3, 4, 5, 6, 7, 8]),
    }
    allowed_slots = create_professor_available_slots(prof_availability)
    
    section = CourseSection(
        section_key="ING12011",
        course_code="ING1201",
        title="Cálculo I",
        plan_comun_level=1,
        required_clases=3,
        required_ayudantias=1,
        required_laboratorios=0,
        professor_1_rut="12345678-K",
        professor_2_rut="87654321-9",
        lab_professor_rut=None,
        special_room=None,
        class_distribution="2+1",
        allowed_slots=allowed_slots
    )
    print(f"  • {section}")
    print(f"    - Clase blocks: {section.required_clases}")
    print(f"    - Ayudantía blocks: {section.required_ayudantias}")
    print(f"    - Distribution: {section.class_distribution}")
    print(f"    - Professor 1: {section.professor_1_rut}")
    print(f"    - Professor 2: {section.professor_2_rut}")
    
    print("\n[4] GLOBAL CONSTRAINT VALIDATION")
    print("-" * 80)
    
    test_cases = [
        (TimeSlot(DayOfWeek.LUNES, 0), SessionType.CLASE, "Monday 8:30 - Clase"),
        (TimeSlot(DayOfWeek.MARTES, 9), SessionType.CLASE, "Tuesday 17:30 - Clase (Forbidden)"),
        (TimeSlot(DayOfWeek.MIERCOLES, 10), SessionType.CLASE, "Wednesday 18:30 - Clase (Forbidden)"),
        (TimeSlot(DayOfWeek.VIERNES, 2), SessionType.CLASE, "Friday 10:30 - Clase (Forbidden)"),
        (TimeSlot(DayOfWeek.VIERNES, 5), SessionType.CLASE, "Friday 13:30 - Clase (OK)"),
        (TimeSlot(DayOfWeek.LUNES, 2), SessionType.AYUDANTIA, "Monday 10:30 - Ayudantía (Forbidden)"),
        (TimeSlot(DayOfWeek.LUNES, 5), SessionType.AYUDANTIA, "Monday 13:30 - Ayudantía (OK)"),
        (TimeSlot(DayOfWeek.JUEVES, 7), SessionType.LABORATORIO, "Thursday 15:30 - Laboratorio (OK)"),
    ]
    
    for slot, session_type, description in test_cases:
        is_invalid = GlobalTimeConstraints.is_slot_globally_invalid(slot, session_type)
        status = "❌ INVALID" if is_invalid else "✓ VALID"
        print(f"  {status}  {description}")
    
    print("\n[5] VALID SLOTS FOR AYUDANTÍAS (after 12:30)")
    print("-" * 80)
    valid_ayudantia_slots = GlobalTimeConstraints.get_valid_slots_for_session(SessionType.AYUDANTIA)
    
    for day in DayOfWeek:
        blocks_for_day = sorted([s.block_index for s in valid_ayudantia_slots if s.day == day])
        print(f"  {day.name:10s}: Blocks {blocks_for_day}")
    
    print("\n[6] COMPREHENSIVE SLOT VALIDATION")
    print("-" * 80)
    
    test_slot = TimeSlot(DayOfWeek.LUNES, 5)
    is_valid, reason = GlobalTimeConstraints.validate_slot_constraints(
        test_slot,
        SessionType.AYUDANTIA,
        allowed_slots
    )
    print(f"  • {test_slot} + Ayudantía: {reason}")
    
    test_slot2 = TimeSlot(DayOfWeek.MARTES, 9)
    is_valid2, reason2 = GlobalTimeConstraints.validate_slot_constraints(
        test_slot2,
        SessionType.CLASE,
        allowed_slots
    )
    print(f"  • {test_slot2} + Clase: {reason2}")
    
    print("\n[7] MODEL ARCHITECTURE SUMMARY")
    print("-" * 80)
    print("  ✓ Frozen dataclasses for immutability")
    print("  ✓ 13-block academic schedule (08:30-21:20)")
    print("  ✓ Chilean institutional constraints")
    print("  ✓ Tuesday/Wednesday 17:30-20:20 restrictions")
    print("  ✓ Friday 10:30-12:20 restrictions")
    print("  ✓ Ayudantía 12:30+ block restriction")
    print("  ✓ Hashable TimeSlots for OR-Tools integration")
    print("  ✓ Comprehensive constraint validation")
    
    print("\n" + "=" * 80)
    print("✓ All models implemented successfully!")
    print("✓ Ready for OR-Tools CP-SAT solver integration")
    print("=" * 80 + "\n")
