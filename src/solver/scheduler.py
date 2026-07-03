"""
OR-Tools CP-SAT constraint programming solver for university scheduling.

Implements a production-grade course scheduler that solves all Plan Común cohort
levels (1, 2, 3, 4) simultaneously while respecting:
- Professor availability and multi-booking protection
- Special room requirements and capacity
- Semester exclusivity (one course per slot per level; parallel sections of the
  same course may share a slot)
- Chilean institutional time constraints
- Consecutive-pair scheduling (sessions land as pairs of 2 consecutive blocks;
  odd counts get one single at Block 4 — the "2+1" layout)
- Session-type/day separation (a section's Clases, Ayudantías and Labs fall on
  different days)
- 3-juntas distribution (one consecutive lecture triple per week)
"""

import logging
from typing import Dict, List, Tuple, Set, Optional
from collections import defaultdict
from itertools import combinations

from ortools.sat.python import cp_model

from ..models.models import (
    CourseSection,
    DayOfWeek,
    SessionType,
    TimeSlot,
    GlobalTimeConstraints,
    DayOfWeek,
    create_professor_available_slots,
    ACADEMIC_BLOCKS,
)

logger = logging.getLogger(__name__)


# Maps each session-type pair to the relaxation flag that allows the pair to
# share a day. Used by the solver and mirrored by the app-side validator.
SAME_DAY_RELAX_FLAGS: Dict[frozenset, str] = {
    frozenset({SessionType.CLASE.value, SessionType.AYUDANTIA.value}): 'relax_same_day_clase_ayud',
    frozenset({SessionType.CLASE.value, SessionType.LABORATORIO.value}): 'relax_same_day_clase_lab',
    frozenset({SessionType.AYUDANTIA.value, SessionType.LABORATORIO.value}): 'relax_same_day_ayud_lab',
}


