"""File names a measurement run leaves beside the generated ``model.json``.

Runners write diagnostic evidence into their export directory so a result can be
re-checked later.  The evidence is never part of a profile-library entry, so both
the writer and the profile preparation step resolve the names here instead of
repeating string literals that can drift apart.
"""

from typing import Final

ANALYSER_FILENAME: Final = "analyser.json"
SMART_SWITCH_READINGS_FILENAME: Final = "smart_switch_readings.json"

#: Files a run keeps for re-analysis and diagnostics; allowed beside ``model.json``
#: but never uploaded to the profile library.
MEASUREMENT_EVIDENCE_ARTIFACTS: Final = frozenset({ANALYSER_FILENAME, SMART_SWITCH_READINGS_FILENAME})
