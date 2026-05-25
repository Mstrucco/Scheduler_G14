#!/usr/bin/env python
"""
Test the loader against the actual sample_courses.xlsx file
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    from src.data.loader import load_course_sections
    
    # Path to sample data
    sample_file = project_root / "data" / "sample_courses.xlsx"
    
    print("=" * 80)
    print("TESTING LOADER WITH ACTUAL SAMPLE DATA")
    print("=" * 80)
    print(f"\nLoading: {sample_file}")
    print(f"File exists: {sample_file.exists()}\n")
    
    try:
        sections = load_course_sections(str(sample_file))
        
        print(f"✓ Successfully loaded {len(sections)} course sections\n")
        
        for i, section in enumerate(sections, 1):
            print(f"[Section {i}] {section.section_key}")
            print(f"  Course: {section.course_code} - {section.title}")
            print(f"  Plan Común Level: {section.plan_comun_level}")
            print(f"  Requirements: {section.required_clases} Clases, {section.required_ayudantias} Ayudantías, {section.required_laboratorios} Labs")
            print(f"  Professor 1: {section.professor_1_rut}")
            print(f"  Professor 2: {section.professor_2_rut}")
            print(f"  Lab Professor: {section.lab_professor_rut}")
            print(f"  Special Room: {section.special_room}")
            print(f"  Distribution: {section.class_distribution}")
            print(f"  Allowed Slots: {len(section.allowed_slots)} time slots")
            
            # Show breakdown by day
            from src.models.models import DayOfWeek
            for day in DayOfWeek:
                day_slots = sorted([s.block_index for s in section.allowed_slots if s.day == day])
                if day_slots:
                    print(f"    {day.name:10s}: Blocks {day_slots}")
            print()
        
        print("=" * 80)
        print("✓ Test completed successfully!")
        print("=" * 80)
    
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
