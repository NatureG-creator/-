const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=value=>typeof value==='number'&&Number.isFinite(value)?Number(value).toPrecision(6):'—';

export function hasMorphologyArchive(job){return (job.files||[]).some(file=>(typeof file==='string'?file:file.name)==='morphology_bundle.zip');}
export function morphologyModeNote(mode){
 if(mode==='both')return '同一份冻结 NPZ 分别进行 GA 同口径验收和精细形貌分析；对照坑数、参数与分布。两种规则不同，指标不能直接混用。';
 if(mode==='surface')return '实测 MAT 直接生成表面形貌和规则网格坐标，不套用 CA/GA 的坑检测参数或六指标验收口径。';
 return mode==='ga'?'用于核对 GA 优化口径。窗口、突出度、邻域与阈值按评价路径确定；不因图形偏态而删坑或改参数。':'保留较细的局部形貌与小坑；坑数和分布可与 GA 评价不同，不能直接代替优化验收。';
}

const MORPHOLOGY_EXPORT_FORMATS=['png','pdf','svg'];
const MORPHOLOGY_EXPORT_LABELS={png:'PNG（高清）',pdf:'PDF（论文矢量）',svg:'SVG（可编辑矢量）'};
const MORPHOLOGY_MODE_NAMES={ga:'GA 同口径验收',detail:'精细形貌分析'};

export function normalizeMorphologyExportFormats(formats){
 const values=Array.isArray(formats)?[...new Set(formats)]:[];
 if(!values.length||values.some(format=>!MORPHOLOGY_EXPORT_FORMATS.includes(format)))throw new Error('至少选择一种有效导出格式：PNG、PDF 或 SVG');
 return values;
}

