import {apdlDefaults} from './apdl.mjs?v=20261021-baseline-mat';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const numeric=(value,label)=>{if(value===''||value==null||!Number.isFinite(Number(value)))throw new Error(`请填写${label}`);return Number(value);};
const fmt=value=>Number(value).toLocaleString('zh-CN',{maximumSignificantDigits:6});

export function baselineOptions(fields){
 const options={output_variable:'baseline',matrix_only:true};
 for(const [key,label] of Object.entries({window_size:'平滑窗口',gaussian_sigma:'高斯 sigma',expand_factor:'放大倍数 N',physical_layers:'物理 Z 层数 n'}))options[key]=numeric(fields[key],label);
 if(!Number.isInteger(options.window_size)||options.window_size<1||options.window_size>101||options.window_size%2!==1)throw new Error('平滑窗口必须为 1～101 的奇数');
 if(options.gaussian_sigma<0||options.gaussian_sigma>100)throw new Error('高斯 sigma 必须为 0～100');
 if(!Number.isInteger(options.expand_factor)||options.expand_factor<1||options.expand_factor>10)throw new Error('放大倍数 N 必须为 1～10 的整数');
 if(!Number.isInteger(options.physical_layers)||options.physical_layers<1)throw new Error('物理 Z 层数 n 必须为正整数');
 return options;
}

export function baselineApdlDraft(job,current){
 if(job.spec?.options?.matrix_only)throw new Error('纯矩阵的物理尺寸请在有限元建模时设置');
 if(job.state!=='completed'||job.spec?.options?.output_variable!=='baseline')throw new Error('请先完成 baseline 表面转换');
 const draft=current?structuredClone(current):apdlDefaults();
 draft.case_name=(job.display_name||job.spec.case_name||job.id)+' · 有限元';
 draft.registration_confirmed=false;
 draft.options.mapping_profile='manual';
 draft.options.corrosion_mode='single_top';
 draft.top=apdlDefaults().top;
 Object.assign(draft.top,{origin:'task',source_kind:'measured',source_job_id:job.id,source_file:'baseline.mat'});
 draft.top.mapping.variable='baseline';
 return draft;
}

export function renderBaselineResult(job){
 if(job.spec?.options?.output_variable!=='baseline')return '';
 const r=job.result||{},o=job.spec.options;
 if(o.matrix_only)return `<div class="card wide"><h3>NPZ → MAT 二维矩阵</h3><p>MAT 文件只包含 baseline 数值矩阵，每个行列位置对应一个表面层号值（从 1 开始），不换算物理单位。</p><p>平滑窗口 ${esc(o.window_size??1)}；高斯 sigma ${esc(o.gaussian_sigma??0)}；放大倍数 N ${esc(o.expand_factor??1)}；物理 Z 层数 n ${esc(o.physical_layers)}。</p>${r.shape?`<p>矩阵 ${r.shape.map(esc).join(' × ')}；数值范围 ${r.value_range_cells.map(fmt).join(' ～ ')}。</p>`:''}${job.state==='completed'?`<div class="actions"><a class="button primary" href="/api/jobs/${encodeURIComponent(job.id)}/download/baseline.mat" download>下载 baseline.mat</a></div>`:''}</div>`;
 return `<div class="card wide"><h3>NPZ → MATLAB baseline 表面</h3><p>MAT 中的 baseline 保留 MATLAB 从 1 开始的层号；平滑窗口 ${esc(o.window_size)}，高斯 sigma ${esc(o.gaussian_sigma)}，不放大网格。</p><p>XY / Z 元胞尺寸：${esc(o.space_xy_um)} / ${esc(o.space_z_um)} μm；阶段 ${esc(o.npz_stage)}，变量 ${esc(o.npz_variable)}。</p>${r.shape?`<p>矩阵 ${r.shape.map(esc).join(' × ')}；X / Y 跨度 ${r.span_mm.map(fmt).join(' / ')} mm；相对最高点的深度范围 ${r.value_range_mm.map(fmt).join(' ～ ')} mm。</p>`:''}<p class="help-line">${esc(o.configuration_provenance)}。有限元按 −baseline × Z 元胞厚度形成高度，再以最高点为参考面换算正深度；CSV 和预览的单位为 mm。该参考面不表示原始质量损失或绝对减薄。</p>${job.state==='completed'?`<div class="actions"><a class="button secondary" href="/api/jobs/${encodeURIComponent(job.id)}/download/baseline.mat" download>下载 baseline.mat</a><button class="button primary" id="baseline-to-apdl">转入有限元正面 →</button></div>`:''}</div>`;
}

