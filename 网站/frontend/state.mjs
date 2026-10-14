// 与界面无关的规范配置状态。所有提交都由此状态生成，避免导入后回退默认值。
export const clone = (value) => structuredClone(value);
export function getPath(object, path) { return path.split('.').reduce((item, key) => item?.[key], object); }
export function setPath(object, path, value) {
  const parts = path.split('.');
  if (parts.some((key) => ['__proto__', 'prototype', 'constructor'].includes(key))) throw new Error('无效配置路径');
  const key = parts.pop(); let parent = object;
  for (const part of parts) { parent[part] ??= {}; parent = parent[part]; }
  parent[key] = value;
}
function merge(base, incoming) {
  if (!incoming || typeof incoming !== 'object' || Array.isArray(incoming)) return clone(incoming);
  const result = clone(base || {});
  for (const [key, value] of Object.entries(incoming)) {
    if (['__proto__','prototype','constructor'].includes(key)) throw new Error('配置含不允许的字段');
    result[key] = value && typeof value === 'object' && !Array.isArray(value) ? merge(result[key],value) : clone(value);
  }
  return result;
}
export function normaliseCatalog(items) {
  return (items || []).map((item) => ({...item,path:item.path || `${item.group}.${item.key}`,type:item.type || (Array.isArray(item.value)?'array':typeof item.value==='boolean'?'boolean':typeof item.value==='number'?'number':item.value===null?'json':'string'),label:item.label || item.key || item.path,editable:item.editable !== false}));
}
export function catalogFromConfig(config) {
  const result=[];
  function visit(value,path='') { for(const [key,item] of Object.entries(value)) {const current=path?`${path}.${key}`:key;if(item && typeof item==='object' && !Array.isArray(item))visit(item,current);else result.push({path:current,group:path||'常量',key,value:item,help:current});} }
  visit(config);return normaliseCatalog(result);
}
export function applyMode(config, mode) {
  if (!['strict','fast'].includes(mode)) throw new Error('请选择严格或高速模式');
  config.mode=mode; config.TAICHI_CONFIG ||= {};config.TAICHI_CONFIG.use_taichi=mode==='fast';
  if(mode==='strict') for(const group of ['STAGE_GA_CONFIG','SINGLE_STAGE_GA_CONFIG']) { config[group] ||= {};config[group].parallel_workers=1; }
  return config;
}
export function createWorkspace(defaults) {
  const simulation=clone(defaults.simulation), pointcloud={};
  const pointcloudCatalog=normaliseCatalog(defaults.pointcloud_catalog || (Array.isArray(defaults.pointcloud)?defaults.pointcloud:catalogFromConfig(defaults.pointcloud || {})));
  for(const item of pointcloudCatalog) if(item.editable && !['input','output'].includes(item.group))setPath(pointcloud,item.path,clone(item.value));
  applyMode(simulation,simulation.mode || 'strict');
  return {simulation,pointcloud,targets:clone(simulation.ACTIVE_STAGE_TARGET_DATA || []),runMode:'staged',seedMode:'fixed',targetUpload:null,targetIssues:[],targetVariable:'',targetOrientation:'auto',transferGeometry:null,cases:[],batchMode:'sequential',parallelCaseWorkers:2,sequentialEnabled:true,parallelEnabled:true,pointcloudCatalog};
}
export function importSimulation(state, incoming) {
  if (!incoming || typeof incoming!=='object' || Array.isArray(incoming)) throw new Error('JSON配置必须为对象');
  const source=incoming.simulation || incoming.config || incoming;
  state.simulation=merge(state.simulation,source);applyMode(state.simulation,state.simulation.mode || 'strict');
  state.targets=clone(incoming.targets || state.simulation.ACTIVE_STAGE_TARGET_DATA || []);
  if(incoming.run_mode && ['single','staged'].includes(incoming.run_mode))state.runMode=incoming.run_mode;
  state.seedMode=incoming.seed_mode || 'fixed';state.targetUpload=null;state.targetIssues=[];state.targetVariable='';state.transferGeometry=null;
  if(incoming.pointcloud)state.pointcloud=merge(state.pointcloud,incoming.pointcloud);
  const multi=state.simulation.MULTI_CASE_CONFIG;
  if(multi){state.cases=clone(multi.cases||[]);state.batchMode=multi.run_mode;state.parallelCaseWorkers=multi.parallel_case_workers;state.sequentialEnabled=multi.sequential_enabled;state.parallelEnabled=multi.parallel_enabled;}
}
function finiteJson(value) { if(typeof value==='number' && !Number.isFinite(value))throw new Error('数组或对象必须只含有限数值');if(value && typeof value==='object')for(const item of Object.values(value))finiteJson(item);return value; }
export function parseTyped(value,type) {
  if(['boolean','bool'].includes(type)) {if(value===true || value==='true')return true;if(value===false || value==='false')return false;throw new Error('请选择 true / false');}
  if(['number','float','integer','int'].includes(type)) {if(String(value).trim()==='')throw new Error('数值不能为空');const number=Number(value);if(!Number.isFinite(number))throw new Error('请输入有限数值');if(['integer','int'].includes(type)&&!Number.isInteger(number))throw new Error('请输入整数');return number;}
  if(type==='null'){const parsed=JSON.parse(value);if(parsed!==null&&(typeof parsed!=='number'||!Number.isFinite(parsed)))throw new Error('请输入 null 或有限数值');return parsed;}
  if(['array','list','json','object'].includes(type)) {let parsed;try{parsed=JSON.parse(value);}catch{throw new Error('请输入有效JSON，例如 [1, 2, 3]');}if(['array','list'].includes(type)&&!Array.isArray(parsed))throw new Error('请输入JSON数组');return finiteJson(parsed);}
  return String(value);
}
export function validateTargets(rows,mode='staged') {
  if(!Array.isArray(rows)||!rows.length||rows.some(row=>!Array.isArray(row)||row.length!==6||row.some(value=>typeof value!=='number'||!Number.isFinite(value))))throw new Error('目标应为 N×6 数组，六项均为有限数值');
  if(mode==='single'&&rows.length!==1)throw new Error('单阶段模式需要恰好一行六指标，请调整目标或选择多阶段');return rows;
}
export function simulationPayload(state, random=Math.random) {
  if(state.targetUpload && state.targetIssues?.length)throw new Error('上传目标未通过校核：'+state.targetIssues.map(item=>typeof item==='string'?item:item.message||JSON.stringify(item)).join('；'));
  validateTargets(state.targets,state.runMode);
  applyMode(state.simulation,state.simulation.mode);
  if(state.seedMode==='random')state.simulation.GA_CONFIG.seed=Math.floor(random()*4294967296);
  state.simulation.ACTIVE_STAGE_TARGET_DATA=clone(state.targets);if(state.runMode==='single')state.simulation.SINGLE_STAGE_TARGET_DATA=clone(state.targets[0]);
  const result={kind:'simulation',config:clone(state.simulation),run_mode:state.runMode,targets:clone(state.targets)};
  if(state.targetUpload)Object.assign(result,{upload_id:state.targetUpload.id,variable:state.targetVariable||undefined,orientation:state.targetOrientation});
  return result;
}
export function pointcloudPayload(state,reference,detail) {if(!reference||!detail)throw new Error('请先上传参考点云和细节点云');const config=clone(state.pointcloud);delete config.input;delete config.output;return {kind:'pointcloud',reference_id:reference,detail_id:detail,pointcloud_config:config};}
export function applyTransfer(state, transfer) {
  const preview=transfer.preview || transfer.target_preview || transfer;
  const rows=preview.targets || (transfer.six_metrics?[transfer.six_metrics]:null);validateTargets(rows);
  if(preview.issues?.length)throw new Error('点云目标未通过校核：'+preview.issues.map(item=>typeof item==='string'?item:item.message||JSON.stringify(item)).join('；'));
  state.targets=clone(rows);state.targetUpload=transfer.upload || transfer.upload_record || null;state.targetIssues=[];state.targetVariable=preview.selected || 'target_data';state.targetOrientation='rows';state.transferGeometry=clone(transfer.geometry || {});state.runMode=rows.length===1?'single':'staged';
  state.simulation.ACTIVE_STAGE_TARGET_DATA=clone(rows);state.simulation.SINGLE_STAGE_TARGET_DATA=clone(rows[0]);
}
export function prepareBatch(state, random=Math.random) {
  if(!state.cases.length)throw new Error('请先添加工况');
  const common=simulationPayload(state,random);
  const cases=clone(state.cases).map((item,index)=>{if(!item.case_name?.trim())throw new Error(`工况${index+1}名称不能为空`);if(item.upload_id&&item.target_issues?.length)throw new Error(`工况${index+1}上传目标未通过校核`);if(!item.upload_id)validateTargets(item.targets,item.simulation_mode || (['single','staged'].includes(item.mode)?item.mode:'staged'));delete item.source_name;delete item.target_issues;return item;});
  if(!Number.isInteger(state.parallelCaseWorkers)||state.parallelCaseWorkers<1)throw new Error('工况并行数必须为正整数');
  return {config:common.config,cases,run_mode:state.batchMode,parallel_case_workers:state.parallelCaseWorkers,sequential_enabled:state.batchMode==='mixed'?state.sequentialEnabled:state.batchMode==='sequential',parallel_enabled:state.batchMode==='mixed'?state.parallelEnabled:state.batchMode==='parallel'};
}
export function isTerminal(status) {return ['completed','failed','stopped','interrupted','cancelled','canceled'].includes(status);}
export function updateCaseDraft(item, draft, requireRunnable=false) {
  const saved=clone(item);
  saved.case_name=draft.case_name;
  for(const [key,fallback] of [['simulation_mode','staged'],['mode','sequential']])
    if(draft[key] !== (item[key] || fallback)) saved[key]=draft[key];
  const parsed=JSON.parse(draft.targets_text);
  const changed=JSON.stringify(parsed)!==JSON.stringify(item.targets || []);
  if(changed) {
    validateTargets(parsed,saved.simulation_mode || 'staged');
    saved.targets=parsed;
    for(const key of ['upload_id','variable','orientation','matlab_target'])delete saved[key];
    saved.target_issues=[];saved.source_name='手动修改的工况目标';
  }
  if(requireRunnable && !saved.upload_id)validateTargets(saved.targets,saved.simulation_mode || 'staged');
  return saved;
}
export function resetSimulation(state, defaults) {
  const fresh=createWorkspace(defaults);
  for(const key of ['simulation','targets','runMode','seedMode','targetUpload','targetIssues','targetVariable','targetOrientation','transferGeometry'])
    state[key]=fresh[key];
  const multi=state.simulation.MULTI_CASE_CONFIG;
  state.cases=clone(multi?.cases||[]);
  state.batchMode=multi?.run_mode||fresh.batchMode;
  state.parallelCaseWorkers=multi?.parallel_case_workers??fresh.parallelCaseWorkers;
  state.sequentialEnabled=multi?.sequential_enabled??fresh.sequentialEnabled;
  state.parallelEnabled=multi?.parallel_enabled??fresh.parallelEnabled;
}


