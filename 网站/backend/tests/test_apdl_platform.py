import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.apdl_geometry import build_geometry, normalise_options
from backend.apdl_deck import create_tension_bundle


class PlatformTests(unittest.TestCase):
    def options(self, **changes):
        return dict(corrosion_mode='double_independent', platform_enabled=True,
                    platform_top_mean_depth_mm=.8, platform_bottom_mean_depth_mm=.5,
                    dx_mm=.3, dy_mm=.3, thickness_mm=6.,
                    thickness_layer_mode='intermediate_nodes', intermediate_node_layers=10,
                    **changes)

    def test_exact_flat_lengths_source_relief_and_linear_thickness_on_both_axes(self):
        top=np.array([[.1,.4,.2],[.2,.6,.3]])
        bottom=np.array([[.05,.1,.2],[.1,.3,.15]])
        for direction in ('X','Y'):
            with self.subTest(direction=direction):
                g=build_geometry(top,bottom,self.options(tensile_direction=direction))
                p=g['platforms']; axis=1 if direction=='X' else 0
                coords=g['x'] if direction=='X' else g['y']
                start,stop=p['source_start_index'],p['source_stop_index']
                self.assertEqual(p['fixed_flat_length_mm'],2.5)
                self.assertAlmostEqual(coords[start-1]-coords[0],2.5)
                self.assertAlmostEqual(coords[-1]-coords[stop],2.5)
                self.assertAlmostEqual(coords[start]-coords[start-1],.3)
                np.testing.assert_allclose(np.diff(coords[start:stop]),.3)
                section=[slice(None),slice(None)];section[axis]=slice(start,stop)
                np.testing.assert_allclose(g['top_depth'][tuple(section)],top+.8-top.max())
                np.testing.assert_allclose(g['bottom_depth'][tuple(section)],bottom+.5-bottom.max())
                np.testing.assert_array_equal(top,[[.1,.4,.2],[.2,.6,.3]])
                end=[slice(None),slice(None)];end[axis]=slice(0,start)
                np.testing.assert_array_equal(g['top_depth'][tuple(end)],0)
                np.testing.assert_array_equal(g['bottom_depth'][tuple(end)],0)
                self.assertEqual(g['options']['layers'],11)
                self.assertEqual(g['stats']['node_plane_count'],12)
                self.assertEqual(len(g['elements']),(len(g['x'])-1)*(len(g['y'])-1)*11)
                z=g['nodes'][:,3].reshape(12,*g['top_depth'].shape)
                np.testing.assert_allclose(z[0],g['bottom_depth'])
                np.testing.assert_allclose(z[-1],6-g['top_depth'])
                for k in range(12):
                    np.testing.assert_allclose(z[k],z[0]+k/11*(z[-1]-z[0]))
                self.assertAlmostEqual(g['stats']['remaining_volume_mm3'],
                    np.sum(np.diff(g['y'])[:,None]*np.diff(g['x'])[None,:]*
                    (g['remaining'][:-1,:-1]+g['remaining'][1:,:-1]+g['remaining'][:-1,1:]+g['remaining'][1:,1:])/4))

    def test_formula_preserves_protrusions_and_reports_different_sample_mean(self):
        o=self.options();o['platform_top_mean_depth_mm']=.2
        g=build_geometry(np.array([[0,.5],[.1,.2]]),np.zeros((2,2)),o)
        self.assertTrue(g['platforms']['faces']['top']['protrudes_above_platform'])
        self.assertAlmostEqual(g['platforms']['faces']['top']['normalized_platform_reference_height_mm'],-.3)
        self.assertLess(g['top_depth'].min(),0)
        self.assertTrue(any('保留凸起' in w for w in g['warnings']))
        self.assertNotEqual(g['platforms']['faces']['top']['calibrated_sample_mean_depth_mm'],.2)

    def test_unsafe_or_incomplete_inputs_rejected_without_clipping(self):
        top=np.ones((2,3))*.1
        for changes,message in [({'local_corrosion':True},'局部贴片'),
                                 ({'mesh_type':'solid187_tetra'},'SOLID185'),
                                 ({'platform_top_mean_depth_mm':None},'实测'),
                                 ({'platform_top_mean_depth_mm':7},'穿透'),
                                 ({'platform_fixed_mm':0},'平台长度'),
                                 ({'platform_enabled':'true'},'布尔'),
                                 ({'intermediate_node_layers':True},'整数'),
                                 ({'platform_fixed_mm':1e12},'超过上限')]:
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,message):
                build_geometry(top,top,{**self.options(),**changes})

    def test_single_face_does_not_require_depth_for_flat_face(self):
        o={**self.options(),'corrosion_mode':'single_top','platform_bottom_mean_depth_mm':None}
        g=build_geometry(np.ones((2,2))*.2,None,o)
        np.testing.assert_array_equal(g['bottom_depth'],0)
        self.assertFalse(g['platforms']['faces']['bottom']['active'])

    def test_disabled_keeps_legacy_mesh_and_layers(self):
        g=build_geometry(np.ones((2,3))*.1,None,dict(layers=8))
        self.assertIsNone(g['platforms'])
        self.assertEqual(g['stats']['element_count'],16)
        self.assertEqual(g['stats']['intermediate_node_layers'],7)
        self.assertEqual(normalise_options({'thickness_layer_mode':'intermediate_nodes','intermediate_node_layers':0})['layers'],1)

    def test_export_contains_exact_coordinates_audit_report_and_solid185(self):
        g=build_geometry(np.ones((2,3))*.1,np.ones((2,3))*.2,self.options())
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)
            summary=create_tension_bundle(g,out,{})
            self.assertEqual(summary['stats']['platforms'],g['platforms'])
            self.assertEqual(json.loads((out/'platform_geometry.json').read_text(encoding='utf-8')),g['platforms'])
            with np.load(out/'surface_inputs.npz') as values:
                np.testing.assert_array_equal(values['x'],g['x'])
            self.assertIn('ET,1,SOLID185',(out/'main.inp').read_text())
            self.assertIn('platform_geometry.json',json.loads((out/'manifest.json').read_text(encoding='utf-8'))['files'])
