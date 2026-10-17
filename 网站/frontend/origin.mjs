import {escapeHtml as esc} from './fitting.mjs';

const numeric=new Set('font_size title_size tick_size legend_size line_width symbol_size opacity x_min x_max y_min y_max z_min z_max x_major_ticks y_major_ticks x_minor_ticks y_minor_ticks width_mm height_mm dpi azimuth elevation color_min color_max'.split(' '));
const surfaceOnly=new Set('z_label z_unit z_min z_max azimuth elevation colormap color_min color_max colorbar_title'.split(' '));
const choices={line_style:['solid','dash','dot'],symbol:['circle','square','triangle','none'],x_scale:['linear','log'],y_scale:['linear','log'],legend:['none','top_right','top_left','bottom_right','bottom_left'],colormap:['viridis','rainbow','grayscale']};
const groups=[
 ['标题、坐标名称与单位',[['title','图标题'],['x_label','X 轴标题'],['x_unit','X 单位'],['y_label','Y 轴标题'],['y_unit','Y 单位'],['z_label','Z 轴标题'],['z_unit','Z 单位']]],
 ['字体',[['font_family','字体名称'],['font_size','轴标题字号'],['title_size','图标题字号'],['tick_size','刻度字号'],['legend_size','图例字号']]],
 ['线与观测点',[['line_width','线宽'],['line_style','线型'],['line_color','线/观测点颜色'],['symbol','点符号'],['symbol_size','符号大小'],['opacity','不透明度（0–100）'],['show_observed','显示观测点']]],
 ['坐标范围与刻度',[['x_min','X 下限（空为自动）'],['x_max','X 上限（空为自动）'],['y_min','Y 下限（空为自动）'],['y_max','Y 上限（空为自动）'],['z_min','Z 下限（空为自动）'],['z_max','Z 上限（空为自动）'],['x_scale','X 坐标类型'],['y_scale','Y 坐标类型'],['x_reverse','反向 X 轴'],['y_reverse','反向 Y 轴'],['x_major_ticks','X 主刻度数量'],['y_major_ticks','Y 主刻度数量'],['x_minor_ticks','X 次刻度数量'],['y_minor_ticks','Y 次刻度数量']]],
 ['图例与输出',[['legend','图例位置'],['legend_border','图例边框'],['grid','网格线'],['width_mm','页面宽度（mm）'],['height_mm','页面高度（mm）'],['dpi','输出分辨率（DPI）'],['formats','输出格式']]],
 ['三维视角与色标',[['azimuth','方位角'],['elevation','仰角'],['colormap','色带'],['color_min','色标下限（空为自动）'],['color_max','色标上限（空为自动）'],['colorbar_title','色标标题']]],
];
const labels={solid:'实线',dash:'虚线',dot:'点线',circle:'圆形',square:'方形',triangle:'三角形',none:'不显示',linear:'线性',log:'对数',top_right:'右上',top_left:'左上',bottom_right:'右下',bottom_left:'左下',viridis:'Viridis',rainbow:'彩虹',grayscale:'灰度'};
export function originCandidates(summary={}){
 return (summary.groups||[]).flatMap((group,group_index)=>(group.candidates||[]).filter(c=>['ok','success','completed'].includes(c.status)).sort((a,b)=>Number(b.id===group.recommended_id)-Number(a.id===group.recommended_id)).map(c=>({group_index,model_id:c.id,label:`${group.label||'全部数据'} · ${c.label||c.id}${c.id===group.recommended_id?'（推荐）':''}`})));
}
export function renderOriginSources(summary,candidates){
 const groupIndexes=[...new Set(candidates.map(c=>c.group_index))],first=groupIndexes[0];
 return `<div class="grid two"><label class="field"><span>数据组</span><select data-origin-group aria-label="数据组">${groupIndexes.map(index=>`<option value="${index}">${esc(summary.groups[index].label||'全部数据')}</option>`).join('')}</select></label><label class="field"><span>成功候选模型</span><select data-origin-candidate aria-label="成功候选模型">${candidates.map((c,i)=>c.group_index===first?`<option value="${i}">${esc(c.label)}</option>`:'').join('')}</select></label></div>`;
}
export function originPayload(source,candidate,plot_type,values){
 if(!candidate)throw new Error('请选择已成功完成的候选模型');
 const options={};
 for(const [key,value] of Object.entries(values)){
  if(numeric.has(key)){options[key]=value===''||value==null?null:Number(value);if(options[key]!==null&&!Number.isFinite(options[key]))throw new Error(`${key} 需要有限数值`);}
  else options[key]=value;
 }
 return {source_job_id:source,group_index:candidate.group_index,model_id:candidate.model_id,plot_type,options};
}
export function originDefaults(defaults,summary){
 if(summary.fitting_mode!=='multivariate2')return defaults;
 const selection=summary.selection||{},plot=summary.plot||{};
 const label=(key,fallback)=>typeof plot[key]==='string'&&plot[key].trim()&&!['X','Y','Z'].includes(plot[key])?plot[key]:fallback;
 return {...defaults,x_label:label('x_label',selection.x1_label||'X1'),y_label:label('y_label',selection.x2_label||'X2'),z_label:label('z_label',selection.y_label||'Y')};
}
export function renderOriginSettings(defaults={},type='curve'){
 const field=([key,label])=>{
  if(!(key in defaults)||type!=='surface'&&surfaceOnly.has(key)||type==='surface'&&['line_width','line_style'].includes(key))return '';
  const value=defaults[key],attr=`data-origin-option="${key}" aria-label="${esc(label)}"`;
  if(key==='formats')return `<div class="field"><span>${label}</span><div class="actions">${['png','tiff','pdf','svg'].map(f=>`<label><input type="checkbox" data-origin-format="${f}" ${value?.includes(f)?'checked':''}> ${f.toUpperCase()}</label>`).join('')}</div></div>`;
  if(typeof value==='boolean')return `<label class="check-field"><input type="checkbox" ${attr} ${value?'checked':''}>${label}</label>`;
  const control=choices[key]?`<select ${attr}>${choices[key].map(v=>`<option value="${v}" ${v===value?'selected':''}>${labels[v]||v}</option>`).join('')}</select>`:`<input ${attr} type="${numeric.has(key)?'number':key==='line_color'?'color':'text'}" ${numeric.has(key)?'step="any"':''} value="${esc(value??'')}">`;
  return `<label class="field"><span>${label}</span>${control}</label>`;
 };
 return groups.map(([label,fields])=>{const html=fields.map(field).join('');return html?`<details class="origin-settings"><summary>${label}</summary><div class="grid two">${html}</div></details>`:'';}).join('');
}
export function renderOriginResult(job){
 const summary=job.summary||job.result?.summary||job.result||{};
 const warnings=(summary.warnings||[]).map(text=>`<p class="notice">${esc(text)}</p>`).join('');
 return `<div class="card wide"><h3>Origin 绘图</h3><p>来源拟合任务：${esc(summary.source_job_id||job.spec?.source_job_id||'—')} · ${(summary.plot_type||job.spec?.plot_type)==='surface'?'三维响应面':'二维拟合曲线'}</p><p class="help-line">图形使用已冻结的拟合数据。OPJU 工程及图像见下方任务文件；手动编辑不会反向修改网页设置。</p>${warnings}${job.state==='completed'?'<button class="button secondary" data-origin-open>在 Origin 中继续编辑</button>':''}<p data-origin-message role="status" aria-live="polite"></p><details><summary>本次绘图设置</summary><pre>${esc(JSON.stringify(summary.options||job.spec?.options||{},null,2))}</pre></details></div>`;
}
export async function mountOrigin(root,{job,get,post,openJob}){
 const note=root.querySelector('[data-origin-message]');
 const message=text=>{if(note)note.textContent=text;};
 if(job.kind==='origin_plot'){
  root.querySelector('[data-origin-open]')?.addEventListener('click',async event=>{event.target.disabled=true;try{const result=await post(`/api/origin/jobs/${encodeURIComponent(job.id)}/open`,{});message(result.note||'已请求在本机 Origin 中打开工程。');}catch(error){message(`Origin 打开失败：${error.message}`);}finally{event.target.disabled=false;}});
  return;
 }
 if(job.kind!=='fitting'||job.state!=='completed')return;
 const summary=job.summary||job.result?.summary||job.result||{},candidates=originCandidates(summary),type=summary.fitting_mode==='multivariate2'?'surface':'curve';
 const card=document.createElement('div');card.className='card wide origin-panel';card.innerHTML='<h3>调用 Origin 绘图</h3><p role="status" aria-live="polite">正在检查本机 Origin 联动状态…</p>';root.firstElementChild?.after(card);
 try{
  const capabilities=await get('/api/origin/capabilities');if(!card.isConnected)return;
  card.innerHTML=`<h3>调用 Origin 绘图</h3><p class="notice">${capabilities.available?'本机 Origin 联动可用。':'本机 Origin 联动暂不可用。'}${esc(capabilities.note||'')} 安装：${capabilities.installed?'已检测':'未检测'}；联动依赖：${esc(typeof capabilities.dependency==='object'?JSON.stringify(capabilities.dependency):capabilities.dependency??'未提供')}。</p><p class="help-line">从已有拟合数据生成${type==='surface'?'三维响应面':'散点与拟合曲线'}；修改设置会创建独立绘图任务，保留拟合结果。支持的输出以本机 Origin 实际导出为准。</p><form>${renderOriginSources(summary,candidates)}${renderOriginSettings(originDefaults(capabilities.defaults||{},summary),type)}<div class="actions"><button class="button primary" ${!capabilities.available||!candidates.length?'disabled':''}>调用 Origin 绘图</button></div><p data-origin-status role="status" aria-live="polite">${candidates.length?'':'当前没有成功的候选模型可供绘图。'}</p></form>`;
  const form=card.querySelector('form');
  form.querySelector('[data-origin-group]').addEventListener('change',event=>{form.querySelector('[data-origin-candidate]').innerHTML=candidates.map((c,i)=>c.group_index===Number(event.target.value)?`<option value="${i}">${esc(c.label)}</option>`:'').join('');});
  form.addEventListener('submit',async event=>{
   event.preventDefault();const button=form.querySelector('button'),status=form.querySelector('[data-origin-status]');button.disabled=true;
   try{
    const values={};form.querySelectorAll('[data-origin-option]').forEach(el=>{values[el.dataset.originOption]=el.type==='checkbox'?el.checked:el.value;});
    if('formats' in (capabilities.defaults||{}))values.formats=Array.from(form.querySelectorAll('[data-origin-format]:checked'),el=>el.dataset.originFormat);
    const result=await post('/api/origin/jobs',originPayload(job.id,candidates[Number(form.querySelector('[data-origin-candidate]').value)],type,values));
    await openJob(result.id||result.job_id);
   }catch(error){status.textContent=`Origin 绘图提交失败：${error.message}`;}finally{button.disabled=false;}
  });
 }catch(error){if(card.isConnected)card.innerHTML=`<h3>调用 Origin 绘图</h3><p role="status" class="notice error">无法读取本机 Origin 状态：${esc(error.message)}。请刷新任务后重试。</p>`;}
}
