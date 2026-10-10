"""Physical geometry for the paper's anisotropic cellular automaton grid."""

from __future__ import annotations

from unified_config import GEOMETRY_CONFIG


class PaperGeometry:
    """Map cell counts to the paper's physical dimensions.

    The CA operates on integer cells. This class is only used when converting
    a result into physical units, so it does not change CA or GA iteration.
    """

    def __init__(
        self,
        space_xy_um: float | None = None,
        space_z_um: float | None = None,
        plate_thickness_um: float | None = None,
    ) -> None:
        if space_xy_um is None:
            space_xy_um = float(GEOMETRY_CONFIG["space_xy_um"])
        if space_z_um is None:
            space_z_um = float(GEOMETRY_CONFIG["space_z_um"])
        if plate_thickness_um is None:
            plate_thickness_um = float(GEOMETRY_CONFIG["plate_thickness_um"])
        if space_xy_um <= 0 or space_z_um <= 0 or plate_thickness_um <= 0:
            raise ValueError("all physical dimensions must be positive")
        self.space_xy_um = float(space_xy_um)
        self.space_z_um = float(space_z_um)
        self.plate_thickness_um = float(plate_thickness_um)

    def model_width_um(self, cells: int) -> float:
        return float(cells) * self.space_xy_um

    def model_length_um(self, cells: int) -> float:
        return float(cells) * self.space_xy_um

    def model_thickness_um(self, cells: int) -> float:
        return float(cells) * self.space_z_um

    def depth_um(self, cells: float) -> float:
        return float(cells) * self.space_z_um

    def diameter_um(self, cells: float) -> float:
        return float(cells) * self.space_xy_um

    def area_um2(self, cells: float) -> float:
        return float(cells) * self.space_xy_um**2

    def ratio_from_cell_ratio(self, cell_ratio: float) -> float:
        return float(cell_ratio) * self.space_z_um / self.space_xy_um
