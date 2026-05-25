# University Scheduler MVP 📅

A comprehensive university course scheduling system using Google OR-Tools constraint programming to automatically assign courses to rooms and time slots while respecting instructor availability, room capacity, and facility requirements. Designed for Chilean universities with support for multiple session types (lectures, workshops, labs).

## Overview

The University Scheduler MVP is an intelligent constraint-based scheduling solution that optimizes complex scheduling problems across university departments. It uses Google OR-Tools' CP-SAT solver to generate conflict-free schedules while respecting instructor availability, room constraints, course requirements, and time preferences. The system is tailored for Chilean educational institutions with detailed session type categorization.

## Features

- **Multi-Session Scheduling**: Assigns different session types (lectures, workshops, labs) to appropriate time slots and rooms
- **Advanced Constraint Handling**:
  - Professor availability and workload limits
  - Room capacity matching and special requirements
  - Prevent professor double-booking across sessions
  - Session type-specific room requirements (computer labs, workshop spaces, etc.)
  - Time slot conflicts detection
- **Flexible Session Configuration**: Support for lectures (Clases), workshops (Ayudantías), labs (Laboratorios), seminars, and practice sessions
- **Room Requirement Matching**: Automatically matches sessions to rooms with required facilities (projectors, computer labs, equipment)
- **Data Validation**: Comprehensive validation of professor availability, room capacity, and session requirements
- **Web-Based Interface**: Streamlit dashboard for visualization and interaction
- **Excel & CSV Support**: Load course data from multiple file formats
- **Sample Data**: Pre-configured datasets for testing

## Technology Stack

- **Python 3.8+**: Core programming language
- **Streamlit 1.28.1**: Interactive web dashboard
- **Google OR-Tools**: Constraint programming CP-SAT solver
- **Pandas 2.1.3**: Data manipulation and analysis
- **openpyxl**: Excel file handling
- **pytest**: Unit testing framework
- **python-dotenv**: Environment variable management

## Project Structure

```
scheduler-mvp/
├── app.py                          # Main Streamlit application entry point
├── requirements.txt                # Project dependencies
├── README.md                       # This file
├── data/                           # Sample and input data directory
│   └── sample_courses.csv          # Sample course data with session and professor information
├── src/                            # Source code package
│   ├── __init__.py
│   ├── models.py                   # Core data models (Professor, Room, Course, Session, etc.)
│   ├── models/                     # Legacy model files
│   │   └── models.py
│   ├── data/                       # Data loading and validation
│   │   └── loader.py               # CSV and Excel data loader
│   ├── solver/                     # OR-Tools scheduling solver
│   │   ├── __init__.py
│   │   └── scheduler.py            # Core CP-SAT scheduling engine
│   ├── ui/                         # Streamlit UI components
│   │   ├── __init__.py
│   │   ├── dashboard.py            # Main dashboard interface
│   │   └── components.py           # Reusable UI components
│   └── utils/                      # Utility functions
│       ├── __init__.py
│       └── helpers.py              # Helper functions
└── tests/                          # Test suite
    ├── __init__.py
    ├── test_loader.py              # Data loader tests
    ├── test_models.py              # Data model tests
    └── test_solver.py              # Scheduler solver tests
```

### Installation

#### Prerequisites

- Python 3.8 or higher
- pip package manager

#### Setup Steps

1. **Clone or navigate to the project directory**:
   ```bash
   cd scheduler-mvp
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv .venv
   
   # On Windows:
   .venv\Scripts\activate
   
   # On macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

#### Dependencies

Complete dependency list from `requirements.txt`:
```
streamlit==1.28.1       # Web interface framework
pandas==2.1.3           # Data manipulation
openpyxl                # Excel file support
ortools                 # Constraint programming solver
pytest                  # Testing framework
python-dotenv           # Environment variable management
```

## Usage

### Running the Application

Start the Streamlit web interface:

```bash
streamlit run app.py
```

The application will open in your default browser at `http://localhost:8501`

### Running Tests

Execute the test suite using pytest:

```bash
pytest tests/
```

Run tests with verbose output:

```bash
pytest tests/ -v
```

### Working with Data

#### Input Data Format

The scheduler expects course data in Excel or CSV format with the following structure:

