"""
Financial Calculator Service (Frontend Compatibility Layer).
Re-exports pure calculation functions from the decoupled backend domain service
(backend.services.financial_calculator) to preserve 100% backward compatibility with app.py.
"""

import sys
import os

# Ensure src is on sys.path if invoked directly from frontend directory
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from backend.services.financial_calculator import (
    calculate_category_totals,
    calculate_503020_percentages,
    calculate_annual_metrics,
    get_monthly_needs_budget,
)

__all__ = [
    "calculate_category_totals",
    "calculate_503020_percentages",
    "calculate_annual_metrics",
    "get_monthly_needs_budget",
]
