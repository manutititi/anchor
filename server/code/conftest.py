"""
Pytest configuration for server/code tests.
Run from server/code/:  python -m pytest tests/ -v --rootdir=.
"""
import os
import sys

# Ensure server/code is on the import path so test modules can
# import from vpn/, auth/, vault/, etc. without installing the package.
sys.path.insert(0, os.path.dirname(__file__))
