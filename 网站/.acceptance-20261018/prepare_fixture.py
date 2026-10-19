import io,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from backend.server import make_server
from backend.morphology_service import run_morphology_pair,write_morphology_archive,run_export
from backend.runner import _atomic_json
root=Path(__file__).resolve().parent
server=make_server(port=0,runtime=root)
try:
    a=np.ones((35,28,12));a[8:16,7:15,:6]=0
    stream=io.BytesIO();np.savez(stream,perfect_a=a,space_xy_um=25.,space_z_um=25.);stream.seek(0)
    upload=server.upload('acceptance.npz',stream,len(stream.getbuffer()))
    job=server.create_job({'kind':'morphology_analysis','upload_id':upload['id'],'analysis_mode':'both'},launch=False)
    folder=root/'jobs'/job['id'];spec=json.loads((folder/'spec.json').read_text(encoding='utf-8'))
    modes=run_morphology_pair(spec,folder)
    _atomic_json(folder/'outputs/summary.json',{'modes':modes})
    write_morphology_archive(folder)
    _atomic_json(folder/'status.json',dict(job,state='completed',created_at=1792234800))
    legacy=server.create_job({'kind':'diagnostics'},launch=False)
    old=root/'jobs'/legacy['id']
    _atomic_json(old/'spec.json',{'kind':'morphology_analysis','analysis_mode':'ga'})
    _atomic_json(old/'status.json',dict(legacy,kind='morphology_analysis',state='completed',created_at=1792148400))
    _atomic_json(old/'outputs/summary.json',modes['ga'])
    exported=server.create_job({'kind':'morphology_export','source_job_id':job['id'],'formats':['png','pdf','svg']},launch=False)
    out=root/'jobs'/exported['id'];espec=json.loads((out/'spec.json').read_text(encoding='utf-8'))
    run_export(espec,out)
    _atomic_json(out/'status.json',dict(exported,state='completed',created_at=1792234800))
    print(json.dumps({'pair':job['id'],'legacy':legacy['id'],'export':exported['id']}))
finally:server.server_close()
