"""
Comprehensive Integration Diagnostic Runner

Validates data pipeline (loader → scheduler) for structural and type mismatches.
Provides detailed telemetry on data ingestion, variable allocation, and solver execution.
"""

import sys
import logging
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple

import pandas as pd
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.data.loader import load_course_sections
from src.solver.scheduler import CourseScheduler
from src.models.models import CourseSection, DayOfWeek, SessionType

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# File path to real dataset (EDIT HERE to change data source)
DATA_FILE_PATH = "data/sample_courses.xlsx"

# ============================================================================
# PHASE 1: DATA INGESTION TELEMETRY
# ============================================================================

def validate_data_types(sections: List[CourseSection]) -> Dict[str, any]:
    """
    Validate data types of loaded sections for pandas conversion issues.
    
    Returns:
        Dict with validation results
    """
    print("\n" + "="*80)
    print("PHASE 1: DATA INGESTION TELEMETRY")
    print("="*80)
    
    results = {
        'total_sections': len(sections),
        'empty_sections': 0,
        'type_issues': [],
        'empty_slots_sections': [],
    }
    
    print(f"\n✓ Total Sections Loaded: {len(sections)}")
    
    # Check for completely empty requirements
    empty_requirement_count = 0
    for i, section in enumerate(sections):
        if section.required_clases == 0 and section.required_ayudantias == 0 and section.required_laboratorios == 0:
            empty_requirement_count += 1
            if empty_requirement_count <= 5:  # Print first 5
                print(f"  - Section {section.section_key}: NO REQUIREMENTS (0,0,0)")
    
    results['empty_sections'] = empty_requirement_count
    if empty_requirement_count > 0:
        print(f"\n⚠ WARNING: {empty_requirement_count} sections have ZERO requirements")
        print("  These sections will create no decision variables in the solver.")
    
    # Check for empty allowed_slots
    empty_slots_count = 0
    for section in sections:
        if len(section.allowed_slots) == 0:
            empty_slots_count += 1
            results['empty_slots_sections'].append(section.section_key)
    
    if empty_slots_count > 0:
        print(f"\n⚠ CRITICAL: {empty_slots_count} sections have EMPTY allowed_slots!")
        print(f"  Section keys: {results['empty_slots_sections'][:5]}")
        print("  These sections cannot be scheduled (no valid time slots).")
    
    # Validate data types for first 3 sections
    print(f"\n📊 Data Type Validation (First 3 Sections):")
    print("-" * 80)
    
    for i, section in enumerate(sections[:3]):
        print(f"\nSection {i+1}: {section.section_key}")
        
        # Check requirement types
        types_info = {
            'required_clases': (type(section.required_clases).__name__, section.required_clases),
            'required_ayudantias': (type(section.required_ayudantias).__name__, section.required_ayudantias),
            'required_laboratorios': (type(section.required_laboratorios).__name__, section.required_laboratorios),
        }
        
        for field, (type_name, value) in types_info.items():
            is_correct = isinstance(value, int)
            status = "✓" if is_correct else "✗"
            print(f"  {status} {field}: {type_name} = {value}")
            
            # Check for pandas float64 or NaN issues
            if isinstance(value, (float, np.floating)):
                print(f"    WARNING: Got {type_name} instead of int! Value: {value}")
                results['type_issues'].append({
                    'section': section.section_key,
                    'field': field,
                    'type': type_name,
                    'value': value,
                })
        
        # Check professor RUT types
        print(f"  ✓ professor_1_rut: {type(section.professor_1_rut).__name__} (len={len(section.professor_1_rut)})")
        print(f"  ✓ allowed_slots: frozenset with {len(section.allowed_slots)} slots")
        
        if section.allowed_slots:
            sample_slot = list(section.allowed_slots)[0]
            print(f"    Sample slot: {sample_slot} (day={sample_slot.day.name}, block={sample_slot.block_index})")
    
    print("\n" + "-" * 80)
    return results