**Courses** (`sample_courses.csv` or `.xlsx`):
- `LLAVE Código- sec`: Unique course section identifier (encrypted)
- `CODIGO`: Course code (encrypted)
- `TITULO`: Course name (encrypted)
- `Plan Común`: Curriculum/program level (1-4)
- `Clases`: Number of lectures per week (e.g., 8)
- `Ayudantías`: Number of workshop/recitation sessions per week (e.g., 4)
- `Laboratorios o Talleres`: Number of lab sessions per week (e.g., 0-4)
- `Sala especial`: Special room requirements (e.g., "BIBLIOTECA COMP-01", "CIENCIAS LABORATORIO DE CIENCIAS BÁSICAS")
- `2+1 o 3? (distribución horario de clases)`: Class distribution format (e.g., "2+1", "2+1-separadas", "3-juntas")
- `RUT PROFESOR 1`: ID of primary instructor (encrypted token)
- `RUT PROFESOR 2`: ID of secondary instructor (encrypted token, optional)
- `RUT PROFESOR LABT`: ID of lab/workshop instructor (encrypted token, optional)
- Day-time preferences: `LUNES`, `MARTES`, `MIERCOLES`, `JUEVES`, `VIERNES` with time ranges
  - Format: "08:30-09:20, 10:30-11:20" (comma-separated time ranges per day)
  - Leading zeros optional: "8:30" automatically normalized to "08:30"
  - Maps to ACADEMIC_BLOCKS indices (0-12)

#### Data Models

The system uses immutable dataclasses for consistent OR-Tools indexing:

**Core Entities:**
- **Professor**: Instructor with RUT, name, max hours/week, and unavailable time slots
- **Room**: Physical classroom with capacity, building location, and special requirements
- **Course**: Academic course definition with code and prerequisites
- **CourseSection**: Specific section of a course (A, B, etc.) with enrolled students and assigned professors
- **Session**: Schedulable activity (lecture, workshop, lab) with required duration and professor
- **TimeSlot**: Day and time with duration (45-480 minutes)
- **ScheduleAssignment**: Solver output mapping session to room, time, and professor

**Session Types:**
- `Clases` (Lectures)
- `Ayudantías` (Workshops/Recitations)
- `Laboratorios o Talleres` (Laboratories)

## Architecture

### Core Components

#### Models Module (`src/models.py`) - Chilean Academic Calendar
Implements immutable frozen dataclasses for OR-Tools CP-SAT constraint programming:

**Enumerations:**
- **DayOfWeek**: LUNES, MARTES, MIERCOLES, JUEVES, VIERNES
- **SessionType**: CLASE, AYUDANTIA, LABORATORIO

**Time Block System (13-Block Daily Matrix 08:30-21:20):**
- Blocks 0-12 with 50-minute duration + 10-minute breaks
- ACADEMIC_BLOCKS: Pre-defined dictionary with all blocks

**Core Dataclasses (Frozen & Hashable):**
- **TimeSlot**: (day, block_index) - immutable, hashable for OR-Tools indexing
- **CourseSection**: Complete section definition with 13 attributes (section_key, course_code, title, plan_comun_level, required_clases, required_ayudantias, required_laboratorios, professor RUTs, special_room, class_distribution, allowed_slots)

**Institutional Constraints (GlobalTimeConstraints):**
1. Tuesday/Wednesday 17:30-20:20 (Blocks 9-11): Forbidden for all session types
2. Friday 10:30-12:20 (Blocks 2-3): Forbidden for all session types
3. Before 12:30 (Blocks 0-3): Forbidden for Ayudantías only

**Validation Methods:**
- `is_slot_globally_invalid()`: Check slot against all rules (O(1) via frozensets)
- `get_valid_slots_for_session()`: Generate valid TimeSlots for session type
- `validate_slot_constraints()`: Comprehensive validation (global + professor availability)

**Utility Functions:**
- `parse_class_distribution()`: Parse "2+1" format strings
- `create_professor_available_slots()`: Convert availability dict to TimeSlots

#### Data Module (`src/data/`)
Handles data loading and validation:
- **loader.py**: Robust data ingestion engine for course sections
  - `parse_availability_string()`: Parses day availability strings with leading-zero handling (e.g., "8:30-9:20" → "08:30-09:20")
  - `load_course_sections()`: Reads Excel/CSV files and constructs CourseSection objects with validated time slots
  - Blind Optimization pattern: Encrypted RUT professor identifiers passed as-is without decryption
  - Defensive error handling with non-identifiable warnings
  - Successfully loads 56+ course sections with complex availability constraints

#### Solver Module (`src/solver/`)
Core scheduling engine:
- **scheduler.py**: Implements Google OR-Tools CP-SAT constraint satisfaction solver

#### UI Module (`src/ui/`)
Streamlit interface components:
- **dashboard.py**: Main schedule visualization and interaction
- **components.py**: Reusable UI elements

#### Utils Module (`src/utils/`)
Helper functions:
- **helpers.py**: Common utility functions for data transformation and formatting

