"""Demand-driven planogram engine.

Estimates, per item at each managed-shelf location, the *unconstrained* monthly
demand ceiling — correcting for the fact that observed sales are censored by
whatever stock happened to be on the shelf — and turns it into a 12-month
seasonal "AI Suggested Planogram" profile.

See engine.py for the algorithm and the design notes at the top of that file.
"""
from .engine import compute_ai_planograms, build_panel  # noqa: F401