function comparisonCell(value){return value==null||value===''?'—':typeof value==='number'&&Number.isFinite(value)?num(value):esc(value);}
function comparisonSource(modes){
 const reports=Object.values(modes||{}),metadata=reports.map(report=>report?.metadata||{}),names=[...new Set(metadata.map(item=>item.source_name).filter(Boolean))],hashes=[...new Set(metadata.map(item=>item.source_sha256).filter(Boolean))];
 return names.length===1&&hashes.length<=1?`同一冻结来源：${esc(names[0])}`:'来源或冻结哈希不一致，请先复核分析口径。';
}
function comparisonTable(modes,rows){
 return `<div class="table-wrap"><table><thead><tr><th>比较项</th><th>${MORPHOLOGY_MODE_NAMES.ga}</th><th>${MORPHOLOGY_MODE_NAMES.detail}</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${esc(row.label)}</td><td>${comparisonCell(row.ga)}</td><td>${comparisonCell(row.detail)}</td></tr>`).join('')}</tbody></table></div>`;
}
export function renderMorphologyComparison(modes){
 const ga=modes?.ga||{},detail=modes?.detail||{},gm=ga.metadata||{},dm=detail.metadata||{};
 const rows=[
  {label:'有效坑数',ga:ga.valid_count,detail:detail.valid_count},
  {label:'窗口大小',ga:gm.window_size,detail:dm.window_size},
  {label:'高斯 σ',ga:gm.gaussian_sigma,detail:dm.gaussian_sigma},
  {label:'突出度',ga:gm.min_prominence,detail:dm.min_prominence},
  {label:'最小间距',ga:gm.min_distance,detail:dm.min_distance},
  {label:'邻域',ga:gm.neighborhood,detail:dm.neighborhood},
  {label:'分水岭阈值',ga:gm.threshold,detail:dm.threshold},
  {label:'放大倍数',ga:gm.expand_factor,detail:dm.expand_factor},
  {label:'坑深对数均值',ga:ga.log_depth?.mean,detail:detail.log_depth?.mean},
  {label:'坑深对数标准差',ga:ga.log_depth?.std,detail:detail.log_depth?.std},
  {label:'坑深 Shapiro p',ga:ga.log_depth?.shapiro_p,detail:detail.log_depth?.shapiro_p},
  {label:'径深比对数均值',ga:ga.log_ratio?.mean,detail:detail.log_ratio?.mean},
  {label:'径深比对数标准差',ga:ga.log_ratio?.std,detail:detail.log_ratio?.std},
  {label:'径深比 Shapiro p',ga:ga.log_ratio?.shapiro_p,detail:detail.log_ratio?.shapiro_p},
 ];
 const metrics=['平均腐蚀深度 / μm','不均匀腐蚀深度 / μm','对数径深比均值','对数坑深均值','对数径深比标准差','对数坑深标准差'];
 const metricRows=metrics.map((label,index)=>({label,ga:ga.six_metrics?.[index],detail:detail.six_metrics?.[index]}));
 const notes=[ga.log_depth?.normality_note,detail.log_depth?.normality_note,ga.log_ratio?.normality_note,detail.log_ratio?.normality_note].filter(Boolean);
 return `<div class="card wide morphology-comparison"><h3>双模式对照</h3><p>${comparisonSource(modes)}</p><p class="help-line">两列使用同一份输入和同一阶段；参数不同会改变坑的数量和分布。六指标仅作模式内记录，不能把两种分析规则混成一个结果。</p><h4>分析参数与分布检验</h4>${comparisonTable(modes,rows)}<h4>六指标对照</h4>${comparisonTable(modes,metricRows)}${notes.length?`<div class="notice"><p>${[...new Set(notes)].map(esc).join('<br>')}</p></div>`:''}</div>`;
}

function renderMorphologySingleResult(summary){
 const m=summary.metadata||{},labels=['平均腐蚀深度 / μm','不均匀腐蚀深度 / μm','对数径深比均值','对数坑深均值','对数径深比标准差','对数坑深标准差'];
 if(m.source_type==='mat_surface')return `<div class="card wide"><h3>实测表面形貌</h3><p>来源：${esc(m.source_name)} · 变量 ${esc(m.source_variable||'—')} · 矩阵 ${esc(m.matrix_shape?.join(' × ')||'—')}</p><div class="notice"><strong>二维 MAT 规则网格</strong>：${esc(m.value_mode)} / ${esc(m.input_unit)}，XY ${esc(m.dx_mm)} × ${esc(m.dy_mm)} mm；表面范围 ${esc(m.surface_range_um?.map(v=>num(v)).join(' ～ ')||'—')} μm，均值 ${num(m.surface_mean_um)} μm，标准差 ${num(m.surface_std_um)} μm。${esc(m.reference_assumption||'')}<br>本任务只保留实测表面和坐标，不套用 CA/GA 坑数量、坑径或六指标验收口径。结果文件包含 <code>surface_points.csv</code> 和 <code>surface_points.xyz</code>，点云由规则网格行列展开，不是原始散乱扫描点云。</div><p class="help-line">${esc(summary.extraction||'')} ${esc(summary.warnings?.join('；')||'')}</p></div>`;
 if(m.source_type==='mat_surface')return `<div class="card wide"><h3>实测表面形貌</h3><p>来源：${esc(m.source_name)} · 变量 ${esc(m.source_variable||'—')} · 矩阵 ${esc(m.matrix_shape?.join(' × ')||'—')}</p><div class="notice"><strong>二维 MAT 规则网格</strong>：${esc(m.value_mode)} / ${esc(m.input_unit)}，XY ${esc(m.dx_mm)} × ${esc(m.dy_mm)} mm；表面范围 ${esc(m.surface_range_um?.map(v=>num(v)).join(' ～ ')||'—')} μm，均值 ${num(m.surface_mean_um)} μm，标准差 ${num(m.surface_std_um)} μm。${esc(m.reference_assumption||'')}<br>本任务只保留实测表面和坐标，不套用 CA/GA 坑数量、坑径或六指标验收口径。结果文件包含 <code>surface_points.csv</code> 和 <code>surface_points.xyz</code>，点云由规则网格行列展开，不是原始散乱扫描点云。</div><p class="help-line">${esc(summary.extraction||'')} ${esc(summary.warnings?.join('；')||'')}</p></div>`;
 const matrixNote=m.source_type==='mat_surface'?`<div class="notice"><strong>二维 MAT 表面</strong>：${esc(m.source_variable||'')}，矩阵 ${esc(m.matrix_shape?.join(' × ')||'—')}；${esc(m.value_mode)} / ${esc(m.input_unit)}，XY ${esc(m.dx_mm)} × ${esc(m.dy_mm)} mm。点云由规则网格展开，结果文件中包含 <code>surface_points.csv</code> 和 <code>surface_points.xyz</code>；它们不等同于原始散乱扫描点云。${esc(m.point_cloud_note||'')}</div>`:'';
 return `<div class="card wide"><h3>${esc(m.mode_label||'腐蚀形貌分布分析')}</h3><p>来源：${esc(m.source_name)} · 有效正深度样本 ${esc(summary.valid_count)} 个 · 空边界回退 ${esc(m.boundary_fallback_count??0)} 个</p><p class="help-line">窗口 ${esc(m.window_size)} · 高斯 σ=${esc(m.gaussian_sigma)} · 突出度 ${esc(m.min_prominence)} · 间距 ${esc(m.min_distance)} · 邻域 ${esc(m.neighborhood)} · 分水岭阈值 ${esc(m.threshold)} · 放大 ${esc(m.expand_factor)} · XY/Z ${esc(m.space_xy_um)}/${esc(m.space_z_um)} μm · 柱宽 ${esc(m.log_bin_width)}</p>${matrixNote}<div class="notice">${esc(m.configuration_provenance)}<br>${esc(m.layer_rule)}<br>红线为正态参考曲线，有曲线不代表样本通过正态检验；小样本未拒绝也不等于证明正态。</div>${['log_depth','log_ratio'].map((key,i)=>`<p><strong>${i?'径深比对数':'坑深对数'}：</strong>${esc(summary[key]?.normality_note)}；Shapiro p=${num(summary[key]?.shapiro_p)}</p>`).join('')}${summary.six_metrics?`<div class="table-wrap"><table><thead><tr><th>本模式指标（不同模式不可直接混用）</th><th>数值</th></tr></thead><tbody>${labels.map((label,i)=>`<tr><td>${label}</td><td>${num(summary.six_metrics[i])}</td></tr>`).join('')}</tbody></table></div>`:''}<p class="help-line">${esc(summary.objective_note)}</p></div>`;
}

export function mountMorphologyExport(root,job,{post,openJob}){
 if(job.kind!=='morphology_analysis'||job.state!=='completed')return;
 if(job.spec?.source_type==='mat_surface'){const box=document.createElement('div');box.className='card wide';box.innerHTML='<h3>实测表面成果下载</h3><p>整包 ZIP 包含源 MAT、分析配置、表面报告、PNG 形貌图和 CSV/XYZ 点云。</p><a class="button secondary" href="/api/jobs/'+encodeURIComponent(job.id)+'/download/morphology_bundle.zip" download>下载成果整包 ZIP</a>';root.prepend(box);return;}
 const box=document.createElement('div');box.className='card wide';
 box.innerHTML='<h3>高清导出与整包下载</h3><p>预览默认生成 PNG。高清导出复用已保存的分析数组，只生成勾选格式；成果 ZIP 包含来源、配置、分析数组、报告和图片。</p><div class="benchmark-modes morphology-export-formats">'+MORPHOLOGY_EXPORT_FORMATS.map(format=>`<label class="check-field"><input type="checkbox" data-export-format="${format}" ${format==='pdf'||format==='svg'?'checked':''}>${MORPHOLOGY_EXPORT_LABELS[format]}</label>`).join('')+'</div><button class="button secondary" data-export>导出所选高清格式</button> <a class="button secondary" href="/api/jobs/'+encodeURIComponent(job.id)+'/download/morphology_bundle.zip" download>下载成果整包 ZIP</a><p role="status"></p>';
 const archive=box.querySelector('a');
 if(!hasMorphologyArchive(job)){archive.remove();const note=document.createElement('p');note.className='help-line';note.textContent='本任务未生成成果 ZIP，已有文件可在下方逐项下载。';box.append(note);}
 root.prepend(box);const button=box.querySelector('button');
 button.onclick=async()=>{button.disabled=true;try{const formats=normalizeMorphologyExportFormats([...box.querySelectorAll('[data-export-format]:checked')].map(input=>input.dataset.exportFormat));const result=await post('/api/jobs',{kind:'morphology_export',source_job_id:job.id,formats});await openJob(result.id);}catch(error){box.querySelector('[role=status]').textContent=error.message;}finally{button.disabled=false;}};
}

export function morphologyPayload({mode,jobId,uploadId,geometry,sourceStage,sourceKind,surfaceVariable,surfaceOptions}){
 if(!['ga','detail','both','surface'].includes(mode))throw new Error('请选择有效分析模式');
 if(Boolean(jobId)===Boolean(uploadId))throw new Error('请选择一个来源');
 if(uploadId&&sourceStage!=null&&(!Number.isInteger(sourceStage)||sourceStage<1))throw new Error('NPZ 阶段必须为正整数');
 return {kind:'morphology_analysis',analysis_mode:mode,...(uploadId?{upload_id:uploadId,...(sourceKind?{source_kind:sourceKind}:{}),...(surfaceVariable?{surface_variable:surfaceVariable}:{}),...(surfaceOptions?{surface_options:surfaceOptions}:{}),...(geometry?{cell_geometry:geometry}:{}),...(sourceStage==null?{}:{source_stage:sourceStage})}:{source_job_id:jobId})};
}

export function morphologyBatchPayload({mode,jobId,uploadId,geometry,stages}){
 const payload=morphologyPayload({mode,jobId,uploadId,geometry});
 if(!uploadId)throw new Error('批量阶段分析仅支持外部 NPZ');
 if(stages!=='all'&&(!Array.isArray(stages)||!stages.length||stages.some(stage=>!Number.isInteger(stage)||stage<1)))throw new Error('批量阶段必须为 all 或正整数列表');
 return {...payload,source_stages:stages};
}

export function renderMorphologyBatch(summary){
 const rows=(summary.stages||[]).map(item=>{const report=item.report||{};const value=report.six_metrics||[];return `<tr><td>${esc(item.stage)}</td><td>${esc(report.valid_count??item.modes?.ga?.valid_count??'—')}</td><td>${num(value[0]??item.modes?.ga?.six_metrics?.[0])}</td><td>${num(value[1]??item.modes?.ga?.six_metrics?.[1])}</td><td>${esc(report.metadata?.mode_label||'双模式')}</td></tr>`;}).join('');
 return `<div class="card wide"><h3>阶段批量分析</h3><p>来源：${esc(summary.source_name)} · 状态变量 ${esc(summary.npz_variable)} · 已分析 ${esc(summary.npz_stages?.join('、'))} 阶段。每个阶段独立保存，指标仅用于观察阶段变化。</p><div class="table-wrap"><table><thead><tr><th>阶段</th><th>有效坑数</th><th>平均腐蚀深度 / μm</th><th>不均匀腐蚀深度 / μm</th><th>模式</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}

