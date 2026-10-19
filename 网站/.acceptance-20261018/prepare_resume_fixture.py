import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.server import make_server
from backend.config import default_simulation_config
from backend.runner import run_simulation,_atomic_json
root=Path(__file__).resolve().parent
server=make_server(port=0,runtime=root)
cfg=default_simulation_config()
cfg['mode']='pycharm'
cfg['TAICHI_CONFIG']['use_taichi']=False
cfg['GEOMETRY_CONFIG'].update(grid_w=5,grid_l=6,grid_n=4)
cfg['SINGLE_STAGE_GA_CONFIG'].update(F=2,nind=4,selected_count=1,maxgen=3,parallel_workers=2)
def stop(event):
    if '已完成 1/4 个体' in event.get('label',''):raise InterruptedError('独立页面验收中断')
if __name__=='__main__':
    try:
        job=server.create_job(dict(kind='simulation',case_name='阶段内恢复 · 独立验收',
            run_mode='single',seed_mode='fixed',config=cfg,targets=[[10,2,1,3,.2,.3]]),launch=False)
        folder=root/'jobs'/job['id']
        spec=json.loads((folder/'spec.json').read_text(encoding='utf-8'))
        try:run_simulation(spec,folder,progress=stop)
        except InterruptedError:pass
        _atomic_json(folder/'status.json',dict(job,state='interrupted',pid=None,error='独立验收：已保存一个个体后中断'))
        print(job['id'])
    finally:server.server_close()
