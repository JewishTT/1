"""Fundamental Intelligence Silo.

Acquisition, extraction, resolution and projection remain implemented by their
existing platform components; this package is their domain ownership boundary.
Downstream domains consume only the shared IntelligenceReadPort contract.
"""

from .ports import IntelligenceReadPort

__all__ = ["IntelligenceReadPort"]
