"""Streamlit UI for the pouch-cell tool.

Launch with ``python -m pouch_cell --ui`` (or ``streamlit run pouch_cell/ui/app.py``).

Pages
-----
* ``app.py`` -- overview / status.
* ``pages/1_Model_and_Run.py`` -- model, mesh, thermal, parameter set, solver.
* ``pages/2_Design.py`` -- cell geometry + auto-sizing + chemistry overrides.
* ``pages/3_Thermal.py`` -- cooling, heat pipe, thermal-map preview, overrides.
* ``pages/4_Protocols.py`` -- discharge / charge / multi-step protocol.
* ``pages/5_Results.py`` -- metrics, per-step maps, V/T CSV, saved-run review.
* ``pages/6_History.py`` -- in-session + persistent JSONL run history.
* ``pages/7_Help.py`` -- per-tab reference generated from the registry.

Long solves run in a subprocess (:mod:`pouch_cell.ui.worker`) so the UI stays
responsive and a run can be cancelled.
"""
