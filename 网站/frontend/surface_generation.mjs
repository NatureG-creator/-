const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=value=>typeof value==='number'&&Number.isFinite(value)?Number(value.toPrecision(8)):'—';
const sides=[['front','正面 · Z_filled'],['back','反面 · F_filled']];
const field=(key,label,value='',help='')=>`<div class="field"><label>${label}<input data-surface="${key}" type="number" step="any" value="${value}"></label>${help?`<small>${help}</small>`:''}</div>`;
const select=(key,label,options)=>`<div class="field"><label>${label}<select data-surface="${key}">${options.map(([v,t])=>`<option value="${v}">${t}</option>`).join('')}</select></label></div>`;
const check=(key,label,checked=false)=>`<label class="check-field"><input type="checkbox" data-surface="${key}" ${checked?'checked':''}>${label}</label>`;

export function defaultSurfaceVariable(variables){
 const preferred=variables.filter(v=>['Z_filled','F_filled'].includes(v.name));
 return preferred.length===1?preferred[0].name:variables.length===1?variables[0].name:'';
}

export function generationPayload(faces,options){
 const active=faces.filter(face=>face.enabled);
 if(!active.length)throw new Error('至少选择正面或反面');
 return {kind:'surface_generation',faces:active.map(face=>{
  const source=face.origin==='task'?{source_job_id:face.jobId}:{upload_id:face.uploadId};
  if(!Object.values(source)[0])throw new Error(`${face.side==='front'?'正面':'反面'}尚未选择来源`);
  const stage=face.stage===''||face.stage==null?undefined:Number(face.stage);
  if(stage!==undefined&&(!Number.isInteger(stage)||stage<1))throw new Error('NPZ阶段必须为正整数');
  const merged={...face.options,...options};
  for(const key of ['length_mm','width_mm','length_axis','offset_x_mm','offset_y_mm']){
   const value=merged['override_'+key];delete merged['override_'+key];
   if(value!==undefined&&value!==null&&value!=='')merged[key]=value;
  }
  return {side:face.side,...source,...(face.variable?{variable:face.variable}:{}),...(stage===undefined?{}:{stage}),options:merged};
 })};
}

export function renderGenerationSummary(summary){
 if(!summary.faces?.length)return '<p class="help-line">等待表面生成与数值校核。</p>';
 return `<div class="card wide"><h3>独立表面与 MAT 结果</h3><p>MAT 只含一个二维 double 变量；矩阵行对应 Y，列对应 X，数值单位 mm。各面分别输出，未自动配准或拼接。</p>${summary.faces.map(face=>`<div class="stage-block"><h4>${face.side==='front'?'正面 · Z_filled':'反面 · F_filled'}</h4><p>来源：${esc(face.source_name)} · 变量 ${esc(face.source_variable)} · ${face.value_mode==='depth'?'腐蚀深度':'表面高程'}</p><div class="resource-grid"><div><small>实际 X × Y 尺寸 / mm</small><strong>${fmt(face.size_x_mm)} × ${fmt(face.size_y_mm)}</strong></div><div><small>矩阵行 × 列 / 点数</small><strong>${esc(face.matrix_shape?.join(' × '))} / ${esc(face.point_count)}</strong></div><div><small>实际 X/Y 间距 / mm</small><strong>${fmt(face.dx_mm)} / ${fmt(face.dy_mm)}</strong></div><div><small>生成方式</small><strong>${face.source_resampled?'XYZ线性网格化；':''}${face.grid_mode==='exact'||(!face.grid_mode&&face.resampled)?'精确尺寸 · 双线性重采样':face.source_resampled?'保留网格化节点 · 区域内裁剪':'保留原始网格 · 区域内裁剪'}</strong></div></div><p class="help-line">长度方向 ${esc(face.length_axis)}；目标长度 ${face.requested_length_mm==null?'完整来源':fmt(face.requested_length_mm)+' mm'}，实际 ${fmt(face.actual_length_mm)} mm；实际宽度 ${fmt(face.actual_width_mm)} mm。${face.missing_filled_count?`最近邻填补 ${esc(face.missing_filled_count)} 个未覆盖格，包含边缘外推，请检查形貌。`:''}${face.duplicate_xy_count?`重复XY合并 ${esc(face.duplicate_xy_count)} 点（Z取均值）。`:''}${esc(face.npz_selection||'')} ${esc(face.point_cloud_note||'点云由规则网格展开。')}</p></div>`).join('')}</div>`;
}