## Scheduling Algorithm

The system uses Google OR-Tools' CP-SAT (Constraint Programming - Satisfiability) solver to solve the course scheduling problem as a constraint satisfaction problem (CSP).

### Problem Formulation

1. **Decision Variables**: For each session, which room and time slot should it be assigned to?
2. **Constraints**: Professor availability, room capacity, time conflicts, facility requirements
3. **Objective**: Minimize unscheduled sessions and constraint violations

### Key Constraints

- **No Double-Booking**: No professor teaches multiple sessions simultaneously
- **Room Capacity**: Room must fit the session's student count
- **Time Availability**: Both professor and room must be available at assigned time
- **Special Requirements**: Sessions requiring labs only assigned to equipped rooms
- **Duration Matching**: Session duration fits within available time slot
- **Facility Matching**: Room must have required equipment/facilities
- **Load Balancing**: Respect maximum teaching hours per professor per week

### Solver Output

The solver generates `ScheduleAssignment` objects mapping each session to:
- Assigned room
- Assigned time slot
- Assigned professor (may differ if substitutions needed)

## Sample Data

The project includes sample course data:

**`data/sample_courses.csv`**: Contains Chilean university course data including:
- Course identifier, code, and title
- Session requirements (lectures, workshops, labs)
- Student capacity and sections
- Professor assignments (RUT identifiers)
- Time slot preferences by day of week
- Special room requirements

This sample data is formatted for Chilean educational institutions and demonstrates the complete scheduling data model.

## Development Guide

### Project Layout

