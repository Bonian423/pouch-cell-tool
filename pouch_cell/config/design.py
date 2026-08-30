"""Cell specification for the 3D pouch cell modelling tool.

This module defines :class:`PouchCellSpec`, a plain-data description of the
9 Ah NCM811/graphite pouch cell used throughout the tool.

Architecture
------------
The cell is a **multi-stack pouch cell**: electrode pairs (graphite negative
electrode + separator + NCM811 positive electrode) stacked in the through-plane
direction and connected electrically **in parallel** between two current
collectors.

PyBaMM models a single *representative* unit cell and accounts for the parallel
stacks through the parameter ``Number of electrodes connected in parallel to
make a cell``.  In ``pybamm/parameters/geometric_parameters.py`` the
current-collector cross-sectional area is defined as

    A_cc = L_y * L_z * n_electrodes_parallel

so the applied current density ``I / A_cc`` automatically reflects the parallel
layers carrying equal shares of the total current -- exactly the physics of a
parallel stack.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields

# Design constants ------------------------------------------------------------
COPPER = "Cu"
ALUMINIUM = "Al"
NEGATIVE_ELECTRODE = "graphite"
POSITIVE_ELECTRODE = "NCM811"  # LiNi0.8Co0.1Mn0.1O2
SEPARATOR = "separator (PE/PP)"

FARADAY = 96485.33212  # C/mol


@dataclass
class PouchCellSpec:
    """Design specification of the 9 Ah NCM811/graphite pouch cell.

    All lengths are in metres.  Defaults describe the target cell:

    * footprint **15 cm (z) x 9 cm (y)**, outer thickness **1 cm (x)**
    * **20 electrode pairs** (graphite anode / separator / NCM811 cathode)
    * nominal capacity **9 Ah**

    ``height`` is the pouch dimension along the *z* coordinate and ``width``
    the dimension along *y* (this matches PyBaMM's ``Electrode height [m]`` /
    ``Electrode width [m]`` convention, with tabs on the top edge ``z = height``).
    """

    # --- footprint ---------------------------------------------------------
    height: float = 0.15            # z coordinate  ("Electrode height [m]"),
    width: float = 0.1             # y coordinate  ("Electrode width [m]"),
    thickness_total: float = 0.007   # x, outer pouch thickness, 1 cm (incl. packaging)

    # --- stack -------------------------------------------------------------
    n_stacks: int = 10              # electrode pairs connected in parallel

    # --- representative unit-cell layer thicknesses (m) --------------------
    L_cn: float = 8.0e-6           # negative current collector (Cu)
    L_n: float = 100.0e-6            # negative electrode (graphite)
    L_s: float = 12.0e-6            # separator
    L_p: float = 90.0e-6            # positive electrode (NCM811)
    L_cp: float = 12.0e-6           # positive current collector (Al)

    # --- electrical --------------------------------------------------------
    capacity_Ah: float = 9.0        # nominal cell capacity
    n_series: int = 1               # cells in series in the battery

    # --- chemistry (labels; property values come from the parameter set) ---
    negative_electrode: str = NEGATIVE_ELECTRODE
    positive_electrode: str = POSITIVE_ELECTRODE

    # --- tabs (both on the top edge z = height, split across y) ------------
    tab_width: float = 0.02         # tab width along y
    neg_tab_y_centre: float = 0.02
    pos_tab_y_centre: float = 0.07

    # --- operating conditions ----------------------------------------------
    ambient_temperature_K: float = 298.15
    lower_cutoff_V: float = 2.5
    upper_cutoff_V: float = 4.2

    # --- heat-pipe cooling (optional; applied in 2+1D x-lumped solves) -----
    # A copper heat pipe runs ACROSS THE FULL WIDTH of the cell (along y),
    # right below the top edge (z = height) -- a horizontal band of height
    # heat_pipe_height -- so it sits beside both tabs.  The folded tabs +
    # thermal paste + pipe are lumped into an effective coefficient
    # heat_pipe_h rejecting to heat_pipe_temperature_K.
    heat_pipe_enabled: bool = False
    heat_pipe_height: float = 0.005          # pipe band height below the top edge (0.5 cm)
    heat_pipe_h: float = 2000.0             # effective cell/tab -> pipe coeff (W/m^2/K)
    heat_pipe_temperature_K: float = 288.15  # actively chilled pipe temperature

    # ------------------------------------------------------------------ #
    # Derived geometry
    # ------------------------------------------------------------------ #
    @property
    def footprint_area(self) -> float:
        """Footprint area of one layer (m^2)."""
        return self.height * self.width

    @property
    def total_area(self) -> float:
        """Total active electrode area over all parallel stacks (m^2)."""
        return self.n_stacks * self.footprint_area

    @property
    def active_stack_thickness(self) -> float:
        """Total electrochemically active stack thickness (all pairs)."""
        return self.n_stacks * (self.L_n + self.L_s + self.L_p)

    @property
    def stack_thickness_incl_cc(self) -> float:
        """Estimated full stack thickness incl. shared current collectors (m).

        A ``n_stacks``-pair stack needs ``n_stacks + 1`` current collectors
        (shared between adjacent cells).  We use the mean collector thickness
        for the estimate.
        """
        n_cc = self.n_stacks + 1
        mean_cc = (self.L_cn + self.L_cp) / 2.0
        return self.active_stack_thickness + n_cc * mean_cc

    @property
    def unit_cell_thickness(self) -> float:
        """Thickness of one representative unit cell modelled by PyBaMM (m)."""
        return self.L_cn + self.L_n + self.L_s + self.L_p + self.L_cp

    @property
    def packaging_margin(self) -> float:
        """Outer thickness not accounted for by the active stack (pouch foil etc.)."""
        return max(self.thickness_total - self.stack_thickness_incl_cc, 0.0)

    @property
    def areal_capacity_Ah_m2(self) -> float:
        """Areal capacity over the whole stack (Ah per m^2 of footprint)."""
        return self.capacity_Ah / self.total_area

    @property
    def areal_capacity_mAh_cm2(self) -> float:
        """Areal capacity over the whole stack (mAh per cm^2 of footprint).

        1 Ah/m^2 == 0.1 mAh/cm^2.
        """
        return self.areal_capacity_Ah_m2 * 0.1

    # ------------------------------------------------------------------ #
    # Parameter overrides for PyBaMM
    # ------------------------------------------------------------------ #
    def geometry_overrides(self) -> dict:
        """Return the ``parameter_values.update(...)`` dict for this cell."""
        return {
            # footprint / geometry
            "Electrode height [m]": self.height,
            "Electrode width [m]": self.width,
            # unit-cell layer thicknesses
            "Negative current collector thickness [m]": self.L_cn,
            "Negative electrode thickness [m]": self.L_n,
            "Separator thickness [m]": self.L_s,
            "Positive electrode thickness [m]": self.L_p,
            "Positive current collector thickness [m]": self.L_cp,
            # tabs
            "Negative tab width [m]": self.tab_width,
            "Negative tab centre y-coordinate [m]": self.neg_tab_y_centre,
            "Negative tab centre z-coordinate [m]": self.height,
            "Positive tab width [m]": self.tab_width,
            "Positive tab centre y-coordinate [m]": self.pos_tab_y_centre,
            "Positive tab centre z-coordinate [m]": self.height,
            # stack / electrical
            "Number of electrodes connected in parallel to make a cell": float(
                self.n_stacks
            ),
            "Number of cells connected in series to make a battery": float(
                self.n_series
            ),
            "Nominal cell capacity [A.h]": self.capacity_Ah,
            # voltage limits
            "Lower voltage cut-off [V]": self.lower_cutoff_V,
            "Upper voltage cut-off [V]": self.upper_cutoff_V,
        }

    # ------------------------------------------------------------------ #
    # Capacity sanity checks
    # ------------------------------------------------------------------ #
    def theoretical_layer_capacities(self, param: dict) -> tuple[float, float]:
        """Maximum Li inventory per electrode (Ah), computed from geometry.

        ``param`` must be a processed ``pybamm.ParameterValues`` dictionary-like
        object with the active-material properties for the electrode in question.

        Returns ``(Q_n_max, Q_p_max)`` in Ah, the maximum capacities of the
        negative and positive electrodes of the full-stack cell.
        """
        A = self.total_area
        c_n_max = param["Maximum concentration in negative electrode [mol.m-3]"]
        c_p_max = param["Maximum concentration in positive electrode [mol.m-3]"]
        eps_n = param["Negative electrode active material volume fraction"]
        eps_p = param["Positive electrode active material volume fraction"]
        # coulombic capacity: Q = n * F * A * L * eps_s * c_max / 3600
        Q_n_max = self.n_stacks * self.footprint_area * self.L_n * eps_n * c_n_max * FARADAY / 3600
        Q_p_max = self.n_stacks * self.footprint_area * self.L_p * eps_p * c_p_max * FARADAY / 3600
        return Q_n_max, Q_p_max

    def report(self, param: dict | None = None) -> str:
        """Human-readable summary of the cell design."""
        lines = [
            f"Pouch cell design:  {self.negative_electrode} / {self.positive_electrode}",
            f"  Footprint        : {self.height * 1e2:.0f} cm (z) x {self.width * 1e2:.0f} cm (y)",
            f"  Outer thickness  : {self.thickness_total * 1e3:.1f} mm (1 cm, incl. packaging)",
            f"  Active stack     : {self.active_stack_thickness * 1e3:.1f} mm "
            f"({self.n_stacks} pairs x {self.unit_cell_thickness * 1e6:.1f} um unit cell)",
            f"  Packaging margin : {self.packaging_margin * 1e3:.1f} mm",
            f"  Stacks in parallel: {self.n_stacks}   |  series cells: {self.n_series}",
            f"  Nominal capacity : {self.capacity_Ah:.2f} Ah",
            f"  Total area       : {self.total_area * 1e4:.0f} cm^2 "
            f"(= {self.n_stacks} x {self.footprint_area * 1e4:.0f} cm^2)",
            f"  Areal capacity   : {self.areal_capacity_mAh_cm2:.2f} mAh/cm^2 "
            f"(over the whole stack)",
        ]
        if param is not None:
            try:
                q_n, q_p = self.theoretical_layer_capacities(param)
                lim = "negative" if q_n < q_p else "positive"
                lines += [
                    f"  Electrode capacity (max): {q_n:.2f} Ah (neg) / {q_p:.2f} Ah (pos)",
                    f"  -> capacity-limiting electrode: {lim}",
                    f"  -> ratio nominal/limiting: {self.capacity_Ah / min(q_n, q_p):.2f}",
                ]
            except KeyError as err:  # pragma: no cover - depends on the parameter set
                lines.append(f"  (capacity check skipped: missing {err})")
        if self.heat_pipe_enabled:
            lines.append(
                f"  Heat pipe cooling: full-width band "
                f"{self.heat_pipe_height * 1e2:.1f} cm tall right below the top edge "
                f"| h = {self.heat_pipe_h:.0f} W/m^2/K "
                f"@ {self.heat_pipe_temperature_K - 273.15:.0f} C"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def field_names(cls) -> list[str]:
        return [f.name for f in fields(cls)]
