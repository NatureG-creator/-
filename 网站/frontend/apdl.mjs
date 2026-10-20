// APDL 单轴拉伸工作区：独立于 CA–GA 配置，统一使用 N-mm-MPa。
import {mountApdl3DPreview,previewGeometry} from './apdl_preview_3d.mjs';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=(value,label)=>{if(value===''||value==null||!Number.isFinite(Number(value)))throw new Error(`${label}必须为有限数值`);return Number(value);};
const positive=(value,label)=>{const n=number(value,label);if(n<=0)throw new Error(`${label}必须大于 0`);return n;};
const fmt=value=>value==null||!Number.isFinite(Number(value))?'—':Number(value).toLocaleString('zh-CN',{maximumSignificantDigits:6});
const baseOptions={surface_grid_mode:'strict',mapping_dx_mm:null,mapping_dy_mm:null,corrosion_mode:'flat',local_corrosion:false,patch_offset_x_mm:'',patch_offset_y_mm:'',patch_rotation_deg:0,patch_flip_x:false,patch_flip_y:false,thickness_mm:6,length_mm:100,width_mm:20,nx:11,ny:5,layers:3,mesh_type:'solid185_hex',E_MPa:206000,poisson_ratio:.3,material_model:'elastic',yield_MPa:235,tangent_MPa:1000,target_displacement_mm:.1,substeps:10,min_substeps:1,max_substeps:450,large_deflection:false,boundary_mode:'poisson_free',tensile_direction:'X',grip_length_fixed_mm:0,grip_length_loaded_mm:0,export_full_field:true,cores:2,timeout_seconds:3600,restart_frequency:1,plastic_curve:null,allow_negative_slope:false,result_save_mode:'all',field_output_times:'0.25, 0.5, 0.75, 1'};
const mappingDefaults={variable:'',unit:'mm',layout:'auto',value_mode:'depth',reference_mode:'manual',reference_height:0,height_sign:1,dx_mm:'',dy_mm:'',origin_x_mm:'',origin_y_mm:'',transpose:false,flip_x:false,flip_y:false,center_crop_columns:''};
export function apdlDefaults(){return {preset_id:'elastic_flat',case_name:'无腐蚀弹性板验证',registration_confirmed:false,options:{...baseOptions},top:{source_kind:'simulation',source_job_id:'',coordinate_uploads:{},coordinate_direction:'front',mapping:{...mappingDefaults}},bottom:{source_kind:'simulation',source_job_id:'',coordinate_uploads:{},coordinate_direction:'back',mapping:{...mappingDefaults}}};}

export function loadedApdlDraft(saved){
 const next=apdlDefaults();
 next.options={...next.options,...structuredClone(saved.options)};
 next.case_name=saved.case_name||'载入的有限元配置';
 next.preset_id=saved.preset_id||'';
 for(const face of ['top','bottom'])if(saved[face]){
  next[face]={...next[face],...structuredClone(saved[face]),mapping:{...mappingDefaults,...structuredClone(saved[face].mapping||{})}};
 }
 next.registration_confirmed=false;
 return next;
}

// 所有控件通过同一入口保存原始字符串，避免异步重绘依赖 change/失焦。
export function createApdlDraftState(initial=apdlDefaults()){
 let draft=initial,revision=0,precheck=null;
 const invalidate=()=>{revision++;precheck=null;};
 return {get draft(){return draft;},get revision(){return revision;},get precheck(){return precheck;},invalidate,
  replace(next){draft=next;invalidate();},
  update(scope,key,value,face){
   const target=scope==='option'?draft.options:scope==='source'?draft[face]:scope==='map'?draft[face].mapping:draft;
   const previous=target[key];target[key]=value;
   if(previous===value||(typeof previous!=='object'&&String(previous??'')===String(value??'')))return false;
   if(scope==='source'&&['origin','source_kind','source_job_id'].includes(key)){
    delete target.source_stage;delete target.source_file;
    if(key!=='source_job_id')target.source_job_id='';
    if(key==='origin'){for(const field of ['upload_id','upload_name','npz_info','npz_variable','npz_stage','space_xy_um','space_z_um','coordinate_uploads','coordinate_names','conversion_summary'])delete target[field];if(value==='upload')target.source_kind='measured';if(value==='upload_npz')target.source_kind='simulation';if(value==='coordinates'){target.source_kind='coordinates';target.coordinate_uploads={};target.coordinate_names={};}if(value==='task'&&target.source_kind==='coordinates')target.source_kind='simulation';}
   }
   if(scope==='source'&&key==='npz_variable')delete target.npz_stage;
   if(scope==='source'||scope==='map'||(scope==='option'&&['corrosion_mode','surface_grid_mode','mapping_dx_mm','mapping_dy_mm'].includes(key)))draft.registration_confirmed=false;
   invalidate();return true;
  },
  acceptPrecheck(result,version,payload){
   if(version!==revision)throw new Error('读取期间配置发生变化，请重新预检。');
   const requestedDirection=payload.options?.tensile_direction||'X';
   const resolvedDirection=result.options?.tensile_direction||'X';
   if(resolvedDirection!==requestedDirection)throw new Error('服务端未确认所选拉伸方向，预检已停止以避免按错误方向生成模型。请更新本机网站服务；如有MAPDL任务，待其结束后再重启。');
   if(payload.options?.corrosion_mode==='double_independent'&&payload.options?.surface_grid_mode==='common_xy'){
    const mapping=result.surface_mapping;
    if(result.options?.surface_grid_mode!=='common_xy'||mapping?.mode!=='common_xy'||mapping.extrapolation!==false)throw new Error('服务端未确认共同XY映射，请更新并重启本机网站服务后重新预检。');
    for(const key of ['dx_mm','dy_mm'])if(payload.options['mapping_'+key]!=null&&mapping[key]!==payload.options['mapping_'+key])throw new Error('服务端未确认手动目标间距，请重新预检。');
   }
   precheck=result;
   if(result.registration_signature)payload.registration_signature=result.registration_signature;
   return payload;
  }
 };
}
export function apdlMappingDisplay(source){
 const mapping={...mappingDefaults,...source.mapping};
 if(source.origin==='upload_npz'||(source.origin!=='upload'&&source.source_kind==='simulation'))Object.assign(mapping,{unit:'mm',value_mode:'depth',variable:'',dx_mm:'',dy_mm:'',origin_x_mm:'',origin_y_mm:'',center_crop_columns:'',reference_mode:'manual',reference_height:0,height_sign:1});
 return mapping;
}

export function matlabConversionPayload(source,face){
 const mapping=apdlMappingDisplay(source),mode=source.conversion_mode||'surface_mm';
 if(source.origin!=='upload'||!source.upload_id)throw new Error('请先上传二维矩阵');
 if(!['surface_mm','baseline_cells'].includes(mode))throw new Error('未知的矩阵转换模式');
 const body={upload_id:source.upload_id,variable:source.mat_info?.variable||mapping.variable||'',dx_mm:positive(mapping.dx_mm,'X 间距'),dy_mm:positive(mapping.dy_mm,'Y 间距'),x_start_mm:mapping.origin_x_mm===''?0:number(mapping.origin_x_mm,'X 原点'),y_start_mm:mapping.origin_y_mm===''?0:number(mapping.origin_y_mm,'Y 原点'),conversion_mode:mode,coordinate_direction:face==='bottom'?'back':'front'};
 if(mode==='baseline_cells')body.cell_thickness_mm=positive(source.cell_thickness_mm??.025,'Z 向元胞厚度 / mm');
 return body;
}

export function validateMatlabConversion(result,request){
 const summary=result.conversion;
 if(summary?.conversion_mode!==request.conversion_mode||summary?.coordinate_direction!==request.coordinate_direction||(request.conversion_mode==='baseline_cells'&&summary.cell_thickness_mm!==request.cell_thickness_mm))throw new Error('服务端未确认所选转换规则，未采用生成坐标。请结束当前任务后重启网站服务，再重新转换。');
}

export function renderMatlabConversionControls(source,prefix){
 const mode=source.conversion_mode||'surface_mm';
 return `<div class="grid two"><div class="field"><label for="apdl-${prefix}conversion-mode">MATLAB 转换规则</label><select id="apdl-${prefix}conversion-mode" data-conversion="conversion_mode"><option value="surface_mm" ${mode==='surface_mm'?'selected':''}>矩阵已经是 mm：原值、行列保持不变</option><option value="baseline_cells" ${mode==='baseline_cells'?'selected':''}>原始 baseline 元胞层数：转置并换算 mm</option></select><small>只影响下方 MATLAB 转换按钮，不改变直接读取矩阵的映射规则。</small></div><div class="field"><label for="apdl-${prefix}cell-thickness">Z 向元胞厚度 / mm</label><input id="apdl-${prefix}cell-thickness" data-conversion="cell_thickness_mm" type="number" min="0" step="any" value="${esc(source.cell_thickness_mm??.025)}"><small>仅层数模式生效。0.025 mm = 25 μm，请按原模拟配置填写；与下方 X/Y 点距独立。</small></div></div><p class="help-line">层数模式：先转置，正面 Z = −baselineᵀ × 元胞厚度，反面取相反号以保持相同深度含义。生成相对形貌，不自动添加夹持区或修补穿透；请另行核对板厚、X/Y 方向与点距。</p>`;
}

export function renderMatlabConversionSummary(summary){
 if(!summary)return '';
 return `<p class="help-line">MATLAB 转换报告：${summary.conversion_mode==='baseline_cells'?'元胞层数 → mm（已转置）':'毫米矩阵原值保留'}；原始 ${summary.input_shape.map(esc).join(' × ')} → ${summary.shape.map(esc).join(' × ')}（行 × 列）；原值范围 ${summary.input_range.map(fmt).join(' ～ ')}；Z 范围 ${summary.z_range_mm.map(fmt).join(' ～ ')} mm；最大相对深度 ${fmt(summary.max_relative_depth_mm)} mm${summary.cell_thickness_mm!=null?`；Z 元胞厚度 ${fmt(summary.cell_thickness_mm)} mm`:''}。</p>`;
}

export function applyApdlPreset(draft,preset){
 const next=structuredClone(draft);
 next.preset_id=preset.id;next.case_name=preset.name;next.options={...baseOptions,...structuredClone(preset.options||{})};next.registration_confirmed=false;
 for(const face of ['top','bottom']){
  const mapping=preset[face+'_mapping'];
  next[face].mapping={...mappingDefaults,...structuredClone(mapping||{})};
  if(mapping){if(next[face].source_kind!=='measured')next[face].source_job_id='';next[face].source_kind='measured';if(next[face].origin==='upload_npz'){next[face].origin='task';for(const key of ['upload_id','upload_name','npz_info','npz_variable','npz_stage','space_xy_um','space_z_um'])delete next[face][key];}}
 }
 return next;
}

