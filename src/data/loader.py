"""
Data ingestion and tokenization engine for the university scheduling system.

Implements a "Blind Optimization" design pattern where the solver works entirely
with pre-encrypted string identifiers from the source data. No decryption logic
is performed here; encrypted strings (especially in "RUT" columns) are treated
as absolute, unique structural keys.

Key Components:
- parse_availability_string: Robust time slot string parsing with leading zero handling
- load_course_sections: Excel/CSV ingestion with defensive error handling
- create_professor_available_slots: Converts parsed blocks to TimeSlot objects
"""

import logging
from pathlib import Path
from typing import Dict, Set, Optional, List
import pandas as pd
import math
import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

from ..models.models import (
    ACADEMIC_BLOCKS,
    DayOfWeek,
    TimeSlot,
    CourseSection,
    create_professor_available_slots,
)

# Configure logging for non-identifiable warnings
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# ENCRYPTION MANAGEMENT
# ============================================================================

load_dotenv()  # Load EncryptionKey from .env if present

def _get_rut_cipher() -> Optional[Fernet]:
    """Build the Fernet cipher used to encrypt professor RUTs for anonymization.

    The key lives in the gitignored .env file as EncryptionKey. If it is missing
    or invalid we return None, and RUTs fall back to their raw stored token
    rather than crashing the app (e.g. on a fresh clone without a .env)."""
    key = os.getenv("EncryptionKey")
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except Exception:
        return None

def _encrypt_rut(cipher: Optional[Fernet], value) -> Optional[str]:
    """Encrypt a professor RUT for anonymization. Falls back to the raw value for
    placeholders (e.g. UNKNOWN_PROF_1) or when the key is unavailable/invalid."""
    if value is None:
        return None
    if cipher is None:
        return value
    try:
        return cipher.encrypt(str(value).encode()).decode()
    except Exception:
        return value

# ============================================================================
# TIME SLOT PARSING
# ============================================================================

def parse_availability_string(day_str: str) -> Set[int]:
    """
    Parse a day's availability string into a set of block indices.
    
    Handles:
    - Whitespace stripping
    - Trailing period removal (e.g., "17:30-18:20." -> "17:30-18:20")
    - Comma-separated time ranges
    - Missing leading zeros (e.g., "8:30" -> "08:30")
    
    Args:
        day_str: Availability string like "8:30-9:20, 10:30-11:20." or NaN
    
    Returns:
        Set of integer block indices (0-12), empty set if NaN/blank
    
    Raises:
        ValueError: If time format cannot be parsed after normalization
    """
    # Handle NaN or blank input
    if pd.isna(day_str) or not day_str:
        return set()
    
    if isinstance(day_str, float):
        return set()
    
    # Clean the input: strip whitespace and remove trailing periods
    cleaned = str(day_str).strip().rstrip(".")
    
    if not cleaned:
        return set()
    
    block_indices = set()
    
    # Split by commas to get individual time ranges
    time_ranges = cleaned.split(",")
    
    for time_range in time_ranges:
        time_range = time_range.strip()
        if not time_range:
            continue
        
        # Parse "start_time-end_time" format
        if "-" not in time_range:
            logger.warning(f"Skipping malformed time range (no dash): '{time_range}'")
            continue
        
        try:
            start_str, end_str = time_range.split("-", 1)
            start_str = start_str.strip()
            end_str = end_str.strip()
            
            # Normalize start time: add leading zero if needed
            start_normalized = _normalize_time(start_str)
            
            # Find matching start block
            start_block = _find_block_by_time(start_normalized)
            if start_block is None:
                logger.warning(
                    f"Could not match start time '{start_str}' "
                    f"(normalized: '{start_normalized}') to ACADEMIC_BLOCKS"
                )
                continue
            
            # Normalize and find end time to determine the last block in the range
            end_normalized = _normalize_time(end_str)
            end_block = _find_block_by_time(end_normalized)
            if end_block is None:
                logger.warning(
                    f"Could not match end time '{end_str}' "
                    f"(normalized: '{end_normalized}') to ACADEMIC_BLOCKS"
                )
                continue
            
            # The end_block could be the block that ENDS at that time, or STARTS at that time
            # If it's the end time of a block, use that block; otherwise, use the previous block
            # This handles "8:30-9:20" correctly: start=block 0, end=block 0 (which ends at 09:20)
            # and "8:30-10:30" correctly: start=block 0, end=block 1 (which ends at 10:20)
            
            # Check if end_normalized is a start time or end time
            is_end_time = end_normalized != ACADEMIC_BLOCKS[end_block].start_time
            
            # Add all blocks from start_block to end_block (inclusive)
            if start_block <= end_block:
                block_indices.update(range(start_block, end_block + 1))
            else:
                logger.warning(
                    f"End block ({end_block}) is before start block ({start_block}) "
                    f"in range '{time_range}'"
                )
        
        except Exception as e:
            logger.warning(f"Error parsing time range '{time_range}': {e}")
            continue
    
    return block_indices


