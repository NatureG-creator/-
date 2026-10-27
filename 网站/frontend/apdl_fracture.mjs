const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=value=>Number.isFinite(value)?Number(value).toLocaleString('zh-CN',{maximumSignificantDigits:5}):'未取得';

export const fractureDefaults={damage_model:'none',density_tonne_mm3:7.85e-9,loading_time_s:.002,damage_output_intervals:200,damage_critical_strain:.12,damage_exponent:2,damage_fading_exponent:2,damage_failure_curve:'[[-0.333333,1],[0,0.6],[0.333333,0.4],[0.666667,0.25],[1,0.2]]',damage_size_curve:'[[0.25,1],[1,1],[4,1]]',damage_parameter_basis:'example',neck_imperfection_fraction:0,neck_width_mm:2,damage_damping_per_s:0};

export function fractureFields({input,select}){
 return `${select('damage_model','分析模式',[['none','MAPDL · 原弹塑性拉伸'],['gissmo','LS-DYNA · GISSMO 损伤与断裂']],'损伤模式使用本机 LS-DYNA，保留原有 MAPDL 分析。')}<div id="apdl-fracture-fields" hidden><p class="help-line">塑性变形和局部颈缩由真实材料硬化与大变形计算；GISSMO 累积损伤、退化承载并在达到失效条件时删除单元。只支持八节点六面体，需选 MISO、启用大变形并使用无下降段的真实塑性曲线。</p><div class="grid four">${select('damage_parameter_basis','参数来源',[['example','示例参数 · 仅验证流程'],['calibrated','用户试验标定值']],'“标定值”为用户声明，网站不会自动证明材料已标定。')}${input('density_tonne_mm3','密度 / tonne·mm⁻³','钢材示例 7.85e-9，对应 7850 kg/m³。')}${input('loading_time_s','加载时间 / s','前90%平滑加载、末10%保持位移；延长时间复算以检查惯性影响，不使用质量缩放。')}${input('damage_output_intervals','输出间隔数','20 至 500；保存 d3plot、binout 和真实能量历史。')}${input('damage_critical_strain','耦合临界塑性应变','ECRIT：达到材料失稳指标后，损伤开始影响应力。')}${input('damage_exponent','损伤累积指数','GISSMO DMGEXP，需试验标定。')}${input('damage_fading_exponent','应力退化指数','GISSMO FADEXP，控制软化形状，需标定。')}${input('neck_imperfection_fraction','平板初始厚度缺陷比例','0 为不添加；范围 0–0.1，仅无腐蚀模型允许。腐蚀模型保留真实形貌。')}${input('damage_damping_per_s','数值阻尼系数 / s⁻¹','0关闭。减小断裂后的数值振荡；需检查阻尼耗能并减小系数复算。不是材料粘性。')}${input('neck_width_mm','平板初始缺陷宽度 / mm','沿拉伸方向的高斯宽度；仅初始缺陷非零时生效。')}</div><div class="grid two"><label class="field">失效曲线 [应力三轴度, 等效塑性失效应变]<textarea data-option="damage_failure_curve" rows="5" aria-label="GISSMO失效曲线"></textarea><small>JSON 二维数组；三轴度须递增，不能用试件断后伸长率直接替代局部失效应变。</small></label><label class="field">尺寸正则化 [单元尺寸mm, 失效应变倍率]<textarea data-option="damage_size_curve" rows="5" aria-label="GISSMO尺寸正则化曲线"></textarea><small>LCREGD；默认倍率均为1，表示没有经过网格标定的尺寸修正，不代表网格无关。</small></label></div><p class="help-line">颈缩、损伤、单元删除和完整断开分别校核。输出时间为秒；原 APDL 子步、RST 和重启动选项不控制 LS-DYNA。示例曲线不能作为你的钢材定量预测。</p></div>`;
}

