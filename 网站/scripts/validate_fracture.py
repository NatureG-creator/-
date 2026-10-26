"""Run three real LS-DYNA acceptance cases in a new, isolated output directory."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.apdl_geometry import build_geometry
from backend.apdl_deck import create_tension_bundle
from backend.apdl_fracture import run_fracture
from backend.apdl_fracture_results import read_fracture_results
from backend.apdl_presets import get_presets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    preset = next(p['options'] for p in get_presets() if p['id'] == 'gissmo_demo')
    reports = {}
    for name, duration, damping in [('base', .002, 10000), ('less_damping', .002, 5000), ('slower', .004, 5000)]:
        output = args.output/name
        geometry = build_geometry(None, None, dict(preset, loading_time_s=duration, damage_damping_per_s=damping))
        summary = create_tension_bundle(geometry, output, {'purpose': 'example acceptance; not calibrated'})
        summary['solver'] = run_fracture(output, geometry['options'])
        summary['results'] = read_fracture_results(output, geometry['stats'], geometry['options'])
        (output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        report = summary['results']['fracture']
        assert report['necking_observed'] and report['coupling_observed'] and report['fracture_confirmed'], report
        assert report['quasistatic_screen_passed'], report
        reports[name] = report
        print(name, json.dumps(report, ensure_ascii=False), flush=True)
    for name, reference in [('less_damping', 'base'), ('slower', 'less_damping')]:
        difference = abs(reports[name]['peak_force_n']/reports[reference]['peak_force_n']-1)
        assert difference < .05, (name, difference)
    (args.output/'acceptance.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