class CourseScheduler:
    """
    Constraint satisfaction solver for university course scheduling.
    
    Solves the problem of assigning course sessions to time slots and rooms
    while maximizing scheduled courses and respecting all constraints.
    """
    
    def __init__(self, sections: List[CourseSection], relaxation_flags: Optional[Dict[str, bool]] = None) -> None:
        """
        Initialize the scheduler with course sections.

        Args:
            sections: List of CourseSection objects to schedule
            relaxation_flags: Dict of relaxation options (all default to False):
                - 'relax_availability'        : ADD blocks 0–8 of every day to each professor's
                                                declared availability (declared slots are kept)
                - 'relax_3juntas_medium'      : allow 3-juntas in any consecutive 3 blocks within 1–7
                - 'relax_3juntas_full'        : allow 3-juntas in any consecutive 3 blocks in the day
                - 'relax_block4'              : single-block sessions can use any slot (not just block 4)
                - 'relax_ayudantia_partial'   : only blocks 0–2 forbidden for Ayudantías
                - 'relax_ayudantia_full'      : no morning restriction for Ayudantías
                - 'relax_same_day_clase_ayud' : a section may hold Clases and Ayudantías the same day
                - 'relax_same_day_clase_lab'  : a section may hold Clases and Laboratorios the same day
                - 'relax_same_day_ayud_lab'   : a section may hold Ayudantías and Laboratorios the same day
        """
        self.sections = sections
        self.model = cp_model.CpModel()
        self.vars: Dict[Tuple, cp_model.IntVar] = {}
        self._solver_solution = {}
        self._relaxation_flags: Dict[str, bool] = {
            'relax_availability': False,
            'relax_3juntas_medium': False,
            'relax_3juntas_full': False,
            'relax_block4': False,
            'relax_ayudantia_partial': False,
            'relax_ayudantia_full': False,
            'relax_same_day_clase_ayud': False,
            'relax_same_day_clase_lab': False,
            'relax_same_day_ayud_lab': False,
        }
        if relaxation_flags:
            self._relaxation_flags.update(relaxation_flags)
        
        # Build the model
        self._build_model()
    
    def _build_model(self) -> None:
        """Build the complete CP-SAT model with all constraints."""
        logger.info(f"Building model with {len(self.sections)} course sections")
        
        # 1. Create decision variables
        self._create_decision_variables()
        logger.info(f"Created {len(self.vars)} decision variables")
        
        # 2. Add demand constraints (relaxed upper bounds)
        self._add_demand_constraints()
        
        # 3. Add hard resource constraints
        self._add_professor_constraints()
        self._add_room_constraints()
        self._add_cohort_constraints()

        # 4. Add Chilean institutional rules
        self._add_block4_constraint()
        self._add_contiguous_blocks_constraint()

        # 5. Add structural distribution rules
        self._add_session_type_day_separation()
        self._add_session_pattern_constraints()

        # 6. Set maximization objective
        self._set_objective()
    
    # ------------------------------------------------------------------
    # Relaxation helpers
    # ------------------------------------------------------------------

    def _get_valid_3juntas_blocks(self) -> Set[int]:
        """Block indices that 3-juntas Clase sessions may occupy."""
        flags = self._relaxation_flags
        if flags.get('relax_3juntas_full'):
            return set(range(13))
        if flags.get('relax_3juntas_medium'):
            return set(range(1, 8))   # blocks 1–7 → triplets {1,2,3}…{5,6,7}
        return {2, 3, 4, 5, 6}        # fixed: only {2,3,4} or {4,5,6}

    def _get_forbidden_ayudantia_blocks(self) -> Set[int]:
        """Block indices that are forbidden for Ayudantías."""
        flags = self._relaxation_flags
        if flags.get('relax_ayudantia_full'):
            return set()
        if flags.get('relax_ayudantia_partial'):
            return {0, 1, 2}
        return set(GlobalTimeConstraints.FORBIDDEN_AYUDANTIA_BLOCKS)  # {0,1,2,3}

    # ------------------------------------------------------------------

    def _create_decision_variables(self) -> None:
        """
        Create boolean decision variables for each valid section/session/slot.

        Variables: self.vars[(section_key, session_type, day, block_index)]
        A variable is created only when all of the following hold:
        - The slot is in the section's allowed_slots (or availability is relaxed)
        - The slot does not violate global time rules for this plan_comun_level
        - For 3-juntas Clases: the block is within the valid 3-juntas range
        """
        flags = self._relaxation_flags
        forbidden_ayudantia = self._get_forbidden_ayudantia_blocks()

        # Availability relaxation ADDS blocks 0–8 of every day on top of the
        # professor's declared availability (it must never replace it: some
        # professors declare evening blocks 9+ that would otherwise be lost).
        relaxation_slots = None
        if flags.get('relax_availability'):
            relaxation_slots = create_professor_available_slots({
                day: frozenset(range(9)) for day in DayOfWeek
            })

        for section in self.sections:
            section_key = section.section_key
            plan_level = section.plan_comun_level

            for session_type_enum in [SessionType.CLASE, SessionType.AYUDANTIA, SessionType.LABORATORIO]:
                if session_type_enum == SessionType.CLASE:
                    required_blocks = section.required_clases
                elif session_type_enum == SessionType.AYUDANTIA:
                    required_blocks = section.required_ayudantias
                else:
                    required_blocks = section.required_laboratorios

                if required_blocks == 0:
                    continue

                # Candidate slots: declared availability, plus the extra
                # blocks when the availability relaxation is enabled
                if relaxation_slots is not None:
                    available_slots = frozenset(section.allowed_slots) | relaxation_slots
                else:
                    available_slots = section.allowed_slots

                # For 3-juntas Clases: pre-compute valid block set
                valid_3juntas: Optional[Set[int]] = None
                if section.class_distribution == "3-juntas" and session_type_enum == SessionType.CLASE:
                    valid_3juntas = self._get_valid_3juntas_blocks()

                for slot in available_slots:
                    # Rule 1 & 2: Tue/Wed evening and Friday morning (only Plan Común 3 & 4)
                    if plan_level not in (1, 2):
                        if slot.day in (DayOfWeek.MARTES, DayOfWeek.MIERCOLES):
                            if slot.block_index in GlobalTimeConstraints.FORBIDDEN_MARTES_MIERCOLES_BLOCKS:
                                continue
                        if slot.day == DayOfWeek.VIERNES:
                            if slot.block_index in GlobalTimeConstraints.FORBIDDEN_VIERNES_BLOCKS:
                                continue

                    # Rule 3: Ayudantía morning (with relaxation)
                    if session_type_enum == SessionType.AYUDANTIA:
                        if slot.block_index in forbidden_ayudantia:
                            continue

                    # 3-juntas block range restriction
                    if valid_3juntas is not None and slot.block_index not in valid_3juntas:
                        continue

                    var_key = (section_key, session_type_enum.value, slot.day.value, slot.block_index)
                    self.vars[var_key] = self.model.NewBoolVar(f"slot_{var_key}")
    
    def _add_demand_constraints(self) -> None:
        """
        Add upper bound constraints for each section/session type.
        
        Sum of allocations <= required blocks (relaxed to allow partial scheduling)
        """
        for section in self.sections:
            section_key = section.section_key
            
            for session_type_enum in [SessionType.CLASE, SessionType.AYUDANTIA, SessionType.LABORATORIO]:
                if session_type_enum == SessionType.CLASE:
                    required_blocks = section.required_clases
                elif session_type_enum == SessionType.AYUDANTIA:
                    required_blocks = section.required_ayudantias
                else:
                    required_blocks = section.required_laboratorios
                
                if required_blocks == 0:
                    continue
                
                # Collect all variables for this section/session type
                relevant_vars = [
                    var for (sk, st, _, _), var in self.vars.items()
                    if sk == section_key and st == session_type_enum.value
                ]
                
                if relevant_vars:
                    # Upper bound: scheduled <= required
                    self.model.Add(sum(relevant_vars) <= required_blocks)
    
    def _add_professor_constraints(self) -> None:
        """
        Add professor multi-booking protection constraints.
        
        No professor can teach multiple concurrent sessions.
        Group variables by (day, block_index, professor_rut).
        """
        professor_blocks = defaultdict(list)
        
        for (section_key, session_type, day, block_index), var in self.vars.items():
            # Find the section and determine which professor RUT
            section = next(s for s in self.sections if s.section_key == section_key)
            
            # Determine professor based on session type
            if session_type == SessionType.CLASE.value and section.professor_1_rut:
                prof_rut = section.professor_1_rut
            elif session_type == SessionType.AYUDANTIA.value and section.professor_2_rut:
                prof_rut = section.professor_2_rut
            elif session_type == SessionType.LABORATORIO.value and section.lab_professor_rut:
                prof_rut = section.lab_professor_rut
            else:
                # Default to professor_1_rut if no specific professor
                prof_rut = section.professor_1_rut
            
            if prof_rut:
                key = (day, block_index, prof_rut)
                professor_blocks[key].append(var)
        
        # Add constraints: at most 1 session per professor per block
        for key, vars_list in professor_blocks.items():
            if len(vars_list) > 1:
                self.model.Add(sum(vars_list) <= 1)
    
    def _add_room_constraints(self) -> None:
        """
        Add special room multi-booking protection constraints.
        
        No room can host multiple concurrent sessions.
        Group variables by (day, block_index, special_room).
        """
        room_blocks = defaultdict(list)
        
        for (section_key, session_type, day, block_index), var in self.vars.items():
            section = next(s for s in self.sections if s.section_key == section_key)
            
            if section.special_room:
                key = (day, block_index, section.special_room)
                room_blocks[key].append(var)
        
        # Add constraints: at most 1 session per room per block
        for key, vars_list in room_blocks.items():
            if len(vars_list) > 1:
                self.model.Add(sum(vars_list) <= 1)
    
    def _add_cohort_constraints(self) -> None:
        """
        Add semester (Plan Común) exclusivity constraints.

        At any given time slot, only ONE course per cohort level may hold
        sessions. The exception is parallel sections of the SAME course code:
        students belong to a single section, so different sections of one
        course may share a slot. Two DIFFERENT courses of the same semester
        may never share a slot.
        """
        section_lookup = {s.section_key: s for s in self.sections}

        # Group variables by (level, course_code, day, block_index)
        course_slot_vars = defaultdict(list)
        for (section_key, session_type, day, block_index), var in self.vars.items():
            section = section_lookup[section_key]
            key = (section.plan_comun_level, section.course_code, day, block_index)
            course_slot_vars[key].append(var)

        # One "course occupies this slot" indicator per course per slot;
        # then at most one active course per (level, day, block).
        slot_course_indicators = defaultdict(list)
        for (level, course_code, day, block_index), vars_list in course_slot_vars.items():
            indicator = self.model.NewBoolVar(f"course_at_{level}_{course_code}_{day}_{block_index}")
            for var in vars_list:
                self.model.AddImplication(var, indicator)
            slot_course_indicators[(level, day, block_index)].append(indicator)

        for key, indicators in slot_course_indicators.items():
            if len(indicators) > 1:
                self.model.Add(sum(indicators) <= 1)
    
    def _add_block4_constraint(self) -> None:
        """
        Add Block 4 (lunch hour) single-allocation rule.

        Block 4 = 12:30–13:20 slot
        Rules:
        1. If a section needs exactly 1 block for a session type,
           only allow allocation to block 4.
        2. For "2+1" distributions, if any day has exactly 1 lecture,
           that block must be block 4.

        Skipped entirely when 'relax_block4' is enabled.
        """
        if self._relaxation_flags.get('relax_block4'):
            return

        for section in self.sections:
            section_key = section.section_key
            
            # Rule 1: Exactly 1 required block -> only block 4
            for session_type_enum in [SessionType.CLASE, SessionType.AYUDANTIA, SessionType.LABORATORIO]:
                if session_type_enum == SessionType.CLASE:
                    required_blocks = section.required_clases
                elif session_type_enum == SessionType.AYUDANTIA:
                    required_blocks = section.required_ayudantias
                else:
                    required_blocks = section.required_laboratorios
                
                if required_blocks == 1:
                    # Disallow blocks other than 4
                    for (sk, st, day, block), var in self.vars.items():
                        if sk == section_key and st == session_type_enum.value and block != 4:
                            self.model.Add(var == 0)
            
            # Rule 2: "2+1" distribution single-lecture enforcement
            # (matches "2+1", "2+1-separadas", … — same family as the validator)
            if (section.class_distribution or "").strip().lower().startswith("2+1"):
                # For each day, if any non-4 block is active, then total must be >= 2
                for day_enum in DayOfWeek:
                    day_val = day_enum.value
                    
                    # Blocks other than 4
                    non_block4_vars = [
                        var for (sk, st, day, block), var in self.vars.items()
                        if sk == section_key and st == SessionType.CLASE.value and day == day_val and block != 4
                    ]
                    
                    # All blocks for this day
                    all_day_vars = [
                        var for (sk, st, day, block), var in self.vars.items()
                        if sk == section_key and st == SessionType.CLASE.value and day == day_val
                    ]
                    
                    if non_block4_vars and all_day_vars:
                        # If any non-4 block is active, total must be >= 2
                        # Enforce: sum(non_block4) <= 1 => sum(all) >= 2 doesn't work directly
                        # Instead: if any non_block4 active, then count >= 2
                        for non_var in non_block4_vars:
                            # If this block is active, total must be >= 2
                            self.model.Add(sum(all_day_vars) >= 2).OnlyEnforceIf(non_var)
    
    def _add_contiguous_blocks_constraint(self) -> None:
        """
        Add contiguous block allocation rule for "3-juntas" distribution.

        For a section with "3-juntas" lectures:
        - Exactly ONE day carries 3 CONSECUTIVE lecture blocks (the "juntas").
        - Lectures beyond the 3 (e.g. required_clases = 4) follow the
          single-block rule: at most (required - 3) single-block days, each
          at Block 4 unless 'relax_block4' is enabled.
        - Fixed case (no relaxation): only triplets {2,3,4} or {4,5,6} are
          valid. Variables outside blocks 2–6 are never created, and an
          extra constraint (x₃ ≤ x₂) prevents the otherwise-legal {3,4,5}.
        - Relaxation B: any consecutive triplet within blocks 1–7
        - Relaxation C: any consecutive triplet in the day (no restriction)
        """
        flags = self._relaxation_flags
        # 'restrict_start' is True in the fixed case: only start blocks 2 or 4 allowed
        restrict_start = not (flags.get('relax_3juntas_medium') or flags.get('relax_3juntas_full'))
        relax_block4 = flags.get('relax_block4', False)

        for section in self.sections:
            if section.class_distribution != "3-juntas":
                continue

            section_key = section.section_key
            singles_budget = max(0, section.required_clases - 3)

            triple_day_vars = []
            single_day_vars = []

            for day_enum in DayOfWeek:
                day_val = day_enum.value

                day_vars = {
                    block: var for (sk, st, day, block), var in self.vars.items()
                    if sk == section_key and st == SessionType.CLASE.value and day == day_val
                }

                if not day_vars:
                    continue

                # Daily count = 3·triple + single ∈ {0, 1, 3}
                is_triple = self.model.NewBoolVar(f"3j_triple_{section_key}_{day_val}")
                is_single = self.model.NewBoolVar(f"3j_single_{section_key}_{day_val}")
                self.model.Add(is_triple + is_single <= 1)
                self.model.Add(sum(day_vars.values()) == 3 * is_triple + is_single)

                # A day with fewer than 3 available blocks can never host the triple
                if len(day_vars) < 3:
                    self.model.Add(is_triple == 0)

                blocks_sorted = sorted(day_vars)

                # Consecutiveness of the triple:
                # (a) no two active blocks more than 2 apart
                for i, block_a in enumerate(blocks_sorted):
                    for block_b in blocks_sorted[i + 1:]:
                        if block_b > block_a + 2:
                            self.model.Add(day_vars[block_a] + day_vars[block_b] <= 1)

                # (b) if b and b+2 are both active, b+1 must be active too;
                #     if b+1 has no variable, b and b+2 cannot combine at all
                for start_block in range(11):
                    b0 = day_vars.get(start_block)
                    b1 = day_vars.get(start_block + 1)
                    b2 = day_vars.get(start_block + 2)
                    if b0 is not None and b2 is not None:
                        if b1 is not None:
                            self.model.Add(b1 >= b0 + b2 - 1)
                        else:
                            self.model.Add(b0 + b2 <= 1)

                # A lone lecture (single day) may only sit at Block 4
                if not relax_block4:
                    for block, var in day_vars.items():
                        if block != 4:
                            self.model.Add(var <= is_triple)

                # Fixed case: prevent triplet {3,4,5}
                # (variables are already restricted to blocks 2–6, so the only
                # remaining invalid triplet is {3,4,5}; x₃ ≤ x₂ rules it out)
                if restrict_start:
                    x2 = day_vars.get(2)
                    x3 = day_vars.get(3)
                    if x2 is not None and x3 is not None:
                        self.model.Add(x3 <= x2)

                triple_day_vars.append(is_triple)
                single_day_vars.append(is_single)

            # One triple day at most; extra singles only within budget
            if triple_day_vars:
                self.model.Add(sum(triple_day_vars) <= 1)
            if single_day_vars:
                self.model.Add(sum(single_day_vars) <= singles_budget)

    def _add_session_type_day_separation(self) -> None:
        """
        A section's Clases, Ayudantías and Laboratorios must fall on
        DIFFERENT days: no two session types of the same section may share
        a day.

        Applies per section — other sections of the same course are
        independent (their students are different groups).

        Each type pair can be relaxed individually through the flags in
        SAME_DAY_RELAX_FLAGS (e.g. 'relax_same_day_clase_ayud' lets Clases
        and Ayudantías coexist on a day). With all three flags enabled the
        rule disappears entirely.
        """
        flags = self._relaxation_flags

        # (section_key, day) -> {session_type: [vars]}
        day_type_vars = defaultdict(lambda: defaultdict(list))
        for (section_key, session_type, day, block_index), var in self.vars.items():
            day_type_vars[(section_key, day)][session_type].append(var)

        for (section_key, day), type_vars in day_type_vars.items():
            if len(type_vars) < 2:
                continue

            # Type pairs that must stay on different days (pair not relaxed)
            enforced_pairs = [
                pair for pair in combinations(sorted(type_vars), 2)
                if not flags.get(SAME_DAY_RELAX_FLAGS.get(frozenset(pair), ''), False)
            ]
            if not enforced_pairs:
                continue

            indicators: Dict[str, cp_model.IntVar] = {}
            for session_type in {t for pair in enforced_pairs for t in pair}:
                indicator = self.model.NewBoolVar(f"type_on_day_{section_key}_{session_type}_{day}")
                for var in type_vars[session_type]:
                    self.model.AddImplication(var, indicator)
                indicators[session_type] = indicator

            for type_a, type_b in enforced_pairs:
                self.model.Add(indicators[type_a] + indicators[type_b] <= 1)

    def _add_session_pattern_constraints(self) -> None:
        """
        Sessions must be scheduled as pairs of two CONSECUTIVE blocks.

        For every (section, session type), the blocks placed on one day must
        form either a consecutive pair {b, b+1} or — only when the weekly
        required count is odd — one single block, which must sit at Block 4
        (12:30–13:20) unless 'relax_block4' is enabled. At most one such
        single day is allowed per session type.

        Consequences:
        - required = 2 -> one pair on one day
        - required = 4 -> two pairs on two different days ("2 bloques de dos")
        - required = 3 ("2+1" or no distribution) -> one pair + one single
          at Block 4 — exactly the "2+1" layout
        - required = 1 -> one single at Block 4

        Exempt: Clases with '3-juntas' -> _add_contiguous_blocks_constraint
        (one consecutive triple; any remainder handled there as singles).
        """
        relax_block4 = self._relaxation_flags.get('relax_block4', False)

        for section in self.sections:
            section_key = section.section_key
            distribution = (section.class_distribution or "").strip().lower()

            for session_type_enum in [SessionType.CLASE, SessionType.AYUDANTIA, SessionType.LABORATORIO]:
                if session_type_enum == SessionType.CLASE:
                    required_blocks = section.required_clases
                    if distribution == "3-juntas":
                        continue
                elif session_type_enum == SessionType.AYUDANTIA:
                    required_blocks = section.required_ayudantias
                else:
                    required_blocks = section.required_laboratorios

                if required_blocks == 0:
                    continue

                single_day_terms = []
                for day_enum in DayOfWeek:
                    day_val = day_enum.value
                    day_vars = {
                        block: var for (sk, st, day, block), var in self.vars.items()
                        if sk == section_key and st == session_type_enum.value and day == day_val
                    }
                    if not day_vars:
                        continue

                    # ge1 = "at least 1 block today", ge2 = "2 blocks today"
                    # -> daily count = ge1 + ge2, capped at 2 by construction
                    ge1 = self.model.NewBoolVar(f"ge1_{section_key}_{session_type_enum.value}_{day_val}")
                    ge2 = self.model.NewBoolVar(f"ge2_{section_key}_{session_type_enum.value}_{day_val}")
                    self.model.Add(ge2 <= ge1)
                    self.model.Add(sum(day_vars.values()) == ge1 + ge2)

                    # Two blocks on the same day must be consecutive:
                    # forbid every non-adjacent combination.
                    blocks_sorted = sorted(day_vars)
                    for i, block_a in enumerate(blocks_sorted):
                        for block_b in blocks_sorted[i + 1:]:
                            if block_b > block_a + 1:
                                self.model.Add(day_vars[block_a] + day_vars[block_b] <= 1)

                    # A lone block on a day (ge2 = 0) may only sit at Block 4
                    if not relax_block4:
                        for block, var in day_vars.items():
                            if block != 4:
                                self.model.Add(var <= ge2)

                    single_day_terms.append(ge1 - ge2)

                # Single-block days: at most one, and only when required is odd
                if single_day_terms:
                    self.model.Add(sum(single_day_terms) <= required_blocks % 2)

    def _set_objective(self) -> None:
        """Set the optimization objective: maximize total scheduled blocks."""
        if self.vars:
            self.model.Maximize(sum(self.vars.values()))
    
    def solve(self, timeout_seconds: int = 60) -> Tuple[List[Dict], List[Dict]]:
        """
        Solve the scheduling problem.
        
        Args:
            timeout_seconds: Maximum time in seconds for solver
        
        Returns:
            Tuple of (scheduled_list, unscheduled_report_list):
            - scheduled_list: List of dicts with scheduled assignments
            - unscheduled_report_list: List of dicts with conflict diagnostics
        """
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = timeout_seconds
        solver.parameters.log_search_progress = True
        
        status = solver.Solve(self.model)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            logger.info(f"Solution found: status={status}")
            self._solver_solution = solver
            return self._extract_solution(solver)
        else:
            logger.warning(f"No feasible solution found: status={status}")
            return [], []
    
    def _extract_solution(self, solver: cp_model.CpSolver) -> Tuple[List[Dict], List[Dict]]:
        """
        Extract scheduled assignments and generate conflict diagnostics.
        
        Returns:
            Tuple of (scheduled_list, unscheduled_report_list)
        """
        scheduled = []
        
        # Build scheduled list
        for (section_key, session_type, day, block_index), var in self.vars.items():
            if solver.BooleanValue(var):
                section = next(s for s in self.sections if s.section_key == section_key)
                scheduled.append({
                    'section_key': section_key,
                    'course_code': section.course_code,
                    'title': section.title,
                    'session_type': session_type,
                    'day': DayOfWeek(day).name,
                    'block_index': block_index,
                    'block_times': f"{ACADEMIC_BLOCKS[block_index].start_time}-{ACADEMIC_BLOCKS[block_index].end_time}",
                    'professor_rut': self._get_professor_for_session(section, session_type),
                    'special_room': section.special_room,
                })
        
        # Generate unscheduled report
        unscheduled = self._generate_conflict_report(solver)
        
        return scheduled, unscheduled
    
    def _get_professor_for_session(self, section: CourseSection, session_type: str) -> str:
        """Determine which professor for a given session type."""
        if session_type == SessionType.CLASE.value:
            return section.professor_1_rut
        elif session_type == SessionType.AYUDANTIA.value:
            return section.professor_2_rut or section.professor_1_rut
        else:  # LABORATORIO
            return section.lab_professor_rut or section.professor_1_rut
    
    def _generate_conflict_report(self, solver: cp_model.CpSolver) -> List[Dict]:
        """
        Generate diagnostic report for unscheduled courses.
        
        For each section, check if all required blocks were scheduled.
        If not, attempt to diagnose why.
        """
        report = []
        
        for section in self.sections:
            section_key = section.section_key
            total_required = section.required_clases + section.required_ayudantias + section.required_laboratorios
            
            # Count scheduled blocks for this section
            scheduled_count = 0
            for (sk, st, day, block), var in self.vars.items():
                if sk == section_key and solver.BooleanValue(var):
                    scheduled_count += 1
            
            if scheduled_count < total_required:
                # This section is under-scheduled
                diagnosis = self._diagnose_conflicts(section, solver, scheduled_count, total_required)
                report.append({
                    'section_key': section_key,
                    'course_code': section.course_code,
                    'title': section.title,
                    'plan_comun_level': section.plan_comun_level,
                    'required_blocks': total_required,
                    'scheduled_blocks': scheduled_count,
                    'missing_blocks': total_required - scheduled_count,
                    'diagnosis': diagnosis,
                })
        
        return report
    
    def _diagnose_conflicts(
        self,
        section: CourseSection,
        solver: cp_model.CpSolver,
        scheduled_count: int,
        total_required: int
    ) -> Dict:
        """
        Diagnose why a section couldn't be fully scheduled.
        
        Scans allowed slots to identify bottlenecks.
        """
        diagnosis = {
            'allowed_slots_count': len(section.allowed_slots),
            'bottlenecks': [],
        }
        
        # Check professor availability
        prof_rut = section.professor_1_rut
        slot_conflicts = []
        for slot in section.allowed_slots:
            if GlobalTimeConstraints.is_slot_globally_invalid(slot, SessionType.CLASE, section.plan_comun_level):
                slot_conflicts.append(f"{slot.day.name} Block {slot.block_index}")
        
        if slot_conflicts:
            diagnosis['bottlenecks'].append({
                'type': 'global_constraint',
                'description': f'Professor {prof_rut} has {len(slot_conflicts)} slots violating global constraints (Plan Común {section.plan_comun_level})',
                'examples': slot_conflicts[:3],
            })
        
        # Check room availability if special room required
        if section.special_room:
            diagnosis['bottlenecks'].append({
                'type': 'special_room',
                'room': section.special_room,
                'description': f'Special room {section.special_room} may be over-booked',
            })
        
        # Check cohort level conflicts
        cohort_courses = [s for s in self.sections if s.plan_comun_level == section.plan_comun_level]
        diagnosis['bottlenecks'].append({
            'type': 'cohort_overlap',
            'cohort_level': section.plan_comun_level,
            'courses_in_cohort': len(cohort_courses),
            'description': f'{len(cohort_courses)} courses competing for Plan Común {section.plan_comun_level} slots',
        })
        
        return diagnosis


