import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from backend.apdl_geometry import build_geometry
from backend.apdl_deck import create_tension_bundle


class APDLDeckTests(unittest.TestCase):
    def geometry(self, **options):
        return build_geometry(np.array([[.2, .3, .4], [.5, .6, .7]]), None,
                              dict(dx_mm=10, dy_mm=5, layers=2, **options))

    def test_ascii_deck_outputs_real_result_contract_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            summary = create_tension_bundle(self.geometry(material_model='bilinear_iso'), out,
                                             {'source_sha256': 'abc'})
            self.assertEqual(summary['analysis'], 'tension')
            self.assertEqual(summary['build_state'], 'built')
            for name in ('main.inp', 'materials.mac', 'nodes.dat', 'elements.dat',
                         'boundary.mac', 'solve.mac', 'post.mac', 'run_apdl.cmd'):
                raw = (out/name).read_bytes()
                raw.decode('ascii')
                self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
            self.assertIn('ET,1,SOLID185', (out/'main.inp').read_text())
            self.assertIn('TB,BISO,1', (out/'materials.mac').read_text())
            post = (out/'post.mac').read_text()
            self.assertIn('SET,,,,,,,iset', post)
            self.assertIn('RF,FX', post)
            self.assertIn('force_displacement,csv', post)
            self.assertIn('E19.11', post)
            self.assertNotIn('I12', post)
            self.assertIn('F12.0', post)
            self.assertIn('EPPL,EQV', post)
            self.assertIn('RESCONTROL', (out/'solve.mac').read_text())
            self.assertIn('SAVE', (out/'main.inp').read_text())
            self.assertFalse((out/'force_displacement.csv').exists())
            manifest = json.loads((out/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['provenance']['source_sha256'], 'abc')
            self.assertEqual(manifest['files']['nodes.dat'], hashlib.sha256((out/'nodes.dat').read_bytes()).hexdigest())
            with zipfile.ZipFile(out/'apdl_tension_input_bundle.zip') as archive:
                self.assertIn('main.inp', archive.namelist())
                self.assertIn('remaining_thickness.csv', archive.namelist())

    def test_poisson_free_boundary_uses_only_rigid_body_transverse_constraints(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            create_tension_bundle(self.geometry(), out, {})
            text = (out/'boundary.mac').read_text()
            self.assertIn('D,ALL,UX,0', text)
            self.assertIn('D,1,UY,0', text)
            self.assertIn('D,1,UZ,0', text)
            self.assertIn('D,4,UZ,0', text)
            self.assertNotIn('D,ALL,UY,0', text)
            self.assertNotIn('D,ALL,UZ,0', text)

    def test_sloping_bottom_corner_removes_only_rotation_using_ce(self):
        g = build_geometry(None, np.array([[0, .2], [.5, .7]]), {
            'corrosion_mode': 'single_bottom', 'dx_mm': 2, 'dy_mm': 3})
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            create_tension_bundle(g, out, {})
            text = (out/'boundary.mac').read_text()
            self.assertIn('CE,1,0,3,UZ,3,3,UY,-0.5', text)
            self.assertNotIn('D,3,UZ,0', text)

    def test_clamped_grips_and_elastic_eqpl(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            create_tension_bundle(self.geometry(boundary_mode='clamped_grips'), out, {})
            self.assertEqual((out/'boundary.mac').read_text().count('D,ALL,UY,0'), 2)
            self.assertIn('eqpl=0', (out/'post.mac').read_text())
            self.assertNotIn('EPPL,EQV', (out/'post.mac').read_text())

    def test_plot_failure_keeps_numeric_files_and_zip(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            with patch('backend.apdl_deck._write_preview', side_effect=RuntimeError('plot failed')):
                summary = create_tension_bundle(self.geometry(), out, {})
            self.assertTrue(summary['warnings'])
            self.assertTrue((out/'apdl_tension_input_bundle.zip').is_file())
            np.testing.assert_allclose(np.loadtxt(out/'top_depth.csv', delimiter=','), self.geometry()['top_depth'])

    def test_apdl_fortran_format_and_output_width_limits(self):
        from backend.apdl_deck import _post
        text = _post(self.geometry())
        formats = [line for line in text.splitlines() if line.startswith('(')]
        self.assertTrue(all(len(line) <= 80 for line in formats))
        self.assertLessEqual(6*19+5, 128)
        self.assertLessEqual(12+8*13+8, 128)

    def test_origin_offset_does_not_widen_grip_selection(self):
        from backend.apdl_deck import _boundaries
        g = build_geometry(np.zeros((2, 3)), None, {
            'origin_x_mm': 1000, 'dx_mm': .01, 'dy_mm': .01})
        text = _boundaries(g)
        self.assertIn('SELTOL,', text)
        self.assertLess(text.index('SELTOL,'), text.index('NSEL,S,LOC,X'))

    def test_legacy_template_and_multilinear_original_options(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g = self.geometry(boundary_mode='legacy_recommended', material_model='multilinear_iso',
                              plastic_curve=[[0, 235], [.01, 250], [.02, 240]],
                              allow_negative_slope=True, substeps=100, max_substeps=450, min_substeps=50)
            create_tension_bundle(g, out, {})
            boundary = (out/'boundary.mac').read_text()
            self.assertIn('D,16,UY,0', boundary)
            self.assertIn('D,16,UZ,0', boundary)
            self.assertIn('D,4,UY,0', boundary)
            self.assertNotIn('D,1,UY,0', boundary)
            material = (out/'materials.mac').read_text()
            self.assertIn('TB,PLASTIC,1,0,3,MISO', material)
            self.assertIn('TBEO,NEGSLOPE,1', material)
            self.assertEqual(material.count('TBPT,'), 3)
            self.assertIn('NSUBST,100,450,50', (out/'solve.mac').read_text())
            self.assertIn('SOLCONTROL,ON', (out/'solve.mac').read_text())
            self.assertIn('LNSRCH,1', (out/'solve.mac').read_text())
            self.assertIn('EPPL,EQV', (out/'post.mac').read_text())