// 每面有独立来源世代；过期请求仍计入 pending，直到其真实结束。
export function createFaceUploadManager(){
 const generations=new Map();let pending=0;
 const invalidate=face=>generations.set(face,(generations.get(face)||0)+1);
 return {invalidate,get pending(){return pending;},async run(face,getSource,recordPromise,name){
  invalidate(face);const generation=generations.get(face),origin=getSource()?.origin;pending++;
  const current=()=>generations.get(face)===generation&&getSource()?.origin===origin&&['upload','upload_npz'].includes(origin);
  try{const record=await recordPromise;if(!current())return false;const source=getSource();source.upload_id=record.id||record.upload_id;source.upload_name=name;if(record.mat_info)source.mat_info=record.mat_info;
   if(origin==='upload_npz'){source.npz_info=record.npz_info;source.npz_variable=record.npz_info.default_variable;source.npz_stage=record.npz_info.variables.find(v=>v.name===source.npz_variable).stage_count;delete source.space_xy_um;delete source.space_z_um;}return true;}
  catch(error){if(!current())return false;throw error;}
  finally{pending--;}
 }};
}

function sourcePayload(source,label){
 const coordinate=source?.origin==='coordinates'||source?.source_kind==='coordinates';
 if(coordinate){const uploads=source?.coordinate_uploads||{};if(!['x','y','z'].every(axis=>typeof uploads[axis]==='string'&&uploads[axis]))throw new Error(`${label}坐标来源必须完整上传 X、Y、Z 三个文件`);return {source_kind:'coordinates',coordinate_uploads:{x:uploads.x,y:uploads.y,z:uploads.z},coordinate_direction:source.coordinate_direction|| (label==='正面'?'front':'back'),mapping:{}};}
 const external=source?.origin==='upload_npz',isUpload=external||source?.origin==='upload'||(!source?.origin&&!!source?.upload_id);
 if(!source||(isUpload?!source.upload_id:!source.source_job_id))throw new Error(`请选择${label}来源任务或上传文件`);
 const kind=external?'simulation':isUpload?'measured':source.source_kind;
 const result={source_kind:kind,mapping:{...mappingDefaults,...source.mapping}};
 if(isUpload)result.upload_id=source.upload_id;else result.source_job_id=source.source_job_id;
 if(kind==='simulation'){
  Object.assign(result.mapping,apdlMappingDisplay(source));
  if(external){
   const info=source.npz_info;if(!info)throw new Error(`${label} NPZ 尚未完成结构检查，请重新上传`);
   const variable=source.npz_variable||info.default_variable,selected=info.variables.find(v=>v.name===variable&&v.supported);
   if(!selected)throw new Error('请选择可读取的 NPZ 状态变量');
   const stage=source.npz_stage==null||source.npz_stage===''?selected.stage_count:positive(source.npz_stage,'NPZ 阶段');
   if(!Number.isInteger(stage)||stage>selected.stage_count)throw new Error(`NPZ 阶段必须是 1 至 ${selected.stage_count} 的整数`);
   result.mapping.npz_variable=variable;result.mapping.npz_stage=stage;result.cell_geometry={};
   for(const key of ['space_xy_um','space_z_um'])if(info.geometry[key]==null)result.cell_geometry[key]=positive(source[key],`${label} ${key} 元胞尺寸 / μm`);
  }else if(source.source_stage!==''&&source.source_stage!=null){result.source_stage=positive(source.source_stage,'阶段');if(!Number.isInteger(result.source_stage))throw new Error('阶段必须是整数');}
  delete result.mapping.dx_mm;delete result.mapping.dy_mm;delete result.mapping.center_crop_columns;
 }else{
  if(!isUpload&&source.source_file)result.source_file=source.source_file;
  for(const key of ['dx_mm','dy_mm']){
   if(result.mapping[key]===''||result.mapping[key]==null){if(isUpload)throw new Error(`${label}上传矩阵必须填写 X/Y 物理间距`);delete result.mapping[key];}
   else result.mapping[key]=positive(result.mapping[key],`${label}${key}间距`);
  }
 }
 for(const key of ['reference_height','height_sign'])result.mapping[key]=number(result.mapping[key],key);
 for(const key of ['origin_x_mm','origin_y_mm']){
  if(result.mapping[key]===''||result.mapping[key]==null)delete result.mapping[key];
  else result.mapping[key]=number(result.mapping[key],key);
 }
 if(kind==='simulation'){delete result.mapping.origin_x_mm;delete result.mapping.origin_y_mm;}
 for(const key of ['transpose','flip_x','flip_y'])result.mapping[key]=result.mapping[key]===true;
 if(result.mapping.center_crop_columns===''||result.mapping.center_crop_columns==null)delete result.mapping.center_crop_columns;
 else {result.mapping.center_crop_columns=positive(result.mapping.center_crop_columns,'中心裁剪列数');if(!Number.isInteger(result.mapping.center_crop_columns)||result.mapping.center_crop_columns<2)throw new Error('中心裁剪列数必须是至少 2 的整数');}
 return result;
}
export function buildApdlPayload(draft,runMode='build'){
 if(!['build','solve'].includes(runMode))throw new Error('运行模式无效');
 const o={...baseOptions,...draft.options};
 o.local_corrosion=o.corrosion_mode!=='flat'&&o.local_corrosion===true;
 o.patch_rotation_deg=number(o.patch_rotation_deg,'局部腐蚀区域旋转角度');
 if(!Number.isInteger(o.patch_rotation_deg)||![0,90,180,270].includes(o.patch_rotation_deg))throw new Error('局部腐蚀区域旋转角度只能选择 0、90、180 或 270 度');
 for(const key of ['patch_flip_x','patch_flip_y'])if(typeof o[key]!=='boolean')throw new Error(`${key}必须为布尔值`);
 if(!['solid185_hex','solid285_tetra','solid187_tetra'].includes(o.mesh_type))throw new Error('实体网格类型无效');
 if(!['X','Y'].includes(o.tensile_direction))throw new Error('拉伸方向只能选择 X 或 Y');
 if(!['strict','common_xy'].includes(o.surface_grid_mode))throw new Error('双面网格模式无效');
 for(const key of ['mapping_dx_mm','mapping_dy_mm'])o[key]=o.corrosion_mode!=='double_independent'||o.surface_grid_mode!=='common_xy'||o[key]==null||String(o[key]).trim()===''?null:positive(o[key],key);
 for(const key of ['grip_length_fixed_mm','grip_length_loaded_mm'])if(o[key]===''||o[key]==null)o[key]=0;
 for(const key of ['patch_offset_x_mm','patch_offset_y_mm'])o[key]=o.local_corrosion&&o[key]!==''&&o[key]!=null?number(o[key],key):null;
 for(const key of Object.keys(baseOptions))if(typeof baseOptions[key]==='number')o[key]=number(o[key],key);
 for(const key of ['grip_length_fixed_mm','grip_length_loaded_mm'])if(o[key]<0)throw new Error(`${key}必须是有限且不小于 0 的数值`);
 for(const key of ['layers','nx','ny','substeps','min_substeps','max_substeps','cores','timeout_seconds','restart_frequency'])if(!Number.isInteger(o[key]))throw new Error(`${key}必须为整数`);
 if(!(o.min_substeps<=o.substeps&&o.substeps<=o.max_substeps))throw new Error('子步需满足：最小 ≤ 初始 ≤ 最大');
 if(!['all','last','selected'].includes(o.result_save_mode))throw new Error('结果保存模式无效');
 if(o.result_save_mode==='selected'){
  const raw=o.field_output_times;
  const values=typeof raw==='string'?raw.split(',').map(v=>v.trim()===''?NaN:Number(v)):raw;
  if(!Array.isArray(values)||!values.length||values.length>20||values.some((v,i)=>typeof v!=='number'||!Number.isFinite(v)||v<=0||v>1||(i>0&&v<=values[i-1]))||values.at(-1)!==1)throw new Error('保存比例需为1至20个严格递增的数值，范围(0,1]并包含1；用英文逗号分隔');
  o.field_output_times=[...values];
 }else o.field_output_times=[.25,.5,.75,1];
 if(typeof o.plastic_curve==='string')try{o.plastic_curve=o.plastic_curve.trim()?JSON.parse(o.plastic_curve):null;}catch{throw new Error('MISO 曲线必须为二维 JSON 数组');}
 if(o.material_model==='multilinear_iso'&&(!Array.isArray(o.plastic_curve)||o.plastic_curve.length<2||o.plastic_curve.some(p=>!Array.isArray(p)||p.length!==2||p.some(v=>typeof v!=='number'||!Number.isFinite(v)))))throw new Error('MISO 曲线需至少两个 [塑性应变, 应力MPa] JSON 数值点');
 const p={preset_id:draft.preset_id,case_name:(draft.case_name||'单轴拉伸').trim(),run_mode:runMode,options:o,registration_confirmed:!!draft.registration_confirmed};
 if(draft.material_source)p.material_source=structuredClone(draft.material_source);
 if(o.corrosion_mode==='double_independent'&&!p.registration_confirmed)throw new Error('独立双面需要确认已配准到相同的物理 XY 位置');
 if(['single_top','double_independent','double_symmetric'].includes(o.corrosion_mode))p.top_source=sourcePayload(draft.top,'正面');
 if(['single_bottom','double_independent'].includes(o.corrosion_mode))p.bottom_source=sourcePayload(draft.bottom,'反面');
 return p;
}
export function availableSurfaceFiles(job){return (job?.files||[]).map(f=>typeof f==='string'?f:f.name).filter(name=>job.kind==='simulation'?/(^|\/)stage_\d+\.npz$|(^|\/)simulation\.npz$/i.test(name):/\.mat$/i.test(name));}
const statLabels={node_count:'节点数',element_count:'有限元单元数',mesh_type:'网格类型',positive_tetra_count:'正体积四面体数',negative_tetra_count:'负体积四面体数',min_tetra_volume_mm3:'最小四面体体积 / mm³',length_mm:'X 方向跨度 / mm',width_mm:'Y 方向跨度 / mm',min_remaining_thickness_mm:'最小剩余厚度 / mm',mean_remaining_thickness_mm:'平均剩余厚度 / mm',volume_loss_fraction:'体积损失比例',max_cell_aspect_ratio:'最大单元边长比',nominal_area_mm2:'原始截面面积 / mm²',analytic_stiffness_n_per_mm:'解析参考刚度 / N·mm⁻¹',analytic_force_n:'解析参考反力 / N'};
const statGrid=stats=>`<div class="resource-grid">${Object.entries(statLabels).filter(([k])=>stats?.[k]!=null).map(([k,label])=>`<div><small>${label}</small><strong>${typeof stats[k]==='string'?esc(stats[k]):fmt(stats[k])}</strong></div>`).join('')}</div>`;
const tensileSummary=(stats={},options={})=>{const direction=options.tensile_direction||'X',axial=direction==='X'?stats.length_mm:stats.width_mm,transverse=direction==='X'?stats.width_mm:stats.length_mm;if(axial==null||transverse==null)return '';return `<p class="help-line">拉伸方向：全局 ${esc(direction)}；轴向标距 ${fmt(axial)} mm，横向跨度 ${fmt(transverse)} mm，名义截面积 ${fmt(stats.nominal_area_mm2)} mm²。判断长边时请比较预检中的 X/Y 跨度；若沿长边拉伸，应选择跨度较大的方向。端面约束、位移/反力分量和结果换算均按此选择。</p>`;};
const warningsHtml=items=>items?.length?`<div class="notice"><div><strong>需要留意</strong><p>${items.map(esc).join('<br>')}</p></div></div>`:'';
export function renderApdlSurfaceMapping(mapping){
 if(mapping?.mode!=='common_xy')return '';
 const range=values=>(values||[]).map(fmt).join(' ～ ');
 return `<div class="apdl-diagnostics"><h4>共同XY映射记录</h4><p class="help-line">目标行Y × 列X：${fmt(mapping.y_count)} × ${fmt(mapping.x_count)}；目标间距 dx=${fmt(mapping.dx_mm)} / dy=${fmt(mapping.dy_mm)} mm。双线性插值，禁止外推；仅使用两面共同覆盖区。</p><div class="table-wrap"><table><thead><tr><th>表面 / 网格</th><th>行Y × 列X</th><th>X 范围 / mm</th><th>Y 范围 / mm</th><th>dx / dy（mm）</th><th>深度范围：原始 → 映射（mm）</th></tr></thead><tbody>${Object.entries(mapping.sources||{}).map(([face,m])=>`<tr><td>${esc(face==='top'?'正面':face==='bottom'?'反面':face)}${m.cropped?'（已裁剪）':''}</td><td>${(m.shape||[]).map(fmt).join(' × ')}</td><td>${range(m.x_range_mm)}</td><td>${range(m.y_range_mm)}</td><td>${fmt(m.dx_mm)} / ${fmt(m.dy_mm)}</td><td>${fmt(m.original_min_depth_mm)} ～ ${fmt(m.original_max_depth_mm)} → ${fmt(m.mapped_min_depth_mm)} ～ ${fmt(m.mapped_max_depth_mm)}</td></tr>`).join('')}<tr><td>物理交集</td><td>—</td><td>${range(mapping.overlap_x_range_mm)}</td><td>${range(mapping.overlap_y_range_mm)}</td><td>—</td><td>—</td></tr><tr><td>实际目标网格</td><td>${fmt(mapping.y_count)} × ${fmt(mapping.x_count)}</td><td>${range(mapping.target_x_range_mm)}</td><td>${range(mapping.target_y_range_mm)}</td><td>${fmt(mapping.dx_mm)} / ${fmt(mapping.dy_mm)}</td><td>—</td></tr></tbody></table></div><p class="help-line">目标网格从交集下界开始，边缘不足一个完整间隔时向内截取。原始文件保留；映射报告保存为 surface_mapping.json，实际建模深度与坐标保存为 surface_inputs.npz。粗网格可能遗漏窄坑峰值，插值不等同于原始形貌精度；请结合剩余厚度、质量报告和网格收敛复核。</p></div>`;
}
export function renderApdlDiagnostics(d={}){
 if(!d||!Object.keys(d).length)return '';
 const m=d.material_coverage||{},q=d.mesh_quality||{},p=d.output_policy||{},actual=d.self_check||d.apdl_self_check;
 const mode={all:'完整保存',last:'仅末步单元场',selected:'指定比例请求（完整保存）'}[p.result_save_mode]||p.result_save_mode||'—';
 const screening=m.screening,first=screening?.first_flag;
 const screenHtml=screening&&['flagged','no_flag'].includes(screening.state)?`<p class="${screening.state==='flagged'?'error-hint':'help-line'}">${screening.state==='flagged'?'元素节点筛查提示超表，待积分点复核':'筛查未见超表，不能证明积分点全部覆盖'}；已保存历史中的最大元素节点等效塑性应变 ${fmt(screening.max_element_nodal_epeq)}。${first?`首次提示加载比例 ${fmt(first.time)}，单元 ${esc(first.element_id)}，重心 ${esc((first.centroid_mm||[]).map(fmt).join(' / '))} mm。`:''}</p>`:'';
 return `<div class="apdl-diagnostics"><h4>材料覆盖提示</h4>${m.status==='estimate_only'?`<p class="help-line">${m.tensile_direction?`按全局 ${esc(m.tensile_direction)} 轴、标距 ${fmt(m.axial_length_mm)} mm估算；`:''}目标工程应变 ${fmt(m.target_engineering_strain)}，均匀拉伸真应变估算 ${fmt(m.target_log_strain)}；材料末点塑性应变 ${fmt(m.last_plastic_strain)}，末点总应变估算 ${fmt(m.estimated_last_total_strain)}，对应均匀延伸约 ${fmt(m.estimated_uniform_extension_mm)} mm。${m.exceeds_estimated_coverage?'均匀估算已超过材料表范围，请重点复核。':'均匀估算不能保证腐蚀局部热点仍在材料表内。'}</p>`:'<p class="help-line">当前材料模型不适用有限 MISO 曲线末点覆盖检查。</p>'}<p class="help-line">保持原材料曲线；均匀估算与求解后的元素节点筛查，均不能替代积分点逐项核验。</p>${screenHtml}${screening?.near_limit_point_count?`<p class="help-line">${fmt(screening.near_limit_point_count)} 个结果集接近材料末点，受导出精度影响，待复核。${esc(screening.comparison_note||'')}</p>`:''}<h4>网格质量报告</h4><p class="help-line">Python 几何预检：最小角点 scaled Jacobian ${fmt(q.min_scaled_jacobian)}；最大边长比 ${fmt(q.max_edge_length_ratio)}；预警单元数 ${fmt(q.warning_element_count)}。低于 0.1 仅作预警，不改变网格。MAPDL 原生质量报告${q.native_report?'已生成，需结合警告人工复核':'未运行 / 未提供'}。</p>${q.worst_elements?.length?`<details><summary>查看最差 ${q.worst_elements.length} 个单元的位置与指标</summary><div class="table-wrap"><table><thead><tr><th>最差单元 ID</th><th>最小 scaled Jacobian</th><th>边长比</th><th>重心 X / Y / Z（mm）</th></tr></thead><tbody>${q.worst_elements.map(e=>`<tr><td>${esc(e.element_id)}</td><td>${fmt(e.scaled_jacobian??e.min_scaled_jacobian)}</td><td>${fmt(e.edge_length_ratio)}</td><td>${(e.centroid_mm||[]).map(fmt).join(' / ')}</td></tr>`).join('')}</tbody></table></div></details>`:''}<p class="help-line">命令流内部自检：${actual?.state==='passed'?'节点、单元和端面集合自检通过':'尚未运行或尚未提供真实自检文件'}。</p><h4>结果保存模式</h4><p class="help-line">${esc(mode)}${p.result_save_mode==='selected'?` · 比例 ${esc((p.field_output_times||[]).join(', '))}`:''}；曲线与反力逐收敛子步保留。${m.material_model==='multilinear_iso'?'MISO 材料筛查历史逐子步保留。':'当前材料没有有限 MISO 表筛查历史。'}</p><p class="help-line">比例表示静力加载步 TIME=1 的加载份额，不是秒。指定比例模式当前因 MAPDL 输出兼容限制回退为完整保存，比例仅作请求记录，不减少 RST 体积，也不改变求解步长。末步节点 CSV 另由导出开关控制。</p></div>`;
}
export function renderApdlContours(report){
 if(!report)return '';
 if(report.state!=='completed')return `<div class="notice"><p>云图导出失败，求解结果保留。${esc(report.error||'请检查 contour_plots 中的日志。')}</p></div>`;
 return `<div class="apdl-diagnostics"><h4>MAPDL 原生云图</h4><p class="help-line">${(report.plots||[]).map(p=>`${esc(p.label)}（${p.unit==='1'?'无量纲':esc(p.unit)}）`).join('、')}。读取末步结果，真实比例 1 倍显示变形；应力与塑性应变为 FULL 模式的节点平均值，不代表积分点峰值。图中 TIME 是静力加载比例。</p><p class="help-line">出图耗时 ${fmt(report.elapsed_seconds)} 秒。下方“科研图像预览”可查看和下载 PNG；云图宏和日志保存在 contour_plots 文件夹。出图完成不替代独立 RST 交叉验收。</p></div>`;
}
export function renderApdlFailureAnalysis(summary={}){
 const failed=summary.solve_state==='failed'||summary.build_state==='failed'||summary.state==='failed'||summary.exit_code!=null;
 if(!failed)return '';
 const text=String(summary.error||summary.failure_reason||summary.message||'').toLowerCase(),diagnostics=summary.diagnostics||summary.results?.diagnostics||{},categories=diagnostics.categories||diagnostics.category||'',categoryText=Array.isArray(categories)?categories.join(' '):String(categories),evidence=[],suggestions=[];
 if(summary.exit_code!=null)evidence.push(`MAPDL 进程退出码：${summary.exit_code}`);
 if(summary.failure_stage)evidence.push(`失败阶段：${({reading:'读取输入',geometry:'几何与网格',build:'生成输入包',solver:'MAPDL 求解',postprocess:'后处理与校核'})[summary.failure_stage]||summary.failure_stage}`);
 if(text.includes('distort')||text.includes('inside out')||text.includes('形状')||categoryText.includes('element')){evidence.push('日志包含单元严重畸变或翻转证据。');suggestions.push('减小单步位移或增加最大子步数，避免加载突变。','检查腐蚀最薄区域和局部网格质量，必要时提高局部网格密度。','优先尝试四面体或自适应网格，并保持几何尺寸与材料曲线不变。');}
 if(text.includes('plastic')||text.includes('miso')||categoryText.includes('material')){evidence.push('日志或诊断指向材料曲线覆盖范围。');suggestions.push('检查塑性应变是否超过 49 点 MISO 曲线末点。','保留原材料曲线时，降低目标位移或确认材料曲线覆盖目标应变。');}
 if(text.includes('license')||text.includes('flexnet')||categoryText.includes('license')){evidence.push('日志指向许可证或求解器启动问题。');suggestions.push('确认 MAPDL 许可证服务可用，再重新求解。');}
 if(text.includes('converg')||categoryText.includes('converg')){evidence.push('日志指向非线性收敛失败。');suggestions.push('增加最大子步数并降低初始子步，检查大变形、接触和边界约束。');}
 if(!evidence.length)evidence.push(summary.error?`原始错误：${summary.error}`:'未提供足够的失败证据，请展开任务日志查看 MAPDL 原始输出。');
 if(!suggestions.length)suggestions.push('下载并查看 mapdl.out、.err 和命令流，确认失败发生在建模、求解还是后处理阶段。','修改参数后重新预检，不要直接复用未校核的 RST 文件。');
 return `<div class="notice apdl-failure-analysis"><h4>求解失败原因与改进建议</h4><p><strong>证据</strong></p><ul>${evidence.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p><strong>建议</strong></p><ul>${suggestions.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p class="help-line">以上建议根据任务日志和诊断字段生成；未通过独立结果校核前，不将失败任务视为有效力学结果。</p></div>`;
}

