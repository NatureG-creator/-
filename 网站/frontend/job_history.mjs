import {isTerminal} from './state.mjs';

export function historyDay(job){
  const date=new Date(typeof job.created_at==='number'?job.created_at*1000:job.created_at);
  return Number.isNaN(date.getTime())?'时间未知':new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
}
export function historyDates(jobs){return [...new Set(jobs.map(historyDay))].sort().reverse();}

export function checkpointNotice(job){
  const saved=job.checkpoint?.saved;
  if(!saved)return '';
  return '磁盘检查点：阶段 '+saved.stage+' · 已完成 '+saved.generation_completed+' 代'+
    (saved.completed?' · 本阶段已计算完成':' · 第 '+saved.generation+' 代已保存 '+saved.completed_individuals+' 个体评价')+
    '。恢复前将核对配置、输入和文件完整性。';
}

export function historyControls(job){
  if(!isTerminal(job.state)||job.export_pending)return '';
  const action=job.history_hidden?'unhide':'hide';
  return `${job.history_hidden?'<span class="badge neutral">已隐藏</span>':''}<button class="button ghost" data-history-action="${action}" data-job-id="${job.id}">${job.history_hidden?'恢复显示':'隐藏'}</button><button class="button danger" data-history-action="delete" data-job-id="${job.id}">永久删除</button>`;
}

export function resumeNotice(job){
  if(job?.checkpoint?.backend==='pycharm')
    return '恢复请求已提交：从阶段内检查点继续，复用已保存个体评价；未保存个体按原种子重算。';
  return job?.spec?.config?.mode==='pycharm'
    ?'恢复请求已提交：复用已完成阶段；中断阶段将按原配置重新计算。'
    :'恢复请求已提交：有效配置和随机状态由完整检查点恢复；尚未保存的工作重新计算。';
}

export function bindHistoryActions(root,{post,refresh,onDeleted=()=>{},report,jobs=[],confirmDelete=text=>window.confirm(text)}){
  if(root.ownerDocument)mountHistorySelection(root,{post,refresh,onDeleted,report,confirmDelete,jobs});
  root.querySelectorAll('[data-history-action]').forEach(button=>button.addEventListener('click',async()=>{
    const {historyAction:action,jobId:id}=button.dataset;
    if(action==='delete'&&!confirmDelete(`永久删除任务 ${id}？\n将删除该任务的输入副本、结果、日志和检查点，之后不能续算。\n外部已导出的副本保留。此操作无法撤销。`))return;
    button.disabled=true;
    try{
      await post(`/api/jobs/${encodeURIComponent(id)}/${action}`,action==='delete'?{confirm_job_id:id}:{});
      if(action==='delete')onDeleted(id);
      report(action==='delete'?'任务记录及其任务目录已永久删除。':action==='hide'?'记录已隐藏，结果和续算检查点保留。勾选“包含已隐藏记录”可恢复显示。':'记录已恢复显示。');
      await refresh();
    }catch(error){report(error.message,true);}
    finally{button.disabled=false;}
  }));
}

function mountHistorySelection(root,{post,refresh,onDeleted,report,confirmDelete,jobs}){
  try{
    const byId=new Map(jobs.map(job=>[job.id,job]));
    let toolbar=document.querySelector('#history-selection');
    const previous=toolbar?.querySelector('select')?.value||'';
    if(!toolbar){toolbar=document.createElement('div');toolbar.id='history-selection';toolbar.className='actions';root.before(toolbar);}
    toolbar.replaceChildren();
    const label=document.createElement('label');label.textContent='按日期（北京时间） ';
    const select=document.createElement('select');
    for(const day of ['',...historyDates(jobs)]){const option=document.createElement('option');option.value=day;option.textContent=day||'全部日期';select.append(option);}
    if([...select.options].some(o=>o.value===previous))select.value=previous;
    label.append(select);toolbar.append(label);
    const all=document.createElement('button');all.className='button secondary';all.textContent='全选当日可删除记录';
    const remove=document.createElement('button');remove.className='button danger';
    const countLabel=document.createElement('span');countLabel.className='help-line';
    toolbar.append(all,remove,countLabel);
    const rows=[];
    for(const open of root.querySelectorAll('[data-open]')){
      const job=byId.get(open.dataset.open),row=open.closest('.history-item');if(!job||!row)continue;
      const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.setAttribute('aria-label','选择任务 '+job.id);
      checkbox.disabled=!isTerminal(job.state)||job.export_pending===true;
      row.prepend(checkbox);rows.push({row,job,checkbox});
      if(checkpointNotice(job)){
        const saved=document.createElement('p');saved.className='help-line';saved.textContent=checkpointNotice(job);
        row.querySelector('.history-info > div').append(saved);
      }
      if(job.kind==='simulation'&&['failed','interrupted'].includes(job.state)&&!job.checkpoint?.available){
        const note=document.createElement('p');note.className='help-line';
        note.textContent=job.spec?.config?.mode==='fast'?'无法恢复：Taichi 模式不支持续算。':'无法恢复：尚无完整检查点或已完成阶段；可查看并载入原配置新建任务。';
        row.querySelector('.history-info > div').append(note);
      }
    }
    function update(){const visible=rows.filter(r=>!r.row.hidden),count=visible.filter(r=>r.checkbox.checked).length;remove.textContent='删除已选（'+count+'）';remove.disabled=count===0;countLabel.textContent='显示 '+visible.length+' / '+rows.length+' 条；引用中的任务由服务端拒绝删除。';}
    function filter(){for(const r of rows){r.row.hidden=!!select.value&&historyDay(r.job)!==select.value;r.checkbox.checked=false;}update();}
    select.onchange=filter;
    for(const r of rows)r.checkbox.onchange=update;
    all.onclick=()=>{const available=rows.filter(r=>!r.row.hidden&&!r.checkbox.disabled),checked=available.some(r=>!r.checkbox.checked);for(const r of available)r.checkbox.checked=checked;update();};
    remove.onclick=async()=>{
      const ids=rows.filter(r=>!r.row.hidden&&r.checkbox.checked).map(r=>r.job.id);
      if(!ids.length||!confirmDelete('永久删除所选 '+ids.length+' 个任务及其输入、结果、日志和检查点？外部导出副本保留；此操作不可撤销。'))return;
      remove.disabled=true;
      try{const result=await post('/api/jobs/delete-batch',{job_ids:ids,confirm_job_ids:ids});for(const id of result.deleted_ids||[])onDeleted(id);report(result.error||'已删除 '+result.deleted_ids.length+' 个任务。',!!result.error);await refresh();}
      catch(error){report(error.message,true);update();}
    };
    filter();
  }catch(error){report(error.message,true);}
}