# ============================================================================
# PHASE 2: SOLVER VARIABLE TELEMETRY
# ============================================================================

def analyze_scheduler_variables(scheduler: CourseScheduler) -> Dict[str, any]:
    """
    Analyze decision variable allocation in the scheduler.
    
    Returns:
        Dict with variable telemetry
    """
    print("\n" + "="*80)
    print("PHASE 2: SOLVER VARIABLE TELEMETRY")
    print("="*80)
    
    results = {
        'total_vars': len(scheduler.vars),
        'vars_by_section': defaultdict(int),
        'vars_by_session_type': defaultdict(int),
        'vars_by_day': defaultdict(int),
    }
    
    print(f"\n✓ Total Decision Variables Created: {len(scheduler.vars)}")
    
    if len(scheduler.vars) == 0:
        print("\n" + "!"*80)
        print("CRITICAL WARNING: NO DECISION VARIABLES CREATED!")
        print("!"*80)
        print("\nThis means NO valid time slots matched the constraints.")
        print("Possible causes:")
        print("  1. All sections have empty allowed_slots (professor availability)")
        print("  2. All allowed_slots violate GlobalTimeConstraints")
        print("  3. No sections have required_clases > 0, required_ayudantias > 0, or required_laboratorios > 0")
        print("\nAction: Review Phase 1 output for empty_slots or empty_sections.")
        return results
    
    # Breakdown by section
    for (section_key, session_type, day, block), var in scheduler.vars.items():
        results['vars_by_section'][section_key] += 1
        results['vars_by_session_type'][session_type] += 1
        results['vars_by_day'][DayOfWeek(day).name] += 1
    
    print(f"\n📊 Variables by Section (Top 10):")
    print("-" * 80)
    sorted_sections = sorted(results['vars_by_section'].items(), key=lambda x: x[1], reverse=True)
    for section_key, count in sorted_sections[:10]:
        section = next((s for s in scheduler.sections if s.section_key == section_key), None)
        if section:
            total_req = section.required_clases + section.required_ayudantias + section.required_laboratorios
            print(f"  {section_key:15} | {count:4} vars | Required: {total_req} blocks | "
                  f"Allowed slots: {len(section.allowed_slots)}")
    
    print(f"\n📊 Variables by Session Type:")
    print("-" * 80)
    for session_type, count in sorted(results['vars_by_session_type'].items()):
        print(f"  {session_type:15} | {count:5} vars")
    
    print(f"\n📊 Variables by Day:")
    print("-" * 80)
    for day in [d.name for d in DayOfWeek]:
        count = results['vars_by_day'].get(day, 0)
        print(f"  {day:15} | {count:5} vars")
    
    print("\n" + "-" * 80)
    return results

# ============================================================================
# PHASE 3: MODEL CONSTRAINTS INSPECTION
# ============================================================================

def inspect_model_constraints(scheduler: CourseScheduler) -> None:
    """
    Inspect the CP-SAT model constraints for debugging.
    """
    print("\n" + "="*80)
    print("PHASE 3: MODEL CONSTRAINTS INSPECTION")
    print("="*80)
    
    model = scheduler.model
    print(f"\n✓ CP-SAT Model Statistics:")
    print("-" * 80)
    print(f"  Decision Variables Created: {len(scheduler.vars)}")
    print(f"  Model Status: Ready for solving")
    print(f"  Variable Key Format: (section_key, session_type, day, block_index)")
    
    print("\n" + "-" * 80)

# ============================================================================
# PHASE 4: SOLVER EXECUTION
# ============================================================================

