const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=value=>value==null?'—':Number(value).toLocaleString('zh-CN',{maximumSignificantDigits:7});

export function platformFields({input,check,select}){
 return `<div id="apdl-platform-toggle">${check('platform_enabled','添加两侧未腐蚀平台（实测深度参考面）')}</div><div id="apdl-platform-fields"><div class="grid two">${input('platform_fixed_mm','固定端平平台长度 / mm','默认 2.5；精确长度，不要求是腐蚀区点距整数倍。')}${input('platform_loaded_mm','加载端平平台长度 / mm','默认 2.5；宽度自动与腐蚀面一致。')}${input('platform_top_mean_depth_mm','正面实测平均腐蚀深度 / mm','必填试验值，不自动以点云起伏或坑深代替。')}${input('platform_bottom_mean_depth_mm','反面实测平均腐蚀深度 / mm','双面模式必填；单面平整一侧不参与参考面计算。')}</div><p class="help-line">按给定方法：两面统一为朝外为正的高程 h，平台参考高度 = min(h) + 实测输入深度；保持表面起伏不变，分别平移到顶面 t₀、底面 0。平台高度差由原始板厚控制，默认 6 mm。输入值不保证等于校准后矩阵平均深度，预检会同时报告。</p><p class="help-line">每侧平平台之外增加一格原始轴向点距的连接段，完整保留所有实测点。总长 = 腐蚀区长度 + 两侧平平台长度 + 两格连接段。腐蚀区保持原点距；平台均分，不超过原轴向点距。不与局部贴片模式叠加，使用 SOLID185。</p></div><div class="grid two">${select('thickness_layer_mode','厚度分层计数方式',[['element_layers','按单元层数'],['intermediate_nodes','按中间节点层数']],'沿正反面之间线性插值。')}${input('intermediate_node_layers','中间节点层数','10 层中间节点 = 12 层节点平面 = 11 层单元。')}</div><p id="apdl-layer-counts" class="help-line"></p>`;
}

export function renderPlatformReport(p){
 if(!p?.enabled)return '';
 return `<section class="apdl-platform-report"><h4>两侧平台与参考高度核验</h4><p>沿 ${esc(p.tensile_direction)} 拉伸；固定端平平台 ${fmt(p.fixed_flat_length_mm)} mm，加载端平平台 ${fmt(p.loaded_flat_length_mm)} mm，宽度与腐蚀区一致。每侧另有 ${fmt(p.transition_length_each_mm)} mm 连接段；腐蚀区范围 ${p.source_axial_range_mm.map(fmt).join(' ～ ')} mm。</p><p>底平台 Z=${fmt(p.platform_bottom_z_mm)} mm；顶平台 Z=${fmt(p.platform_top_z_mm)} mm；高度差 ${fmt(p.platform_separation_mm)} mm。固定端/加载端平台实际点距 ${fmt(p.fixed_platform_spacing_mm)} / ${fmt(p.loaded_platform_spacing_mm)} mm。</p><div class="table-wrap"><table><thead><tr><th>表面</th><th>实测输入深度 / mm</th><th>归一化最低高程 / mm</th><th>最低高程＋输入深度 / mm</th><th>校准后采样平均深度 / mm</th></tr></thead><tbody>${Object.entries(p.faces).filter(([,v])=>v.active).map(([key,v])=>`<tr><td>${key==='top'?'正面':'反面'}</td><td>${fmt(v.measured_mean_depth_mm)}</td><td>${fmt(v.normalized_outward_min_height_mm)}</td><td>${fmt(v.normalized_platform_reference_height_mm)}</td><td>${fmt(v.calibrated_sample_mean_depth_mm)}</td></tr>`).join('')}</tbody></table></div><p class="help-line">归一化朝外高程 h=−输入向内深度；上述参考高度在装配平移前计算。负校准深度表示表面高于平台，保留凸起不裁剪；剩余厚度必须处处为正。该公式不保证输出平均深度等于实测输入值。</p></section>`;
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
 if(!o.platform_enabled)return;
 if(o.corrosion_mode==='flat')throw new Error('平台模式需要选择腐蚀表面来源');
 if(o.local_corrosion)throw new Error('两侧平台不能与局部贴片模式同时启用');
 if(o.mesh_type!=='solid185_hex')throw new Error('两侧平台请使用 SOLID185');
 for(const key of ['platform_fixed_mm','platform_loaded_mm'])if(!Number.isFinite(Number(o[key]))||Number(o[key])<=0)throw new Error('两侧平平台长度必须大于 0');
 for(const face of ['top','bottom'])if(o.corrosion_mode!==`single_${face==='top'?'bottom':'top'}`&&o[`platform_${face}_mean_depth_mm`]==null)throw new Error(`请填写${face==='top'?'正面':'反面'}实测平均腐蚀深度（mm）`);
}
