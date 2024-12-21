## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""A simple Python package for computing ASI scores for decklists."""

from .archetypes import *
from .bigrams import *

# The postgres module is optional and may not be available at runtime.
try:
  from .postgres import *
except ImportError:
  import warnings
  warnings.warn("The 'psycopg2-binary' package is not installed. "
                "The 'asi.postgres' module will not be available.",
                ImportWarning)
