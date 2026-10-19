import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import numpy as np
from unittest.mock import patch
from backend.server import make_server


class MorphologyServiceTests(unittest.TestCase):
    def test_dual_analysis_writes_preview_reports_without_vector_exports(self):
        from backend.morphology_service import run_morphology_pair
        with tempfile.TemporaryDirectory() as tmp:
            server=make_server(port=0,runtime=Path(tmp))
            try:
                a=np.ones((35,28,12));a[8:16,7:15,:6]=0
                stream=io.BytesIO();np.savez(stream,perfect_a=a,space_xy_um=25.,space_z_um=25.);stream.seek(0)
                upload=server.upload('sample.npz',stream,len(stream.getbuffer()))
                ga=server.create_job({'kind':'morphology_analysis','upload_id':upload['id'],'analysis_mode':'ga'},launch=False)
                folder=Path(tmp)/'jobs'/ga['id'];spec=json.loads((folder/'spec.json').read_text(encoding='utf-8'))
                from backend.morphology_service import read_npz_state
                with patch('backend.morphology_service.read_npz_state',wraps=read_npz_state) as reader:
                    result=run_morphology_pair(spec,folder)
                self.assertEqual(reader.call_count,1)
                self.assertEqual(set(result),{'ga','detail'})
                for mode in result:
                    out=folder/'outputs'/mode
                    self.assertTrue((out/'surface_and_contour.png').exists())
                    self.assertTrue((out/'analysis_report.json').exists())
                    self.assertFalse((out/'surface_and_contour.svg').exists())
                # Export is a separate queued job; it must never extract pits again.
                from backend.morphology_service import run_morphology,run_export
                both=dict(spec,analysis_mode='both')
                (folder/'spec.json').write_text(json.dumps(both),encoding='utf-8')
                run_morphology(both,folder)
                archive=folder/'outputs/morphology_bundle.zip'
                with zipfile.ZipFile(archive) as bundle:
                    names=bundle.namelist()
                    self.assertTrue(any('/分析结果/GA同口径验收/surface_and_contour.png' in name for name in names))
                    self.assertTrue(any('/分析结果/精细形貌分析/surface_and_contour.png' in name for name in names))
                    self.assertTrue(any('/来源文件/sample.npz' in name for name in names))
                    self.assertTrue(any('/报告/清单.json' in name for name in names))
                original=(folder/'outputs/ga/analysis_arrays.npz').read_bytes()
                status=dict(ga,state='completed')
                (folder/'status.json').write_text(json.dumps(status),encoding='utf-8')
                child=server.create_job({'kind':'morphology_export','source_job_id':ga['id'],'formats':['pdf']},launch=False)
                child_folder=Path(tmp)/'jobs'/child['id']
                child_spec=json.loads((child_folder/'spec.json').read_text(encoding='utf-8'))
                with patch('morphology_analysis.analyze_surface',side_effect=AssertionError('must reuse arrays')):
                    exported=run_export(child_spec,child_folder)
                self.assertEqual(exported['modes']['ga']['six_metrics'],result['ga']['six_metrics'])
                for mode in ('ga','detail'):
                    self.assertTrue((child_folder/f'outputs/{mode}/surface_and_contour.pdf').exists())
                    self.assertFalse((child_folder/f'outputs/{mode}/surface_and_contour.svg').exists())
                    self.assertFalse((child_folder/f'outputs/{mode}/surface_and_contour.png').exists())
                with zipfile.ZipFile(child_folder/'outputs/morphology_bundle.zip') as bundle:
                    names=bundle.namelist()
                    self.assertTrue(any('/冻结分析数据/GA同口径验收/analysis_arrays.npz' in name for name in names))
                    self.assertTrue(any('/冻结分析数据/精细形貌分析/analysis_arrays.npz' in name for name in names))
                    self.assertTrue(any('/分析结果/GA同口径验收/surface_and_contour.pdf' in name for name in names))
                    self.assertTrue(any('/来源文件/sample.npz' in name for name in names))
                self.assertEqual((folder/'outputs/ga/analysis_arrays.npz').read_bytes(),original)
            finally: server.server_close()

    def test_morphology_archive_contains_pair_outputs_and_metadata(self):
        from backend.morphology_service import write_morphology_archive
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); out=root/'outputs'/'ga';out.mkdir(parents=True);(out/'analysis_report.json').write_text('{}',encoding='utf-8');(out/'preview.png').write_bytes(b'png')
            (root/'spec.json').write_text(json.dumps({'kind':'morphology_analysis','analysis_mode':'both','source_name':'sample.npz','source_sha256':'a'*64,'npz_stage':4,'npz_variable':'perfect_a'}),encoding='utf-8');(root/'inputs').mkdir();(root/'inputs/source.npz').write_bytes(b'npz')
            archive=write_morphology_archive(root)
            with zipfile.ZipFile(archive) as zf:
                manifest_path=f"成果/sample_{'a'*10}/stage_004/报告/清单.json"
                self.assertEqual(set(zf.namelist()),{f"成果/sample_{'a'*10}/stage_004/配置与溯源/任务配置.json",f"成果/sample_{'a'*10}/stage_004/来源文件/sample.npz",f"成果/sample_{'a'*10}/stage_004/分析结果/GA同口径验收/analysis_report.json",f"成果/sample_{'a'*10}/stage_004/分析结果/GA同口径验收/preview.png",manifest_path})
                manifest=json.loads(zf.read(manifest_path))
                self.assertEqual(manifest['kind'],'morphology_bundle')
                self.assertEqual(manifest['archive_root'],f"成果/sample_{'a'*10}/stage_004")
                self.assertEqual({row['mode'] for row in manifest['files'] if row['mode']},{'GA同口径验收'})
    def test_upload_frozen_job_runs_without_simulation(self):
        from backend.morphology_service import run_morphology
        with tempfile.TemporaryDirectory() as tmp:
            server=make_server(port=0,runtime=Path(tmp))
            try:
                a=np.ones((35,28,12));a[8:16,7:15,:6]=0
                stream=io.BytesIO();np.savez(stream,perfect_a=a,space_xy_um=25.,space_z_um=25.)
                stream.seek(0);upload=server.upload('sample.npz',stream,len(stream.getbuffer()))
                state=server.create_job({'kind':'morphology_analysis','upload_id':upload['id'],'analysis_mode':'detail'},launch=False)
                folder=Path(tmp)/'jobs'/state['id'];spec=json.loads((folder/'spec.json').read_text(encoding='utf-8'))
                self.assertTrue((folder/'inputs/source.npz').exists())
                result=run_morphology(spec,folder)
                self.assertEqual(result['metadata']['mode_label'],'精细形貌分析')
                self.assertIn('未冻结',result['metadata']['configuration_provenance'])
                self.assertTrue((folder/'outputs/surface_and_contour.png').exists())
                self.assertTrue((folder/'outputs/analysis_report.json').exists())
                self.assertIn('source_sha256',result['metadata'])
                self.assertEqual(len(result['six_metrics']),6)
                np.testing.assert_array_equal(np.load(folder/'inputs/source.npz')['perfect_a'],a)
            finally: server.server_close()

    def test_external_npz_stage_is_selected_validated_and_frozen(self):
        from backend.morphology_service import prepare_morphology, run_morphology
        with tempfile.TemporaryDirectory() as tmp:
            server=make_server(port=0,runtime=Path(tmp))
            try:
                states=np.ones((3,35,28,12));states[0,2:4,2:4,:2]=0;states[1,8:16,7:15,:6]=0;states[2,20:25,18:23,:4]=0
                stream=io.BytesIO();np.savez(stream,a_sd=states,space_xy_um=25.,space_z_um=25.);stream.seek(0)
                upload=server.upload('stages.npz',stream,len(stream.getbuffer()))
                spec,_=prepare_morphology(server,{'upload_id':upload['id'],'analysis_mode':'detail','source_stage':2})
                self.assertEqual(spec['npz_stage'],2)
                self.assertEqual(spec['case_name'],'stages.npz · 精细形貌分析')
                job=server.create_job({'kind':'morphology_analysis','upload_id':upload['id'],'analysis_mode':'detail','source_stage':2},launch=False)
                folder=Path(tmp)/'jobs'/job['id'];saved=json.loads((folder/'spec.json').read_text(encoding='utf-8'))
                self.assertEqual(saved['npz_stage'],2)
                from backend.morphology_service import read_npz_state
                with patch('backend.morphology_service.read_npz_state',wraps=read_npz_state) as reader:
                    report=run_morphology(saved,folder)
                self.assertEqual(reader.call_args.args[2],2)
                self.assertEqual(report['metadata']['npz_stage'],2)
                state,_=read_npz_state(folder/'inputs/source.npz','a_sd',2)
                np.testing.assert_array_equal(state,states[1])
                with self.assertRaisesRegex(ValueError,'1 至 3'):
                    prepare_morphology(server,{'upload_id':upload['id'],'source_stage':4})
                with self.assertRaisesRegex(ValueError,'1 至 3'):
                    prepare_morphology(server,{'upload_id':upload['id'],'source_stage':1.5})
            finally: server.server_close()

    def test_external_npz_batch_stages_are_frozen_and_archived(self):
        from backend.morphology_service import prepare_morphology, run_morphology
        with tempfile.TemporaryDirectory() as tmp:
            server=make_server(port=0,runtime=Path(tmp))
            try:
                states=np.ones((3,35,28,12));states[0,2:4,2:4,:2]=0;states[1,8:16,7:15,:6]=0;states[2,20:25,18:23,:4]=0
                stream=io.BytesIO();np.savez(stream,a_sd=states,space_xy_um=25.,space_z_um=25.);stream.seek(0)
                upload=server.upload('batch.npz',stream,len(stream.getbuffer()))
                spec,_=prepare_morphology(server,{'upload_id':upload['id'],'analysis_mode':'detail','source_stages':[1,3]})
                self.assertEqual(spec['npz_stages'],[1,3]);self.assertIsNone(spec['npz_stage'])
                job=server.create_job({'kind':'morphology_analysis','upload_id':upload['id'],'analysis_mode':'detail','source_stages':[1,3]},launch=False)
                folder=Path(tmp)/'jobs'/job['id'];saved=json.loads((folder/'spec.json').read_text(encoding='utf-8'))
                with patch('backend.morphology_service.read_npz_state',wraps=__import__('backend.apdl_npz',fromlist=['read_npz_state']).read_npz_state) as reader:
                    summary=run_morphology(saved,folder)
                self.assertEqual(summary['npz_stages'],[1,3]);self.assertEqual(reader.call_count,2)
                self.assertTrue((folder/'outputs/stage_001/analysis_report.json').exists())
                self.assertTrue((folder/'outputs/stage_003/analysis_report.json').exists())
                with zipfile.ZipFile(folder/'outputs/morphology_bundle.zip') as bundle:
                    names=bundle.namelist()
                    self.assertTrue(any('/分析结果/stage_001/精细形貌分析/' in name for name in names))
                    self.assertTrue(any('/分析结果/stage_003/精细形貌分析/' in name for name in names))
            finally: server.server_close()

    def test_invalid_mode_rejected_before_job_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            server=make_server(port=0,runtime=Path(tmp))
            try:
                with self.assertRaisesRegex(ValueError,'ga、detail 或 both'):
                    server.create_job({'kind':'morphology_analysis','analysis_mode':'fake'},launch=False)
                self.assertEqual(list((Path(tmp)/'jobs').iterdir()),[])
            finally:server.server_close()

    def test_source_task_uses_frozen_config_and_physical_layers(self):
        from backend.config import default_simulation_config
        from backend.morphology_service import prepare_morphology
        with tempfile.TemporaryDirectory() as tmp:
            server=make_server(port=0,runtime=Path(tmp))
            try:
                job=server.create_job({'kind':'diagnostics'},launch=False)
                folder=Path(tmp)/'jobs'/job['id'];(folder/'outputs').mkdir()
                config=default_simulation_config();config['GEOMETRY_CONFIG'].update(grid_w=20,grid_l=25,grid_n=8,space_xy_um=20,space_z_um=30)
                config['POSTPROCESS_CONFIG']['auto_plot_window_size']=9
                (folder/'spec.json').write_text(json.dumps({'kind':'simulation','config':config}),encoding='utf-8')
                (folder/'status.json').write_text(json.dumps(dict(job,kind='simulation',state='completed')),encoding='utf-8')
                np.savez(folder/'outputs/simulation.npz',perfect_a=np.ones((20,25,8)))
                spec,_=prepare_morphology(server,{'analysis_mode':'ga','source_job_id':job['id']})
                self.assertEqual(spec['physical_layers'],8)
                pair_spec,_=prepare_morphology(server,{'analysis_mode':'both','source_job_id':job['id']})
                self.assertEqual(pair_spec['case_name'],f"{job['id']}/simulation.npz · 双模式对照")
                self.assertEqual(spec['config']['POSTPROCESS_CONFIG']['auto_plot_window_size'],9)
                self.assertEqual(spec['geometry'],{'space_xy_um':20,'space_z_um':30})
                self.assertIn('冻结',spec['configuration_provenance'])
                np.savez(folder/'outputs/simulation.npz',perfect_a=np.ones((21,25,8)))
                with self.assertRaisesRegex(ValueError,'XY维'):
                    prepare_morphology(server,{'analysis_mode':'ga','source_job_id':job['id']})
            finally:server.server_close()


if __name__=='__main__':unittest.main()