def _normalize_time(time_str: str) -> str:
    """
    Normalize time string to HH:MM format by adding leading zero if needed.
    
    Args:
        time_str: Time string like "8:30" or "08:30"
    
    Returns:
        Normalized time string like "08:30"
    """
    time_str = time_str.strip()
    
    if ":" not in time_str:
        raise ValueError(f"Invalid time format (no colon): '{time_str}'")
    
    parts = time_str.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format (too many colons): '{time_str}'")
    
    hour, minute = parts
    hour = hour.strip().zfill(2)
    minute = minute.strip().zfill(2)
    
    return f"{hour}:{minute}"


def _find_block_by_time(time_str: str) -> Optional[int]:
    """
    Find the block index for a given time string by matching against ACADEMIC_BLOCKS.
    Matches both start_time (e.g., "08:30") and end_time (e.g., "09:20") patterns.
    
    Args:
        time_str: Time in HH:MM format (e.g., "08:30" or "09:20")
    
    Returns:
        Block index (0-12) or None if not found
    """
    for block_idx, block in ACADEMIC_BLOCKS.items():
        if block.start_time == time_str or block.end_time == time_str:
            return block_idx
    return None


# ============================================================================
# COURSE SECTION LOADER
# ============================================================================

def load_course_sections(file_path: str) -> List[CourseSection]:
    """
    Load course sections from Excel or CSV file.
    
    Expected columns (case-sensitive):
    - LLAVE Código- sec: Unique section identifier
    - CODIGO: Course code
    - TITULO: Course title
    - Plan Común: Academic level (1, 2, 3, etc.)
    - Clases: Number of class blocks per week
    - Ayudantías: Number of workshop blocks per week
    - Laboratorios o Talleres: Number of lab blocks per week
    - Sala especial: Special room requirement (optional)
    - 2+1 o 3? (distribución horario de clases): Class distribution format
    - LUNES, MARTES, MIERCOLES, JUEVES, VIERNES: Availability strings for each day
    - RUT PROFESOR 1: Main professor encrypted identifier
    - RUT PROFESOR 2: Secondary professor encrypted identifier (optional)
    - RUT PROFESOR LABT: Lab professor encrypted identifier (optional)
    
    Args:
        file_path: Path to Excel or CSV file
    
    Returns:
        List of CourseSection objects
    
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If required columns are missing or data is malformed
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"Data file not found: {file_path}")
    
    # Read file based on extension
    if file_path.suffix.lower() == ".csv":
        df = pd.read_csv(file_path)
    elif file_path.suffix.lower() in [".xlsx", ".xls"]:
        df = pd.read_excel(file_path)
        try:
            profs = pd.read_excel(file_path, sheet_name="PROFESORES")
        except ValueError:
            logger.warning("Sheet 'PROFESORES' not found in the Excel file.")
    else:
        raise ValueError(f"Unsupported file format: {file_path.suffix}")
    
    # Validate required columns
    required_columns = {
        "LLAVE Código- sec",
        "CODIGO",
        "TITULO",
        "Plan Común",
        "Clases",
        "Ayudantías",
        "Laboratorios o Talleres",
        "Sala especial",
        "2+1 o 3? (distribución horario de clases)",
        "LUNES",
        "MARTES",
        "MIERCOLES",
        "JUEVES",
        "VIERNES",
        "RUT PROFESOR 1",
        "RUT PROFESOR 2",
        "RUT PROFESOR LABT",
    }
    
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")
    
    course_sections = []

    if 'profs' in locals():
        # Cleaning of the raw Master File to ensure that only valid Plan Común courses are processed
        df = df.dropna(subset=["Plan Común"])

        full = '10:30-11:20,11:30-12:20,12:30-13:20,13:30-14:20,14:30-15:20,15:30-16:20,16:30-17:20'
        days = ['LUNES', 'MARTES', 'MIERCOLES', 'JUEVES', 'VIERNES']
        prof_j = profs[profs['TIPO DE PROFESOR 1'] == 'JORNADA']
        rut_prof_jornada = prof_j['RUT PROFESOR 1']

        df.loc[df['RUT PROFESOR 1'].isin(rut_prof_jornada), days] = full
        df['Plan Común'] = pd.to_numeric(df['Plan Común'], errors='coerce').fillna(0)
        df = df[(df['Plan Común'] > 0) & (df['Plan Común'] < 5)]
    
    # Iterate through records with defensive error handling
    for idx, row in df.iterrows():
        try:
            # Extract and validate basic fields
            section_key = str(row["LLAVE Código- sec"]).strip()
            course_code = str(row["CODIGO"]).strip()
            title = str(row["TITULO"]).strip()
            
            if not section_key or section_key == "nan":
                logger.warning(f"Row {idx}: Skipping section with empty section_key")
                continue
            
            if not course_code or course_code == "nan":
                logger.warning(f"Row {idx}: Skipping section with empty course_code")
                continue
            
            if not title or title == "nan":
                logger.warning(f"Row {idx}: Skipping section with empty title")
                continue
            
            # Parse numeric fields
            try:
                plan_comun_level = int(row["Plan Común"])
            except (ValueError, TypeError):
                logger.warning(f"Row {idx} ({section_key}): Invalid Plan Común value, using 0")
                plan_comun_level = 0
            
            try:
                required_clases = int(row["Clases"])
            except (ValueError, TypeError):
                required_clases = 0
            
            try:
                required_ayudantias = int(row["Ayudantías"])
            except (ValueError, TypeError):
                required_ayudantias = 0
            
            try:
                required_laboratorios = int(row["Laboratorios o Talleres"])
            except (ValueError, TypeError):
                required_laboratorios = 0
            
            # Extract optional fields
            special_room = _extract_optional_field(row["Sala especial"])
            class_distribution = _extract_optional_field(
                row["2+1 o 3? (distribución horario de clases)"]
            )
            
            # RUT identifiers arrive pre-encrypted in the source file and are
            # passed through untouched. They serve as opaque unique keys for the
            # solver; the UI decrypts them for display (see serialize_sections).
            cipher = _get_rut_cipher()
            professor_1_rut = str(row["RUT PROFESOR 1"]).strip()
            if not professor_1_rut or professor_1_rut == "nan":
                logger.warning(f"Row {idx} ({section_key}): Missing RUT PROFESOR 1")
                professor_1_rut = "UNKNOWN_PROF_1"
            else:
                professor_1_rut = _encrypt_rut(cipher, professor_1_rut)

            professor_2_rut = _extract_optional_field(row["RUT PROFESOR 2"])
            if professor_2_rut:
                professor_2_rut = _encrypt_rut(cipher, professor_2_rut)
            lab_professor_rut = _extract_optional_field(row["RUT PROFESOR LABT"])
            if lab_professor_rut:
                lab_professor_rut = _encrypt_rut(cipher, lab_professor_rut)
            
            # Parse availability for each day
            availability_dict = {}
            
            for day_name, day_enum in [
                ("LUNES", DayOfWeek.LUNES),
                ("MARTES", DayOfWeek.MARTES),
                ("MIERCOLES", DayOfWeek.MIERCOLES),
                ("JUEVES", DayOfWeek.JUEVES),
                ("VIERNES", DayOfWeek.VIERNES),
            ]:
                block_indices = parse_availability_string(row[day_name])
                if block_indices:
                    availability_dict[day_enum] = frozenset(block_indices)
            
            # Create TimeSlot frozenset using the helper function
            allowed_slots = create_professor_available_slots(availability_dict)
            
            # Construct CourseSection object
            section = CourseSection(
                section_key=section_key,
                course_code=course_code,
                title=title,
                plan_comun_level=plan_comun_level,
                required_clases=required_clases,
                required_ayudantias=required_ayudantias,
                required_laboratorios=required_laboratorios,
                professor_1_rut=professor_1_rut,
                professor_2_rut=professor_2_rut,
                lab_professor_rut=lab_professor_rut,
                special_room=special_room,
                class_distribution=class_distribution,
                allowed_slots=allowed_slots,
            )
            
            course_sections.append(section)
        
        except ValueError as e:
            logger.warning(f"Row {idx}: Validation error - {e}")
            continue
        except Exception as e:
            logger.warning(f"Row {idx}: Unexpected error during row processing - {e}")
            continue
    
    return course_sections


def _extract_optional_field(value) -> Optional[str]:
    """
    Extract optional string field, returning None if empty/NaN.
    
    Args:
        value: Field value from DataFrame
    
    Returns:
        Stripped string or None
    """
    if pd.isna(value):
        return None
    
    value_str = str(value).strip()
    if not value_str or value_str == "nan":
        return None
    
    return value_str


# ============================================================================
# EXECUTABLE TEST BLOCK
# ============================================================================
