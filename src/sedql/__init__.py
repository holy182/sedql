"""SEDQL - Semantic Entity Query Layer

A semantic layer for AI to understand your database.
"""

__version__ = "0.2.0"
__author__ = "Brijesh Chettri"

from .core.semantic_layer_generator import SemanticLayerGenerator
from .rules.engine import RulesEngine

__all__ = ["SemanticLayerGenerator", "RulesEngine"]
