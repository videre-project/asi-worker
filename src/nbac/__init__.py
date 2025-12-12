"""NBAC: Naive Bayes Archetype Classification."""

from .archetypes import *
from .binary import *
from .model import *
from .score import *
from .train import *

# The postgres module is optional at runtime.
try:
  from .postgres import *
except ImportError:
  import warnings
  warnings.warn("The 'psycopg2-binary' package is not installed. "
                "The 'nbac.postgres' module will not be available.",
                ImportWarning)