export function generationPage(){
 return `<div class="section-heading"><div><div class="section-overline">INDEPENDENT SURFACE</div><h2>独立点云 / MAT 生成</h2><p>单独生成指定长度的规则表面，支持 190、60、50 mm 和自定义尺寸。正反面分别生成。</p></div><span class="badge neutral">单面即可运行</span></div>
 <div class="card"><h3>1 · 选择表面来源</h3><p class="help-line">从已有表面裁剪或网格化；不会凭空合成腐蚀。XYZ无需第二份参考扫描。NPZ读取所选阶段的模拟深度。</p><div class="actions"><button class="button secondary" id="surface-refresh">刷新已完成模拟</button><small id="surface-source-message">选择模拟任务前请刷新；上传文件无需刷新。</small></div></div>
 ${sides.map(([side,label])=>`<details class="card" data-face="${side}" open><summary><strong>${label}</strong></summary><div class="actions">${check('enabled','生成本面',side==='front')}</div><div class="grid two">${select('origin','读取方式',[['upload','上传文件'],['task','已完成模拟']])}<div class="field" data-upload-row><label>表面文件（MAT / NPZ / XYZ / TXT / CSV / TSV）<input data-surface="file" type="file" accept=".mat,.npz,.xyz,.txt,.csv,.tsv"></label><small data-upload-note>请选择本面的数据文件。MAT支持传统格式至v7.2；v7.3请用MATLAB另存-v7。</small></div><div class="field" data-task-row hidden><label>模拟任务<select data-surface="job"><option value="">请刷新并选择</option></select></label></div><div class="field" data-variable-row hidden><label>表面 / 状态变量<select data-surface="variable"></select></label></div><div data-npz-row hidden>${field('stage','NPZ 阶段（留空=最后阶段）','','已完成模拟按历史阶段从1编号；外部NPZ按所选变量内部顺序。perfect_a只含最终快照（仅1帧），历史阶段应选a_sd。')}</div></div>
 <div data-mat-xyz-row><div class="grid four">${select('unit','文件数值单位',[['mm','mm'],['um','μm']])}${select('value_mode','Z数值含义',[['height','表面高程'],['depth','正向腐蚀深度']])}${field('dx_mm','输入 X 网格间距 / mm',.3,'默认0.3 mm，请按来源核对；MAT原始列间距，XYZ网格化间距。')}${field('dy_mm','输入 Y 网格间距 / mm',.3,'MAT的行间距；XYZ的网格化间距。')}</div><div class="grid two" data-mat-row>${field('origin_x_mm','MAT X 坐标原点 / mm',0)}${field('origin_y_mm','MAT Y 坐标原点 / mm',0)}</div><div data-xyz-row hidden>${check('fill_missing','允许最近邻填补未覆盖格（含边缘外推）')}<p class="help-line">默认拒绝未覆盖格；启用后在结果中报告填补数量。同一XY多个Z取均值。</p></div></div>
 <div data-cell-row hidden><div class="grid two">${field('cell_xy_um','原模拟 XY 元胞尺寸 / μm','','文件缺少物理尺寸时必填。')}${field('cell_z_um','原模拟 Z 元胞尺寸 / μm','','已有文件尺寸不可覆盖。')}</div><p class="help-line">已完成模拟沿用冻结配置；不会使用0.3 mm拉伸模拟尺寸。原始[X,Y,Z]状态会转换为行Y、列X的深度矩阵。</p></div>
 <details><summary>本面独立裁剪（留空沿用公共设置）</summary><div class="grid two">${field('override_length_mm','本面目标长度 / mm')}${field('override_width_mm','本面目标宽度 / mm')}${select('override_length_axis','本面长度方向',[['','沿用公共方向'],['X','X方向'],['Y','Y方向']])}${field('override_offset_x_mm','本面 X 起始偏移 / mm')}${field('override_offset_y_mm','本面 Y 起始偏移 / mm')}</div></details><details><summary>坐标方向设置</summary><div class="grid two">${select('height_sign','Z 符号',[['1','保持原符号'],['-1','反转 Z 符号']])}<div class="actions">${check('transpose','转置矩阵（交换行列）')}${check('flip_x','沿X翻转')}${check('flip_y','沿Y翻转')}</div></div><p class="help-line">翻转保留坐标范围并反射高度；间距指转置前的行列；转置会交换XY方向及间距，保留物理尺度。高程和深度不会自动互换。</p></details></details>`).join('')}
 <div class="card" id="surface-dimensions"><h3>2 · 尺寸与裁剪</h3><div class="grid four">${select('preset','长度预设',[['full','完整来源'],['190','190 mm'],['60','60 mm'],['50','50 mm'],['custom','自定义']])}${field('length_mm','目标长度 / mm','','完整来源时留空。')}${field('width_mm','目标宽度 / mm','','留空采用完整宽度。')}${select('length_axis','长度方向',[['X','X方向'],['Y','Y方向']])}${select('grid_mode','网格处理',[['preserve','保留原网格（默认）'],['exact','精确尺寸（双线性插值）']])}${field('offset_x_mm','裁剪 X 起始偏移 / mm','','距来源最小X，留空居中。')}${field('offset_y_mm','裁剪 Y 起始偏移 / mm','','距来源最小Y，留空居中。')}</div><div id="surface-exact-fields" class="grid two" hidden>${field('target_dx_mm','目标最大 X 间距 / mm',.3)}${field('target_dy_mm','目标最大 Y 间距 / mm',.3)}</div><p class="help-line">MAT/NPZ保留模式只取区域内原节点，报告实际跨度，裁剪不作插值；XYZ会先按输入间距线性网格化。例如0.3 mm网格截取50 mm通常为49.8 mm。精确模式包含目标端点并均匀分格，实际间距不超过设置值。来源不足时拒绝，不平铺或放大。</p><p class="help-line">“190”示例文件可能实际仅189.3 mm；可用“完整来源”保留真实尺寸。各面可在“本面独立裁剪”覆盖公共尺寸、方向与偏移；网格模式与目标间距共用，各自预检和输出。</p></div>
 <div class="card"><h3>3 · 预检与生成</h3><div class="actions"><button class="button secondary" id="surface-inspect">预检尺寸与来源</button><button class="button primary" id="surface-run">生成点云与 MAT →</button></div><p id="surface-message" class="help-line" role="status" aria-live="polite"></p><div id="surface-preview"></div><p class="help-line">成果包含各面的单变量MAT、surface_points.csv / .xyz、表面预览、manifest.json 和 surface_bundle.zip。</p></div>`;
}

