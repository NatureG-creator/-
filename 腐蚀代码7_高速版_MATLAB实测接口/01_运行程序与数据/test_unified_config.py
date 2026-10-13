"""统一参数配置的最小回归测试。"""

from __future__ import annotations

import importlib.util
import inspect
import ast
from pathlib import Path

import numpy as np


def main() -> None:
    from unified_config import (
        ACTIVE_STAGE_TARGET_DATA,
        FIGURE_CONFIG,
        GEOMETRY_CONFIG,
        MATLAB_CA_COMPARISON_CONFIG,
        STAGE_GA_CONFIG,
    )

    assert GEOMETRY_CONFIG["space_xy_um"] == 25.0
    assert GEOMETRY_CONFIG["space_z_um"] == 25.0
    assert GEOMETRY_CONFIG["plate_thickness_um"] == 6000.0
    assert ACTIVE_STAGE_TARGET_DATA[0].tolist() == [697.0, 262.0, 2.0, 5.79, 0.63, 0.23]
    assert STAGE_GA_CONFIG["F"] == 2000
    assert STAGE_GA_CONFIG["nind"] == 301
    assert STAGE_GA_CONFIG["selected_count"] == 10
    assert FIGURE_CONFIG["interactive_figsize"] == (14.0, 6.8)
    assert FIGURE_CONFIG["interactive_dpi"] == 160
    assert FIGURE_CONFIG["mesh_dpi"] == 260
    assert FIGURE_CONFIG["surface_cmap"] == "jet"
    assert MATLAB_CA_COMPARISON_CONFIG["min_prominence"] == 0.05
    assert MATLAB_CA_COMPARISON_CONFIG["min_distance"] == 15
    assert MATLAB_CA_COMPARISON_CONFIG["sjb_divisor"] == 10.0
    assert MATLAB_CA_COMPARISON_CONFIG["hist_bin_width"] == 0.1

    from unified_config import matlab_ca_postprocess_settings

    assert matlab_ca_postprocess_settings(2.99) == (0.3, 15)
    assert matlab_ca_postprocess_settings(3.0) == (0.4, 20)
    assert matlab_ca_postprocess_settings(4.99) == (0.4, 20)
    assert matlab_ca_postprocess_settings(5.0) == (0.5, 25)

    from corrosion_model.distribution import _matlab_bin_edges

    edges = _matlab_bin_edges([0.03, 0.08, 0.11, 0.21], 0.1)
    assert np.allclose(edges, [0.0, 0.1, 0.2, 0.3])

    root = Path(__file__).resolve().parent

    visualization_path = root / "corrosion_model" / "visualization.py"
    spec = importlib.util.spec_from_file_location("unified_visualization_test", visualization_path)
    assert spec is not None and spec.loader is not None
    visualization = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(visualization)
    surface_signature = inspect.signature(visualization.plot_depth_surfaces)
    mesh_signature = inspect.signature(visualization.plot_conv2_mesh_surfaces)
    assert surface_signature.parameters["xy_spacing_um"].default is None
    assert mesh_signature.parameters["window_size"].default is None
    assert mesh_signature.parameters["xy_spacing_um"].default is None

    # 03 脚本依赖 scikit-image；这里用 AST 检查函数默认值，避免配置测试被外部
    # 图像依赖阻断。真实运行 03 时仍需要安装 scikit-image。
    auto_plot_path = root / "03_自动生成腐蚀图.py"
    tree = ast.parse(auto_plot_path.read_text(encoding="utf-8"))
    plot_node = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "plot_result_file"
    )
    assert plot_node.args.defaults[-1].__class__ is ast.Constant
    assert plot_node.args.defaults[-1].value is None

    from unified_config import PATH_CONFIG

    assert PATH_CONFIG["auto_plots"].name == "腐蚀综合代码_auto_plots"

    # 第四步回归测试：compute_surface_data 必须显式接收 X/Y 元胞尺寸，
    # 不能在函数内部引用未定义的 `space_xy_um`。
    interactive_path = root / "04_交互查看腐蚀形貌.py"
    interactive_spec = importlib.util.spec_from_file_location(
        "interactive_viewer_test", interactive_path
    )
    assert interactive_spec is not None and interactive_spec.loader is not None
    interactive = importlib.util.module_from_spec(interactive_spec)
    interactive_spec.loader.exec_module(interactive)
    assert hasattr(interactive, "INPUT_RESULT_FILE")
    assert Path(interactive.INPUT_RESULT_FILE).suffix == ".npz"
    a_state = np.ones((3, 3, 4), dtype=float)
    a_state[:, :, 0] = 0.0
    surface_stats = interactive.compute_surface_data(
        a_state=a_state,
        space=25.0,
        space_xy_um=25.0,
        window_size=3,
        expand_factor=1,
        min_prominence=0.05,
        min_distance=1,
        neighborhood=3,
        threshold=0.3,
    )
    assert "jsb" in surface_stats

    converted_jsb, converted_depth = interactive.convert_ca_distribution_values(
        shengdu=np.array([10.0, 20.0]),
        sjb=np.array([0.02, 0.05]),
        space_z_um=25.0,
    )
    assert np.allclose(converted_jsb, np.log([500.0, 200.0]))
    assert np.allclose(converted_depth, np.log([250.0, 500.0]))


if __name__ == "__main__":
    main()
    print("unified config test passed")
