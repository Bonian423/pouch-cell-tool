"""Streamlit UI for the pouch-cell tool.

Launch with ``python -m pouch_cell --ui`` (or ``streamlit run pouch_cell/ui/app.py``).

Pages
-----
* ``app.py`` -- overview / status.
* ``pages/1_Design.py`` -- cell geometry + auto-sizing.
* ``pages/2_Model_and_Run.py`` -- model, mesh, SOC, C-rate, duration...
* ``pages/3_Thermal.py`` -- cooling, ambient, heat pipe, per-face h.
* ``pages/4_Results.py`` -- metrics + figures of the last run.
* ``pages/5_History.py`` -- run history comparison table + CSV export.

Long solves run in a subprocess (:mod:`pouch_cell.ui.worker`) so the UI stays
responsive and a run can be cancelled.
"""
