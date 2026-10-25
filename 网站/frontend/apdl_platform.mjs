const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=value=>value==null?'—':Number(value).toLocaleString('zh-CN',{maximumSignificantDigits:7});

export function platformFields({input,check,select}){
 return `<div id="apdl-platform-toggle">${check('platform_enabled','添加两侧参考平台（定位方式见下方）')}</div><div id="apdl-platform-fields">${select('platform_reference_mode','平台定位方式',[['manual_mean','手动实测均值校准'],['empirical_190','完整扫描20%经验参考（单面试点）']],'自动方式读取所选点云任务冻结的完整与局部扫描，共用完整扫描坐标变换；轻微腐蚀区按 min(H)+0.2×[max(H)−min(H)] 定位，不代表实测零腐蚀面。原始板厚须填写实测值。')}<div class="grid two">${input('platform_fixed_mm','固定端平平台长度 / mm','默认 2.5；精确长度，不要求是腐蚀区点距整数倍。')}${input('platform_loaded_mm','加载端平平台长度 / mm','默认 2.5；宽度自动与腐蚀面一致。')}${input('platform_top_mean_depth_mm','正面实测平均腐蚀深度 / mm','填写与建模腐蚀区同一范围、同一统计口径的实测平均值，单位 mm；不以最大坑深代替。')}${input('platform_bottom_mean_depth_mm','反面实测平均腐蚀深度 / mm','双面模式填写反面同一区域的实测平均值（mm）；单面平整一侧不参与校准。')}</div><p id="apdl-manual-mean-help" class="help-line">按实测平均深度校准：校准深度 = 原深度 − 腐蚀区采样平均深度 + 实测平均深度。正反面分别整体平移，保持原始起伏和采样不变；新增平台与连接段不参与均值。校准后腐蚀区采样点算术平均值在浮点精度内等于输入值。平台底面为 0、顶面为原始板厚 t₀（默认 6 mm）；预检同时报告平移量、校准后均值和均值误差。</p><p class="help-line">每侧平平台之外增加一格原始轴向点距的连接段，完整保留所有实测点。总长 = 腐蚀区长度 + 两侧平平台长度 + 两格连接段。腐蚀区保持原点距；平台均分，不超过原轴向点距。不与局部贴片模式叠加，使用 SOLID185。</p></div><div class="grid two">${select('thickness_layer_mode','厚度分层计数方式',[['element_layers','按单元层数'],['intermediate_nodes','按中间节点层数']],'沿正反面之间线性插值。')}${input('intermediate_node_layers','中间节点层数','10 层中间节点 = 12 层节点平面 = 11 层单元。')}</div><p id="apdl-layer-counts" class="help-line"></p>`;
}