export function validateFractureDraft(o){
 if(!['none','gissmo'].includes(o.damage_model))throw new Error('损伤模型无效');
 if(o.damage_model==='none')return;
 if(o.material_model!=='multilinear_iso'||!o.large_deflection)throw new Error('损伤模式需要 MISO 并启用大变形');
 if(o.mesh_type!=='solid185_hex'||o.boundary_mode==='legacy_recommended')throw new Error('损伤模式需要八节点六面体及自由泊松/两端夹持约束');
 if(o.plastic_curve.some((p,i)=>i&&p[1]<o.plastic_curve[i-1][1]))throw new Error('损伤模式的塑性硬化曲线不能包含下降段');
 for(const key of ['damage_failure_curve','damage_size_curve']){
  try{if(typeof o[key]==='string')o[key]=JSON.parse(o[key]);}catch{throw new Error(`${key} 必须为二维JSON数组`);}
  if(!Array.isArray(o[key])||o[key].length<2||o[key].length>100||o[key].some((p,i)=>!Array.isArray(p)||p.length!==2||p.some(v=>typeof v!=='number'||!Number.isFinite(v))||p[1]<=0||(key==='damage_size_curve'&&p[0]<=0)||(i&&p[0]<=o[key][i-1][0])))throw new Error(`${key} 须为横坐标递增、因变量为正的有限数值点`);
 }
 for(const key of ['density_tonne_mm3','loading_time_s','damage_critical_strain','damage_exponent','damage_fading_exponent','neck_width_mm'])if(!Number.isFinite(o[key])||o[key]<=0)throw new Error(`${key} 必须大于0`);
 if(!Number.isFinite(o.damage_damping_per_s)||o.damage_damping_per_s<0)throw new Error('数值阻尼系数必须非负');
 if(!Number.isInteger(o.damage_output_intervals)||o.damage_output_intervals<20||o.damage_output_intervals>500)throw new Error('输出间隔数须为20至500的整数');
 if(o.damage_critical_strain>=Math.min(...o.damage_failure_curve.map(p=>p[1])))throw new Error('耦合临界应变须小于最小失效应变');
 if(o.neck_imperfection_fraction<0||o.neck_imperfection_fraction>.1||(o.neck_imperfection_fraction&&o.corrosion_mode!=='flat'))throw new Error('初始厚度缺陷仅用于无腐蚀平板，比例0至0.1');
 if(!['example','calibrated'].includes(o.damage_parameter_basis))throw new Error('请明确参数来源');
}

export function renderFractureResult(summary={},job={}){
 const r=summary.results||{},f=r.fracture;
 if(!f)return `<div class="card wide"><h3>LS-DYNA 损伤断裂</h3><p>${esc(summary.error|| (summary.solve_state==='running'?'正在计算塑性、颈缩与损伤。':summary.build_state==='built'?'损伤输入包已生成。':'正在创建独立任务。'))}</p><p>只有真实求解并通过后处理后才会出现曲线及断裂判定。</p></div>`;
 const base=`/api/jobs/${encodeURIComponent(job.id)}/view/`,downloadBase=`/api/jobs/${encodeURIComponent(job.id)}/download/`;
 const facts=[['颈缩筛查',f.necking_observed?'局部截面非均匀收缩':'尚未确认'],['原生损伤最大值',fmt(f.max_damage_observed)],['失效单元数',fmt(f.deleted_elements)],['两端存活网格连接',f.load_path_separated?'已断开':'仍连接'],['峰值拉力 / N',fmt(f.peak_force_n)],['末步/峰值拉力',fmt(f.final_force_ratio)],['断裂前最大动能/内能',fmt(f.prefracture_max_kinetic_internal_ratio)],['数值阻尼系数 / s⁻¹',fmt(f.damping_per_s)],['断裂前最大阻尼耗能/内能',fmt(f.prefracture_max_damping_internal_ratio)],['准静态筛查',f.quasistatic_screen_passed?'通过；仍需加载时间敏感性复算':'未通过，需减慢加载复算']];
 const markerLabels={necking_start:'颈缩起点',first_localization:'首次局部化',first_damage_coupling:'首次损伤耦合',first_element_deletion:'首次失效单元删除',load_path_separation:'承载路径断开'};
 const markers=Object.entries(f.stage_markers||{}).filter(([,m])=>m).map(([key,m])=>`<tr><td>${esc(markerLabels[key]||m.label||key)}</td><td>${fmt(m.time_s)} s</td><td>${fmt(m.applied_displacement_mm)} mm</td><td>${fmt(m.engineering_strain*100)} %</td><td>${fmt(m.force_n)} N</td></tr>`).join('');
 const markerTable=markers?`<h4>曲线阶段标记</h4><div class="table-wrap"><table><thead><tr><th>阶段</th><th>时间</th><th>施加位移</th><th>工程应变</th><th>拉力</th></tr></thead><tbody>${markers}</tbody></table></div>`:'';
 return `<section class="card wide apdl-result"><h3>${f.fracture_confirmed?'已通过数值断开检查':'加载完成 · 尚未确认完整断裂'}</h3><p><strong>${f.parameter_basis==='example'?'示例参数，仅验证计算流程':'用户提供的标定参数；尚未独立验证标定'}</strong></p><dl class="outcome-facts">${facts.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>${markerTable}<p class="help-line">${esc(f.note)}</p>${(r.warnings||[]).map(v=>`<p class="help-line">${esc(v)}</p>`).join('')}${['engineering_stress_strain.png','load_displacement.png','fracture_snapshots.png'].map(name=>`<figure><img src="${base}${name}" alt="${esc(name)}" style="width:100%;max-width:1200px;height:auto"><figcaption>${esc(name)}</figcaption></figure>`).join('')}<div class="actions">${['force_displacement.csv','damage_history.csv','energy_history.csv','fracture_report.json','lsdyna_fracture_input_bundle.zip'].map(name=>`<a class="button secondary" href="${downloadBase}${name}" download>${esc(name)}</a>`).join('')}</div><p class="help-line">原生 d3plot 与 binout 可在任务文件下载并用 LS-PrePost 检查。曲线未平滑或人为补下降段；应变为模型端面相对位移/原始跨度。</p></section>`;
}