- **models.py**: Core immutable data models for all entities
- **data/**: Data loading and validation modules
- **solver/**: OR-Tools constraint programming solver
- **ui/**: Streamlit web interface
- **utils/**: Helper functions
- **tests/**: Test suite with pytest

### Adding a New Feature

1. **Create a new file** in the appropriate module directory
2. **Implement functionality** following existing patterns (immutable dataclasses for models)
3. **Write tests** in the tests directory
4. **Update imports** in `__init__.py` files
5. **Document changes** in this README

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/test_solver.py -v

# Run with coverage report
pytest --cov=src tests/
```

## Dependencies

See `requirements.txt` for complete list:

```
streamlit==1.28.1       # Web interface framework
pandas==2.1.3           # Data manipulation
openpyxl                # Excel file support
ortools                 # Constraint programming solver
pytest                  # Testing framework
python-dotenv           # Environment variable management
```

## Troubleshooting

### Issue: "Module not found" errors
**Solution**: Ensure all dependencies are installed:
```bash
pip install -r requirements.txt
```

### Issue: "Invalid time slot" errors
**Solution**: Time slots must be valid (start_hour 0-23, duration 45-480 minutes)

### Issue: Streamlit port already in use
**Solution**: Specify a different port:
```bash
streamlit run app.py --server.port 8502
```


## Future Enhancements

- [ ] Multi-objective optimization (Allow some restrictions to be bypassed)
- [ ] Real-time conflict resolution and rescheduling
- [ ] Export to calendar formats (Excell and csv)
- [ ] Machine learning for prediction of scheduling conflicts


## API Documentation

### Core Models - Chilean Academic Calendar

```python
from src.models import (
    DayOfWeek, SessionType, TimeSlot, CourseSection, 
    GlobalTimeConstraints, ACADEMIC_BLOCKS,
    create_professor_available_slots, parse_class_distribution
)

# Create a time slot (day + block index)
slot = TimeSlot(DayOfWeek.LUNES, 5)  # Monday, Block 5 (13:30-14:20)
print(slot.block_times)  # TimeBlock(5, "13:30", "14:20")

# Create a course section with professor availability
prof_availability = {
    DayOfWeek.LUNES: frozenset([0, 1, 2, 3, 4, 5, 6, 7, 8]),
    DayOfWeek.MARTES: frozenset([0, 1, 2, 3, 4, 5, 6, 7, 8]),
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

# Validate slots against institutional rules
is_invalid = GlobalTimeConstraints.is_slot_globally_invalid(
    TimeSlot(DayOfWeek.MARTES, 9), SessionType.CLASE
)
# True - Tuesday 17:30 is forbidden for all classes

# Get all valid slots for a session type
valid_ayudantia_slots = GlobalTimeConstraints.get_valid_slots_for_session(
    SessionType.AYUDANTIA
)

# Comprehensive validation
is_valid, reason = GlobalTimeConstraints.validate_slot_constraints(
    slot, SessionType.CLASE, allowed_slots
)
```

**13-Block Academic Schedule:**
- Block 0: 08:30-09:20 | Block 1: 09:30-10:20 | Block 2: 10:30-11:20
- Block 3: 11:30-12:20 | Block 4: 12:30-13:20 | Block 5: 13:30-14:20
- Block 6: 14:30-15:20 | Block 7: 15:30-16:20 | Block 8: 16:30-17:20
- Block 9: 17:30-18:20 | Block 10: 18:30-19:20 | Block 11: 19:30-20:20
- Block 12: 20:30-21:20

### Data Loader

The data loader module provides robust ingestion of course section data with advanced time-slot parsing:

```python
from src.data.loader import load_course_sections

# Load courses from Excel or CSV file
courses = load_course_sections('data/sample_courses.xlsx')

# Each CourseSection contains:
# - section_key: Unique identifier (encrypted in Blind Optimization pattern)
# - course_code, title: Course information (encrypted)
# - plan_comun_level: Curriculum level (1-4)
# - required_clases, required_ayudantias, required_laboratorios: Session counts
# - professor_1_rut, professor_2_rut, lab_professor_rut: Encrypted professor IDs (passed as-is)
# - special_room: Required facility (e.g., "BIBLIOTECA COMP-01")
# - class_distribution: Format string (e.g., "2+1", "2+1-separadas", "3-juntas")
# - allowed_slots: Frozenset of TimeSlot objects representing professor availability

for section in courses:
    print(f"Section: {section.section_key}")
    print(f"Requirements: {section.required_clases} classes, "
          f"{section.required_ayudantias} workshops, "
          f"{section.required_laboratorios} labs")
    print(f"Available slots: {len(section.allowed_slots)}")
```

**Data Privacy - Blind Optimization Pattern:**
The loader implements a "Blind Optimization" design where encrypted identifiers (RUT tokens, course codes, titles) are treated as opaque structural keys. No decryption is performed—tokens are passed directly to the solver, ensuring strict data privacy against external LLM tracking.

**Time-Slot Parsing Features:**
- Handles leading-zero normalization (e.g., "8:30" → "08:30")
- Parses day availability strings with time ranges (e.g., "10:30-12:20")
- Maps times to ACADEMIC_BLOCKS using both start and end time matching
- Supports day-of-week columns: LUNES, MARTES, MIERCOLES, JUEVES, VIERNES
- Defensive error handling with non-identifiable logging
- Successfully loads 56+ course sections from real sample data

### Scheduler

```python
from src.solver.scheduler import UniversityScheduler

scheduler = UniversityScheduler()
schedule = scheduler.solve(courses, instructors, rooms)
```

## Testing

The project includes a pytest-based test suite:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_loader.py -v

# Run with coverage report
pytest --cov=src tests/
```


## Contributing

To contribute to this project:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request


## Changelog

### Version 0.1.0 (Current MVP)

**Latest Updates (2026-05-25):**
- ✅ **Data Ingestion Engine** (`src/data/loader.py`):
  - Implemented robust time-slot string parsing with leading-zero handling
  - `parse_availability_string()`: Converts day availability strings to block indices (e.g., "10:30-12:20" → blocks [2,3])
  - `load_course_sections()`: Reads Excel/CSV files and constructs CourseSection objects with validated time slots
  - Blind Optimization pattern: Encrypted RUT professor identifiers preserved as-is (no decryption)
  - Defensive error handling with non-identifiable warnings
  - Tested with 56 real course sections from sample data

**Bug Fixes:**
- Fixed time-slot matching to handle both start times (e.g., "08:30") and end times (e.g., "09:20")
  - Previous behavior: Failed to match end times, resulting in 0 allowed slots per section
  - Fixed behavior: Now correctly maps time ranges to consecutive block indices
  - Result: All 56 sections now have 3-55 valid time slots depending on availability

**Earlier Implementation (2026-05-24):**
- Initial MVP release with core scheduling functionality
- CP-SAT based constraint programming solver
- Support for multiple session types (lectures, workshops, labs)
- Professor availability and room capacity constraints
- Streamlit web interface foundation
- Sample Chilean university course data
- Comprehensive data models with immutable dataclasses
  - DayOfWeek, SessionType, TimeBlock, TimeSlot, CourseSection
  - GlobalTimeConstraints for institutional rules
  - ACADEMIC_BLOCKS: 13-block daily matrix (08:30-21:20)
- Unit test framework

## Authors

- **Development Team**: IAA Project Team (Grupo 14)
- **Project**: University Course Scheduling with Constraint Programming

---

**Status**: ⚠️ In Development (MVP Phase)  
**Last Updated**: 2026-05-25  
**Version**: 0.1.0 (Data Loader Complete)  
**Repository**: Mstrucco/Proyect_IAA_G14
