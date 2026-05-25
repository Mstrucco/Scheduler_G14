#!/usr/bin/env python
"""Quick syntax validation of models.py"""

import sys
import py_compile

try:
    py_compile.compile('src/models.py', doraise=True)
    print("✓ Syntax check passed: src/models.py is valid Python")
    
    # Try importing
    from src.models import (
        DayOfWeek, SessionType, TimeBlock, TimeSlot, CourseSection,
        GlobalTimeConstraints, ACADEMIC_BLOCKS, parse_class_distribution,
        create_professor_available_slots
    )
    print("✓ Import check passed: All components imported successfully")
    
    # Quick instantiation test
    slot = TimeSlot(DayOfWeek.LUNES, 0)
    print(f"✓ TimeSlot instantiation: {slot}")
    
    # Test constraint validation
    is_invalid = GlobalTimeConstraints.is_slot_globally_invalid(slot, SessionType.CLASE)
    print(f"✓ Constraint validation works: Monday Block 0 + Clase = {'Invalid' if is_invalid else 'Valid'}")
    
    # Test academic blocks
    print(f"✓ Academic blocks defined: {len(ACADEMIC_BLOCKS)} blocks total")
    print(f"  - Block 0: {ACADEMIC_BLOCKS[0].start_time}-{ACADEMIC_BLOCKS[0].end_time}")
    print(f"  - Block 12: {ACADEMIC_BLOCKS[12].start_time}-{ACADEMIC_BLOCKS[12].end_time}")
    
    print("\n" + "=" * 60)
    print("ALL VALIDATION CHECKS PASSED")
    print("=" * 60)
    
except SyntaxError as e:
    print(f"❌ Syntax error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
