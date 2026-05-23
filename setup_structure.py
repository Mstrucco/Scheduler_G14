#!/usr/bin/env python
"""Setup script to create folder structure for scheduler MVP"""

import os
import sys

def create_structure():
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    # Define directory structure
    dirs = [
        "src",
        "src/data",
        "src/models",
        "src/solver",
        "src/ui",
        "src/utils",
        "tests",
        "data",
    ]
    
    # Create directories
    print("Creating directories...")
    for dir_path in dirs:
        full_path = os.path.join(base_path, dir_path)
        os.makedirs(full_path, exist_ok=True)
        print(f"  ✓ {dir_path}")
    
    # Define file contents
    files_to_create = {
        # __init__.py files
        "src/__init__.py": '"""\nMain src package\n"""\n\n__version__ = "0.1.0"\n',
        "src/data/__init__.py": '"""\nData loading and validation module\n"""\n',
        "src/models/__init__.py": '"""\nData models for scheduling entities\n"""\n',
        "src/solver/__init__.py": '"""\nOR-Tools based scheduling solver\n"""\n',
        "src/ui/__init__.py": '"""\nStreamlit UI components and pages\n"""\n',
        "src/utils/__init__.py": '"""\nUtility functions and helpers\n"""\n',
        "tests/__init__.py": '"""\nTest suite for university scheduling MVP\n"""\n',
        
        # Data loader
        "src/data/loader.py": '''"""\nCSV and Excel data loading functionality\n"""\n\nclass DataLoader:\n    """Handles loading data from CSV and Excel files"""\n    pass\n''',
        
        # Data validator
        "src/data/validator.py": '''"""\nData validation and integrity checking\n"""\n\nclass DataValidator:\n    """Validates loaded data for consistency and completeness"""\n    pass\n''',
        
        # Models
        "src/models/course.py": '''"""\nCourse model\n"""\n\nclass Course:\n    """Represents a university course"""\n    pass\n''',
        
        "src/models/instructor.py": '''"""\nInstructor model\n"""\n\nclass Instructor:\n    """Represents an instructor with availability constraints"""\n    pass\n''',
        
        "src/models/room.py": '''"""\nRoom model\n"""\n\nclass Room:\n    """Represents a classroom or meeting room"""\n    pass\n''',
        
        "src/models/schedule.py": '''"""\nSchedule model\n"""\n\nclass Schedule:\n    """Represents the complete schedule with all assignments"""\n    pass\n''',
        
        # Solver
        "src/solver/scheduler.py": '''"""\nOR-Tools constraint programming solver for university scheduling\n"""\n\nclass UniversityScheduler:\n    """Solves the university scheduling problem using OR-Tools"""\n    pass\n''',
        
        # UI
        "src/ui/dashboard.py": '''"""\nMain Streamlit dashboard\n"""\n\nclass Dashboard:\n    """Main dashboard for schedule visualization and interaction"""\n    pass\n''',
        
        "src/ui/components.py": '''"""\nReusable Streamlit UI components\n"""\n\nclass StreamlitComponents:\n    """Collection of custom Streamlit components"""\n    pass\n''',
        
        # Utils
        "src/utils/helpers.py": '''"""\nHelper functions and utilities\n"""\n\nclass Helpers:\n    """Collection of helper functions"""\n    pass\n''',
        
        # Tests
        "tests/test_loader.py": '''"""\nTests for data loader functionality\n"""\n\ndef test_placeholder():\n    """Placeholder test"""\n    pass\n''',
        
        "tests/test_solver.py": '''"""\nTests for scheduling solver\n"""\n\ndef test_placeholder():\n    """Placeholder test"""\n    pass\n''',
        
        "tests/test_models.py": '''"""\nTests for data models\n"""\n\ndef test_placeholder():\n    """Placeholder test"""\n    pass\n''',
        
        # Sample data
        "data/sample_courses.csv": '''course_id,course_name,instructor_id,duration_hours,student_count\nCS101,Introduction to Python,INS001,3,50\nCS102,Data Structures,INS002,4,45\nMATH201,Calculus II,INS003,3,60\nMATH202,Linear Algebra,INS001,4,55\nENG101,English Composition,INS004,3,40\n''',
        
        "data/sample_instructors.csv": '''instructor_id,instructor_name,department,max_hours_per_week,preferred_times\nINS001,John Smith,Computer Science,12,Morning\nINS002,Jane Doe,Computer Science,12,Afternoon\nINS003,Bob Johnson,Mathematics,12,Morning\nINS004,Alice Williams,English,12,Afternoon\n''',
        
        "data/sample_rooms.csv": '''room_id,room_name,capacity,building,has_projector\nR001,Lab A,30,Science Hall,Yes\nR002,Lecture Hall 1,100,Main Building,Yes\nR003,Classroom 101,50,Main Building,Yes\nR004,Seminar Room,25,Science Hall,Yes\nR005,Computer Lab,40,Tech Building,Yes\n''',
    }
    
    # Create files
    print("\nCreating files...")
    for file_path, content in files_to_create.items():
        full_path = os.path.join(base_path, file_path)
        if not os.path.exists(full_path):
            with open(full_path, "w") as f:
                f.write(content)
            print(f"  ✓ {file_path}")
    
    print("\n✓ Project structure initialized successfully!")
    print("\nNext steps:")
    print("1. Install dependencies: pip install -r requirements.txt")
    print("2. Run the app: streamlit run app.py")

if __name__ == "__main__":
    create_structure()

