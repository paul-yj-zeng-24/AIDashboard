"""
The tools package. Each module defines tools with the @tool decorator, and a
decorator only runs when its module is imported, so this file imports every
tool module once. To add a tool file: create it, then add it to the line below.
"""
from app.tools import clock, weather  # noqa: F401
