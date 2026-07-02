import os
import json
import logging
from typing import Any, Dict

def save_to_json(data: Dict[str, Any], file_path: str = "schedule_state.json") -> None:
    """
    Save a dictionary to a JSON file.

    Args:
        data (Dict[str, Any]): The data to save.
        file_path (str): The path to the JSON file.
    """
    serialized = {}
    try:
        for k, v in data.items():
            subserialized = {}
            if isinstance(v, dict):
                for subk, subv in v.items():
                    if isinstance(subk, tuple):
                        # Converts (10, 20) to "10,20"
                        str_subkey = f"{','.join(map(str, subk))}"
                        subserialized[str_subkey] = subv
                    else:
                        subserialized[subk] = subv
                serialized[k] = subserialized
            else:
                serialized[k] = v
        with open(f"./src/storage/{file_path}", 'w') as json_file:
            json.dump(serialized, json_file, indent=4)
    except Exception as e:
        logging.error("Failed to save session state to JSON")
        raise e

def load_from_json(file_path: str = "schedule_state.json") -> Dict[str, Any]:
    """
    Load the saved schedule state from a JSON file.

    Args:
        file_path (str): The path to the JSON file.

    Returns:
        Dict[str, Any]: The loaded data.
    """
    try:
        with open(f"./src/storage/{file_path}", 'r') as json_file:
            data = json.load(json_file)
        
        original_data = {}
        for k, v in data.items():
            suboriginal = {}
            if isinstance(v, dict):
                for subk, subv in v.items():
                    if isinstance(subk, str) and ',' in subk:
                        # Converts "10,20" back to (10, 20)
                        tuple_subkey = tuple(map(int, subk.split(',')))
                        suboriginal[tuple_subkey] = subv
                    else:
                        suboriginal[subk] = subv
                original_data[k] = suboriginal
            else:
                original_data[k] = v
        return original_data
    except Exception as e:
        logging.warning(f"File {file_path} not found. Returning empty dictionary.")
        raise FileNotFoundError(f"File {file_path} not found.")

def delete_json_file(file_path: str = "schedule_state.json") -> None:
    """
    Delete the specified JSON file.

    Args:
        file_path (str): The path to the JSON file.
    """
    try:
        os.remove(f"./src/storage/{file_path}")
        logging.info(f"Deleted file {file_path}.")
    except FileNotFoundError:
        logging.warning(f"File {file_path} not found. Nothing to delete.")
    except Exception as e:
        logging.error(f"Failed to delete file {file_path}.")
        raise e