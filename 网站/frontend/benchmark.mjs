const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = value => value != null && Number.isFinite(Number(value)) ? Number(value).toFixed(4) : '—';
const yes = value => value == null ? '—' : value ? '是' : '否';
export const benchmarkModes = [['numpy_serial','NumPy 单进程'],['numpy_parallel','NumPy 多进程'],['taichi_cpu','Taichi CPU'],['taichi_gpu','Taichi GPU'],['taichi_cpu_parallel','Taichi CPU 多进程'],['taichi_gpu_parallel','Taichi GPU 多进程']];
const fields = [['grid_w','X 向元胞数',2,1000],['grid_l','Y 向元胞数',2,1000],['grid_n','Z 向元胞层数',2,1000],['steps','CA 步数 F',1,10000],['population','种群数量',2,500],['selected_count','GA 选择数量（必须小于种群）',1,499],['workers','默认并行进程数',2,16],['repeats','预热后重复次数',1,7],['seed','默认随机种子',0,4294967295],['target_index','目标行',0,100000],['timeout_seconds','单方案超时 / 秒',10,1800],['threads_per_worker','每进程线程数',1,16],['cpu_budget','逻辑 CPU 预算',1,4096],['generations','短程 GA 最大代数',1,10]];
export function quickOptions(seed=42, selectedCount=2) {
 return {grid_w:40,grid_l:40,grid_n:16,steps:8,population:6,selected_count:Math.min(selectedCount,5),workers:2,repeats:5,seed,target_index:0,timeout_seconds:180,modes:benchmarkModes.slice(0,4).map(x=>x[0]),pool_policies:['recreate'],worker_counts:[2],threads_per_worker:1,cpu_budget:2,workload:'population',generations:3,seeds:[],order_mode:'fixed',retain_detail:true};
}
export function selfCheckOptions(seed=42) { return {...quickOptions(seed),grid_w:5,grid_l:6,grid_n:4,steps:3,population:2,selected_count:1,repeats:1}; }
export function parseIntegerList(text, label, allowEmpty=false) {
 if (!text.trim() && allowEmpty) return [];
 const parts=text.split(',');
 if(parts.some(p=>!p.trim() || !/^\d+$/.test(p.trim()))) throw new Error(`${label} 请填写逗号分隔的整数，不能有空项`);
 return parts.map(Number);
}
export function validateOptions(o,targetCount) {
 for(const [key,,min,max] of fields) {
  if(['threads_per_worker','cpu_budget','generations'].includes(key) && o[key]===undefined) continue;
  if(!Number.isInteger(o[key])||o[key]<min||o[key]>max) throw new Error(`${key} 必须为 ${min}–${max} 的整数`);
 }
 if(o.selected_count>=o.population)throw new Error('selected_count 必须小于 population，请明确调整选择数量');
 if(o.target_index>=targetCount)throw new Error(`target_index 必须小于目标行数 ${targetCount}`);
 if(!o.modes?.includes('numpy_serial'))throw new Error('必须保留 NumPy 单进程基准');
 if(o.modes.some(m=>!benchmarkModes.some(([id])=>id===m)))throw new Error('包含未知方案');
 const counts=o.worker_counts??[o.workers],pools=o.pool_policies??['recreate'];
 if(!Array.isArray(counts)||!counts.length||counts.some(n=>!Number.isInteger(n)||n<2||n>16))throw new Error('worker_counts 必须包含 2–16 的整数');
 if(!Array.isArray(pools)||!pools.length||pools.some(p=>!['recreate','persistent'].includes(p)))throw new Error('pool_policies 不能为空且必须为受支持的池口径');
 if(counts.some(n=>n*(o.threads_per_worker??1)>(o.cpu_budget??Infinity)))throw new Error('进程 × 线程超过 CPU 预算');
 if(o.seeds!==undefined&&(!Array.isArray(o.seeds)||o.seeds.some(n=>!Number.isInteger(n)||n<0||n>4294967295)))throw new Error('seeds 必须为随机种子整数数组');
 if(o.workload!==undefined&&!['population','short_ga'].includes(o.workload))throw new Error('workload 无效');
 if(o.order_mode!==undefined&&!['fixed','random'].includes(o.order_mode))throw new Error('order_mode 无效');
 return o;
}
export function benchmarkPayload(payload,options,source={}) {
 validateOptions(options,payload.targets?.length||0);
 if(payload.targets.some(row=>!Array.isArray(row)||row.length!==6||row.some(v=>typeof v!=='number'||!Number.isFinite(v))))throw new Error('六指标目标必须为完整有限数值，不能为空');
 if(source.source_job_id&&(!Number.isInteger(source.source_stage)||source.source_stage<1))throw new Error('来源阶段必须为正整数');
 return JSON.parse(JSON.stringify({config:payload.config,targets:payload.targets,options,...source}));
}
export function withSourceGeometry(payload, geometry) {
 const copy=JSON.parse(JSON.stringify(payload));
 if(geometry)for(const key of ['space_xy_um','space_z_um'])copy.config.GEOMETRY_CONFIG[key]=geometry[key];
 return copy;
}
export function currentOptions(payload) {
 const c=payload.config,g=c.GEOMETRY_CONFIG||{},ga=c[payload.run_mode==='single'?'SINGLE_STAGE_GA_CONFIG':'STAGE_GA_CONFIG']||{},workers=Math.max(2,ga.parallel_workers||2);
 return {...quickOptions(),grid_w:g.grid_w,grid_l:g.grid_l,grid_n:g.grid_n,steps:ga.F,population:ga.nind,selected_count:ga.selected_count??2,workers,worker_counts:[workers],cpu_budget:Math.max(2,workers),seed:c.GA_CONFIG?.seed??42};
}
export function applicationPolicy(row) {
 if(row.state!=='completed')return {allowed:false,reason:'仅有效完成方案可采用'};
 if(row.mode==='numpy_serial')return {allowed:true,mode:'strict',workers:1};
 if(row.mode==='numpy_parallel')return {allowed:false,reason:'当前正式严格模式仅单进程'};
 const cpu=row.mode?.startsWith('taichi_cpu'),gpu=row.mode?.startsWith('taichi_gpu'),arch=String(row.actual_arch||'').toLowerCase().replace(/^arch\./,'');
 if(!(cpu&&['cpu','x64','arm64'].includes(arch)||gpu&&['gpu','cuda','vulkan','metal','opengl'].includes(arch)))return {allowed:false,reason:'实际设备未匹配，不能采用'};
 return {allowed:true,mode:'fast',arch:cpu?'cpu':'gpu',workers:row.workers||1};
}
export function rowSpeedup(row,rows) {
 if(!row.baseline_id || row.seed==null)return null;
 const baseline=rows.find(b=>b.variant_id===row.baseline_id&&b.mode==='numpy_serial'&&b.seed===row.seed&&(b.workload??'population')===(row.workload??'population'));
 return baseline?.state==='completed'&&row.state==='completed'&&baseline.median_seconds>0&&row.median_seconds>0 ? baseline.median_seconds/row.median_seconds : null;
}
function physicalDetails(row) {
 const p=row.physical_comparison;
 if(!p)return '<p>未提供物理差异；请查看方案原因及原始结果。</p>';
 return `<p>表面深度最大差 ${num(p.surface_depth?.max_abs_diff_um)} μm；RMSE ${num(p.surface_depth?.rmse_um)} μm</p><div class="table-wrap"><table><thead><tr><th>六指标</th><th>基准</th><th>本方案</th><th>差值</th></tr></thead><tbody>${Object.entries(p.metrics||{}).map(([name,m])=>`<tr><td>${esc(name)}</td><td>${num(m.reference)}</td><td>${num(m.candidate)}</td><td>${num(m.delta)}</td></tr>`).join('')}</tbody></table></div><p>${Array.isArray(p.notes)?p.notes.map(n=>typeof n==='string'?esc(n):`${esc(({reference:'基准',candidate:'本方案'})[n.source]||n.source||'来源未提供')} · ${esc(n.metric||'物理指标')}：${esc(n.reason||'未提供原因')}`).join('<br>'):esc(p.notes||'')}</p>`;
}
export function renderBenchmarkResult(summary={}) {
 const rows=summary.rows||[],states={completed:'有效',unavailable:'不可用',failed:'失败',timeout:'超时'},valid=rows.filter(r=>r.state==='completed'&&r.median_seconds>0),max=Math.max(...valid.map(r=>r.median_seconds),1e-9);
 return `<div class="card wide"><h3>${summary.options?.workload==='short_ga'?'短程完整 GA（含迭代与实际早停）':'固定种群一代 CA 适应度'}性能对比</h3><p>${esc(summary.scope_note||'相同输入的独立测量；固定种群结果不能代表完整 GA。')}</p><p>${Object.entries(states).map(([state,label])=>`${label} ${rows.filter(r=>r.state===state).length}`).join(' · ')}</p><p class="help-line">加速比仅使用本任务同种子的 baseline_id；各随机种子、工作负载分别比较。首次评估含惰性编译。池创建与传输按各行口径计时。ZIP 点击下载时生成并缓存。</p>${[summary.detail_note,summary.warning,summary.memory_note,summary.parallel_note,summary.objective_note||'objv 为六项舍入误差，不是实际六项形貌指标。'].filter(Boolean).map(n=>`<p class="help-line">${esc(Array.isArray(n)?n.join('；'):n)}</p>`).join('')}
 <div class="table-wrap"><table><thead><tr><th>方案 / 状态</th><th>设备 / 进程×线程 / 池</th><th>种子 / 阶段 / 工作负载</th><th>首次 / 初始化 (s)</th><th>中位 / 最小 / 最大 (s)</th><th>加速比</th><th>采样 RSS (MiB)</th><th>完全一致 / 容差内 / 重复一致</th><th>采用</th></tr></thead><tbody>${rows.map((r,i)=>{const speed=rowSpeedup(r,rows),policy=applicationPolicy(r);return `<tr><td>${esc(r.label||r.mode)} · ${esc(states[r.state]||r.state)}${r.reason?`<small class="error-hint">${esc(r.reason)}</small>`:''}${r.low_sample_warning?'<small class="error-hint">低采样：样本不足，暂勿据此确定性能优势。</small>':''}</td><td>${esc(r.actual_arch||'—')} / ${esc(r.workers??1)}×${esc(r.threads_per_worker??summary.options?.threads_per_worker??1)} / ${r.workers===1?'单进程':r.pool_policy==='persistent'?'常驻池':'重建池'}</td><td>${esc(r.seed??'—')} / ${esc(r.stage_number??1)} / ${r.workload==='short_ga'?'短程完整 GA':'固定种群'}</td><td>${num(r.first_seconds)} / ${num(r.initialization_seconds)}</td><td>${num(r.median_seconds)} / ${num(r.min_seconds)} / ${num(r.max_seconds)}</td><td>${speed==null?'—':num(speed)+'×'}</td><td>${num(r.sampled_peak_rss_bytes==null?null:r.sampled_peak_rss_bytes/1048576)}</td><td>${yes(r.comparison?.exact)} / ${yes(r.comparison?.within_tolerance)} / ${yes(r.repeat_exact)}</td><td>${policy.allowed?`<button class="button secondary" data-benchmark-apply="${i}">查看采用方案</button>`:esc(policy.reason)}</td></tr>`;}).join('')}</tbody></table></div>
 <p class="help-line">内存为父子进程 RSS 采样，不含 GPU 显存，可能漏过峰值；空值表示未取得。</p><h4>预热后中位耗时（秒）</h4>${valid.map(r=>`<div class="benchmark-bar"><span>${esc(r.label||r.mode)} · seed ${esc(r.seed)}</span><div><i style="width:${r.median_seconds/max*100}%"></i></div><strong>${num(r.median_seconds)} s</strong></div>`).join('')||'<p>尚无可绘制的已完成方案。</p>'}
 <details><summary>原始样本、四分位数与完整试验耗时</summary>${rows.map(r=>`<h4>${esc(r.label||r.mode)}</h4><p>样本 ${esc(JSON.stringify(r.samples_seconds||[]))}；样本数 ${esc(r.sample_count??'—')}；Q1 / Q3 / IQR ${num(r.q1_seconds)} / ${num(r.q3_seconds)} / ${num(r.iqr_seconds)}；变异比 ${num(r.variation_ratio)}</p><p>读取 / 导出 / 比较 / 完整试验 / 进程总耗时 (s)：${[r.read_seconds,r.export_seconds,r.comparison_seconds,r.total_trial_seconds,r.process_wall_seconds].map(num).join(' / ')}</p>`).join('')}</details>
 <details><summary>数组差异详细表</summary>${rows.map(r=>`<p>${esc(r.label||r.mode)}：rtol=${esc(r.comparison?.rtol??'—')}；atol=${esc(r.comparison?.atol??'—')}</p>${Object.entries(r.comparison?.arrays||{}).map(([name,a])=>`<p>${esc(name)}：形状一致 ${yes(a.shape_match)}；完全一致 ${yes(a.exact)}；容差内 ${yes(a.within_tolerance)}；最大差 ${esc(a.max_abs_diff??'—')}；RMSE ${esc(a.rmse??'—')}；不匹配 ${esc(a.mismatch_count??'—')} / ${esc(a.mismatch_fraction??'—')}</p>`).join('')}`).join('')}</details>
 <details><summary>实际表面深度与六指标差异</summary>${rows.map(r=>`<h4>${esc(r.label||r.mode)}</h4>${physicalDetails(r)}`).join('')}</details><details><summary>参数、目标与溯源</summary><pre>${esc(JSON.stringify({input_hash:summary.input_hash,options:summary.options,target:summary.target,provenance:summary.provenance,wall_seconds:summary.wall_seconds},null,2))}</pre></details><div id="benchmark-apply-preview"></div><button class="button secondary" id="benchmark-retry">重新测量失败项（含新基准）</button><p class="help-line">重试创建新测量任务，不与原任务样本合并。</p></div>`;
}
export function renderDiagnostics(summary={}) {
 const labels={passed:'通过',unavailable:'不可用',failed:'失败',timeout:'超时'};
 return `<div class="card wide"><h3>本机运行环境诊断</h3><p>${esc(summary.scope_note||'安装、动态库加载及 CPU/GPU 实际运行分别检查。')}</p><table><thead><tr><th>检查</th><th>状态</th><th>实际设备 / 耗时</th><th>说明</th></tr></thead><tbody>${(summary.checks||[]).map(c=>`<tr><td>${esc(({import:"Python 包与原生扩展加载",cpu:"CPU 实际运行",gpu:"GPU 实际运行"})[c.name]||c.name)}</td><td>${esc(labels[c.state]||c.state)}</td><td>${esc(c.actual_arch||'—')} / ${num(c.elapsed_seconds)} s</td><td>${esc(c.message)}</td></tr>`).join('')}</tbody></table><p>${esc((summary.recommendations||[]).join('；'))}</p><details><summary>Python、软件包、硬件与原生依赖</summary><pre>${esc(JSON.stringify({python:summary.python,packages:summary.packages,hardware:summary.hardware,native_dependencies:summary.native_dependencies,configured_runtime:summary.configured_runtime},null,2))}</pre></details></div>`;
}
export function bindBenchmarkResult(root,{summary,jobId,post,openJob,onApply}) {
 root.querySelectorAll('[data-benchmark-apply]').forEach(button=>button.onclick=()=>onApply?.(summary.rows[Number(button.dataset.benchmarkApply)],summary));
 const retry=root.querySelector('#benchmark-retry');
 if(retry)retry.onclick=async()=>{retry.disabled=true;try{const job=await post(`/api/benchmarks/${encodeURIComponent(jobId)}/retry`,{});await openJob(job.id);}catch(e){retry.disabled=false;retry.textContent=e.message;}};
}
function inputField([id,label,min,max]) {
 if(id==='target_index')return '<div class="field"><label for="benchmark-target_index">当前目标行</label><select id="benchmark-target_index"></select></div>';
 return `<div class="field"><label for="benchmark-${id}">${label}</label><input id="benchmark-${id}" type="number" min="${min}" max="${max}" step="1" required></div>`;
}
export function mountBenchmark({getPayload,post,openJob,get=async url=>{const response=await fetch(url);if(!response.ok)throw new Error('来源任务读取失败');return response.json();}}) {
 const root=document.querySelector('#benchmark-panel');if(!root)return;
 root.innerHTML=`<div class="section-heading"><div><div class="section-overline">02 / SIMULATION ASSIST</div><h2>性能对比</h2><p>独立参数快照；固定种群与短程完整 GA 分开测量。</p></div><span class="badge neutral">模拟辅助</span></div><div class="card"><div class="actions"><button id="benchmark-self" class="button secondary">功能自检 5×6×4 · F3 · pop2 · 重复1</button><button id="benchmark-quick" class="button secondary">性能基准 40×40×16 · F8 · pop6 · 重复5</button><button id="benchmark-current" class="button secondary">采用当前 GA 配置</button><button id="benchmark-diagnostics" class="button secondary">本机环境诊断</button></div><p class="help-line">预设仅修改本页；不写回腐蚀演化配置。服务端预检累计所有种子、进程数与池方案的工作量，限制主机数组 1 GiB 和总工作量 2×10⁹。CPU 预算不得超过本机逻辑 CPU 数。</p>
 <div class="grid four"><div class="field"><label for="benchmark-initial">初始状态</label><select id="benchmark-initial"><option value="fresh">全新表面</option value="source">已完成阶段</option></select></div><div class="field"><label for="benchmark-source">来源模拟任务</label><select id="benchmark-source"><option value="">正在读取…</option></select></div><div class="field"><label for="benchmark-stage">来源阶段</label><select id="benchmark-stage"></select></div><button id="benchmark-source-grid" class="button secondary">采用源网格与物理间距</button></div><p id="benchmark-source-note" class="help-line">来源为已完成模拟的 stage_XXX.npz；下一次运行阶段为来源阶段 + 1，网格必须一致，不重采样。</p><p id="benchmark-spacing-note" class="help-line">尚未采用来源物理间距，沿用当前配置。</p>
 <div class="grid four">${fields.map(inputField).join('')}<div class="field"><label for="benchmark-workload">工作负载</label><select id="benchmark-workload"><option value="population">固定种群一代适应度</option><option value="short_ga">短程完整 GA（迭代与实际早停）</option></select></div><div class="field"><label for="benchmark-order_mode">执行顺序</label><select id="benchmark-order_mode"><option value="fixed">固定</option><option value="random">随机</option></select></div><div class="field"><label for="benchmark-worker_counts">进程数列表（逗号分隔）</label><input id="benchmark-worker_counts" value="2"></div><div class="field"><label for="benchmark-seeds">多种子（留空使用默认种子）</label><input id="benchmark-seeds" value=""></div></div><label class="check-field"><input id="benchmark-retain_detail" type="checkbox" checked>保留原始对照 NPZ 明细</label><p class="help-line">取消后仅保留报告与图片，全部对比结束后清理原始对照；失败或中断仍保留已生成数据。</p><h3>池生命周期</h3><div class="benchmark-modes"><label class="check-field"><input type="checkbox" data-benchmark-pool="recreate" checked>每次重建池（含创建）</label><label class="check-field"><input type="checkbox" data-benchmark-pool="persistent">常驻池（复用）</label></div><p class="help-line">单进程不区分池。并行进程数 × 每进程线程数必须在 CPU 预算内。</p><h3>参与方案</h3><div class="benchmark-modes">${benchmarkModes.map(([id,label],i)=>`<label class="check-field"><input type="checkbox" data-benchmark-mode="${id}" ${i<4?'checked':''} ${i===0?'disabled':''}>${label}${i===0?'（必选基准）':''}</label>`).join('')}</div><p class="help-line">Taichi 安装成功不等于动态库能加载或设备能运行；先运行本机环境诊断可定位依赖。多进程 Taichi 为实验方案。</p><div class="actions"><button id="benchmark-precheck" class="button secondary">预检全部方案</button><button id="benchmark-run" class="button primary">预检并运行 →</button></div><div id="benchmark-precheck-result"></div><div id="benchmark-message" class="message" role="status" hidden></div></div>`;
 const $=s=>root.querySelector(s),status=$('#benchmark-message');let sources=[],sourceGeometry=null;
 const report=e=>{status.hidden=false;status.textContent=e.message||String(e);status.classList.add('error');};
 function refreshTargets() {
  const previous=$('#benchmark-target_index').value,p=getPayload();
  $('#benchmark-target_index').innerHTML=(p.targets||[]).map((r,i)=>`<option value="${i}">第 ${i+1} 行 · ${esc(r.join(' / '))}</option>`).join('');
  if(previous&&Number(previous)<p.targets.length)$('#benchmark-target_index').value=previous;
 }
 function set(o) {
  try{refreshTargets();}catch{};
  fields.forEach(([key])=>{if(key!=='target_index')$('#benchmark-'+key).value=o[key]??'';});
  $('#benchmark-target_index').value=String(o.target_index??0);
  for(const key of ['workload','order_mode'])$('#benchmark-'+key).value=o[key];
  $('#benchmark-retain_detail').checked=o.retain_detail!==false;
  $('#benchmark-worker_counts').value=o.worker_counts.join(',');$('#benchmark-seeds').value=o.seeds.join(',');
  status.hidden=true;
  if(o.selected_count>=o.population)report(new Error('当前 selected_count 不小于种群数量，请明确调整后预检'));
 }
 function sourceStages() {
  const source=sources.find(s=>s.id===$('#benchmark-source').value),files=(source?.files||[]).map(f=>typeof f==='string'?f:f.name),numbers=files.map(name=>name.match(/stage_(\d+)\.npz$/)?.[1]).filter(Boolean).map(Number);
  const count=source?.result?.stages_completed??source?.stages_completed??source?.progress?.stages_completed??0;
  const stages=numbers.length?[...new Set(numbers)].sort((a,b)=>a-b):Array.from({length:Number(count)},(_,i)=>i+1);
  $('#benchmark-stage').innerHTML=stages.map(n=>`<option value="${n}">第 ${n} 阶段 → 测量第 ${n+1} 阶段</option>`).join('');
 }
 async function loadSources() {
  try{const data=await get('/api/jobs');sources=(Array.isArray(data)?data:data.jobs||[]).filter(j=>j.kind==='simulation'&&j.state==='completed');
   $('#benchmark-source').innerHTML=sources.length?sources.map(s=>`<option value="${esc(s.id)}">${esc(s.spec?.case_name||s.id)}</option>`).join(''):'<option value="">无可用的已完成模拟来源</option>';
   sourceStages();if(!sources.length)$('#benchmark-source-note').textContent='无可用来源：尚无已完成模拟任务，仍可从全新表面运行。';
  }catch(e){$('#benchmark-source').innerHTML='<option value="">来源读取失败</option>';$('#benchmark-source-note').textContent=e.message;}
 }
 async function hydrateSource(){const id=$('#benchmark-source').value;if(!id)return;const detail=await get(`/api/jobs/${encodeURIComponent(id)}`);sources=sources.map(s=>s.id===id?{...s,...detail}:s);sourceStages();}
 function read() {
  refreshTargets();
  const options={};for(const [key] of fields){const value=$('#benchmark-'+key).value;if(!value.trim())throw new Error(key+' 不能为空');options[key]=Number(value);}
  for(const key of ['workload','order_mode'])options[key]=$('#benchmark-'+key).value;
  options.retain_detail=$('#benchmark-retain_detail').checked;
  options.worker_counts=parseIntegerList($('#benchmark-worker_counts').value,'进程数');options.seeds=parseIntegerList($('#benchmark-seeds').value,'随机种子',true);
  options.modes=[...root.querySelectorAll('[data-benchmark-mode]:checked')].map(e=>e.dataset.benchmarkMode);options.pool_policies=[...root.querySelectorAll('[data-benchmark-pool]:checked')].map(e=>e.dataset.benchmarkPool);
  let source={};if($('#benchmark-initial').value==='source'){if(!$('#benchmark-source').value||!$('#benchmark-stage').value)throw new Error('请选择可用来源任务与已完成阶段');source={source_job_id:$('#benchmark-source').value,source_stage:Number($('#benchmark-stage').value)};}
  return withSourceGeometry(benchmarkPayload(getPayload(),options,source),source.source_job_id?sourceGeometry:null);
 }
 async function check(payload) {
  const result=await post('/api/benchmarks/precheck',payload);
  $('#benchmark-precheck-result').innerHTML=`<p>预检方案 ${esc(result.variants?.length??0)} 项 · 主机数组 ${num(result.estimated_host_array_bytes/1048576)} MiB · 总工作量 ${esc(result.estimated_work)}</p><p>${esc(result.scope_note)}</p><pre>${esc(JSON.stringify(result.issues||[],null,2))}</pre>`;
  if(result.issues?.length)throw new Error('预检未通过：'+result.issues.map(i=>typeof i==='string'?i:i.message||JSON.stringify(i)).join('；'));
  return result;
 }
 const action=(id,fn)=>{$(id).onclick=async event=>{const button=event.currentTarget;button.disabled=true;try{status.hidden=true;await fn();}catch(e){report(e);}finally{button.disabled=false;}};};
 set(quickOptions());loadSources();
 action('#benchmark-self',()=>set(selfCheckOptions(getPayload().config.GA_CONFIG?.seed??42)));
 action('#benchmark-quick',()=>{const p=getPayload();set(quickOptions(p.config.GA_CONFIG?.seed??42,p.config.STAGE_GA_CONFIG?.selected_count??2));});
 action('#benchmark-current',()=>set(currentOptions(getPayload())));
 action('#benchmark-diagnostics',async()=>{const job=await post('/api/benchmark-diagnostics',{});await openJob(job.id);});
 action('#benchmark-precheck',()=>check(read()));
 action('#benchmark-run',async()=>{const payload=read();await check(payload);const job=await post('/api/benchmarks',payload);await openJob(job.id);});
 function clearSourceOverride(){sourceGeometry=null;$('#benchmark-spacing-note').textContent='尚未采用来源物理间距，沿用当前配置。';}
 $('#benchmark-source').onchange=()=>{clearSourceOverride();hydrateSource().catch(report);};
 $('#benchmark-initial').onchange=()=>{clearSourceOverride();if($('#benchmark-initial').value==='source')hydrateSource().catch(report);};
 action('#benchmark-source-grid',async()=>{if($('#benchmark-initial').value!=='source')throw new Error('请先选择已完成阶段初始状态');await hydrateSource();const source=sources.find(s=>s.id===$('#benchmark-source').value),g=(source?.effective_config?.config||source?.effective_config||source?.spec?.config)?.GEOMETRY_CONFIG;if(!g)throw new Error('来源未提供网格配置');for(const k of ['grid_w','grid_l','grid_n'])$('#benchmark-'+k).value=g[k];sourceGeometry={space_xy_um:g.space_xy_um,space_z_um:g.space_z_um};$('#benchmark-spacing-note').textContent=`已采用来源物理间距：XY ${g.space_xy_um} μm，Z ${g.space_z_um} μm；仅用于本次性能对比。`;});
 root.addEventListener('focusin',event=>{if(event.target.id==='benchmark-target_index')try{refreshTargets();}catch(e){report(e);}});
}