def run_solver(scheduler: CourseScheduler, timeout_seconds: int = 60) -> Tuple[List, List]:
    """
    Execute the scheduler and capture results.
    
    Returns:
        Tuple of (scheduled_list, unscheduled_list)
    """
    print("\n" + "="*80)
    print("PHASE 4: SOLVER EXECUTION")
    print("="*80)
    
    print(f"\n⏱ Running solver with {timeout_seconds}s timeout...")
    print("-" * 80)
    
    scheduled, unscheduled = scheduler.solve(timeout_seconds=timeout_seconds)
    
    return scheduled, unscheduled

# ============================================================================
# PHASE 5: RESULTS REPORTING
# ============================================================================

def report_results(
    sections: List[CourseSection],
    scheduled: List[Dict],
    unscheduled: List[Dict]
) -> None:
    """
    Print comprehensive results report.
    """
    print("\n" + "="*80)
    print("PHASE 5: RESULTS REPORTING")
    print("="*80)
    
    # Calculate total requirements
    total_required = sum(
        s.required_clases + s.required_ayudantias + s.required_laboratorios
        for s in sections
    )
    
    scheduled_count = len(scheduled)
    unscheduled_count = len(unscheduled)
    
    print(f"\n{'='*80}")
    print(f"SOLVER SUMMARY")
    print(f"{'='*80}")
    print(f"Total Sections Loaded:        {len(sections)}")
    print(f"Total Blocks Required:        {total_required}")
    print(f"Blocks Successfully Scheduled: {scheduled_count}")
    print(f"Sections with Conflicts:      {unscheduled_count}")
    
    if scheduled_count == 0 and total_required > 0:
        print(f"\n⚠ WARNING: ZERO blocks scheduled despite {total_required} requirements!")
    else:
        utilization = (scheduled_count / total_required * 100) if total_required > 0 else 0
        print(f"Utilization Rate:             {utilization:.1f}%")
    
    # Scheduled blocks detail
    if scheduled_count > 0:
        print(f"\n{'─'*80}")
        print(f"✓ SCHEDULED BLOCKS ({scheduled_count} total, showing first 20):")
        print(f"{'─'*80}")
        for i, assignment in enumerate(scheduled[:20]):
            print(f"{i+1:3}. {assignment['section_key']:15} | {assignment['day']:10} "
                  f"Block {assignment['block_index']} | {assignment['block_times']:12} | "
                  f"{assignment['session_type']:10} | Room: {assignment['special_room'] or 'Standard'}")
        if scheduled_count > 20:
            print(f"... and {scheduled_count - 20} more scheduled blocks")
    
    # Unscheduled/conflict report
    if unscheduled_count > 0:
        print(f"\n{'─'*80}")
        print(f"⚠ UNSCHEDULED CONFLICTS ({unscheduled_count} sections):")
        print(f"{'─'*80}")
        
        # Group by bottleneck type
        bottleneck_by_type = defaultdict(list)
        for conflict in unscheduled:
            for bottleneck in conflict['diagnosis']['bottlenecks']:
                bottleneck_by_type[bottleneck['type']].append(conflict)
        
        for conflict_idx, conflict in enumerate(unscheduled[:15]):
            print(f"\n{conflict_idx+1}. {conflict['section_key']} | {conflict['title']}")
            print(f"   Required: {conflict['required_blocks']} blocks | "
                  f"Scheduled: {conflict['scheduled_blocks']} blocks | "
                  f"Missing: {conflict['missing_blocks']} blocks")
            print(f"   Plan Común Level: {conflict['plan_comun_level']}")
            print(f"   Bottlenecks:")
            for bottleneck in conflict['diagnosis']['bottlenecks']:
                print(f"     - {bottleneck['type'].upper()}: {bottleneck['description']}")
                if 'examples' in bottleneck:
                    print(f"       Examples: {', '.join(bottleneck['examples'][:3])}")
        
        if unscheduled_count > 15:
            print(f"\n... and {unscheduled_count - 15} more sections with conflicts")
        
        # Summary of bottleneck types
        print(f"\n{'─'*80}")
        print(f"Bottleneck Summary:")
        print(f"{'─'*80}")
        for btype, conflicts in bottleneck_by_type.items():
            unique_courses = set(c['section_key'] for c in conflicts)
            print(f"  {btype.upper():20} | Affecting {len(unique_courses):3} sections")
    
    print(f"\n{'='*80}")

