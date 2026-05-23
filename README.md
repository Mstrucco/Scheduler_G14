# University Scheduling MVP

A constraint programming solution for university course scheduling using Python, Streamlit, and OR-Tools.

## Architecture

```
scheduler-mvp/
├── src/
│   ├── data/           # CSV/Excel loading and validation
│   ├── models/         # Data models (Course, Instructor, Room, Schedule)
│   ├── solver/         # OR-Tools constraint solver
│   ├── ui/             # Streamlit dashboard and components
│   └── utils/          # Helper functions
├── tests/              # Unit tests
├── data/               # Sample data files
├── app.py              # Main Streamlit entry point
└── requirements.txt    # Python dependencies
```

## Installation

1. Create a virtual environment:
```bash
python -m venv venv
```

2. Activate the virtual environment:
- Windows: `venv\Scripts\activate`
- macOS/Linux: `source venv/bin/activate`

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Application

```bash
streamlit run app.py
```

## Development

Run tests with:
```bash
pytest tests/
```

## Dependencies

- **Streamlit**: Web UI framework
- **Pandas**: Data manipulation and analysis
- **OR-Tools**: Constraint programming solver
- **OpenPyXL**: Excel file support
- **Pytest**: Testing framework

## Status

Initial project structure - implementation in progress.