export function renderApdlResult(summary={}){
 if(summary.execution_mode==='custom_commands')return `<div class="card wide"><h3>自定义 APDL 命令</h3><p>${esc(summary.solve_state==='process_finished'?'MAPDL进程已退出':summary.solve_state==='failed'?'运行失败':summary.solve_state==='running'?'正在运行':'输入包已另存')}</p><p>未自动物理校核。来源参数不能代表编辑后的材料、加载与边界，请检查命令、日志和结果。</p>${summary.error?`<p>${esc(summary.error)}</p>`:''}</div>`;
 const solved=summary.solve_state==='solved',built=summary.build_state==='built'||summary.solve_state==='built',passed=(summary.results?.validation_state||summary.validation_state)==='passed';
 const building=summary.stage_states?.reading==='running'?'正在读取 APDL 来源':summary.stage_states?.geometry==='running'?'正在生成几何与网格':summary.stage_states?.build==='running'?'正在写入 APDL 输入包':null;
 const status=summary.solve_state==='stopped'?'APDL 任务已停止':solved?'MAPDL 求解完成':summary.solve_state==='running'?'MAPDL 正在求解':summary.solve_state==='postprocessing'?'正在后处理与校核':summary.build_state==='failed'?'APDL 建模失败':summary.solve_state==='failed'?(summary.failure_stage==='postprocess'?'结果后处理或校核失败':'MAPDL 求解失败'):building|| (built?'APDL 输入包已生成':'等待 APDL 结果');
 const results=summary.results||summary;
 const checks=results.checks||summary.checks||{};
 const names={target_time:'末步时间达到 1',target_displacement:'达到目标位移',reaction_balance:'两端反力平衡',engineering_strain:'工程应变一致',nominal_stress:'名义应力一致',nonempty_rst:'非空 RST 结果文件',rst_consistency:'RST 内容与导出结果一致',nodal_coordinates:'节点坐标与网格一致',nodal_displacements:'端部位移与加载曲线一致',nonzero_response:'拉伸响应非零',ramped_displacement:'中间步线性加载一致',analytic_reference:'解析参考误差 ≤ 5%',max_reaction_residual_n:'最大反力残差 / N',reaction_relative_tolerance:'反力相对容差',reaction_absolute_tolerance_n:'反力绝对容差 / N'};
 const rstNotice=(results.rst_validation?.state==='unverified'?`<p class="help-line">RST 内容尚未核验：${esc(results.rst_validation.reason||'当前尚未解析二进制结果，CSV 校核不能替代真实 RST 验收。')}</p>`:'')+renderApdlContours(results.contour_plots);
 const checkValue=(key,value)=>value===true?'通过':value===false?'未通过':value===null?(key==='rst_consistency'||key.startsWith('nodal_')?'尚未核验':'不适用'):esc(fmt(value));
 const timings={reading_seconds:'读取',geometry_seconds:'几何与网格',build_export_seconds:'输入包写入',solver_seconds:'MAPDL 求解',postprocess_seconds:'后处理',total_seconds:'总耗时'};
 return `<div class="card wide apdl-result"><div class="card-heading"><div><h3>${status}</h3><p>${solved?'求解状态与结果校核独立展示；曲线峰值只代表已保存加载路径。':summary.solve_state==='running'?'本机 MAPDL 正在运行，结果以完成后的文件和校核为准。':summary.solve_state==='postprocessing'?'求解器已退出，正在提取并交叉检查结果。':'未调用 MAPDL 时只生成输入包和解析参考，不产生数值求解结果。'}</p></div><span class="badge ${solved&&!passed?'failed':'neutral'}">${solved?(passed?'校核通过':'需要复核'):'输入与网格'}</span></div>${renderApdlFailureAnalysis(summary)}${renderApdlSurfaceMapping(summary.provenance?.surface_mapping)}${statGrid(summary.stats)}${tensileSummary(summary.stats,summary.options||results.options||{})}${solved?`<div class="resource-grid apdl-result-values">${[['final_displacement_mm','末步位移 / mm'],['final_load_n','末步反力 / N'],['peak_load_n','已保存曲线峰值 / N'],['peak_nominal_stress_mpa','曲线峰值名义应力 / MPa'],['secant_stiffness_n_per_mm','末步割线刚度 / N·mm⁻¹']].map(([k,label])=>`<div><small>${label}</small><strong>${fmt(results[k])}</strong></div>`).join('')}</div><p class="help-line">名义应力 = 加载端反力 / 原始实际截面积。未定义断裂模型，曲线峰值不等同于极限承载力。</p>`:''}${Object.keys(checks).length?`<h4>结果校核</h4><div class="table-wrap"><table><tbody>${Object.entries(checks).map(([k,v])=>`<tr><td>${esc(names[k]||k)}</td><td>${checkValue(k,v)}</td></tr>`).join('')}</tbody></table></div>`:''}${rstNotice}${renderApdlDiagnostics(results.diagnostics||summary.diagnostics)}${results.nodal_summary?`<p class="help-line">末步平均节点场：最大位移 ${fmt(results.nodal_summary.max_displacement_mm)} mm；最大等效应力 ${fmt(results.nodal_summary.max_equivalent_stress_mpa)} MPa；最大等效塑性应变 ${fmt(results.nodal_summary.max_equivalent_plastic_strain)}。${esc(results.nodal_summary.note||'')}</p>`:''}${Object.keys(summary.timing||{}).length?`<div class="timing-grid">${Object.entries(timings).filter(([k])=>summary.timing[k]!=null).map(([k,label])=>`<div><small>${label}</small><strong>${fmt(summary.timing[k])} 秒</strong></div>`).join('')}</div>`:''}${summary.failure_stage?`<p class="help-line">失败阶段：${esc(({reading:'读取输入',geometry:'几何与网格',build:'生成输入包',solver:'MAPDL 求解',postprocess:'后处理与校核'})[summary.failure_stage]||summary.failure_stage)}</p>`:''}${summary.error?`<p class="error-hint">${esc(summary.error)}</p>`:''}${warningsHtml([...new Set([...(summary.warnings||[]),...(summary.results?.warnings||[])])])}<p class="help-line">重启动文件按配置保存；可在任务文件中下载。此版本不提供未经 MAPDL 验证的一键续算。</p></div>`;
}