# ============================================================================
# DATA TYPE REPAIR SUGGESTIONS
# ============================================================================

def suggest_type_fixes(data_issues: List[Dict]) -> None:
    """
    Suggest fixes for data type issues found in loader.
    """
    if not data_issues:
        return
    
    print("\n" + "="*80)
    print("DATA TYPE REPAIR SUGGESTIONS")
    print("="*80)
    
    print("\n⚠ Found data type issues. Suggested fixes for src/data/loader.py:")
    print("-" * 80)
    
    for issue in data_issues[:5]:
        print(f"\nSection: {issue['section']}")
        print(f"  Field: {issue['field']}")
        print(f"  Current Type: {issue['type']} (value: {issue['value']})")
        print(f"  Fix: Use int(row['{issue['field']}']) or np.int32(row['{issue['field']}'])")
    
    print("\n" + "-" * 80)

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main diagnostics runner."""
    print("\n")
    print("#" * 80)
    print("# INTEGRATION DIAGNOSTIC RUNNER - Loader → Scheduler Pipeline")
    print("#" * 80)
    print(f"Data File: {DATA_FILE_PATH}")
    print("#" * 80)
    
    # Check if file exists
    if not Path(DATA_FILE_PATH).exists():
        print(f"\n✗ ERROR: Data file not found: {DATA_FILE_PATH}")
        print(f"Current working directory: {Path.cwd()}")
        print(f"Available files in data/:")
        data_dir = Path("data")
        if data_dir.exists():
            for f in data_dir.glob("*"):
                print(f"  - {f.name}")
        sys.exit(1)
    
    # PHASE 1: Load and validate data
    print(f"\n📥 Loading data from: {DATA_FILE_PATH}")
    try:
        sections = load_course_sections(DATA_FILE_PATH)
        print(f"✓ Successfully loaded {len(sections)} sections")
    except Exception as e:
        print(f"\n✗ ERROR during data loading:")
        print(f"  {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # PHASE 1: Ingest telemetry
    ingest_results = validate_data_types(sections)
    
    # PHASE 2: Create scheduler and analyze variables
    print(f"\n🔧 Instantiating CourseScheduler...")
    try:
        scheduler = CourseScheduler(sections)
        print(f"✓ Scheduler instantiated successfully")
    except Exception as e:
        print(f"\n✗ ERROR during scheduler instantiation:")
        print(f"  {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    var_results = analyze_scheduler_variables(scheduler)
    inspect_model_constraints(scheduler)
    
    # Check if we have any variables
    if var_results['total_vars'] == 0:
        print("\n" + "!"*80)
        print("STOPPING: Cannot proceed with solver (zero variables).")
        print("!"*80)
        print("\nDiagnosis needed:")
        if ingest_results['empty_sections'] == len(sections):
            print("  → All sections have zero requirements")
        if ingest_results['empty_slots_sections']:
            print(f"  → {len(ingest_results['empty_slots_sections'])} sections have empty allowed_slots")
        sys.exit(1)
    
    # PHASE 4: Run solver
    scheduled, unscheduled = run_solver(scheduler, timeout_seconds=60)
    
    # PHASE 5: Report results
    report_results(sections, scheduled, unscheduled)
    
    # Data type fixes
    if ingest_results['type_issues']:
        suggest_type_fixes(ingest_results['type_issues'])
    
    # Final summary
    print(f"\n{'='*80}")
    print("DIAGNOSTIC RUN COMPLETE")
    print(f"{'='*80}")
    if len(scheduled) > 0 or len(unscheduled) == 0:
        print("✓ No critical errors detected")
    else:
        print("⚠ Check bottleneck analysis above for resource constraints")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