export function mountSurfaceGeneration(root,{get,post,openJob}){
 if(!root)return;
 root.innerHTML=generationPage();
 const q=s=>root.querySelector(s), records={front:{},back:{}}, revisions={front:0,back:0};
 let pending=0,busy=false;
 const note=(message,error=false)=>{q('#surface-message').textContent=message;q('#surface-message').classList.toggle('error-hint',error);};
 const buttons=()=>{for(const id of ['#surface-inspect','#surface-run'])q(id).disabled=busy||pending>0;};
 const read=container=>Object.fromEntries([...container.querySelectorAll('[data-surface]')].filter(el=>!['file','origin','job','variable','stage','enabled'].includes(el.dataset.surface)).map(el=>[el.dataset.surface,el.type==='checkbox'?el.checked:el.type==='number'?(el.value===''?null:Number(el.value)):el.value]));
 function payload(){return generationPayload(sides.map(([side])=>{
  const box=q(`[data-face="${side}"]`),v=key=>box.querySelector(`[data-surface="${key}"]`).value;
  return {side,enabled:box.querySelector('[data-surface="enabled"]').checked,origin:v('origin'),jobId:v('job'),uploadId:records[side].id,variable:v('variable'),stage:v('stage'),options:read(box)};
 }),read(q('#surface-dimensions')));}
 function visibility(){for(const [side] of sides){const box=q(`[data-face="${side}"]`),task=box.querySelector('[data-surface="origin"]').value==='task',ext=records[side].extension||'',npz=task||ext==='.npz',xyz=ext&&ext!=='.mat'&&!npz;
  for(const [selector,hidden] of [['[data-upload-row]',task],['[data-task-row]',!task],['[data-npz-row]',!npz],['[data-cell-row]',!npz],['[data-mat-xyz-row]',npz],['[data-xyz-row]',!xyz],['[data-mat-row]',xyz],['[data-variable-row]',task||!['.mat','.npz'].includes(ext)]])box.querySelector(selector).hidden=hidden;
 }const preset=q('[data-surface="preset"]').value;q('[data-surface="length_mm"]').disabled=preset!=='custom';q('#surface-exact-fields').hidden=q('[data-surface="grid_mode"]').value!=='exact';}
 async function refresh(){const jobs=await get('/api/jobs');for(const [side] of sides){const el=q(`[data-face="${side}"] [data-surface="job"]`),old=el.value;el.innerHTML='<option value="">请选择已完成模拟</option>'+(Array.isArray(jobs)?jobs:jobs.jobs||[]).filter(j=>j.kind==='simulation'&&j.state==='completed').map(j=>`<option value="${esc(j.id)}">${esc(j.display_name||j.spec?.case_name||j.case_name||j.id)} · ${esc(j.id)}</option>`).join('');el.value=old;}}
 root.addEventListener('input',()=>{q('#surface-preview').innerHTML='';});
 root.addEventListener('change',async event=>{
  const el=event.target;
  if(el.dataset.surface==='preset')q('[data-surface="length_mm"]').value=['full','custom'].includes(el.value)?'':el.value;
  const box=el.closest('[data-face]');
  if(box&&el.dataset.surface==='origin')box.querySelector('[data-surface="variable"]').value='';
  if(box&&el.dataset.surface==='file'){
   const side=box.dataset.face,token=++revisions[side],file=el.files[0],uploadNote=box.querySelector('[data-upload-note]');
   records[side]={};box.querySelector('[data-surface="variable"]').innerHTML='';box.querySelector('[data-surface="stage"]').value='';
   if(file){pending++;buttons();uploadNote.textContent='正在上传并识别…';try{
    const response=await fetch(`/api/uploads?name=${encodeURIComponent(file.name)}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
    const record=await response.json();if(!response.ok)throw new Error(record.error||'上传失败');
    if(token!==revisions[side])return;
    const ext='.'+file.name.split('.').pop().toLowerCase();let info;
    if(['.mat','.npz'].includes(ext))info=await get(`/api/uploads/${record.id}/inspect?kind=${ext==='.mat'?'surface_generation_mat':'apdl_npz'}`);
    if(token!==revisions[side])return;
    const variables=(info?.variables||[]).filter(v=>v.supported!==false);
    box.querySelector('[data-surface="variable"]').innerHTML='<option value="">请选择表面变量</option>'+variables.map(v=>`<option value="${esc(v.name)}">${esc(v.name)} · ${esc(v.shape.join(' × '))}</option>`).join('');
    box.querySelector('[data-surface="variable"]').value=ext==='.mat'?defaultSurfaceVariable(variables):info?.default_variable||'';
    for(const [key,name] of [['space_xy_um','cell_xy_um'],['space_z_um','cell_z_um']])box.querySelector(`[data-surface="${name}"]`).value=info?.geometry?.[key]??'';
    records[side]={id:record.id,extension:ext};uploadNote.textContent=`${file.name}${variables.length?' · '+variables.map(v=>`${v.name} (${v.shape.join('×')})`).join(' / '):' · 已上传，预检会读取实际坐标'}`;
   }catch(error){if(token===revisions[side]){uploadNote.textContent=error.message;note(error.message,true);}}
   finally{pending--;buttons();visibility();}}
  }
  visibility();q('#surface-preview').innerHTML='';
 });
 q('#surface-refresh').onclick=async()=>{const button=q('#surface-refresh'),message=q('#surface-source-message');button.disabled=true;message.textContent='正在读取已完成模拟…';try{await refresh();message.textContent='已刷新来源任务。';}catch(error){message.textContent=error.message;}finally{button.disabled=false;}};
 for(const [id,run] of [['#surface-inspect',false],['#surface-run',true]])q(id).onclick=async()=>{
  busy=true;buttons();try{const body=payload(),snapshot=JSON.stringify(body);note(run?'正在校核来源并创建生成任务…':'正在预检实际尺寸…');
   const result=await post(run?'/api/jobs':'/api/surface-generation/inspect',body);
   if(run)await openJob(result.id);else if(snapshot===JSON.stringify(payload())){q('#surface-preview').innerHTML=renderGenerationSummary(result);note('预检通过；请核对实际尺寸与插值方式。');}else note('参数已变化，请重新预检。');
  }catch(error){note(error.message,true);}finally{busy=false;buttons();}
 };
 visibility();
}
