import io
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from backend.server import make_server


class MorphologyServiceTests(unittest.TestCase):
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

    def test_invalid_mode_rejected_before_job_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            server=make_server(port=0,runtime=Path(tmp))
            try:
                with self.assertRaisesRegex(ValueError,'analysis_mode'):
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
                self.assertEqual(spec['config']['POSTPROCESS_CONFIG']['auto_plot_window_size'],9)
                self.assertEqual(spec['geometry'],{'space_xy_um':20,'space_z_um':30})
                self.assertIn('冻结',spec['configuration_provenance'])
                np.savez(folder/'outputs/simulation.npz',perfect_a=np.ones((21,25,8)))
                with self.assertRaisesRegex(ValueError,'XY维'):
                    prepare_morphology(server,{'analysis_mode':'ga','source_job_id':job['id']})
            finally:server.server_close()


if __name__=='__main__':unittest.main()
