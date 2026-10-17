"""Native contour orchestration contracts; synthetic PNGs are not solver evidence."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from backend import apdl_plots


class APDLPlotTests(unittest.TestCase):
    def source(self, folder):
        root = Path(folder)
        for name in ('corrosion.db', 'corrosion.rst'):
            (root/name).write_bytes(b'fixture, not real MAPDL data')
        return root

    def test_commands_read_last_results_without_resolving_or_saving_database(self):
        macro = apdl_plots.contour_commands('multilinear_iso')
        self.assertIn('/DSCALE,1,1', macro)
        self.assertIn('/GRAPHICS,FULL', macro)
        for command in ('PLNSOL,U,SUM', 'PLNSOL,S,EQV', 'PLNSOL,EPPL,EQV'):
            self.assertIn(command, macro)
        for command in (macro+'\n'+apdl_plots.RESTORE_COMMANDS).splitlines():
            self.assertNotIn(command.split(',')[0].upper(), ('SOLVE', 'SAVE', '/SOLU', 'UPGEOM'))
        self.assertIn('SET,LAST', apdl_plots.RESTORE_COMMANDS)
        self.assertIn("RESUME,'../corrosion',db", apdl_plots.RESTORE_COMMANDS)
        self.assertIn("FILE,'../corrosion',rst", apdl_plots.RESTORE_COMMANDS)

    def test_elastic_does_not_invent_a_plastic_strain_field(self):
        self.assertNotIn('EPPL', apdl_plots.contour_commands('elastic'))
        self.assertIn('EPPL', apdl_plots.contour_commands('bilinear_iso'))

    def test_success_checks_all_images_and_keeps_source_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.source(temp)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            process = Mock(pid=999999)
            process.wait.return_value = 0
            process.close.return_value = {'verified_empty': True}
            def launch(command, directory, stream):
                (directory/'mapdl.out').write_text('normal postprocessing\n')
                for index in range(3):
                    Image.new('RGB', (800, 600), 'white').save(directory/f'contours{index:03}.png')
                return process
            with patch('backend.apdl_solver.mapdl_capabilities', return_value={'available': True, 'executable': 'ansys.exe'}), \
                 patch.object(apdl_plots, 'launch_owned', side_effect=launch) as started:
                report = apdl_plots.render_result_contours(root, {'material_model': 'multilinear_iso'})
            self.assertEqual(report['state'], 'completed')
            self.assertEqual(len(report['plots']), 3)
            self.assertTrue(report['cleanup']['verified_empty'])
            self.assertEqual(started.call_count, 1)
            self.assertEqual(report['deformation_scale'], 1)
            for plot in report['plots']:
                self.assertTrue((root/plot['file']).is_file())
            for name, content in before.items():
                self.assertEqual((root/name).read_bytes(), content)
            saved = json.loads((root/'contour_plots/plot_report.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['state'], 'completed')
            with self.assertRaisesRegex(ValueError, '已有'):
                apdl_plots.render_result_contours(root, {})

    def test_plot_failure_is_reported_and_owned_process_is_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.source(temp)
            process = Mock(pid=999999)
            process.wait.side_effect = subprocess.TimeoutExpired('ansys', 600)
            process.close.return_value = {'verified_empty': True}
            with patch('backend.apdl_solver.mapdl_capabilities', return_value={'available': True, 'executable': 'ansys.exe'}), \
                 patch.object(apdl_plots, 'launch_owned', return_value=process):
                report = apdl_plots.render_result_contours(root, {})
            self.assertEqual(report['state'], 'failed')
            self.assertEqual(report['plots'], [])
            self.assertTrue(report['error'])
            process.close.assert_called_once()

    def test_error_log_or_missing_plot_cannot_claim_export_success(self):
        for log in ('normal output', '*** ERROR *** missing result field'):
            with self.subTest(log=log), tempfile.TemporaryDirectory() as temp:
                root = self.source(temp)
                process = Mock(pid=999999)
                process.wait.return_value = 0
                process.close.return_value = {'verified_empty': True}
                def launch(command, directory, stream):
                    (directory/'mapdl.out').write_text(log)
                    return process
                with patch('backend.apdl_solver.mapdl_capabilities', return_value={'available': True, 'executable': 'ansys.exe'}), \
                     patch.object(apdl_plots, 'launch_owned', side_effect=launch):
                    report = apdl_plots.render_result_contours(root, {})
                self.assertEqual(report['state'], 'failed')
                self.assertEqual(report['plots'], [])

    def test_missing_database_does_not_start_mapdl(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(apdl_plots, 'launch_owned') as launch:
            report = apdl_plots.render_result_contours(Path(temp), {})
            self.assertEqual(report['state'], 'failed')
            launch.assert_not_called()
