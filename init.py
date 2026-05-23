#!/usr/bin/env python
"""Initialize project structure"""
import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Import and run setup
from setup_structure import create_structure

if __name__ == "__main__":
    create_structure()

