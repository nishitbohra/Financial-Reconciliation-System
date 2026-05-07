# conftest.py — ensures project root is on sys.path for all tests
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
