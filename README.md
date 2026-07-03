# University Scheduler

Constraint-based course scheduler for Chilean universities' *Plan Común* (semesters 1–4).
It ingests a course dataset, builds a conflict-free timetable with Google OR-Tools'
CP-SAT solver, and presents an interactive drag-and-drop Streamlit interface for
reviewing and adjusting the result.

Built by **Grupo 14** for the IAA course project.

## Features

- **Automatic scheduling** — CP-SAT assigns Clases, Ayudantías and Laboratorios to a
  13-block × 5-day week, respecting professor availability and institutional time rules.
- **Interactive grid** — drag course blocks between time slots; every move is validated
  and persisted in session state.
- **Six tabs** — one per Plan Común level (1–4), a colour-coded **Master View** that shows
  every semester at once, and a **Validation & Export** tab.
- **Constraint relaxation** — toggle individual rules from the sidebar and re-optimise.
- **Saving and Loading Progress** — Save unfinished progress to a local json file and load
  it to continue working. 
- **Excel export** — one workbook with a sheet per level plus a master sheet.

## Requirements

- Python 3.10 or higher
- Windows, macOS or Linux (the one-click launcher is Windows-only)

Dependencies (`requirements.txt`): `streamlit`, `pandas`, `openpyxl`, `ortools`,
`cryptography`, `python-dotenv`.

## Quick start

### Windows (one click)

Double-click **`iniciar_scheduler.bat`**. On the first run it creates a virtual
environment, installs the dependencies and launches the app; later runs start
immediately. The app opens at <http://localhost:8501>.

### Manual (any OS)

```bash
cd scheduler
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app starts empty — use the sidebar to upload a course file (for example the bundled
`data/sample_courses.xlsx`), then press **Load and Schedule**.

## Professor RUT encryption (`.env`)

Professor RUTs are stored **encrypted** in the source dataset. To display them as readable
RUTs in the grid, the app reads a Fernet key from a local `.env` file:

```
EncryptionKey="<your-fernet-key>"
```

You don't have to create `.env` by hand:

- **`iniciar_scheduler.bat`** prompts for the key on first launch and writes `.env` for you.
- Or copy the committed **`.env.example`** to `.env` and paste the key between the quotes.

`.env` is gitignored, so it is **not** part of a fresh clone (only `.env.example` is). Without a
valid key the app still runs — it simply shows the encrypted token instead of the RUT. This is
light obfuscation, not strong security: anyone with the key and the data can recover the RUTs.

## Input data format

Excel/CSV with one row per course section and these columns:

| Column | Meaning |
|--------|---------|
| `LLAVE Código- sec` | Unique section key |
| `CODIGO` | Course code |
| `TITULO` | Course title |
| `Plan Común` | Semester level (1–4) |
| `Clases` / `Ayudantías` / `Laboratorios o Talleres` | Sessions required per week |
| `Sala especial` | Special room requirement (optional) |
| `2+1 o 3? (distribución horario de clases)` | Class distribution (`2+1`, `3-juntas`, …) |
| `RUT PROFESOR 1` / `2` / `LABT` | Encrypted professor identifiers |
| `LUNES` … `VIERNES` | Availability, e.g. `08:30-09:20, 10:30-11:20` |

Times map to the 13 academic blocks (08:30–21:20); leading zeros are optional
(`8:30` → `08:30`). A sample dataset with 56 sections lives at `data/sample_courses.xlsx`.

## Project structure

```
scheduler_G14/
├── iniciar_scheduler.bat      # Windows one-click launcher
├── app.py                     # entry point (imports src.app.main)
├── requirements.txt
├── .env.example               # template for the RUT decryption key
├── .env                       # RUT decryption key (the .bat creates it, but it 
│                              # must be created manually for first manual start)
└── src/
    ├── app.py                 # Streamlit UI: tabs, sidebar, validation, export
    ├── data/loader.py         # Excel/CSV ingestion + availability parsing
    ├── models/models.py       # DayOfWeek, SessionType, TimeSlot, CourseSection,
    │                          #   GlobalTimeConstraints, ACADEMIC_BLOCKS
    ├── solver/scheduler.py    # CP-SAT model (CourseScheduler)
    ├── storage/saver.py       # Save File handler to save, load or delete
    └── components/dnd_grid/   # custom drag-and-drop Streamlit component
```

## Scheduling constraints

**Global time rules** (`GlobalTimeConstraints`, applied while building the model):

1. Tuesday & Wednesday blocks 9–11 (17:30–20:20) are forbidden — **except** Plan Común 1 and 2.
2. Friday blocks 2–3 (10:30–12:20) are forbidden — **except** Plan Común 1 and 2.
3. Ayudantías cannot use blocks 0–3 (08:30–12:20).

**Structural rules** (CP-SAT):

4. A single-block session must land on Block 4 (12:30–13:20).
5. `3-juntas` courses need three consecutive blocks, restricted to {2,3,4} or {4,5,6}.

**Resource rules** (CP-SAT, hard):

6. No professor teaches two sessions in the same slot.
7. No special room hosts two sessions in the same slot.
8. The same course code is never scheduled twice in one slot (different courses *may* run in parallel).

The objective maximises the number of scheduled blocks. Professor availability from the
dataset further restricts where each section can be placed.

## Constraint relaxation

From the sidebar you can relax rules and press **Regenerate Automated Schedule**;
relaxations apply to all semesters at once:

- **Ignore professor availability** — open blocks 0–8 every day.
- **3-juntas within blocks 1–7** / **any three consecutive blocks** — widen rule 5.
- **Block 4 rule off** — allow single-block sessions in any slot.
- **Ayudantías from block 3 (11:30) onward** / **anytime** — relax rule 3.

## Saving and loading

From the sidebar you can save your progress by pressing **Save Current Schedule**.
You can load your stored progress by pressing **Load Saved Schedule**. This will
delete any unsaved changes. To delete your stored progress, you must press
**Delete Saved Schedule**. This will not erase your loaded schedule.

## How it works

`loader.py` reads the dataset and turns each day's availability string into a set of
`TimeSlot`s. `CourseScheduler` (`scheduler.py`) builds a CP-SAT model — one boolean per
valid section/session/day/block combination — adds the constraints above and maximises the
number of scheduled blocks. `src/app.py` renders the result in the drag-and-drop grid;
edits update a single shared schedule matrix that every tab, including the Master View,
reads from. `saver.py` saves the current state of the schedule as a serialized json 
dictionary and stores it in a file called `schedule_state.json`.

## Authors

**Grupo 14** — Scheduler_G14. Repository: `Mstrucco/Scheduler_G14`.