export function renderMorphologyResult(summary){
 if(summary.stages)return renderMorphologyBatch(summary);
 if(summary.modes)return renderMorphologyComparison(summary.modes)+Object.entries(summary.modes).map(([,result])=>renderMorphologySingleResult(result)).join('');
 return renderMorphologySingleResult(summary);
}

export function mountMorphology(root,{get,post,openJob,preferredId}){
 if(!root||root.querySelector('[data-morphology]'))return;
 const box=document.createElement('section');box.className='card wide';box.dataset.morphology='';
 box.innerHTML=`<h3>腐蚀形貌与分布出图</h3><p>支持已完成 NPZ 模拟，也支持外部二维 MAT 规则表面。MAT 会按所选变量、单位、方向和 XY 间距生成形貌图，并分别导出本面的 XYZ 点云。</p><div class="grid two"><div class="field"><label>数据来源<select data-source><option value="task">已完成模拟任务（最终阶段）</option><option value="upload">从电脑导入 .npz</option><option value="mat">从电脑导入二维 .mat 表面</option></select></label></div><div class="field" data-mode-field><label>分析模式<select data-mode><option value="both">双模式对照（GA + 精细）</option><option value="ga">GA 同口径验收图（推荐验收）</option><option value="detail">精细形貌分析图（保留原交互规则）</option></select></label></div><div class="field" data-task-field><label>模拟任务<select data-job aria-label="形貌分析来源任务"></select></label></div><div class="field" data-upload-field hidden><label>腐蚀模拟结果 .npz<input type="file" accept=".npz" data-file></label><p data-file-note class="help-line"></p></div><div class="field" data-mat-field hidden><label>二维表面 .mat<input type="file" accept=".mat" data-mat-file></label><p data-mat-note class="help-line"></p></div><div class="field" data-stage-field hidden><label for="morphology-stage-mode">阶段范围<select id="morphology-stage-mode" data-stage-mode><option value="last">最后阶段</option><option value="one">指定阶段</option><option value="all">全部阶段</option></select></label><input id="morphology-stage" data-stage type="number" min="1" step="1"><small data-stage-note></small></div></div><div class="grid two" data-mat-options hidden><label>MAT 变量<select data-mat-variable></select></label><label>矩阵单位<select data-mat-unit><option value="mm">mm</option><option value="um">μm</option></select></label><label>数值含义<select data-mat-value><option value="height">表面高度</option><option value="depth">正值腐蚀深度</option></select></label><label>X 间距 / mm<input type="number" min="0" step="any" value="0.3" data-mat-dx></label><label>Y 间距 / mm<input type="number" min="0" step="any" value="0.3" data-mat-dy></label><label>X 原点 / mm<input type="number" step="any" value="0" data-mat-origin-x></label><label>Y 原点 / mm<input type="number" step="any" value="0" data-mat-origin-y></label><label>高度参考面<select data-mat-reference-mode><option value="maximum">矩阵最大高度</option><option value="manual">手动填写</option></select></label><label>手动参考高度（原单位）<input type="number" step="any" data-mat-reference></label><label>高度方向<select data-mat-sign><option value="1">+1：参考面 − 高度</option><option value="-1">−1：翻转高度方向</option></select></label><label>行列约定<select data-mat-layout><option value="yx">行=Y，列=X</option><option value="xy">行=X，列=Y</option></select></label><label class="check-field"><input type="checkbox" data-mat-transpose>额外转置</label><label class="check-field"><input type="checkbox" data-mat-flip-x>翻转 X</label><label class="check-field"><input type="checkbox" data-mat-flip-y>翻转 Y</label></div><div class="grid two" data-geometry hidden><label>原 XY 元胞尺寸 / μm<input type="number" min="0" step="any" data-xy></label><label>原 Z 元胞尺寸 / μm<input type="number" min="0" step="any" data-z></label></div><p class="help-line" data-mode-note></p><p class="help-line">C17_100D 的 'F_filled'、'Z_filled' 是二维规则矩阵；请正面和反面分别上传、分别核对方向后再用于有限元耦合，网站不会自动把两个未配准矩阵拼成一面。</p><div class="actions"><button type="button" class="button primary" data-run>生成 PNG 预览与报告</button><button type="button" class="button secondary" data-refresh>刷新来源任务</button></div><p data-note role="status" class="help-line"></p>`;
 root.prepend(box);const q=s=>box.querySelector(s);let upload=null,matUpload=null,matInfo=null,missing=[],stageCount=1,pending=false;
 function visibility(){const source=q('[data-source]').value;q('[data-task-field]').hidden=source!=='task';q('[data-upload-field]').hidden=source!=='upload';q('[data-mat-field]').hidden=source!=='mat';q('[data-mat-options]').hidden=source!=='mat'||!matInfo;q('[data-mode-field]').hidden=source==='mat';q('[data-stage-field]').hidden=source!=='upload'||!upload;q('[data-stage]').hidden=q('[data-stage-mode]').value!=='one';q('[data-geometry]').hidden=source!=='upload'||!missing.length;q('[data-mode-note]').textContent=morphologyModeNote(source==='mat'?'surface':q('[data-mode]').value);}
 function busy(value){pending=value;box.querySelectorAll('button,input,select').forEach(el=>el.disabled=value);}
 async function refresh(){busy(true);try{const jobs=await get('/api/jobs');const available=(Array.isArray(jobs)?jobs:jobs.jobs||[]).filter(j=>j.kind==='simulation'&&j.state==='completed');q('[data-job]').innerHTML='<option value="">请选择已完成模拟任务</option>'+available.map(j=>`<option value="${esc(j.id)}" ${j.id===preferredId?'selected':''}>${esc(j.display_name||j.case_name||j.id)}</option>`).join('');q('[data-note]').textContent=available.length?'已列出可用模拟任务；外部结果请选择从电脑导入。':'没有已完成模拟任务，可从电脑导入 NPZ。';}catch(e){q('[data-note]').textContent=e.message;}finally{busy(false);}}
 q('[data-source]').onchange=visibility;q('[data-mode]').onchange=visibility;q('[data-stage-mode]').onchange=visibility;q('[data-refresh]').onclick=refresh;
 q('[data-file]').onchange=async()=>{const file=q('[data-file]').files[0];upload=null;missing=[];visibility();if(!file)return;busy(true);try{const record=await get('/api/uploads?name='+encodeURIComponent(file.name),{method:'POST',body:file,timeout:120000});const info=await get(`/api/uploads/${encodeURIComponent(record.id)}/inspect?kind=apdl_npz`);upload=record;missing=info.missing_geometry||[];const selected=info.variables.find(v=>v.name===info.default_variable);stageCount=selected.stage_count;q('[data-stage]').max=stageCount;q('[data-stage]').value=stageCount;q('[data-stage-note]').textContent=`共 ${stageCount} 个状态；按文件存储顺序编号，不代表腐蚀天数。`;q('[data-file-note]').textContent=`${file.name} · ${selected.state_shape.join(' × ')} · ${stageCount} 个可选阶段；${Object.keys(info.geometry).length?'文件已保存元胞尺寸':'请补填原模拟元胞尺寸'}`;for(const [key,id] of [['space_xy_um','xy'],['space_z_um','z']]){q(`[data-${id}]`).value=info.geometry[key]??'';q(`[data-${id}]`).readOnly=!missing.includes(key);}visibility();}catch(e){q('[data-file-note]').textContent=e.message;}finally{busy(false);}};
 q('[data-mat-file]').onchange=async()=>{const file=q('[data-mat-file]').files[0];matUpload=null;matInfo=null;visibility();if(!file)return;busy(true);try{matUpload=await get('/api/uploads?name='+encodeURIComponent(file.name),{method:'POST',body:file,timeout:120000});matInfo=await get(`/api/uploads/${encodeURIComponent(matUpload.id)}/inspect?kind=mat_surface`);const vars=matInfo.variables||[];q('[data-mat-variable]').innerHTML=vars.map(item=>`<option value="${esc(item.name)}">${esc(item.name)} · ${esc(item.shape?.join(' × '))}</option>`).join('');q('[data-mat-note]').textContent=vars.length?`${file.name} · 已识别 ${vars.length} 个二维数值变量。当前文件只分析一个变量；正反面请分别上传。`:'未识别到二维数值变量。';visibility();}catch(e){q('[data-mat-note]').textContent=e.message;}finally{busy(false);}};
 q('[data-run]').onclick=async()=>{if(pending)return;busy(true);try{const source=q('[data-source]').value;if(source==='mat'){if(!matUpload||!matInfo)throw new Error('请先上传并检查二维 MAT');const options={unit:q('[data-mat-unit]').value,value_mode:q('[data-mat-value]').value,dx_mm:Number(q('[data-mat-dx]').value),dy_mm:Number(q('[data-mat-dy]').value),origin_x_mm:Number(q('[data-mat-origin-x]').value),origin_y_mm:Number(q('[data-mat-origin-y]').value),reference_mode:q('[data-mat-reference-mode]').value,reference_value:q('[data-mat-reference]').value===''?null:Number(q('[data-mat-reference]').value),height_sign:Number(q('[data-mat-sign]').value),layout:q('[data-mat-layout]').value,transpose:q('[data-mat-transpose]').checked,flip_x:q('[data-mat-flip-x]').checked,flip_y:q('[data-mat-flip-y]').checked};if(!Number.isFinite(options.dx_mm)||options.dx_mm<=0||!Number.isFinite(options.dy_mm)||options.dy_mm<=0||!Number.isFinite(options.origin_x_mm)||!Number.isFinite(options.origin_y_mm))throw new Error('MAT 间距必须为正数，X/Y 原点必须为有限数值');const body=morphologyPayload({mode:'surface',uploadId:matUpload.id,sourceKind:'mat_surface',surfaceVariable:q('[data-mat-variable]').value,surfaceOptions:options});q('[data-note]').textContent='正在冻结 MAT、生成实测表面图和规则网格点云…';const job=await post('/api/jobs',body);await openJob(job.id);return;}const external=source==='upload';if(external&&!upload)throw new Error('请先上传并检查 NPZ');const geometry={};for(const key of missing){const id=key==='space_xy_um'?'xy':'z',value=Number(q(`[data-${id}]`).value);if(!Number.isFinite(value)||value<=0)throw new Error('请填写原模拟元胞尺寸');geometry[key]=value;}const stageMode=q('[data-stage-mode]').value;let body;if(external&&stageMode==='all'){body=morphologyBatchPayload({mode:q('[data-mode]').value,uploadId:upload.id,geometry:missing.length?geometry:null,stages:'all'});}else if(external&&stageMode==='one'){const sourceStage=Number(q('[data-stage]').value);if(!Number.isInteger(sourceStage)||sourceStage<1||sourceStage>stageCount)throw new Error(`阶段必须为 1 至 ${stageCount} 的整数`);body=morphologyPayload({mode:q('[data-mode]').value,uploadId:upload.id,geometry:missing.length?geometry:null,sourceStage});}else{body=morphologyPayload({mode:q('[data-mode]').value,jobId:external?null:q('[data-job]').value,uploadId:external?upload.id:null,geometry:missing.length?geometry:null,sourceStage:external?stageCount:undefined});}q('[data-note]').textContent='正在冻结输入并提交独立出图任务…';const job=await post('/api/jobs',body);await openJob(job.id);}catch(e){q('[data-note]').textContent=e.message;}finally{busy(false);}};
 visibility();refresh();
}
