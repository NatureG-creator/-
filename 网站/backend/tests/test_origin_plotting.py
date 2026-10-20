import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.origin_plotting import normalise_origin_options, prepare_origin, freeze_origin, load_origin_snapshot


class OriginPlottingTests(unittest.TestCase):
    def source(self, root, surface=False):
        source = root / '0123456789abcdef'
        (source / 'outputs').mkdir(parents=True)
        candidate = dict(id='interaction2' if surface else 'linear', status='ok', parameters=dict(a=2,b=3,c=.5,d=1),
                         curve=dict(x=[1,2,3], y=[3,5,7]))
        group = dict(label='A',x=[1,2,3],y=[3,5,7],x1=[1,2,1,2],x2=[1,1,2,2],candidates=[candidate],recommended_id=candidate['id'])
        if surface: group['y']=[6.5,9,10,13]
        summary = dict(kind='fitting',fitting_mode='multivariate2' if surface else 'xy',groups=[group],plot={})
        (source/'outputs'/'summary.json').write_text(json.dumps(summary),encoding='utf-8')
        (source/'status.json').write_text(json.dumps(dict(kind='fitting',state='completed')),encoding='utf-8')
        return source

    def test_options_reject_bad_ranges_nonfinite_and_command_text(self):
        for options in [dict(width_mm=float('nan')),dict(x_min=3,x_max=2),dict(dpi=2000),dict(title='x";exit;'),dict(font_family='a\\b'),dict(formats=[]),dict(x_scale='bad'),dict(unknown=True)]:
            with self.subTest(options=options), self.assertRaises(ValueError): normalise_origin_options(options)

    def test_freeze_survives_source_changes_and_detects_snapshot_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=self.source(root);job=root/'new';(job/'inputs').mkdir(parents=True)
            spec=prepare_origin(dict(source_job_id=source.name,group_index=0,model_id='linear',plot_type='curve'),source)
            freeze_origin(spec,source,job)
            (source/'outputs'/'summary.json').write_text('{}')
            data=load_origin_snapshot(job,spec)
            self.assertEqual(data['observed']['y'],[3,5,7])
            (job/spec['snapshot_path']).write_text('{}')
            with self.assertRaisesRegex(ValueError,'校验'):load_origin_snapshot(job,spec)

    def test_changed_source_between_prepare_and_freeze_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=self.source(root);job=root/'new';(job/'inputs').mkdir(parents=True)
            spec=prepare_origin(dict(source_job_id=source.name),source)
            (source/'outputs'/'summary.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'改变'):freeze_origin(spec,source,job)

    def test_log_scale_checks_observations_and_curve(self):
        with tempfile.TemporaryDirectory() as td:
            source=self.source(Path(td));p=source/'outputs'/'summary.json';s=json.loads(p.read_text());s['groups'][0]['candidates'][0]['curve']['y'][0]=0;p.write_text(json.dumps(s))
            with self.assertRaisesRegex(ValueError,'对数'):prepare_origin(dict(source_job_id=source.name,options=dict(y_scale='log')),source)

    def test_surface_uses_fixed_coefficients_and_correct_grid_orientation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=self.source(root,True);job=root/'new';(job/'inputs').mkdir(parents=True)
            spec=prepare_origin(dict(source_job_id=source.name,plot_type='surface'),source);freeze_origin(spec,source,job);data=load_origin_snapshot(job,spec)
            self.assertEqual(data['surface']['z'][0][0],6.5)
            self.assertEqual(data['surface']['z'][-1][-1],13)
            self.assertEqual(data['observed']['z'],[6.5,9,10,13])

    def test_incomplete_or_failed_candidate_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            source=self.source(Path(td));(source/'status.json').write_text('{"kind":"fitting","state":"running"}')
            with self.assertRaisesRegex(ValueError,'完成'):prepare_origin(dict(source_job_id=source.name),source)

    def test_plot_type_requires_known_enum(self):
        with tempfile.TemporaryDirectory() as td:
            source=self.source(Path(td))
            for value in (None, [], 'other'):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError,'绘图类型'):
                    prepare_origin(dict(plot_type=value),source)

    def test_surface_single_sided_z_range_uses_observed_and_predicted_values(self):
        with tempfile.TemporaryDirectory() as td:
            source=self.source(Path(td),True)
            for options in (dict(z_min=14),dict(z_max=6)):
                with self.subTest(options=options), self.assertRaisesRegex(ValueError,'单侧范围'):
                    prepare_origin(dict(options=options),source)
            prepare_origin(dict(options=dict(z_min=7)),source)

    def test_surface_color_bounds_rejected_before_origin_launch(self):
        with tempfile.TemporaryDirectory() as td:
            source=self.source(Path(td),True)
            for options in (dict(color_min=14),dict(color_max=6)):
                with self.subTest(options=options), self.assertRaisesRegex(ValueError,'色标'):
                    prepare_origin(dict(options=options),source)

    def test_stop_rejects_pid_reuse_without_killing(self):
        from backend.origin_plotting import stop_origin_process
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'origin_process.json').write_text('{"pid":123,"create_time":1}')
            with patch('psutil.Process') as factory:
                factory.return_value.create_time.return_value=2
                with self.assertRaises(ValueError):stop_origin_process(p)
                factory.return_value.kill.assert_not_called()

    def test_unknown_origin_ownership_is_never_reported_as_cleaned(self):
        from backend.origin_plotting import stop_origin_process
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'origin_launch.json').write_text('{"state":"starting"}')
            with patch('psutil.Process') as factory:
                with self.assertRaisesRegex(ValueError,'握手'):stop_origin_process(p)
                factory.assert_not_called()

    def test_owner_handshake_records_pid_from_the_actual_instance(self):
        from backend.origin_render import _record_owner
        with tempfile.TemporaryDirectory() as td:
            with patch('psutil.Process') as factory:
                factory.return_value.pid=321
                factory.return_value.name.return_value='Origin64.exe'
                factory.return_value.create_time.return_value=123.45
                from unittest.mock import Mock
                op=Mock();op.lt_float.side_effect=[0,321]
                _record_owner(op,Path(td))
                record=json.loads((Path(td)/'origin_process.json').read_text())
                self.assertEqual(record['pid'],321)
                self.assertEqual(record['create_time'],123.45)
                self.assertIn('CorrosionOriginProcessID()',op.lt_float.call_args.args)