export function mountBaseline(root,{get,post,openJob}){
 if(!root)return;
 root.innerHTML=`<div class="card"><div class="card-heading"><div><h3>模拟结果 → MATLAB 表面</h3><p>按原 moving_avg_3D 流程提取表面、高斯滤波、镜像移动平均，再按 N 做最近邻放大；MAT 只保存 baseline 数值矩阵。</p></div><button type="button" id="baseline-import-external" class="button primary">导入外部 .npz</button></div><div class="grid two"><div class="field"><label for="baseline-source">模拟结果来源</label><select id="baseline-source"><option value="upload">上传外部 .npz（任意文件名）</option></select></div><div class="field" id="baseline-npz-field"><label for="baseline-npz">外部模拟结果 .npz</label><input id="baseline-npz" type="file" accept=".npz"><small>无需先创建模拟任务。支持数值 perfect_a / a_sd 三维元胞状态或四维阶段数据。</small></div></div><div class="actions"><button type="button" id="baseline-inspect" class="button secondary">读取 NPZ</button></div><p id="baseline-info" class="help-line" role="status">选择模拟任务或上传 NPZ，读取后即可生成 MAT。</p><div class="grid four"><div class="field"><label for="baseline-variable">状态变量</label><select id="baseline-variable"><option value="">读取后选择</option></select></div><div class="field"><label for="baseline-stage">阶段（存储顺序）</label><input id="baseline-stage" type="number" min="1" step="1"></div><div class="field"><label for="baseline-physical_layers">物理 Z 层数 n</label><input id="baseline-physical_layers" type="number" min="1" step="1"><small>通常为存储 Z 层数减 1；无金属位置使用 n+1。</small></div><div class="field"><label for="baseline-window_size">平滑窗口（奇数）</label><input id="baseline-window_size" type="number" min="1" max="101" step="2" value="5"><small>untitled.m 示例为 5，CA.m 调用为 11；越大越平滑。</small></div><div class="field"><label for="baseline-gaussian_sigma">高斯 sigma</label><input id="baseline-gaussian_sigma" type="number" min="0" max="100" step="any" value="1"><small>原函数为 1；设为 0 可关闭高斯滤波。</small></div><div class="field"><label for="baseline-expand_factor">放大倍数 N</label><input id="baseline-expand_factor" type="number" min="1" max="10" step="1" value="1"><small>原脚本示例为 1；大于 1 时按最近邻重复各行各列。</small></div></div><p id="baseline-output-shape" class="help-line"></p><div class="actions"><button type="button" id="baseline-create" class="button primary" disabled>生成 baseline.mat →</button></div><p id="baseline-message" class="help-line" role="status"></p></div>`;
 const q=s=>root.querySelector(s);
 let upload=null,info=null,busy=false;
 const note=(text,error=false)=>{q('#baseline-message').textContent=text;q('#baseline-message').classList.toggle('error-hint',error);};
 const invalidate=()=>{info=null;q('#baseline-create').disabled=true;q('#baseline-info').textContent='来源已变更，请重新读取。';q('#baseline-output-shape').textContent='';};
 function source(){const id=q('#baseline-source').value;if(id!=='upload')return {source_job_id:id};if(!upload)throw new Error('请先上传 NPZ');return {upload_id:upload.id};}
 function outputShape(){const factor=Number(q('#baseline-expand_factor').value);q('#baseline-output-shape').textContent=info&&Number.isInteger(factor)&&factor>=1&&factor<=10?`原矩阵 w × l：${info.state_shape.slice(0,2).join(' × ')}；输出矩阵：${info.state_shape.slice(0,2).map(v=>v*factor).join(' × ')}。`:'';}
 function buttons(){q('#baseline-import-external').disabled=busy;q('#baseline-inspect').disabled=busy;q('#baseline-create').disabled=busy||!info;root.querySelectorAll('input,select').forEach(el=>el.disabled=busy);}
 async function inspect(){if(busy)return;busy=true;buttons();note('正在读取 NPZ…');try{const requested=q('#baseline-variable').value;info=await post('/api/baseline/inspect',{...source(),...(requested?{npz_variable:requested}:{})});q('#baseline-variable').innerHTML=info.variables.filter(v=>v.supported).map(v=>`<option value="${esc(v.name)}">${esc(v.name)} · ${v.state_shape.join(' × ')}</option>`).join('');q('#baseline-variable').value=info.npz_variable;q('#baseline-stage').max=info.stage_count;q('#baseline-stage').value=info.stage_count;q('#baseline-physical_layers').value=info.physical_layers;q('#baseline-physical_layers').min=info.state_shape[2]-1;q('#baseline-physical_layers').max=info.state_shape[2];q('#baseline-info').textContent=`${info.name}；原状态 ${info.state_shape.join(' × ')}；w / l 从文件自动读取。`;outputShape();note('已读取，请确认生成参数后生成 MAT。');}catch(error){info=null;note(error.message,true);}finally{busy=false;buttons();}}
 q('#baseline-source').addEventListener('change',()=>{invalidate();q('#baseline-variable').innerHTML='<option value="">读取后选择</option>';const local=q('#baseline-source').value==='upload';q('#baseline-npz-field').hidden=!local;});
 q('#baseline-npz').addEventListener('change',async event=>{invalidate();upload=null;q('#baseline-variable').innerHTML='<option value="">读取后选择</option>';const file=event.target.files[0];if(!file)return;busy=true;buttons();try{const response=await fetch('/api/uploads?name='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});const value=await response.json();if(!response.ok)throw new Error(value.error||'上传失败');upload=value;note('NPZ 已上传，请读取 NPZ。');}catch(error){note(error.message,true);}finally{busy=false;buttons();}});
 function showExternalUpload(){if(busy)return;const source=q('#baseline-source');if(source.value!=='upload'){source.value='upload';source.dispatchEvent(new Event('change'));}root.scrollIntoView({block:'start'});q('#baseline-npz').focus();}
 q('#baseline-import-external').addEventListener('click',()=>{if(busy)return;showExternalUpload();q('#baseline-npz').click();});
 q('#baseline-variable').addEventListener('change',inspect);
 q('#baseline-inspect').addEventListener('click',inspect);
 q('#baseline-expand_factor').addEventListener('input',outputShape);
 q('#baseline-create').addEventListener('click',async()=>{if(busy||!info)return;busy=true;buttons();try{const fields=Object.fromEntries(['window_size','gaussian_sigma','expand_factor','physical_layers'].map(key=>[key,q('#baseline-'+key).value]));const options=baselineOptions(fields);if(![info.state_shape[2]-1,info.state_shape[2]].includes(options.physical_layers))throw new Error('请核对物理 Z 层数 n');const job=await post('/api/finite-element/exports',{...source(),source_kind:'simulation',npz_variable:q('#baseline-variable').value,npz_stage:numeric(q('#baseline-stage').value,'阶段'),options});note('表面转换任务已提交：'+job.id);await openJob(job.id,job);}catch(error){note(error.message,true);}finally{busy=false;buttons();}});
 get('/api/jobs').then(jobs=>{q('#baseline-source').innerHTML='<option value="upload">上传外部 .npz（任意文件名）</option>'+jobs.filter(j=>j.kind==='simulation'&&j.state==='completed').map(j=>`<option value="${esc(j.id)}">${esc(j.display_name||j.case_name||j.id)}</option>`).join('');}).catch(error=>note(error.message,true));
 return {showExternalUpload};
}