export function renderPlatformReport(p){
 if(!p?.enabled)return '';
 if(p.calibration_method==='empirical_reference_preserved'){
  const rows=Object.entries(p.reference_calibrations||{}).map(([face,r])=>`<tr><td>${face==='top'?'正面':'反面'}</td><td>${esc(r.source_job_id)}</td><td>${fmt(r.reference_height_mm)}</td><td>${fmt(p.faces[face].calibrated_sample_mean_depth_mm)}</td><td>${fmt(r.full_reproduction_max_error_mm)}</td></tr>`).join('');
  return `<section class="apdl-platform-report"><h4>两侧平台与参考高度核验</h4><p>完整扫描20%经验参考：H_flat=min(H)+0.2×[max(H)−min(H)]。原始XYZ子集和共同坐标链已数值核验；参考区存在轻微腐蚀，真实零腐蚀面未验证，未知损失未补偿。不做均值二次平移。</p><p>平台底面 ${fmt(p.platform_bottom_z_mm)} mm、顶面 ${fmt(p.platform_top_z_mm)} mm，间距 ${fmt(p.platform_separation_mm)} mm；两端平平台长 ${fmt(p.fixed_flat_length_mm)} / ${fmt(p.loaded_flat_length_mm)} mm，每端另有 ${fmt(p.transition_length_each_mm)} mm 连接段。未测反面按平整未腐蚀面建模，属于单面模型假设。</p><div class="table-wrap"><table><thead><tr><th>表面</th><th>点云源任务</th><th>经验参考高程 / mm</th><th>输出经验平均深度 / mm</th><th>完整扫描复现最大误差 / mm</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
 }
 const meanCalibrated=p.calibration_method==='sample_mean_translation';
 const method=meanCalibrated?'均值校准：仅平移腐蚀区，新增平台与连接段不计入均值。':'历史算法：最低高程参考，不保证输出平均深度等于输入值；此记录保留原结果，未按新公式重算。';
 return `<section class="apdl-platform-report"><h4>两侧平台与参考高度核验</h4><p>${method}</p><p>沿 ${esc(p.tensile_direction)} 拉伸；固定端平平台 ${fmt(p.fixed_flat_length_mm)} mm，加载端平平台 ${fmt(p.loaded_flat_length_mm)} mm，宽度与腐蚀区一致。每侧另有 ${fmt(p.transition_length_each_mm)} mm 连接段；腐蚀区范围 ${p.source_axial_range_mm.map(fmt).join(' ～ ')} mm。</p><p>底平台 Z=${fmt(p.platform_bottom_z_mm)} mm；顶平台 Z=${fmt(p.platform_top_z_mm)} mm；高度差 ${fmt(p.platform_separation_mm)} mm。固定端/加载端平台实际点距 ${fmt(p.fixed_platform_spacing_mm)} / ${fmt(p.loaded_platform_spacing_mm)} mm。</p><div class="table-wrap"><table><thead><tr><th>表面</th><th>${meanCalibrated?'实测平均深度':'历史输入深度'} / mm</th><th>${meanCalibrated?'原采样平均深度':'归一化最低高程'} / mm</th><th>${meanCalibrated?'向内深度平移量':'最低高程＋输入深度'} / mm</th><th>校准后采样平均深度 / mm</th>${meanCalibrated?'<th>均值误差 / mm</th>':''}</tr></thead><tbody>${Object.entries(p.faces).filter(([,v])=>v.active).map(([key,v])=>`<tr><td>${key==='top'?'正面':'反面'}</td><td>${fmt(v.measured_mean_depth_mm)}</td><td>${fmt(meanCalibrated?v.input_sample_mean_depth_mm:v.normalized_outward_min_height_mm)}</td><td>${fmt(meanCalibrated?v.depth_shift_mm:v.normalized_platform_reference_height_mm)}</td><td>${fmt(v.calibrated_sample_mean_depth_mm)}</td>${meanCalibrated?`<td>${fmt(v.mean_calibration_error_mm)}</td>`:''}</tr>`).join('')}</tbody></table></div><p class="help-line">${meanCalibrated?'校准深度 = 原深度 − 原采样均值 + 实测均值；均值误差 = 校准后采样均值 − 实测均值，按浮点精度核对。':'历史参考高度按朝外高程 h=−输入向内深度计算。'}负校准深度表示表面高于平台，保留凸起不裁剪；剩余厚度必须处处为正。</p></section>`;
}

export function validatePlatformOptions(o){
 if(!['element_layers','intermediate_nodes'].includes(o.thickness_layer_mode))throw new Error('厚度分层计数方式无效');
 const count=Number(o.intermediate_node_layers);
 if(o.intermediate_node_layers===''||o.intermediate_node_layers==null||typeof o.intermediate_node_layers==='boolean'||!Number.isInteger(count)||count<0)throw new Error('中间节点层数必须是不小于 0 的整数');
 o.intermediate_node_layers=count;
 if(o.thickness_layer_mode==='intermediate_nodes')o.layers=count+1;
 if(typeof o.platform_enabled!=='boolean')throw new Error('平台开关必须为布尔值');
 for(const key of ['platform_top_mean_depth_mm','platform_bottom_mean_depth_mm']){
  if(o[key]===''||o[key]==null)o[key]=null;
  else {if(typeof o[key]==='boolean')throw new Error('实测平均腐蚀深度必须为数值');o[key]=Number(o[key]);if(!Number.isFinite(o[key])||o[key]<0)throw new Error('实测平均腐蚀深度必须是有限非负数（mm）');}
 }
 if(!['manual_mean','empirical_190'].includes(o.platform_reference_mode||'manual_mean'))throw new Error('平台定位方式无效');
 if(!o.platform_enabled)return;
 if(o.platform_reference_mode==='empirical_190'&&!['single_top','single_bottom'].includes(o.corrosion_mode))throw new Error('完整扫描经验参考试点仅支持单面，不能假定反面已验证');
 if(o.corrosion_mode==='flat')throw new Error('平台模式需要选择腐蚀表面来源');
 if(o.local_corrosion)throw new Error('两侧平台不能与局部贴片模式同时启用');
 if(o.mesh_type!=='solid185_hex')throw new Error('两侧平台请使用 SOLID185');
 for(const key of ['platform_fixed_mm','platform_loaded_mm'])if(!Number.isFinite(Number(o[key]))||Number(o[key])<=0)throw new Error('两侧平平台长度必须大于 0');
 if(o.platform_reference_mode==='empirical_190')o.platform_top_mean_depth_mm=o.platform_bottom_mean_depth_mm=null;
 if(o.platform_reference_mode!=='empirical_190')for(const face of ['top','bottom'])if(o.corrosion_mode!==`single_${face==='top'?'bottom':'top'}`&&o[`platform_${face}_mean_depth_mm`]==null)throw new Error(`请填写${face==='top'?'正面':'反面'}实测平均腐蚀深度（mm）`);
}
