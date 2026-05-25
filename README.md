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
│   │   ├── loader.py               # CSV and Excel data loader
│   │   └── validator.py            # Data validation logic
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

**Courses** (`sample_courses.csv`):
- `LLAVE Código-sec`: Unique course section identifier (e.g., ING12011)
- `CODIGO`: Course code (e.g., ING1201)
- `TITULO`: Course name (e.g., Álgebra Lineal)
- `CUPOS`: Student capacity per section
- `SECCIONES`: Number of course sections
- `Plan Común`: Curriculum/program code
- `Clases`: Number of lectures per week
- `Ayudantías`: Number of workshop/recitation sessions per week
- `Laboratorios o Talleres`: Number of lab sessions per week
- `Sala especial`: Special room requirements (if any)
- `Requisitos`: Course prerequisites
- `RUT PROFESOR 1`: ID of primary instructor
- `RUT PROFESOR 2`: ID of secondary instructor (optional)
- `RUT PROFESOR LABT`: ID of lab/workshop instructor (optional)
- Day-time preferences: `LUNES`, `MARTES`, `MIERCOLES`, `JUEVES`, `VIERNES` with preferred time slots

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
- `Seminario` (Seminars)
- `Práctica` (Practice)

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
- **loader.py**: Reads course data from CSV and Excel files
- **validator.py**: Validates data integrity, constraints, and feasibility

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

### Issue: Data validation errors
**Solution**: Verify your data format matches the sample data structure with correct column names and data types

### Issue: Solver timeout
**Solution**: For large instances (500+ courses), the solver may take longer. Increase timeout or split into multiple problems

## Future Enhancements

- [ ] Multi-objective optimization (minimize cost, maximize preferences, load balance)
- [ ] Real-time conflict resolution and rescheduling
- [ ] Integration with university management systems (SIGA, Canvas, etc.)
- [ ] Advanced filtering and search in UI
- [ ] Export to calendar formats (iCalendar, Google Calendar, Outlook)
- [ ] Automated email notifications to professors
- [ ] Performance optimization for very large institutions (1000+ courses)
- [ ] Machine learning for prediction of scheduling conflicts
- [ ] Mobile app for schedule visualization

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

```python
from src.data.loader import DataLoader

loader = DataLoader()
courses = loader.load_courses('data/sample_courses.csv')
```

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

## Performance Considerations

- **Small institutions** (<100 courses): Solution time typically < 1 second
- **Medium institutions** (100-500 courses): Solution time typically 1-10 seconds
- **Large institutions** (500+ courses): May require 30+ seconds or solver optimization
- **Tips for large problems**:
  - Tighten time slot constraints
  - Reduce special facility requirements
  - Split scheduling into multiple departments
  - Increase solver timeout parameter

## Contributing

To contribute to this project:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

[Specify your license here - e.g., MIT, GPL, Apache 2.0]

## Support

For issues or questions:
- Check the troubleshooting section above
- Review sample data format
- Consult Google OR-Tools documentation: https://developers.google.com/optimization

## Changelog

### Version 0.1.0 (Current MVP)
- Initial MVP release with core scheduling functionality
- CP-SAT based constraint programming solver
- Support for multiple session types (lectures, workshops, labs)
- Professor availability and room capacity constraints
- Streamlit web interface foundation
- Sample Chilean university course data
- Comprehensive data models with immutable dataclasses
- Unit test framework

## Authors

- **Development Team**: IAA Project Team (Grupo 14)
- **Project**: University Course Scheduling with Constraint Programming

## Acknowledgments

- Google OR-Tools team for the CP-SAT constraint programming solver
- Streamlit for the interactive web framework
- Pandas for data manipulation
- The Chilean academic community for domain knowledge

---

**Status**: ⚠️ In Development (MVP Phase)  
**Last Updated**: 2026-05-24  
**Version**: 0.1.0  
**Repository**: Mstrucco/Proyect_IAA_G14
