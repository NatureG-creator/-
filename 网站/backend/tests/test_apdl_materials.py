import unittest
from backend.apdl_geometry import normalise_options


class MaterialImportTests(unittest.TestCase):
    def test_percent_and_pa_are_explicitly_converted(self):
        from backend.apdl_materials import convert_material_table
        table = {'columns': ['ep', 's'], 'rows': [[0, 300e6], [1, 400e6]]}
        result = convert_material_table(table, dict(strain_column=0, stress_column=1,
            strain_unit='percent', stress_unit='Pa', strain_type='true_plastic', E_MPa=200000))
        self.assertEqual(result['curve'], [[0, 300], [.01, 400]])
        normalise_options(dict(material_model='multilinear_iso', plastic_curve=result['curve']))

    def test_true_total_strain_subtracts_elastic_strain(self):
        from backend.apdl_materials import convert_material_table
        table = {'columns': ['e', 's'], 'rows': [[.0015, 300], [.012, 400]]}
        config = dict(strain_column=0, stress_column=1, strain_unit='fraction',
                      stress_unit='MPa', strain_type='true_total', E_MPa=200000,
                      uniform_before_necking=True)
        result = convert_material_table(table, config)
        self.assertEqual(result['curve'][0], [0, 300])
        self.assertAlmostEqual(result['curve'][1][0], .01)
        config['uniform_before_necking'] = False
        with self.assertRaisesRegex(ValueError, '颈缩'):
            convert_material_table(table, config)

    def test_no_silent_sort_drop_or_manufactured_yield_point(self):
        from backend.apdl_materials import convert_material_table
        config = dict(strain_column=0, stress_column=1, strain_type='true_plastic',
                      strain_unit='fraction', stress_unit='MPa', E_MPa=200000)
        for rows in ([[.01, 400], [0, 300]], [[0, 300], [.01, None]],
                     [[.001, 300], [.01, 400]], [[0, 300], [.01, 290]]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                convert_material_table({'columns': ['e', 's'], 'rows': rows}, config)


if __name__ == '__main__':
    unittest.main()
