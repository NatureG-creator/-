export function taskLabel(job) {
  return job.display_name || job.spec?.case_name || job.case_name || job.id;
}

export function withTaskSettings(payload, settings) {
  const name=settings.name.trim(), directory=settings.export_directory.trim();
  if(name.length>100)throw new Error('任务名称最多100字');
  const value={...payload,export_directory:directory};
  if(name)value.case_name=name;
  if(payload.cases)value.cases=payload.cases.map(item=>({...item,export_directory:item.export_directory||directory}));
  return value;
}

function settingsCard(id, request, title='任务名称与成果位置') {
  const card=document.createElement('div');
  card.id=id; card.className='card task-io-card';
  card.innerHTML=`<h3>${title}</h3><div class="grid two"><div class="field"><label for="${id}-name">自定义名称</label><input id="${id}-name" data-task-name type="text" maxlength="100" placeholder="例如：C17 · 100天 · 第一次拟合"></div><div class="field"><label for="${id}-directory">成果导出目录（可选）</label><input id="${id}-directory" data-task-directory type="text" spellcheck="false" placeholder="填写本机完整路径，或点击选择目录"></div></div><div class="actions"><button type="button" class="button secondary" data-task-browse>选择目录…</button></div><p class="help-line">可在本页的文件选择按钮导入本机数据；各模块接受的文件类型以输入说明为准。成果会自动复制到所选目录下的独立子文件夹；留空则保存在任务内部，仍可下载。</p><p class="preview" data-task-io-note role="status"></p>`;
  card.querySelector('[data-task-browse]').onclick=async event=>{
    const button=event.currentTarget, note=card.querySelector('[data-task-io-note]');
    button.disabled=true; note.textContent='请选择电脑上的目录（可取消）…';
    try {
      const result=await request('/api/local-directory',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',timeout:190000});
      if(!result.cancelled){card.querySelector('[data-task-directory]').value=result.path;card.dispatchEvent(new Event('input',{bubbles:true}));}
      note.textContent=result.cancelled?'已取消，原目录保持不变。':`已选择：${result.path}`;
    } catch(error){note.textContent=error.message;}
    finally{button.disabled=false;}
  };
  return card;
}

function readSettings(card) {
  return {name:card.querySelector('[data-task-name]').value,
          export_directory:card.querySelector('[data-task-directory]').value};
}

export function mountTaskIO(request) {
  for(const panelId of ['pointcloud-panel','surface-generation-panel','simulation-panel','benchmark-panel','finite-element-panel','fitting-panel']){
    const panel=document.getElementById(panelId), id=`task-io-${panelId}`;
    if(!panel||document.getElementById(id))continue;
    panel.querySelector('.section-heading').after(settingsCard(id,request));
  }
  const legacy=document.querySelector('.apdl-legacy-body');
  if(legacy&&!document.getElementById('task-io-legacy'))legacy.querySelector('.section-heading').after(settingsCard('task-io-legacy',request));
}

export function taskPayload(url, payload) {
  if(url==='/api/apdl/jobs'&&payload.execution_mode==='custom_commands')return payload;
  let panel;
  if(url==='/api/finite-element/exports')panel='legacy';
  else if(url==='/api/apdl/jobs')panel='finite-element-panel';
  else if(url==='/api/fitting/jobs')panel='fitting-panel';
  else if(['/api/benchmarks','/api/benchmark-diagnostics'].includes(url))panel='benchmark-panel';
  else if(url==='/api/batches')panel='simulation-panel';
  else if(url==='/api/jobs')panel={pointcloud:'pointcloud-panel',surface_generation:'surface-generation-panel',simulation:'simulation-panel',diagnostics:'benchmark-panel'}[payload?.kind];
  else if(url==='/api/origin/jobs')panel='origin';
  const card=panel&&document.getElementById(`task-io-${panel}`);
  return card?withTaskSettings(payload,readSettings(card)):payload;
}

export function mountResultTaskIO(job, {request,post,onSaved}) {
  let card=document.getElementById('result-task-io');
  if(!card){
    card=settingsCard('result-task-io',request,'本次任务：重命名与另存成果');
    card.querySelector('.actions').insertAdjacentHTML('beforeend','<button type="button" class="button secondary" data-task-save>保存名称与目录</button><button type="button" class="button primary" data-task-export>导出到此目录</button>');
    document.querySelector('#job-body .progress-card').after(card);
    card.addEventListener('input',()=>{card.dataset.dirty='true';});
  }
  if(card.dataset.job!==job.id){card.dataset.job=job.id;card.dataset.dirty='';card.dataset.busy='';}
  if(card.dataset.busy)return;
  if(!card.dataset.dirty){
    card.querySelector('[data-task-name]').value=job.display_name||job.spec?.case_name||job.case_name||'';
    card.querySelector('[data-task-directory]').value=job.task_io?.export_directory||'';
  }
  const note=card.querySelector('[data-task-io-note]'), last=job.task_io?.last_export;
  if(!card.dataset.dirty)note.textContent=job.export_pending?'正在复制成果到所选目录…':last?.state==='completed'?`已导出 ${last.file_count} 个成果文件：${last.path}`:last?.state==='failed'?`导出失败：${last.error}。原任务成果保留，可改目录后重试。`:'';
  const save=card.querySelector('[data-task-save]'), exportButton=card.querySelector('[data-task-export]');
  const finished=['completed','failed','interrupted','cancelled','stopped'].includes(job.state);
  exportButton.disabled=!finished||!!job.export_pending;
  exportButton.title=finished?'复制当前已生成的成果，不覆盖原文件':'任务结束后可导出，防止复制尚未写完的文件';
  const operate=async exporting=>{
    if(card.dataset.busy)return;
    card.dataset.busy='true';
    save.disabled=true; exportButton.disabled=true;
    try {
      const saved=await post(`/api/jobs/${job.id}/io`,readSettings(card));
      if(card.dataset.job!==job.id)return;
      card.dataset.dirty='';
      if(exporting){
        note.textContent='正在复制成果…';
        const result=await post(`/api/jobs/${job.id}/export`,{});
        if(card.dataset.job!==job.id)return;
        if(result.state!=='completed')throw new Error(result.error||'导出失败');
        note.textContent=`已导出 ${result.file_count} 个成果文件：${result.path}`;
        saved.task_io.last_export=result;
      }else note.textContent='名称与导出目录已保存。';
      onSaved(saved);
    }catch(error){if(card.dataset.job===job.id)note.textContent=error.message;}
    finally{if(card.dataset.job===job.id){card.dataset.busy='';save.disabled=false;exportButton.disabled=!finished||!!job.export_pending;}}
  };
  save.onclick=()=>operate(false);exportButton.onclick=()=>operate(true);
  mountOriginTaskIO(job,request);
}

export function mountOriginTaskIO(job,request) {
  if(document.getElementById('result-task-io')?.dataset.job!==job.id)return;
  const origin=document.querySelector('#result-content .origin-panel');
  if(origin&&!document.getElementById('task-io-origin')){
    const settings=settingsCard('task-io-origin',request,'新 Origin 绘图任务名称与成果位置');
    settings.querySelector('[data-task-name]').value=`${taskLabel(job)} · Origin`.slice(0,100);
    settings.querySelector('[data-task-directory]').value=job.task_io?.export_directory||'';
    origin.prepend(settings);
  }
}