def main():
    """Test the scheduler with mock data."""
    from ..models.models import create_professor_available_slots
    
    # Create mock sections with intentional bottleneck
    sections = []
    
    # Shared professor with limited availability
    shared_prof = "ENC_PROF_001"
    limited_slots = frozenset([
        TimeSlot(DayOfWeek.LUNES, 5),
        TimeSlot(DayOfWeek.LUNES, 6),
        TimeSlot(DayOfWeek.MARTES, 5),
        TimeSlot(DayOfWeek.MARTES, 6),
    ])
    
    # Section 1: Needs 2 lecture blocks
    sections.append(CourseSection(
        section_key="TEST001",
        course_code="TST101",
        title="Test Course A",
        plan_comun_level=1,
        required_clases=2,
        required_ayudantias=0,
        required_laboratorios=0,
        professor_1_rut=shared_prof,
        professor_2_rut=None,
        lab_professor_rut=None,
        special_room=None,
        class_distribution=None,
        allowed_slots=limited_slots,
    ))
    
    # Section 2: Also needs 2 lecture blocks, same limited slots
    sections.append(CourseSection(
        section_key="TEST002",
        course_code="TST102",
        title="Test Course B",
        plan_comun_level=1,
        required_clases=2,
        required_ayudantias=0,
        required_laboratorios=0,
        professor_1_rut=shared_prof,
        professor_2_rut=None,
        lab_professor_rut=None,
        special_room=None,
        class_distribution=None,
        allowed_slots=limited_slots,
    ))
    
    # Section 3: Needs 1 block (should fit in block 4 by constraint)
    block4_slot = frozenset([TimeSlot(DayOfWeek.MIERCOLES, 4)])
    sections.append(CourseSection(
        section_key="TEST003",
        course_code="TST103",
        title="Test Course C",
        plan_comun_level=2,
        required_clases=1,
        required_ayudantias=0,
        required_laboratorios=0,
        professor_1_rut="ENC_PROF_002",
        professor_2_rut=None,
        lab_professor_rut=None,
        special_room=None,
        class_distribution=None,
        allowed_slots=block4_slot,
    ))
    
    # Run scheduler
    scheduler = CourseScheduler(sections)
    scheduled, unscheduled = scheduler.solve(timeout_seconds=30)
    
    # Print results
    print("\n" + "="*80)
    print("SCHEDULING RESULTS")
    print("="*80)
    
    print(f"\n✓ SCHEDULED BLOCKS: {len(scheduled)}")
    print("-" * 80)
    for assignment in scheduled:
        print(f"{assignment['section_key']:10} | {assignment['course_code']:10} | "
              f"{assignment['day']:10} Block {assignment['block_index']} | "
              f"{assignment['block_times']:12} | Room: {assignment['special_room'] or 'Standard'}")
    
    print(f"\n⚠ UNSCHEDULED CONFLICTS: {len(unscheduled)}")
    print("-" * 80)
    for conflict in unscheduled:
        print(f"\n{conflict['section_key']}: {conflict['title']}")
        print(f"  Required: {conflict['required_blocks']} blocks | "
              f"Scheduled: {conflict['scheduled_blocks']} blocks | "
              f"Missing: {conflict['missing_blocks']} blocks")
        print(f"  Bottlenecks:")
        for bottleneck in conflict['diagnosis']['bottlenecks']:
            print(f"    - {bottleneck['type']}: {bottleneck['description']}")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    main()

