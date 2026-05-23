"""
Main Streamlit application entry point
"""

import os
import streamlit as st

# Create folder structure on startup
def setup_folders():
    """Create necessary folder structure"""
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    dirs = [
        os.path.join(base_path, "src"),
        os.path.join(base_path, "src", "data"),
        os.path.join(base_path, "src", "models"),
        os.path.join(base_path, "src", "solver"),
        os.path.join(base_path, "src", "ui"),
        os.path.join(base_path, "src", "utils"),
        os.path.join(base_path, "tests"),
        os.path.join(base_path, "data"),
    ]
    
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)
    
    # Create __init__.py files
    init_files = {
        os.path.join(base_path, "src", "__init__.py"): "Main src package",
        os.path.join(base_path, "src", "data", "__init__.py"): "Data loading and validation",
        os.path.join(base_path, "src", "models", "__init__.py"): "Data models",
        os.path.join(base_path, "src", "solver", "__init__.py"): "OR-Tools solver",
        os.path.join(base_path, "src", "ui", "__init__.py"): "Streamlit UI",
        os.path.join(base_path, "src", "utils", "__init__.py"): "Utility functions",
        os.path.join(base_path, "tests", "__init__.py"): "Test suite",
    }
    
    for init_file, doc in init_files.items():
        if not os.path.exists(init_file):
            with open(init_file, "w") as f:
                f.write(f'"""\n{doc}\n"""\n')


setup_folders()


def main():
    st.set_page_config(
        page_title="University Scheduler MVP",
        page_icon="📅",
        layout="wide"
    )
    
    st.title("University Scheduler MVP")
    st.write("Coming soon...")


if __name__ == "__main__":
    main()
