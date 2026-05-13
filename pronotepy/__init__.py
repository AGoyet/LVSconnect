"""
An API wrapper for pronote.
"""

__title__ = "pronotepy"
__author__ = "bain, Xiloe"
__license__ = "MIT"
__copyright__ = "Copyright (c) bain, Xiloe"
__version__ = "2.14.4"

import logging

from .clients import ClientBase
from .exceptions import *

def enable_debug_logging(filename: str = "pronotepy_debug.log") -> None:
    """Helper to easily route all pronotepy debug logs to a file."""
    logger = logging.getLogger("pronotepy")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(filename, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