const select=(key,label,choices,help='',scope='option')=>`<div class="field"><label for="apdl-${key}">${label}</label><select id="apdl-${key}" data-${scope}="${key}">${choices.map(([v,l])=>`<option value="${v}">${l}</option>`).join('')}</select>${help?`<small>${help}</small>`:''}</div>`;
const input=(key,label,help='',scope='option',type='number')=>`<div class="field"><label for="apdl-${key}">${label}</label><input id="apdl-${key}" data-${scope}="${key}" type="${type}" ${type==='number'?'step="any"':''}>${help?`<small>${help}</small>`:''}</div>`;
const check=(key,label,scope='option')=>`<label class="check-field"><input type="checkbox" data-${scope}="${key}"> ${label}</label>`;
const group=(title,body,help='',open=true)=>`<details class="card apdl-group" ${open?'open':''}><summary><strong>${title}</strong>${help?`<small>${help}</small>`:''}</summary><div class="apdl-group-body">${body}</div></details>`;

export function renderExternalNpzSource(source,prefix){
 const info=source.npz_info,variable=source.npz_variable||info?.default_variable,selected=info?.variables.find(v=>v.name===variable),count=selected?.stage_count||1,stage=source.npz_stage||count;
 return `<div class="field apdl-source-row"><label for="apdl-${prefix}upload">外部腐蚀状态 NPZ</label><input id="apdl-${prefix}upload" type="file" accept=".npz" data-source="upload"><small>${esc(source.upload_name||'选择其他电脑、原程序或本站导出的模拟结果 .npz；不必重新运行模拟。')}</small></div>${info?`<p class="help-line">已识别 ${info.variables.filter(v=>v.supported).length} 个可读状态变量；结构检查 ${fmt(info.reading_seconds)} 秒。原状态轴顺序 [X,Y,Z]；状态=1 为金属。</p><div class="grid two"><div class="field"><label for="apdl-${prefix}npz-variable">状态变量</label><select id="apdl-${prefix}npz-variable" data-source="npz_variable">${info.variables.map(v=>`<option value="${esc(v.name)}" ${v.name===variable?'selected':''} ${v.supported?'':'disabled'}>${esc(v.name)} · ${v.shape.map(esc).join(' × ')}${v.supported?'':' · 不可直接读取'}</option>`).join('')}</select><small>perfect_a 为最终状态；a_sd 可为单状态或数值阶段序列。</small></div><div class="field"><label for="apdl-${prefix}npz-stage">阶段（按文件存储顺序）</label><input id="apdl-${prefix}npz-stage" data-source="npz_stage" type="number" min="1" max="${count}" step="1" value="${esc(stage)}"><small>共 ${count} 个状态，默认末状态。三维状态仅第 1 项；序号不代表腐蚀天数。</small></div>${['space_xy_um','space_z_um'].map(key=>`<div class="field"><label for="apdl-${prefix}${key}">${key==='space_xy_um'?'XY 平面':'Z 深度'}元胞尺寸 / μm</label><input id="apdl-${prefix}${key}" data-source="${key}" type="number" step="any" min="0" value="${esc(info.geometry[key]??source[key]??'')}" ${info.geometry[key]!=null?'disabled':''}><small>${info.geometry[key]!=null?'已从文件读取，保持原模拟物理尺寸。':'文件未提供，必须按原模拟配置补填，不能猜测。'}</small></div>`).join('')}</div><p class="help-line">所选状态 X × Y × Z：${(selected?.state_shape||[]).map(esc).join(' × ')}。XY 尺寸控制板面采样跨度，Z 尺寸控制腐蚀深度；下方预检可核对实际毫米尺寸和形貌。</p>${warningsHtml(info.warnings)}`:'<p class="help-line">上传后自动检查变量、阶段和元胞尺寸。仅支持数值 CA 状态；普通 ZIP、深度矩阵或仅参数的 NPZ 不能当作三维状态使用。</p>'}`;
}

