"""Generated APDL contracts; these checks do not pretend to execute MAPDL."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from backend.apdl_deck import create_tension_bundle
from backend.apdl_geometry import build_geometry
from backend.apdl_presets import ORIGINAL_CURVE


class APDLMacroTests(unittest.TestCase):
    def test_nonlinear_nodal_export_does_not_alternate_stress_and_strain_reads(self):
        for model in ('bilinear_iso', 'multilinear_iso'):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as directory:
                options = dict(material_model=model, export_full_field=True)
                if model == 'multilinear_iso':
                    options.update(plastic_curve=ORIGINAL_CURVE, allow_negative_slope=True)
                self.bundle(directory, **options)
                post = (Path(directory)/'post.mac').read_text()
                loops = []
                for line in post.splitlines():
                    if line.startswith('*DO,'):
                        loops.append([])
                    elif line == '*ENDDO':
                        body = '\n'.join(loops.pop())
                        self.assertFalse('NODE,nid,S,EQV' in body and 'NODE,nid,EPPL,EQV' in body,
                                         'Alternating result types recomputes nodal averaging for every node.')
                    elif loops:
                        loops[-1].append(line)
                self.assertIn('*GET,seqv,NODE,nid,S,EQV', post)
                self.assertIn('*GET,eqpl,NODE,nid,EPPL,EQV', post)
                self.assertIn('*VWRITE,nid,xx,yy,zz,uu,vv,ww,seqv,eqpl', post)
                self.assertIn("(F12.0,8(',',E13.5))", post)

    def test_tetra_uses_native_error_selection_without_raising_message_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            self.bundle(out, mesh_type='solid187_tetra')
            main=(out/'main.inp').read_text()
            self.assertIn('SHPP,ON\nSHPP,SILENT,ON', main)
            quality=(out/'mesh_quality.mac').read_text()
            self.assertIn('ESCHECK,ESEL,ERR', quality)
            self.assertIn('*GET,ac_nshape,ELEM,0,COUNT', quality)
            self.assertIn('*IF,ac_nshape,GT,0,THEN', quality)
            self.assertNotIn('/NERR', main+quality)
            self.assertNotIn('SHPP,WARN', main+quality)

    def bundle(self, directory, **options):
        geometry = build_geometry(np.array([[.2, .3, .4], [.5, .6, .7]]), None,
                                  dict(dx_mm=10, dy_mm=5, layers=2, **options))
        with patch('backend.apdl_deck._write_preview', side_effect=RuntimeError('skip preview')):
            summary = create_tension_bundle(geometry, Path(directory), {})
        return summary

    def test_bundle_contains_read_only_diagnostics_with_hashes_and_no_run_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            summary = self.bundle(out)
            self.assertEqual(summary.get('diagnostics_schema_version'), 2)
            manifest = json.loads((out/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['diagnostics_schema_version'], 2)
            precheck = json.loads((out/'diagnostics_precheck.json').read_text(encoding='utf-8'))
            self.assertEqual(set(precheck), {'material_coverage', 'mesh_quality', 'output_policy'})
            self.assertEqual(precheck['mesh_quality']['status'], 'precheck_only')
            self.assertEqual(summary['diagnostics'], precheck)
            self.assertEqual(summary['output_policy'], precheck['output_policy'])
            for name in ('mesh_quality.mac', 'mesh_self_check.mac', 'boundary_self_check.mac'):
                data = (out/name).read_bytes()
                data.decode('ascii')
                self.assertEqual(manifest['files'][name], hashlib.sha256(data).hexdigest())
                with zipfile.ZipFile(out/'apdl_tension_input_bundle.zip') as archive:
                    self.assertEqual(archive.read(name), data)
            for name in ('apdl_self_check.csv', 'material_coverage_history.csv', 'mesh_quality_report.txt'):
                self.assertFalse((out/name).exists())

    def test_import_enables_shape_checks_then_runs_mesh_and_boundary_gates_before_solution(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.bundle(out)
            main = (out/'main.inp').read_text()
            ordered = ['SHPP,ON', '/INPUT,nodes,dat', '/INPUT,elements,dat',
                       '/INPUT,mesh_quality,mac', '/INPUT,mesh_self_check,mac',
                       '/INPUT,boundary,mac', '/INPUT,boundary_self_check,mac', '/INPUT,solve,mac']
            for command in ordered:
                self.assertIn(command, main)
            positions = [main.index(command) for command in ordered]
            self.assertEqual(positions, sorted(positions))
            quality = (out/'mesh_quality.mac').read_text()
            self.assertIn('/OUTPUT,mesh_quality_report,txt', quality)
            self.assertNotIn('/NERR', quality)
            self.assertIn('CHECK\nSHPP,STATUS\nSHPP,SUMMARY\n/OUTPUT', quality)
            self.assertNotIn('SHPP,WARN', main+quality)

    def test_runtime_self_check_writes_two_six_column_stages_and_failure_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.bundle(out, origin_x_mm=1000)
            self.assertTrue((out/'mesh_self_check.mac').is_file())
            self.assertTrue((out/'boundary_self_check.mac').is_file())
            mesh = (out/'mesh_self_check.mac').read_text()
            boundary = (out/'boundary_self_check.mac').read_text()
            for command in ('*GET,ac_nn,NODE,0,COUNT', '*GET,ac_ne,ELEM,0,COUNT',
                            '*GET,ac_nmin,NODE,0,NUM,MIN', '*GET,ac_nmax,NODE,0,NUM,MAX',
                            '*GET,ac_emin,ELEM,0,NUM,MIN', '*GET,ac_emax,ELEM,0,NUM,MAX'):
                self.assertIn(command, mesh)
            for condition in ('ac_nn,NE,18', 'ac_ne,NE,4', 'ac_nmax,NE,18', 'ac_emax,NE,4'):
                self.assertIn(condition, mesh)
            self.assertIn('ac_stage=1', mesh)
            self.assertIn('ac_nf=-1', mesh)
            self.assertIn('ac_nl=-1', mesh)
            self.assertIn('ac_stage=2', boundary)
            self.assertIn('*CFOPEN,apdl_self_check,csv,,APPEND', boundary)
            for macro in (mesh, boundary):
                self.assertIn('*VWRITE,ac_stage,ac_nn,ac_ne,ac_nf,ac_nl,ac_pass', macro)
                self.assertIn("(F12.0,5(',',F12.0))", macro)
                self.assertIn('/COM,APDL_SELF_CHECK_FAILED', macro)
                self.assertIn('/EXIT,NOSAVE', macro)
                self.assertLess(macro.index('*CFCLOS'), macro.index('/EXIT,NOSAVE'))
                self.assertTrue(macro.rstrip().endswith('ALLSEL,ALL'))
            self.assertIn('CMSEL,S,GRIP_FIXED', boundary)
            self.assertIn('CMSEL,S,GRIP_LOADED', boundary)
            self.assertIn('CMSEL,R,GRIP_LOADED', boundary)
            self.assertIn('ac_nf,NE,6', boundary)
            self.assertIn('ac_nl,NE,6', boundary)
            self.assertIn('NSEL,U,LOC,X,1000', boundary)
            self.assertIn('NSEL,U,LOC,X,1020', boundary)
            self.assertIn('ac_overlap,NE,0', boundary)
            self.assertIn('SELTOL,0.10000000000000001', boundary)

    def test_sparse_field_modes_keep_curve_and_miso_nldat_at_every_substep(self):
        for mode in ('last', 'selected'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                self.bundle(out, result_save_mode=mode, field_output_times=[.2, .6, 1],
                            material_model='multilinear_iso', plastic_curve=ORIGINAL_CURVE,
                            allow_negative_slope=True)
                solve = (out/'solve.mac').read_text()
                if mode == 'selected':
                    self.assertIn('OUTRES,ALL,ALL', solve)
                    self.assertNotIn('OUTRES,ESOL,%field_times%', solve)
                    self.assertNotIn('*DIM,field_times', solve)
                    continue
                for command in ('OUTRES,ALL,NONE', 'OUTRES,NSOL,ALL', 'OUTRES,RSOL,ALL',
                                'OUTRES,NLDAT,ALL'):
                    self.assertIn(command, solve)
                self.assertNotIn('OUTRES,ALL,ALL', solve)
                self.assertLess(solve.index('OUTRES,ESOL,'), solve.index('OUTRES,NLDAT,ALL'))
                self.assertIn('OUTRES,ESOL,LAST', solve)

    def test_miso_history_is_element_nodal_proxy_with_all_sets_and_own_six_column_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.bundle(out, material_model='multilinear_iso', plastic_curve=ORIGINAL_CURVE,
                        allow_negative_slope=True, result_save_mode='last')
            post = (out/'post.mac').read_text()
            self.assertIn('*CFOPEN,material_coverage_history,csv', post)
            self.assertIn('ETABLE,MCPEEQ,NL,EPEQ,MAX', post)
            self.assertIn('*VGET,mc_values(1),ELEM,1,ETAB,MCPEEQ', post)
            self.assertIn('*VSCFUN,mc_id,LMAX,mc_values(1)', post)
            self.assertIn('mc_max=mc_values(mc_id)', post)
            self.assertIn('*GET,mc_x,ELEM,mc_id,CENT,X', post)
            self.assertIn('*VWRITE,tm,mc_max,mc_id,mc_x,mc_y,mc_z', post)
            self.assertIn('! Element nodal MAX proxy; not a verified integration-point maximum.', post)
            self.assertEqual(post.count('*DO,iset,1,nsets'), 2)
            self.assertIn('*GET,eqpl,NODE,nid,EPPL,EQV', post)
        for model in ('elastic', 'bilinear_iso'):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as directory:
                self.bundle(directory, material_model=model, result_save_mode='last')
                self.assertNotIn('material_coverage_history', (Path(directory)/'post.mac').read_text())
                self.assertNotIn('OUTRES,NLDAT,ALL', (Path(directory)/'solve.mac').read_text())

    def test_original_49_points_boundary_mesh_and_default_solver_are_byte_identical(self):
        hashes = {'materials.mac': '3bdf11b1f1bd4e2f599373427907a197f114e53386eede4604675d9289b9061e',
                  'solve.mac': '100ef2e27c952fbe02a43e22d5ec86d5c63fb4a7b68c29791c2ed0895d283a5c',
                  'nodes.dat': 'f43b1ee73cc2524531620eaa5d4036a267c3c58515a92b7a36392ce9267a247d',
                  'elements.dat': 'b0bd0d92c6461a715f2f6bdd0f9bd66dfb2f34cfff7990667e88154116d18989'}
        boundaries = {'poisson_free': '64460f009b36e69cf3140d60f2038ee6e49c995b11ddea7a3184a30a3e402c47',
                      'clamped_grips': '04244191c0f8326f22746b8840537424f039c584f382a162458b97c5409adfcb',
                      'legacy_recommended': '5a59b4b0a04b3fd17f04413839c56d664dcfdba34f5e0f61894c20ae4ed5b297'}
        for boundary, digest in boundaries.items():
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                self.bundle(out, boundary_mode=boundary, material_model='multilinear_iso',
                            plastic_curve=ORIGINAL_CURVE, allow_negative_slope=True)
                for name, expected in dict(hashes, **{'boundary.mac': digest}).items():
                    self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(), expected, name)
                self.assertEqual((out/'materials.mac').read_text().count('TBPT,'), 49)

    def test_sparse_policy_changes_only_output_control_not_physical_solver_parameters(self):
        physical = ['/SOLU', 'ANTYPE,STATIC,NEW', 'SOLCONTROL,ON', 'LNSRCH,1', 'NLGEOM,ON',
                    'TIME,1', 'NSUBST,100,450,50', 'AUTOTS,ON', 'KBC,0',
                    'RESCONTROL,DEFINE,NONE', 'SOLVE', 'FINISH', 'SAVE']
        for mode in ('all', 'last', 'selected'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                self.bundle(directory, result_save_mode=mode, large_deflection=True, substeps=100,
                            max_substeps=450, min_substeps=50, restart_frequency=0)
                solve = (Path(directory)/'solve.mac').read_text().splitlines()
                self.assertEqual([line for line in solve if not line.startswith(('OUTRES,', '*DIM,', 'field_times('))], physical)
