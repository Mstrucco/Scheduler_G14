"""
OR-Tools CP-SAT constraint programming solver for university scheduling.

Implements a production-grade course scheduler that solves all Plan Común cohort
levels (1, 2, 3, 4) simultaneously while respecting:
- Professor availability and multi-booking protection
- Special room requirements and capacity
- Cohort-level time conflicts
- Chilean institutional time constraints
- Distribution rules (2+1, 3-in-a-row)
"""

import logging
from typing import Dict, List, Tuple, Set, Optional
from collections import defaultdict

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
                - 'relax_availability'     : ignore professor declared availability (all semesters)
                - 'relax_3juntas_medium'   : allow 3-juntas in any consecutive 3 blocks within 1–7
                - 'relax_3juntas_full'     : allow 3-juntas in any consecutive 3 blocks in the day
                - 'relax_block4'           : single-block sessions can use any slot (not just block 4)
                - 'relax_ayudantia_partial': only blocks 0–2 forbidden for Ayudantías
                - 'relax_ayudantia_full'   : no morning restriction for Ayudantías
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
        
        # 5. Set maximization objective
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

                # Determine candidate slots (professor availability or relaxed)
                if flags.get('relax_availability'):
                    relaxed_avail = {
                        DayOfWeek.LUNES:     frozenset(range(9)),
                        DayOfWeek.MARTES:    frozenset(range(9)),
                        DayOfWeek.MIERCOLES: frozenset(range(9)),
                        DayOfWeek.JUEVES:    frozenset(range(9)),
                        DayOfWeek.VIERNES:   frozenset(range(9)),
                    }
                    available_slots = create_professor_available_slots(relaxed_avail)
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
        Add cohort-level non-overlap constraints (Plan Común).
        
        CORRECTED INTERPRETATION: At any given time slot, multiple courses from 
        the SAME cohort level CAN run in parallel. However, they must not be 
        sections of the SAME course code at the SAME time.
        
        This constraint prevents the same course from being double-scheduled,
        not preventing parallel execution of different courses.
        """
        # Group by (plan_comun_level, course_code, day, block_index)
        # This ensures the same course isn't scheduled twice at the same time
        course_blocks = defaultdict(list)
        
        for (section_key, session_type, day, block_index), var in self.vars.items():
            section = next(s for s in self.sections if s.section_key == section_key)
            
            # Key: course code + day + block (same course can't be at same time)
            key = (section.course_code, day, block_index)
            course_blocks[key].append(var)
        
        # For each course/day/block, at most all its required sessions can be scheduled
        # (no double-scheduling of same course)
        for key, vars_list in course_blocks.items():
            if len(vars_list) > 1:
                # Multiple sessions of same course at same time - allow max 1
                # (one session type per slot, e.g., either Clase OR Ayudantia, not both)
                self.model.Add(sum(vars_list) <= 1)
    
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
            if section.class_distribution == "2+1":
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

        If a section has "3-juntas" (3 lectures together):
        - All 3 blocks must occur on the same day
        - All 3 blocks must be consecutive
        - Fixed case (no relaxation): only triplets {2,3,4} or {4,5,6} are valid.
          Variables for blocks outside 2–6 are never created, and an extra
          constraint (x₃ ≤ x₂) prevents the otherwise-legal {3,4,5} triplet.
        - Relaxation B: any consecutive triplet within blocks 1–7
        - Relaxation C: any consecutive triplet in the day (no block restriction)
        """
        flags = self._relaxation_flags
        # 'restrict_start' is True in the fixed case: only start blocks 2 or 4 allowed
        restrict_start = not (flags.get('relax_3juntas_medium') or flags.get('relax_3juntas_full'))

        for section in self.sections:
            if section.class_distribution != "3-juntas":
                continue

            section_key = section.section_key

            for day_enum in DayOfWeek:
                day_val = day_enum.value

                day_vars = {
                    block: var for (sk, st, day, block), var in self.vars.items()
                    if sk == section_key and st == SessionType.CLASE.value and day == day_val
                }

                if len(day_vars) < 3:
                    continue

                # Gap-filling: if b and b+2 are both active, b+1 must be active
                for start_block in range(11):
                    b0 = day_vars.get(start_block)
                    b1 = day_vars.get(start_block + 1)
                    b2 = day_vars.get(start_block + 2)

                    if b0 is not None and b1 is not None and b2 is not None:
                        self.model.Add(b1 >= b0 + b2 - 1)

                # Exactly 3 active on this day (or 0)
                active_vars = list(day_vars.values())
                if active_vars:
                    total = self.model.NewIntVar(0, 3, f"3juntas_day_{section_key}_{day_val}_total")
                    self.model.Add(total == sum(active_vars))
                    for var in active_vars:
                        self.model.Add(total == 3).OnlyEnforceIf(var)

                # Fixed case: prevent triplet {3,4,5}
                # (variables are already restricted to blocks 2–6, so the only
                # remaining invalid triplet is {3,4,5}; x₃ ≤ x₂ rules it out)
                if restrict_start:
                    x2 = day_vars.get(2)
                    x3 = day_vars.get(3)
                    if x2 is not None and x3 is not None:
                        self.model.Add(x3 <= x2)
    
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