export async function mountApdl({get,post,openJob}){
 const root=document.querySelector('#apdl-root');if(!root)return;
 const state=createApdlDraftState();
 let draft=state.draft,jobs=[],presets=[],capability={},busy=false,coordinatePending=0,disposePreview=()=>{};
 const coordinateGenerations=new Map();
 const faceUploads=createFaceUploadManager();
 root.innerHTML=`<div class="section-heading"><div><div class="section-overline">03 / APDL UNIAXIAL TENSION</div><h2>腐蚀钢板 · 单轴拉伸</h2><p>将单 / 双面形貌装配为三维六面体或四面体实体；先检查几何，再生成输入包或调用本机 MAPDL。</p></div><span class="badge neutral" id="apdl-capability">检查求解器…</span></div>
 <ol class="apdl-flow" aria-label="建模与求解流程">${['表面输入','坐标 / 正深度','剩余厚度','实体网格','指定方向拉伸','结果与校核'].map((s,i)=>`<li><span>0${i+1}</span><strong>${s}</strong></li>`).join('')}</ol>
 <div class="card"><div class="grid two">${select('preset','工况预设',[],'预设会更新材料、网格、加载与双面映射。','control')}${input('case_name','工况名称','','control','text')}</div><div id="apdl-preset-notes" class="help-line"></div><div id="apdl-solver-notes" class="help-line"></div></div>
 ${group('1 · 腐蚀模式与表面来源',`${select('corrosion_mode','腐蚀模式',[['flat','无腐蚀平板 · 直接验证'],['single_top','单面腐蚀 · 正面'],['single_bottom','单面腐蚀 · 反面'],['double_independent','双面独立 · 需配准'],['double_symmetric','双面对称 · 复用正面']])}<p id="apdl-mode-help" class="help-line"></p><div class="actions apdl-refresh"><button id="apdl-refresh" class="button secondary">刷新可用源任务</button></div><div id="apdl-sources" class="grid two"></div><div id="apdl-grid-options">${select('surface_grid_mode','双面网格模式',[['strict','严格配准'],['common_xy','共同XY映射']],'两种模式均要求物理位置与方向已配准；共同映射只统一采样，不会自动对齐试件。')}<div id="apdl-target-spacing" class="grid two">${input('mapping_dx_mm','目标 X 间距 / mm（可空）','留空取两面 X 间距较粗值；手动值须大于 0。')}${input('mapping_dy_mm','目标 Y 间距 / mm（可空）','留空取两面 Y 间距较粗值；更细的插值网格不会恢复缺失的细节。')}</div><p class="help-line" id="apdl-grid-help"></p></div><div id="apdl-registration"><label class="check-field"><input type="checkbox" data-control="registration_confirmed"> <span id="apdl-registration-label"></span></label></div>`)}
 ${group('2 · 原板几何与实体网格',`<div class="actions" id="apdl-local-corrosion-toggle">${check('local_corrosion','将腐蚀形貌作为局部区域放置到完整平板')}</div><div id="apdl-local-patch-placement"><div class="grid two">${input('patch_offset_x_mm','局部区域左下角 X 偏移 / mm','相对于完整平板左下角；留空时按几何中心计算并对齐到最近 X 网格线。')}${input('patch_offset_y_mm','局部区域左下角 Y 偏移 / mm','相对于完整平板左下角；留空时按几何中心计算并对齐到最近 Y 网格线。')}${select('patch_rotation_deg','局部形貌旋转',[['0','0°'],['90','90° 逆时针'],['180','180°'],['270','270° 逆时针']],'仅重排采样矩阵，不插值；旋转 90°/270° 时 X/Y 间距互换。')}${check('patch_flip_x','旋转后沿 X 翻转')}${check('patch_flip_y','旋转后沿 Y 翻转')}</div><p class="help-line">方向变换先应用于腐蚀形貌，再按变换后的网格尺寸嵌入平板。正反面使用同一方向变换；预检三维图展示实际变换后的结果。</p></div><div class="grid four">${input('thickness_mm','原始板厚 / mm','全局底面 z=0，顶面 z=t₀。')}${input('layers','厚度方向层数','保留完整 XY 采样；调节厚度分层；四面体单元数约为同层六面体的6倍。')}${select('mesh_type','实体网格类型',[['solid185_hex','SOLID185 · 结构化六面体（兼容）'],['solid285_tetra','SOLID285 · 四节点四面体（需收敛验证）'],['solid187_tetra','SOLID187 · 十节点四面体']],'共形六分四面体保留来源点距与角点深度，不自动加密；体积差与原生形状警告见报告。')}${input('length_mm','完整平板 X 尺寸 / mm','局部腐蚀模式下这是整个构件的 X 跨度。')}${input('width_mm','完整平板 Y 尺寸 / mm','局部腐蚀模式下这是整个构件的 Y 跨度。')}${input('nx','平板 X 方向采样数','无腐蚀模式可调；局部腐蚀模式由板尺寸和原始点距推导。')}${input('ny','平板 Y 方向采样数','无腐蚀模式由输入调整；局部腐蚀模式由板尺寸和原始点距推导。')}</div><p class="help-line">z_top = t₀ − d_top；z_bottom = d_bottom；剩余厚度 = t₀ − d_top − d_bottom。穿透时拒绝，禁止静默修补。局部腐蚀保留来源深度和点距，平板其余区域保持未腐蚀；完整平板长宽必须是 X/Y 间距整数倍，区域偏移必须对齐网格。网格仍覆盖整块平板，因此细点距会增加节点与单元数。</p>`)}
 ${group('3 · 材料与本构',`<div class="grid four">${select('material_model','材料模型',[['elastic','线弹性'],['bilinear_iso','BISO · 双线性等向硬化'],['multilinear_iso','MISO · 多线性等向硬化']],'材料参数仅为示例，应替换为试验值。')}${input('E_MPa','弹性模量 E / MPa')}${input('poisson_ratio','泊松比 ν','范围 −1 < ν < 0.5。')}<div></div><div data-material="bilinear_iso">${input('yield_MPa','屈服强度 / MPa')}</div><div data-material="bilinear_iso">${input('tangent_MPa','切线模量 / MPa','0 ≤ Et < E。')}</div></div><div data-material="multilinear_iso" class="apdl-curve"><label for="apdl-plastic-curve">MISO 曲线 · 二维 JSON [塑性应变, 应力 MPa]</label><textarea id="apdl-plastic-curve" data-option="plastic_curve" rows="9" spellcheck="false"></textarea><small id="apdl-curve-count" class="help-line"></small>${check('allow_negative_slope','明确允许负斜率下降段（原始 49 点预设含下降段，不作平滑）')}</div>`)}
 ${group('4 · 边界、加载与求解',`<div class="grid four">${select('tensile_direction','拉伸方向',[['X','沿全局 X 轴（按 X 跨度加载）'],['Y','沿全局 Y 轴（按 Y 跨度加载）']],'先看预检中的 X/Y 跨度；若要沿较长边拉伸，选择跨度数值较大的方向。选择方向只改变加载轴，不旋转或重排形貌数据。')}${select('boundary_mode','端部约束',[['poisson_free','自由泊松伸缩（推荐验证）'],['clamped_grips','两端夹持'],['legacy_recommended','原推荐脚本角点约束']],'端面与刚体约束按所选拉伸轴生成；自由模板允许横向收缩。')}${input('target_displacement_mm','目标拉伸位移 / mm','沿所选全局轴加载，不包含断裂、接触与屈曲。')}${input('substeps','初始子步数','需满足最小 ≤ 初始 ≤ 最大。')}${input('max_substeps','最大子步数')}${input('min_substeps','最小子步数')}${input('cores','CPU 核数')}${input('timeout_seconds','求解超时 / 秒','超时会终止求解进程树并保留已有文件。')}${input('restart_frequency','重启动保存频率','0 关闭；正整数按子步保存 MAPDL 重启动文件。')}</div><div class="grid four" id="apdl-grip-lengths"><div class="field"><label for="apdl-grip_length_fixed_mm">固定端夹持长度 / mm</label><input id="apdl-grip_length_fixed_mm" data-option="grip_length_fixed_mm" type="number" min="0" step="any" value="0"><small>0 表示仅约束端面节点；仅两端夹持模式生效。</small></div><div class="field"><label for="apdl-grip_length_loaded_mm">加载端夹持长度 / mm</label><input id="apdl-grip_length_loaded_mm" data-option="grip_length_loaded_mm" type="number" min="0" step="any" value="0"><small>0 表示仅约束端面节点；仅两端夹持模式生效。</small></div></div><div class="actions apdl-checks">${check('large_deflection','启用大变形 NLGEOM')}${check('export_full_field','导出末步完整节点场（位移 / 等效应力 / 塑性应变）')}</div><p class="help-line">两端夹持抑制端部横向收缩，可能偏离 EA/L。夹持长度仅在两端夹持模式下生效，把端面约束扩展为一段节点区域，两端之和不得超过所选拉伸轴跨度。原推荐脚本角点约束用于与原始模型对照，尚不代表本机验证通过。</p>`)}
 ${group('结果文件保存',`<div class="grid two">${select('result_save_mode','RST 场结果保存模式',[['all','完整保存（默认）'],['last','仅保存末步单元场'],['selected','指定比例请求（当前完整保存）']],'三种模式均保留逐收敛子步位移与反力；MISO 还保留逐步材料筛查。')}<div id="apdl-field-times">${input('field_output_times','加载比例（英文逗号分隔）','0 < 比例 ≤ 1，严格递增，至多20项且必须包含1。例如0.25, 0.5, 0.75, 1。','option','text')}</div></div><p class="help-line">比例是静力加载份额，不是秒。指定比例请求因 MAPDL 关键时刻数组不能与逐子步输出混用，当前实际完整保存，不减少 RST 体积。仅末步模式保存末步单元场。上方“导出末步完整节点场”仅控制 CSV；重启动文件独立控制。三种模式均不改变加载与子步设置。</p>`)}
 <div class="card precheck-card"><div class="card-heading"><div><h3>5 · 预检与几何预览</h3><p>核对真实行列、坐标变换、深度与剩余厚度；参数变更后自动失效。</p></div><button id="apdl-precheck" class="button secondary">预检并预览</button></div><div id="apdl-preview" class="preview" aria-live="polite">默认平板可以直接预检与生成模型。</div></div>
 <div class="action-bar"><div><strong>创建独立 APDL 拉伸任务</strong><small>提交前重新预检，逐面冻结来源与 SHA-256；输入包可下载后在 ANSYS 中核对。</small></div><div class="actions"><button id="apdl-build" class="button secondary">仅生成模型</button><button id="apdl-solve" class="button primary" disabled>生成并求解 →</button></div></div><div id="apdl-message" class="message" hidden role="status" aria-live="polite"></div>`;
 const q=s=>root.querySelector(s),qa=s=>Array.from(root.querySelectorAll(s));
 function note(text,error=false){q('#apdl-message').textContent=text;q('#apdl-message').hidden=!text;q('#apdl-message').classList.toggle('error',error);}
 function invalidate(){state.invalidate();disposePreview();q('#apdl-preview').textContent='配置已变更，请重新预检；提交时也会自动重新预检。';}
 function buttons(){const blocked=busy||faceUploads.pending>0||coordinatePending>0;q('#apdl-precheck').disabled=blocked;q('#apdl-build').disabled=blocked;q('#apdl-solve').disabled=blocked||!capability.available;q('#apdl-refresh').disabled=blocked;qa('[data-matlab-convert]').forEach(button=>{button.disabled=blocked;});}
 function syncRegistration(){q('[data-control="registration_confirmed"]').checked=draft.registration_confirmed;}
 function syncField(el){
  const value=el.type==='checkbox'?el.checked:el.value;
  if(el.dataset.option)state.update('option',el.dataset.option,value);
  else if(el.dataset.control&&el.dataset.control!=='preset')state.update('control',el.dataset.control,value);
  else if(el.dataset.map&&!el.disabled)state.update('map',el.dataset.map,value,el.closest('[data-face]').dataset.face);
  else if(el.dataset.conversion)state.update('source',el.dataset.conversion,value,el.closest('[data-face]').dataset.face);
 }
 function read(){
  syncField(q('[data-control="registration_confirmed"]'));
  qa('[data-option], [data-control="case_name"], [data-map], [data-conversion]').forEach(syncField);
  syncRegistration();
  const material=q('#apdl-plastic-curve').dataset.materialSource;
  draft.material_source=material?JSON.parse(material):null;
  if(draft.material_source&&(JSON.stringify(JSON.parse(q('#apdl-plastic-curve').value||'null'))!==JSON.stringify(draft.material_source.curve)||Number(draft.options.E_MPa)!==draft.material_source.selection.E_MPa||draft.options.material_model!=='multilinear_iso'))draft.material_source=null;
 }
 function setControls(){qa('[data-option]').forEach(el=>{const value=draft.options[el.dataset.option];if(el.type==='checkbox')el.checked=!!value;else if(el.dataset.option==='field_output_times')el.value=Array.isArray(value)?value.join(', '):(value??'');else el.value=typeof value==='object'?(value?JSON.stringify(value,null,2):''):(value??'');});q('[data-control="case_name"]').value=draft.case_name; q('[data-control="registration_confirmed"]').checked=draft.registration_confirmed;q('[data-control="preset"]').value=draft.preset_id;visibility();}
 function visibility(){q('#apdl-field-times').hidden=q('[data-option="result_save_mode"]').value!=='selected';const mode=q('[data-option="corrosion_mode"]').value,local=q('[data-option="local_corrosion"]').checked,material=q('[data-option="material_model"]').value;q('#apdl-local-corrosion-toggle').hidden=mode==='flat';q('#apdl-local-patch-placement').hidden=!local||mode==='flat';q('#apdl-registration').hidden=mode!=='double_independent';const common=mode==='double_independent'&&q('[data-option="surface_grid_mode"]').value==='common_xy';q('#apdl-grid-options').hidden=mode!=='double_independent';q('#apdl-target-spacing').hidden=!common;q('#apdl-grid-help').textContent=common?'取两面实际物理范围交集，采用双线性插值，不外推；边缘不足完整目标间隔时向内截取。粗网格可能遗漏窄坑，请核对映射前后深度和实际尺寸。':'严格要求正反面行列、间距、原点与 XY 网格一致，保留原采样。';q('#apdl-registration-label').textContent=common?'我确认两面处于同一物理坐标系且方向已配准，同意按交集裁剪与显式插值。':'我确认正反面已在同一物理坐标系与 XY 方向下完成配准。';qa('[data-material]').forEach(el=>el.hidden=el.dataset.material!==material);for(const key of ['length_mm','width_mm'])q(`[data-option="${key}"]`).disabled=mode!=='flat'&&!local;for(const key of ['nx','ny'])q(`[data-option="${key}"]`).disabled=mode!=='flat'||local;q('#apdl-grip-lengths').hidden=q('[data-option="boundary_mode"]').value!=='clamped_grips';q('#apdl-mode-help').textContent=mode==='flat'?'无腐蚀平板不需要表面文件；适用于与 EA/L 解析解对照。':mode==='double_symmetric'?'反面明确复用同一正面深度场；不代表两次独立腐蚀样本。':common?'共同XY映射将两面映射到同一物理网格；下方预检与三维图显示映射后的实际建模区域。':local?'腐蚀形貌按原始点距嵌入完整矩形平板，板外保持未腐蚀；面板尺寸与局部位置以预检显示为准。':'形貌模式从来源继承真实 XY 尺寸，完整保留采样，不进行自动降采样。';try{const curve=JSON.parse(q('#apdl-plastic-curve').value||'null');q('#apdl-curve-count').textContent=Array.isArray(curve)?`当前 ${curve.length} 个点；首点塑性应变应为 0，随后严格递增。`:'请输入二维 JSON 曲线。';}catch{q('#apdl-curve-count').textContent='JSON 格式尚未有效，请检查逗号与方括号。';}}
 function coordinateSourceCard(face,s,label,prefix){
  const uploads=s.coordinate_uploads||{},names=s.coordinate_names||{},direction=s.coordinate_direction||(face==='top'?'front':'back');
  const fields=[['x','X坐标'],['y','Y坐标'],['z','Z坐标']].map(([axis,title])=>`<div class="field"><label for="apdl-${prefix}${axis}">${title}文件</label><input id="apdl-${prefix}${axis}" type="file" accept=".txt,.csv,.tsv" data-coordinate="${axis}"><small>${esc(names[axis]||uploads[axis]||'未上传')}</small></div>`).join('');
  return `<div class="apdl-source" data-face="${face}"><h4>${label}</h4><div class="field"><label for="apdl-${prefix}origin">读取方式</label><select id="apdl-${prefix}origin" data-source="origin"><option value="task">已完成源任务</option><option value="upload">上传二维矩阵</option><option value="upload_npz">上传外部 NPZ</option><option value="coordinates" selected>上传 MATLAB XYZ 坐标</option></select></div><p class="help-line">上传 MATLAB 展平 X/Y/Z 坐标文件，仅接受完整规则 XY 网格；不插值、不猜测尺寸。</p>${renderMatlabConversionSummary(s.conversion_summary)}<div class="grid two">${fields}<div class="field"><label for="apdl-${prefix}direction">Z方向解释</label><select id="apdl-${prefix}direction" data-coordinate="direction"><option value="front" ${direction==='front'?'selected':''}>正面：max(Z) − Z</option><option value="back" ${direction==='back'?'selected':''}>反面：Z − min(Z)</option></select></div></div></div>`;
 }
 function sourceCard(face){const s=draft[face],label=face==='top'?'正面 · 上表面':'反面 · 下表面',coordinate=s.origin==='coordinates'||s.source_kind==='coordinates',external=s.origin==='upload_npz',isUpload=external||s.origin==='upload',isSim=external||(!isUpload&&s.source_kind==='simulation'),job=jobs.find(j=>j.id===s.source_job_id),files=availableSurfaceFiles(job),prefix=`${face}-`;if(coordinate)return coordinateSourceCard(face,s,label,prefix);
  const matInfo=s.mat_info||{};
  const matVariables=Array.isArray(matInfo.variables)?matInfo.variables:[];
  const matVariable=matInfo.variable||s.mapping?.variable||'';
  const matNotice=isUpload&&s.upload_name?.toLowerCase().endsWith('.mat')?(matInfo.loading?'<p class="help-line">正在识别 MAT 变量和行列数…</p>':matVariables.length?`<p class="help-line">已识别变量：${esc(matVariable||'请选择')}；尺寸：${matInfo.shape?matInfo.shape.join(' × '):'待选择'}（行 × 列）。</p>`:'<p class="help-line">未识别到二维数值变量，请检查 MAT 文件内容。</p>') : '';
  const variableField=isUpload&&matVariables.length>1?`<div class="field"><label for="apdl-${prefix}mat-variable">MAT 表面变量</label><select id="apdl-${prefix}mat-variable" data-mat-variable>${matVariables.map(v=>`<option value="${esc(v.name)}" ${v.name===matVariable?'selected':''}>${esc(v.name)} · ${v.shape.join(' × ')}</option>`).join('')}</select><small>自动读取二维数值矩阵；请选择腐蚀 Z 值对应的变量。</small></div>`:'';
  return `<div class="apdl-source" data-face="${face}"><h4>${label}</h4><div class="grid two"><div class="field"><label for="apdl-${prefix}origin">读取方式</label><select id="apdl-${prefix}origin" data-source="origin"><option value="task" ${isUpload?'':'selected'}>已完成源任务</option><option value="upload" ${s.origin==='upload'?'selected':''}>上传二维矩阵</option><option value="upload_npz" ${external?'selected':''}>上传外部 NPZ</option><option value="coordinates" ${coordinate?'selected':''}>上传 MATLAB XYZ 坐标</option></select></div><div class="field"><label for="apdl-${prefix}kind">来源类型</label><select id="apdl-${prefix}kind" data-source="source_kind" ${isUpload?'disabled':''}><option value="simulation" ${isSim?'selected':''}>CA–GA 模拟</option><option value="measured" ${!isSim?'selected':''}>实测 MAT / 矩阵</option></select></div></div>${external?renderExternalNpzSource(s,prefix):isUpload?`<div class="field apdl-source-row"><label for="apdl-${prefix}upload">MAT / CSV / TXT / TSV 数值矩阵</label><input id="apdl-${prefix}upload" type="file" accept=".mat,.csv,.txt,.tsv" data-source="upload"><small>${esc(s.upload_name||'上传无表头二维矩阵；XYZ 点云需先在第一模块处理。')}</small></div>${matNotice}${variableField}${renderMatlabConversionControls(s,prefix)}<div class="actions apdl-source-row"><button type="button" class="button secondary" data-matlab-convert="${face}" ${matInfo.loading||!s.upload_id?'disabled':''}>用 MATLAB 转换为 APDL X/Y/Z</button><small>自动读取矩阵行列，用当前 X/Y 间距和原点生成三份坐标文件。</small></div>`:`<div class="field apdl-source-row"><label for="apdl-${prefix}job">已完成任务</label><select id="apdl-${prefix}job" data-source="source_job_id"><option value="">请选择来源</option>${jobs.filter(j=>isSim?j.kind==='simulation':['pointcloud','finite_element'].includes(j.kind)).map(j=>`<option value="${esc(j.id)}" ${j.id===s.source_job_id?'selected':''}>${esc(j.display_name||j.spec?.case_name||j.case_name||j.id)} · ${esc(j.id)}</option>`).join('')}</select></div><div class="field apdl-source-row"><label for="apdl-${prefix}file">${isSim?'模拟阶段':'可用 MAT 文件'}</label><select id="apdl-${prefix}file" data-source="${isSim?'source_stage':'source_file'}"><option value="">${isSim?'最终 simulation.npz':'自动选择唯一 MAT'}</option>${files.filter(f=>isSim?/stage_\d+\.npz$/i.test(f):true).map(f=>{const value=isSim?String(Number(f.match(/stage_(\d+)\.npz$/i)[1])):f;return `<option value="${esc(value)}" ${String(isSim?s.source_stage:s.source_file)===value?'selected':''}>${esc(f)}</option>`;}).join('')}</select><small>仅列出所选任务实际提供的 ${isSim?'阶段 NPZ':'MAT'} 输出。</small></div>`}
  <details class="apdl-mapping" open><summary>坐标与深度映射</summary><div class="grid two">${select(prefix+'variable','表面变量',[['','自动识别唯一变量'],['Z_filled','Z_filled'],['F_filled','F_filled']],isSim?'模拟使用第一层金属规则，不读取 MAT 变量。':'MAT 含多个表面时必须明确指定。','map')}${select(prefix+'layout','输入行列约定',[['auto','自动 · 使用来源约定'],['yx','行=Y，列=X'],['xy','行=X，列=Y']],'统一输出 depth[row_y,column_x]。','map')}${select(prefix+'unit','原矩阵单位',[['mm','mm'],['um','μm']],'内部统一转为 mm。','map')}${select(prefix+'value_mode','数值含义',[['depth','正值向内腐蚀深度'],['height','相对基准的表面高度']],'模拟固定按正深度 mm 读取。','map')}${select(prefix+'reference_mode','高度参考面',[['manual','手动参考高度'],['maximum','当前矩阵最大高度']],'先按显式裁剪，再计算最大高度。','map')}${input(prefix+'reference_height','参考高度 / 原矩阵单位','','map')}${select(prefix+'height_sign','高度方向',[['1','+1 · reference − height'],['-1','−1 · height − reference']],'方向变换不等于 XY 镜像。','map')}${input(prefix+'center_crop_columns','中心裁剪列数（可空）','仅实测：原双面预设为 193 列。','map')}${input(prefix+'dx_mm','X 间距 / mm',isSim?'继承模拟真实间距，不可覆盖。':'上传必填；任务来源可留空继承已知间距。','map')}${input(prefix+'dy_mm','Y 间距 / mm',isSim?'继承模拟真实间距，不可覆盖。':'上传必填；没有来源间距时需填写。','map')}${input(prefix+'origin_x_mm','X 原点 / mm','留空继承源任务，上传默认 0。','map')}${input(prefix+'origin_y_mm','Y 原点 / mm','留空继承源任务，上传默认 0。','map')}</div><div class="actions apdl-checks">${check(prefix+'transpose','额外转置 X/Y','map')}${check(prefix+'flip_x','翻转 X','map')}${check(prefix+'flip_y','翻转 Y','map')}</div></details></div>`;
 }
 function renderSources(){const mode=draft.options.corrosion_mode,faces=mode==='flat'?[]:mode==='single_bottom'?['bottom']:mode==='double_independent'?['top','bottom']:['top'];q('#apdl-sources').innerHTML=faces.map(sourceCard).join('');for(const face of faces){const node=q(`[data-face="${face}"]`),s=draft[face],sim=s.origin!=='upload'&&s.source_kind==='simulation';node.querySelectorAll('[data-map]').forEach(el=>{el.dataset.map=el.dataset.map.replace(`${face}-`,'');const key=el.dataset.map,value=apdlMappingDisplay(s)[key];if(el.type==='checkbox')el.checked=!!value;else el.value=value??'';if(sim&&['dx_mm','dy_mm','origin_x_mm','origin_y_mm','variable','unit','value_mode','center_crop_columns','reference_mode','reference_height','height_sign'].includes(key)){el.disabled=true;if(['dx_mm','dy_mm','origin_x_mm','origin_y_mm'].includes(key))el.placeholder='继承模拟来源；预检后核对实际值';}});}}
 async function loadJob(id){if(!id)return;const full=await get(`/api/jobs/${encodeURIComponent(id)}`);jobs=jobs.map(j=>j.id===id?{...j,...full}:j);}
 async function refresh(){const data=await get('/api/jobs');jobs=(Array.isArray(data)?data:data.jobs||[]).filter(j=>j.state==='completed'&&['simulation','pointcloud','finite_element'].includes(j.kind));for(const face of ['top','bottom'])if(draft[face].source_job_id)await loadJob(draft[face].source_job_id);renderSources();}
 async function runPrecheck(mode='build'){read();const version=state.revision,payload=buildApdlPayload(draft,mode),result=await post('/api/apdl/precheck',payload);state.acceptPrecheck(result,version,payload);disposePreview();q('#apdl-preview').innerHTML=`${statGrid(result.stats)}${tensileSummary(result.stats,result.options||payload.options)}<p class="help-line">实际网格 ${fmt(result.stats.nx)} × ${fmt(result.stats.ny)}，厚度 ${fmt(result.stats.layers)} 层；输入读取 ${fmt(result.reading_seconds)} 秒。预览最多约 80 × 80，仅用于观察，不改变有限元采样。</p>${Object.entries(result.faces||{}).map(([face,m])=>`<p class="help-line">${face==='top'?'正面':'反面'}：${esc(m.name||m.source_job_id||m.upload_id)} · ${esc(m.variable||m.source_kind)} · 原尺寸 ${(m.original_shape||[]).map(esc).join(' × ')} → Y/X ${(m.shape||[]).map(esc).join(' × ')} · dx=${fmt(m.dx_mm)} / dy=${fmt(m.dy_mm)} mm · 深度 ${fmt(m.min_depth_mm)} ~ ${fmt(m.max_depth_mm)} mm<br>SHA-256：${esc(m.sha256||'待冻结')}</p>`).join('')}${renderApdlSurfaceMapping(result.surface_mapping)}${warningsHtml(result.warnings)}${renderApdlDiagnostics(result.diagnostics)}<div class="apdl-preview-charts"><figure><canvas data-heat="top_depth" aria-label="正面腐蚀深度热图"></canvas><figcaption>正面腐蚀深度 / mm</figcaption></figure><figure><canvas data-heat="remaining" aria-label="剩余厚度热图"></canvas><figcaption>剩余厚度 / mm</figcaption></figure></div><div id="apdl-orientation"></div><div id="apdl-section"></div>`;drawPreview(result,q);disposePreview=mountApdl3DPreview(q('#apdl-orientation'),result);return payload;}
 async function action(mode){if(busy||faceUploads.pending)return;busy=true;buttons();note(mode==='check'?'正在读取与预检…':'正在重新预检并冻结任务输入…');try{const payload=await runPrecheck(mode==='solve'?'solve':'build');if(mode==='check'){note('预检通过。请检查深度、剩余厚度、来源映射与网格规模。');return;}if(mode==='solve'&&!capability.available)throw new Error('未发现本机 MAPDL 可执行文件；可先生成模型包。');const job=await post('/api/apdl/jobs',payload);note(`APDL 任务已创建：${job.id||job.job_id}`);await openJob(job.id||job.job_id,job);}catch(error){note(error.message,true);}finally{busy=false;buttons();}}
 async function convertMatrix(face){if(busy||faceUploads.pending||coordinatePending)return;read();const source=draft[face],body=matlabConversionPayload(source,face);coordinatePending++;buttons();note('正在调用 MATLAB 生成 APDL X/Y/Z 坐标文件…');try{const result=await post('/api/apdl/matlab-convert',body);validateMatlabConversion(result,body);const target=draft[face];target.origin='coordinates';target.source_kind='coordinates';target.coordinate_uploads=Object.fromEntries(Object.entries(result.files).map(([axis,item])=>[axis,item.id]));target.coordinate_names=Object.fromEntries(Object.entries(result.files).map(([axis,item])=>[axis,item.name]));target.coordinate_direction=body.coordinate_direction;target.conversion_summary=result.conversion;for(const key of ['upload_id','upload_name','mapping','mat_info'])delete target[key];target.mapping={...mappingDefaults};draft.registration_confirmed=false;state.invalidate();renderSources();visibility();note(`MATLAB 转换完成：${result.shape[0]} × ${result.shape[1]} 网格，共 ${result.point_count} 点；已切换到坐标预检。`);}finally{coordinatePending--;buttons();}}
 root.addEventListener('click',async event=>{const button=event.target.closest('[data-matlab-convert]');if(!button)return;try{await convertMatrix(button.dataset.matlabConvert);}catch(error){note(error.message,true);}finally{buttons();}});
 root.addEventListener('input',event=>{const el=event.target;if(!el.matches('input,select,textarea'))return;
  if(el.dataset.source&&el.dataset.source!=='upload'){const face=el.closest('[data-face]').dataset.face;read();faceUploads.invalidate(face);state.update('source',el.dataset.source,el.value,face);}
  else syncField(el);
  syncRegistration();invalidate();visibility();
 });
 root.addEventListener('change',async event=>{const el=event.target;try{if(el.dataset.control==='preset'){for(const face of ['top','bottom'])faceUploads.invalidate(face);read();const preset=presets.find(p=>p.id===el.value);if(!preset)return;state.replace(applyApdlPreset(draft,preset));draft=state.draft;q('#apdl-preset-notes').innerHTML=(preset.notes||[]).map(esc).join('<br>')+(preset.provenance?`<br>来源 GitHub：${esc(preset.provenance.repository)} · APDL blob <code>${esc(preset.provenance.apdl_blob)}</code>`:'');setControls();renderSources();invalidate();}
 else if(el.dataset.option==='corrosion_mode'){for(const face of ['top','bottom'])faceUploads.invalidate(face);read();renderSources();visibility();invalidate();}
 else if(el.dataset.coordinate){const face=el.closest('[data-face]').dataset.face,axis=el.dataset.coordinate;if(axis==='direction'){state.update('source','coordinate_direction',el.value,face);renderSources();invalidate();}else{const file=el.files[0];if(!file)return;const key=face+':'+axis,token=(coordinateGenerations.get(key)||0)+1;coordinateGenerations.set(key,token);coordinatePending++;buttons();try{const response=await fetch('/api/uploads?name='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});const record=await response.json();if(!response.ok)throw new Error(record.error||record.message||'上传失败');if(coordinateGenerations.get(key)!==token||draft[face].origin!=='coordinates')return;delete draft[face].conversion_summary;draft[face].coordinate_uploads={...(draft[face].coordinate_uploads||{}),[axis]:record.id||record.upload_id};draft[face].coordinate_names={...(draft[face].coordinate_names||{}),[axis]:file.name};state.invalidate();note('已上传 '+axis.toUpperCase()+' 坐标文件：'+file.name);}catch(error){if(coordinateGenerations.get(key)===token)note(error.message,true);}finally{coordinatePending--;buttons();renderSources();}}}else if(el.dataset.source){read();const face=el.closest('[data-face]').dataset.face,s=draft[face],key=el.dataset.source;if(key==='upload'){const file=el.files[0];if(!file)return;const external=s.origin==='upload_npz';for(const key of ['upload_id','upload_name','npz_info','npz_variable','npz_stage','space_xy_um','space_z_um'])delete s[key];draft.registration_confirmed=false;syncRegistration();invalidate();note(external?'正在上传并检查 NPZ 状态、阶段与尺寸…':'正在上传二维表面矩阵…');
 const recordPromise=(async()=>{const response=await fetch(`/api/uploads?name=${encodeURIComponent(file.name)}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});const record=await response.json();if(!response.ok)throw new Error(record.error||record.message||'上传失败');const id=record.id||record.upload_id;if(external)record.npz_info=await get(`/api/uploads/${encodeURIComponent(id)}/inspect?kind=apdl_npz`);else if(file.name.toLowerCase().endsWith('.mat'))record.mat_info=await get(`/api/uploads/${encodeURIComponent(id)}/inspect?kind=mat`);return record;})();
 const pendingUpload=faceUploads.run(face,()=>draft[face],recordPromise,file.name);buttons();if(!await pendingUpload)return;if(!external&&file.name.toLowerCase().endsWith('.mat')){const info=draft[face].mat_info||{},variables=info.variables||[],preferred=variables.find(v=>v.name==='Z_filled'||v.name==='F_filled')||variables[0];draft[face].mat_info={...info,variables,variable:preferred?.name||'',shape:preferred?.shape||null};draft[face].mapping={...(draft[face].mapping||mappingDefaults),variable:preferred?.name||''};note(variables.length?`已识别 ${file.name}：${preferred?.name||'二维矩阵'}，${preferred?.shape?.join(' × ')||'未知'}（行 × 列）。`:'未识别到二维数值变量，请检查 MAT 文件。');}else note(external?`已读取 ${file.name}；请核对状态、阶段，并补填缺失的元胞尺寸。`:`已上传 ${file.name}；请填写物理间距并核对单位。`);renderSources();}
 else {faceUploads.invalidate(face);state.update('source',key,el.value,face);syncRegistration();invalidate();if(key==='source_job_id')await loadJob(el.value);}renderSources();invalidate();}
 else {read();visibility();invalidate();}}catch(error){note(error.message,true);}finally{buttons();}});
 q('#apdl-refresh').addEventListener('click',async()=>{busy=true;buttons();try{read();invalidate();await refresh();note('已刷新源任务与可用文件。');}catch(error){note(error.message,true);}finally{busy=false;buttons();}});
 q('#apdl-precheck').addEventListener('click',()=>action('check'));q('#apdl-build').addEventListener('click',()=>action('build'));q('#apdl-solve').addEventListener('click',()=>action('solve'));
 try{const [p,c]=await Promise.all([get('/api/apdl/presets'),get('/api/apdl/capabilities')]);presets=Array.isArray(p)?p:p.presets||[];capability=c;q('[data-control="preset"]').innerHTML=presets.map(item=>`<option value="${esc(item.id)}">${esc(item.name)}</option>`).join('');q('#apdl-capability').textContent=c.available?'本机 MAPDL 可调用':'可建模 · 未发现 MAPDL';q('#apdl-solver-notes').innerHTML=`${c.available?'求解器：'+esc(c.executable):'未定位 MAPDL 可执行文件，已禁用求解；可生成输入包后在 ANSYS 中运行。'}<br>许可证状态：${esc(c.license_state==='unchecked'?'尚未实际验证':c.license_state||'尚未实际求解验证')}。${(c.warnings||[]).map(esc).join('；')}`;q('#apdl-preset-notes').textContent=(presets.find(p=>p.id==='elastic_flat')?.notes||[]).join('；');setControls();renderSources();await refresh();}catch(error){setControls();renderSources();note(`APDL 初始化失败：${error.message}`,true);}finally{buttons();}
 return {loadDraft(saved){
  if(busy||faceUploads.pending||coordinatePending)throw new Error('有限元工作区正在处理输入，请结束后重试');
  for(const face of ['top','bottom'])faceUploads.invalidate(face);
  state.replace(loadedApdlDraft(saved));draft=state.draft;
  delete q('#apdl-plastic-curve').dataset.materialSource;
  setControls();renderSources();invalidate();buttons();
  q('#apdl-preset-notes').textContent='已载入任务配置及冻结输入副本；修改后请重新预检。双面独立模式需重新确认配准。';
  note('配置已载入，尚未创建或求解新任务。');
 }};
}

function drawPreview(result,q){const preview=result.preview||{};for(const name of ['top_depth','remaining']){const matrix=preview[name],canvas=q(`[data-heat="${name}"]`);if(!matrix?.length||!matrix[0]?.length||!canvas)continue;canvas.width=640;canvas.height=300;const ctx=canvas.getContext('2d'),values=matrix.flat(),min=Math.min(...values),max=Math.max(...values),w=580/matrix[0].length,h=240/matrix.length;ctx.fillStyle='#f6f9f3';ctx.fillRect(0,0,640,300);matrix.forEach((row,y)=>row.forEach((v,x)=>{const f=max===min ? .5 :(v-min)/(max-min);ctx.fillStyle=`hsl(${145-105*f},45%,${83-46*f}%)`;ctx.fillRect(40+x*w,12+y*h,w+.5,h+.5);}));ctx.fillStyle='#48654b';ctx.font='14px Microsoft YaHei';ctx.fillText(`X →  ·  Y ↓     ${fmt(min)} ~ ${fmt(max)} mm`,40,280);}
 const top=preview.top_depth,bottom=preview.bottom_depth;if(!top?.length||!bottom?.length)return;const direction=result.options?.tensile_direction||'X',i=direction==='X'?Math.floor(top.length/2):Math.floor(top[0].length/2),t=result.options.thickness_mm,a=direction==='X'?top[i].map(v=>t-v):top.map(row=>t-row[i]),b=direction==='X'?bottom[i]:bottom.map(row=>row[i]),coords=direction==='X'?previewGeometry(result).x:previewGeometry(result).y,start=Number(direction==='X'?result.options.origin_x_mm||0:result.options.origin_y_mm||0),x=j=>45+(coords[j]-start)/(direction==='X'?result.stats.length_mm:result.stats.width_mm)*650,z=v=>225-v/t*180,points=v=>v.map((value,j)=>`${x(j).toFixed(1)},${z(value).toFixed(1)}`).join(' '),span=direction==='X'?result.stats.length_mm:result.stats.width_mm,transverse=direction==='X'?'Y':'X';q('#apdl-section').innerHTML=`<figure class="apdl-section"><svg viewBox="0 0 750 270" role="img" aria-label="沿 ${direction} 的 ${transverse} 中线剖面，显示上表面和下表面的实际 Z 坐标"><path d="M45 25V225H710" fill="none" stroke="#a6b5a0"/><polygon points="${points(a)} ${b.map((value,j)=>`${x(j)},${z(value)}`).reverse().join(' ')}" fill="#e4ecdc"/><polyline points="${points(a)}" fill="none" stroke="#276e50" stroke-width="3"/><polyline points="${points(b)}" fill="none" stroke="#a27845" stroke-width="3"/><text x="12" y="24" font-size="12" fill="#526c50">Z / mm</text><text x="40" y="248" font-size="12" fill="#526c50">${fmt(start)}</text><text x="600" y="248" font-size="12" fill="#526c50">${direction} → ${fmt(start+span)} mm</text><text x="6" y="48" font-size="11" fill="#526c50">${fmt(t)}</text></svg><figcaption>${transverse} 中线剖面 · 绿线为顶面，棕线为底面；Z 轴放大展示，非等比例几何。</figcaption></figure>`;
}
