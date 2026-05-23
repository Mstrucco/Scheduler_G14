SCHEDULER MVP - PROJECT STRUCTURE
==================================

Expected folder structure after initialization:

scheduler-mvp/
├── .git/                          # Git repository
├── .venv/                         # Python virtual environment
├── src/                           # Main source code package
│   ├── __init__.py
│   ├── data/                      # Data loading and validation
│   │   ├── __init__.py
│   │   ├── loader.py              # CSV/Excel loading with Pandas
│   │   └── validator.py           # Data validation utilities
│   ├── models/                    # Data models
│   │   ├── __init__.py
│   │   ├── course.py              # Course model
│   │   ├── instructor.py          # Instructor model
│   │   ├── room.py                # Room/Classroom model
│   │   └── schedule.py            # Schedule model
│   ├── solver/                    # OR-Tools solver
│   │   ├── __init__.py
│   │   └── scheduler.py           # UniversityScheduler class
│   ├── ui/                        # Streamlit UI components
│   │   ├── __init__.py
│   │   ├── dashboard.py           # Main dashboard
│   │   └── components.py          # Reusable UI components
│   └── utils/                     # Utility functions
│       ├── __init__.py
│       └── helpers.py             # Helper functions
├── tests/                         # Unit tests
│   ├── __init__.py
│   ├── test_loader.py             # Tests for data loader
│   ├── test_solver.py             # Tests for solver
│   └── test_models.py             # Tests for models
├── data/                          # Sample data files
│   ├── sample_courses.csv         # Sample courses
│   ├── sample_instructors.csv     # Sample instructors
│   └── sample_rooms.csv           # Sample rooms
├── app.py                         # Main Streamlit entry point
├── requirements.txt               # Python dependencies
├── README.md                      # Project documentation
├── setup_structure.py             # Setup script for full initialization
├── init.py                        # Initialization script
└── setup.bat                      # Batch file for Windows setup


QUICK START
===========

1. Install dependencies:
   pip install -r requirements.txt

2. Initialize project structure (creates all directories and files):
   python setup_structure.py
   OR
   python init.py
   OR on Windows:
   setup.bat

3. Run the Streamlit app:
   streamlit run app.py

4. Run tests:
   pytest tests/


ARCHITECTURE OVERVIEW
=====================

The project follows a modular architecture:

- src/data/       → Handles data loading (CSV/Excel) and validation using Pandas
- src/models/     → Defines data structures for Course, Instructor, Room, Schedule
- src/solver/     → Contains the OR-Tools constraint programming solver
- src/ui/         → Streamlit dashboard and UI components
- src/utils/      → Shared utilities and helper functions
- tests/          → Unit tests using pytest
- data/           → Sample data in CSV format


DEPENDENCIES
============

- streamlit==1.28.1       # Web UI framework
- pandas==2.1.3           # Data manipulation and analysis
- openpyxl==3.10.10       # Excel file support
- ortools==9.7.2996       # Constraint programming solver
- pytest==7.4.3           # Testing framework
- python-dotenv==1.0.0    # Environment variable management


STATUS
======

✓ Folder structure created
✓ __init__.py files created
✓ Empty starter files created
✓ requirements.txt configured
✗ Logic implementation - TO DO


NOTES
=====

- All files are created as placeholders with class/function stubs
- No business logic has been implemented yet
- Run setup_structure.py or init.py to create all directories and files
- The app.py includes setup_folders() that can auto-create directories on import
