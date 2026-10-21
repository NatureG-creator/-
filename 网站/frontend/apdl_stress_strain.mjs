const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function selectedStressStrainSources(rows){
 const selected=rows.filter(row=>row.checkbox.checked);
 if(selected.length<2||selected.length>20)throw new Error('请选择 2 至 20 个已完成的 APDL 求解任务');
 return selected.map(row=>{
  const label=row.label.value.trim();
  if(!label||label.length>80||/[\x00-\x1f]/.test(label))throw new Error('请为每条曲线填写 1 至 80 个可显示字符；腐蚀天数不会从任务名自动推断');
  return {job_id:row.checkbox.dataset.jobId,label};
 });
}

export function mountApdlStressStrain(root,{job,get,post}){
 if(!root||root.querySelector('#apdl-stress-strain'))return;
 const section=document.createElement('section');section.id='apdl-stress-strain';section.className='card wide';
 section.innerHTML=`<h3>多任务应力—应变曲线对比</h3><p class="help-line">只读取已完成且通过 APDL 后处理的任务。横轴取结果 CSV 第 5 列工程应变（无量纲小数）并乘 100，标为 Engineering strain (%)；纵轴直接取第 6 列名义应力（MPa）。不重算、不平滑、不重采样。每条曲线名称请手工填写，避免把任务名误当作腐蚀天数。</p><div class="actions"><button id="stress-source-load" class="button secondary">加载已完成求解任务</button></div><div id="stress-source-list" class="case-list"></div><div class="actions"><button id="stress-create" class="button primary" disabled>生成对比图和数据</button></div><p id="stress-note" class="help-line" role="status"></p><div id="stress-result" hidden></div>`;
 root.append(section);
 const q=selector=>section.querySelector(selector),note=text=>{q('#stress-note').textContent=text;};
 let busy=false;
 const rows=()=>[...q('#stress-source-list').querySelectorAll('.case-row')].map(row=>({checkbox:row.querySelector('input[type=checkbox]'),label:row.querySelector('[data-curve-label]')}));
 function setBusy(value){busy=value;q('#stress-source-load').disabled=value;q('#stress-source-list').querySelectorAll('input').forEach(input=>input.disabled=value);updateButton();}
 q('#stress-source-load').onclick=async()=>{
  if(busy)return;
  setBusy(true);note('正在读取已完成的 APDL 求解任务…');
  try{
   const sources=await get('/api/apdl/stress-strain/sources');
   q('#stress-source-list').innerHTML=sources.length?sources.map(source=>`<div class="case-row"><label class="check-field"><input type="checkbox" data-job-id="${esc(source.id)}"><span>${esc(source.name)} · ${esc(source.id)}</span></label><label class="field">曲线名称（手工确认）<input type="text" maxlength="80" data-curve-label placeholder="例如：腐蚀 60 天"></label></div>`).join(''):'<p class="empty-state small">没有可用的已完成 APDL 求解结果。</p>';
   q('#stress-source-list').querySelectorAll('input[type=checkbox]').forEach(input=>input.checked=input.dataset.jobId===job.id);
   q('#stress-source-list').querySelectorAll('input[type=checkbox]').forEach(input=>input.addEventListener('change',updateButton));
   q('#stress-source-list').querySelectorAll('[data-curve-label]').forEach(input=>input.addEventListener('input',updateButton));
   updateButton();note(`找到 ${sources.length} 个已完成且可用于绘图的 APDL 求解任务。`);
  }catch(error){note(error.message);}
  finally{setBusy(false);}
 };
 function updateButton(){let valid=false;try{selectedStressStrainSources(rows());valid=true;}catch{}q('#stress-create').disabled=busy||!valid;}
 q('#stress-create').onclick=async()=>{
  if(busy)return;
  setBusy(true);
  try{
   const sources=selectedStressStrainSources(rows());note('正在读取并核验曲线、生成图像与报告…');
   const report=await post('/api/apdl/stress-strain/comparisons',{sources});
   const prefix=`/api/apdl/stress-strain-comparisons/${encodeURIComponent(report.id)}/`;
   q('#stress-result').hidden=false;
   q('#stress-result').innerHTML=`<img src="${prefix}curve.png" alt="工程应变与名义应力多任务对比图" style="display:block;width:100%;max-width:1000px;height:auto;margin:18px 0"><p>${report.sources.length} 条曲线；横轴工程应变百分数，纵轴名义应力 MPa。CSV 中保留每条曲线的源任务编号与名称。原始应力符号保留，绘图不代表新增求解验收；来源校核限制见 report.json。</p><div class="actions">${['curve.png','curve.svg','curve.csv','report.json'].map(name=>`<a class="button secondary" href="${prefix}${name}?download=1" download>${name}</a>`).join('')}</div>`;
   note(`对比成果已保存，编号 ${report.id}；来源任务 ${report.sources.map(source=>source.job_id).join('、')}`);
  }catch(error){note(error.message);}
  finally{setBusy(false);}
 };
}
