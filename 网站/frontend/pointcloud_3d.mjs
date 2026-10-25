const fmt=n=>Number(n).toLocaleString('zh-CN',{maximumSignificantDigits:6});
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function pointcloudModel(data){
 const points=data.points.map(p=>p.slice(0,3));
 if(!points.length||points.some(p=>p.length!==3||p.some(v=>typeof v!=='number'||!Number.isFinite(v))))throw new Error('预览需要有效XYZ点');
 const bounds=data.bounds_mm||[0,1,2].map(i=>[Math.min(...points.map(p=>p[i])),Math.max(...points.map(p=>p[i]))]);
 const x=[...new Set(points.map(p=>p[0]))].sort((a,b)=>a-b),y=[...new Set(points.map(p=>p[1]))].sort((a,b)=>a-b);
 let grid=null;
 if(data.grid){
  const lookup=new Map(points.map(p=>[JSON.stringify(p.slice(0,2)),p[2]]));
  if(lookup.size!==points.length||x.length*y.length!==points.length)throw new Error('规则预览网格缺点或存在重复XY，禁止强行连面');
  grid=y.map(v=>x.map(u=>lookup.get(JSON.stringify([u,v]))));
  if(grid.flat().some(v=>v===undefined))throw new Error('规则预览网格坐标不完整');
 }
 const common=data.common_reference||null;
 if(common&&(common.numerical_chain_verified!==true||common.physical_pristine_reference_verified!==false||common.reference_column_count!==200||common.reference_ratio!==.2))throw new Error('共同参考视图缺少已验证的前200列20%经验依据');
 const relativeDepth=data.value_kind==='relative_depth',colorBounds=data.color_bounds_mm?.slice()||bounds[2].slice();
 if(colorBounds.length!==2||colorBounds.some(v=>typeof v!=='number'||!Number.isFinite(v))||colorBounds[0]>colorBounds[1])throw new Error('色标范围须为两个递增的有限数值');
 if(relativeDepth&&common)throw new Error('共同高程H视图不能混作局部相对深度');
 return {points,bounds,x,y,grid,total:data.point_count||points.length,note:data.note||'原始扫描坐标；Z为高程，不是腐蚀深度。',common,relativeDepth,colorBounds,inwardPositive:relativeDepth||data.inward_positive===true};
}

export function pointcloudSection(m,axis,index){
 if(!m.grid)throw new Error('原始散点不构造插值剖面');
 if(!['X','Y'].includes(axis))throw new Error('剖面方向必须是X或Y');
 const transverse=axis==='X'?m.y:m.x,coords=axis==='X'?m.x:m.y;
 const i=Math.max(0,Math.min(transverse.length-1,Math.trunc(Number(index)||0)));
 const z=axis==='X'?m.grid[i].slice():m.grid.map(row=>row[i]);
 return {index:i,coordinate:transverse[i],coords,z,min:Math.min(...z),max:Math.max(...z)};
}

export function coincidentSection(local,axis,coordinate){
 const transverse=axis==='X'?local.y:local.x;
 const index=transverse.findIndex(v=>Math.abs(v-coordinate)<=1e-8);
 return index<0?null:pointcloudSection(local,axis,index);
}

export function commonReferenceSummary(c){
 const range=a=>a.map(fmt).join(' ～ ');
 return `<div class="pc3d-common"><p><strong>前200列参考区（第1～200列）</strong>：X ${range(c.reference_x_range_mm)} mm，Y ${range(c.reference_y_range_mm)} mm；实际节点跨度 ${fmt(c.reference_x_range_mm[1]-c.reference_x_range_mm[0])} mm（约60 mm）。</p><p><strong>20%经验参考面 H_flat=${Number(c.reference_height_mm).toFixed(8)} mm</strong><br>H_min=${fmt(c.reference_min_height_mm)} mm，H_max=${fmt(c.reference_max_height_mm)} mm；H_flat=H_min+0.2×(H_max−H_min)。</p><p><strong>局部共同形貌</strong>：X ${range(c.local_x_range_mm)} mm，Y ${range(c.local_y_range_mm)} mm；经验深度均值 ${fmt(c.mean_depth_mm)} mm，最大值 ${fmt(c.max_depth_mm)} mm。</p><p>橙框：参考区XY范围；青色虚线：经验参考面；紫框/网格：局部形貌。共同高程H向内为正，图中向下；d=H−H_flat。参考区有轻微腐蚀，未知损失未补偿，真实零腐蚀面未验证。</p></div>`;
}

export function cropSelection(grid,{length,width,centerX='',centerY=''}){
 length=Number(length);width=Number(width);
 if(!Number.isFinite(length)||!Number.isFinite(width)||length<=0||width<=0)throw new Error('裁剪长宽须为有限正数');
 const cx=centerX===''?(grid.x[0]+grid.x.at(-1))/2:Number(centerX),cy=centerY===''?(grid.y[0]+grid.y.at(-1))/2:Number(centerY);
 if(!Number.isFinite(cx)||!Number.isFinite(cy))throw new Error('裁剪中心须为有限坐标');
 const requested={x:[cx-length/2,cx+length/2],y:[cy-width/2,cy+width/2]};
 if([...requested.x,...requested.y].some(v=>!Number.isFinite(v)))throw new Error('裁剪范围超出有限坐标');
 // Match the existing exporter exactly: closed intervals, original nodes, no tolerance or interpolation.
 const cols=grid.x.map((v,i)=>v>=requested.x[0]&&v<=requested.x[1]?i:-1).filter(i=>i>=0);
 const rows=grid.y.map((v,i)=>v>=requested.y[0]&&v<=requested.y[1]?i:-1).filter(i=>i>=0);
 const sx=[Math.max(requested.x[0],grid.x[0]),Math.min(requested.x[1],grid.x.at(-1))],sy=[Math.max(requested.y[0],grid.y[0]),Math.min(requested.y[1],grid.y.at(-1))];
 const coverage=Math.max(0,sx[1]-sx[0])/length*Math.max(0,sy[1]-sy[0])/width;
 return {requested,shown:sx[0]<=sx[1]&&sy[0]<=sy[1]?{x:sx,y:sy}:null,
  actual:cols.length&&rows.length?{x:[grid.x[cols[0]],grid.x[cols.at(-1)]],y:[grid.y[rows[0]],grid.y[rows.at(-1)]]}:null,
  columns:cols.length,rows:rows.length,pointCount:cols.length*rows.length,coverage,exportable:cols.length>=2&&rows.length>=2};
}

export function draftReference(grid,columns,ratio){
 const n=Number(columns),r=Number(ratio);
 if(columns===''||!Number.isInteger(n)||n<1||n>grid.x.length)throw new Error(`参考列数须为1～${grid.x.length}的整数`);
 if(ratio===''||!Number.isFinite(r)||r<0||r>1)throw new Error('参考比例须在0～1之间');
 let min=Infinity,max=-Infinity;
 for(const row of grid.grid)for(let j=0;j<n;j++){const v=row[j];if(!Number.isFinite(v))throw new Error('参考区含无效高程');min=Math.min(min,v);max=Math.max(max,v);}
 return {status:'draft',columns:n,ratio:r,min,max,height:min+r*(max-min),x:[grid.x[0],grid.x[n-1]],y:[grid.y[0],grid.y.at(-1)]};
}

export function commonCropSnapshot(data,parameters){
 const c=data.common_reference;
 if(data.view!=='common_reference'||!data.source_job_id||c?.numerical_chain_verified!==true||c.reference_column_count!==200||c.reference_ratio!==.2||c.physical_pristine_reference_verified!==false)throw new Error('实际裁剪需要已验证的20%共同坐标来源');
 const selection=cropSelection(c.section_grid,parameters);
 if(!selection.exportable)throw new Error('裁剪范围在X或Y方向不足两个原节点，不能确认导出');
 const reference=Object.fromEntries(['cache_key','complete_surface_sha256','depth_sha256','reference_height_mm','reference_column_count','reference_ratio','original_thickness_mm','physical_pristine_reference_verified'].map(key=>[key,c[key]]));
 if(!reference.cache_key||!reference.complete_surface_sha256||!reference.depth_sha256)throw new Error('来源缺少导出溯源信息，请重新载入预览');
 const body={source_kind:'common_reference',length_mm:Number(parameters.length),width_mm:Number(parameters.width),center_x_mm:parameters.centerX===''?null:Number(parameters.centerX),center_y_mm:parameters.centerY===''?null:Number(parameters.centerY),confirmation:{reference,requested_bounds_mm:selection.requested,actual_bounds_mm:selection.actual,shape:[selection.rows,selection.columns],point_count:selection.pointCount}};
 return {key:JSON.stringify([data.source_job_id,body]),body,selection};
}

export function mountPointcloud3D(container,data,{compact=false,cropExport=null,viewState=null}={}){
 const full=pointcloudModel(data),common=full.common,local=common?pointcloudModel(common.local_surface):null,height=common?420:compact?260:360;
 let m=full;
 container.innerHTML=`<figure class="pc3d ${compact?'pc3d-compact':''}"><div class="pc3d-controls"><button class="button secondary" type="button" data-view="iso">等轴测 / 复位</button><button class="button secondary" type="button" data-view="top">XY 俯视</button><button class="button secondary" type="button" data-view="front">XZ 正视</button><button class="button secondary" type="button" data-zoom="1.2" aria-label="放大点云">＋</button><button class="button secondary" type="button" data-zoom="0.833333" aria-label="缩小点云">−</button><label>竖向比例<select data-scale aria-label="点云竖向比例"><option value="1">真实比例 1×</option><option value="5">观察起伏 5×</option></select></label></div><canvas tabindex="0" aria-label="可旋转的点云三维图；拖动或方向键旋转，滚轮缩放，Home复位"></canvas><figcaption>颜色：Z高程 / mm（蓝低 → 红高） · 拖动旋转，滚轮缩放 · <span data-scale-label>真实比例 1×</span><br>显示 ${m.points.length} / ${m.total} 个已有采样点；${m.grid?'规则网格连接仅用于观察':'原始散点不连面、不插值'}。</figcaption><p class="help-line">X ${m.bounds[0].map(fmt).join(' ～ ')} mm；Y ${m.bounds[1].map(fmt).join(' ～ ')} mm；Z ${m.bounds[2].map(fmt).join(' ～ ')} mm。<br>${esc(m.note)}</p>${m.grid?'<div class="pc3d-section"><label>剖面方向<select data-section-axis aria-label="点云剖面方向"><option value="X">沿X，移动Y</option><option value="Y">沿Y，移动X</option></select></label><label>剖面位置 / mm <output data-position></output><input type="range" data-position-input step="1" aria-label="移动点云剖面"></label><div data-section-plot></div><p class="help-line" data-section-status role="status"></p></div>':''}</figure>`;
 const q=s=>container.querySelector(s),canvas=q('canvas'),ctx=canvas.getContext('2d');
 if(full.relativeDepth){
  q('[data-view="front"]').textContent='XD 正视';
  q('figcaption').innerHTML=`颜色：相对腐蚀深度 D_relative / mm（蓝浅 → 红深） · 深度向下为正 · <span data-scale-label>真实比例 1×</span><br>显示 ${full.points.length} / ${full.total} 个已有节点；${full.grid?'相邻原节点连面':'散点不连面、不插值'}。`;
  q('.pc3d > p.help-line').innerHTML=`X ${full.bounds[0].map(fmt).join(' ～ ')} mm；Y ${full.bounds[1].map(fmt).join(' ～ ')} mm；D_relative ${full.bounds[2].map(fmt).join(' ～ ')} mm。<br>${esc(full.note)}`;
 }
 if(common){
  q('.pc3d-controls').insertAdjacentHTML('beforeend','<label>对照视野<select data-common-focus aria-label="共同坐标对照视野"><option value="full">完整扫描＋局部对照</option><option value="local">局部共同形貌细节</option></select></label><label><input type="checkbox" data-common-plane checked>显示20%经验参考面</label><label><input type="checkbox" data-common-roi checked>标出前200列参考区</label>');
  q('figcaption').innerHTML='颜色：共同高程 H（向内正、图中向下）/ mm，蓝浅 → 红深 · <span data-scale-label>真实比例 1×</span><br><span data-sampling></span>';
  q('.pc3d > p.help-line').innerHTML=`<span data-bounds></span><br>${esc(full.note)}`;
  q('.pc3d-section').insertAdjacentHTML('beforebegin',commonReferenceSummary(common)+'<p class="help-line" data-focus-note role="status"></p>');
  const stage=document.createElement('div');stage.className='pc3d-stage';canvas.before(stage);stage.append(canvas);
  stage.insertAdjacentHTML('beforeend',`<div class="pc3d-drafts"><p><strong>裁剪参数联动 · 参考面草稿不写回</strong></p><fieldset><legend><label><input type="checkbox" data-crop-enabled>裁剪草稿（绿色框）</label></legend><div class="pc3d-draft-grid"><label>X长度 / mm<input type="number" step="any" min="0" data-draft="length" aria-label="草稿裁剪X长度"></label><label>Y宽度 / mm<input type="number" step="any" min="0" data-draft="width" aria-label="草稿裁剪Y宽度"></label><label>中心X / mm<input type="number" step="any" data-draft="centerX" aria-label="草稿裁剪中心X"></label><label>中心Y / mm<input type="number" step="any" data-draft="centerY" aria-label="草稿裁剪中心Y"></label></div><p data-crop-status class="pc3d-draft-status" role="status"></p><button type="button" class="button secondary" data-crop-confirm disabled>确认当前裁剪范围</button><button type="button" class="button primary" data-crop-export disabled>导出已确认范围</button><p data-export-status class="pc3d-draft-status" role="status"></p></fieldset><fieldset><legend><label><input type="checkbox" data-reference-enabled>候选参考面（粉色·未验证）</label></legend><p>已验证20%面保留：<strong>${Number(common.reference_height_mm).toFixed(8)} mm</strong></p><div class="pc3d-draft-grid"><label>从第1列起的列数<input type="number" min="1" max="${common.section_grid.x.length}" step="1" data-draft="columns" aria-label="草稿参考列数"></label><label>极差比例<input type="number" min="0" max="1" step="0.01" data-draft="ratio" aria-label="草稿参考比例"></label></div><p data-reference-status class="pc3d-draft-status" role="status"></p></fieldset><button type="button" class="button secondary" data-reset-drafts>恢复草稿默认值</button><p class="help-line">绿色虚框为请求范围，实框为实际原节点范围；仅显示与当前视野相交的部分。裁剪参数与下方实测裁剪入口双向联动，确认后另存原高程节点及20%经验面溯源。粉色候选面不参与导出。</p></div>`);
 }
 let yaw=viewState?.yaw??-.6,pitch=viewState?.pitch??.65,zoom=viewState?.zoom??1,vertical=viewState?.vertical??1,drag=null,section=null,crop=null,candidate=null,draftFrame=null,cropLink=null;
 q('[data-scale]').value=String(vertical);q('[data-scale-label]').textContent=vertical===1?'真实比例 1×':'竖向放大 5×';
 const zlo=full.colorBounds[0],zhi=full.colorBounds[1];
 const color=z=>`hsl(${215-205*(z-zlo)/(zhi-zlo||1)},72%,48%)`;
 function draw(){
  const w=canvas.clientWidth||600,h=height,dpr=globalThis.devicePixelRatio||1;
  canvas.width=w*dpr;canvas.height=h*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#f4f8f1';ctx.fillRect(0,0,w,h);
  const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
  const viewBounds=m.bounds.map((range,i)=>common&&i===2?full.bounds[2]:range);
  const center=viewBounds.map(([a,b])=>(a+b)/2),spans=viewBounds.map(([a,b])=>b-a),sign=m.inwardPositive?-1:1;
  const ex=spans[0]*Math.abs(cy)+spans[1]*Math.abs(sy),ey=(spans[0]*Math.abs(sy)+spans[1]*Math.abs(cy))*Math.abs(sp)+spans[2]*vertical*Math.abs(cp);
  const scale=Math.min(w*.8/Math.max(ex,1e-9),h*.65/Math.max(ey,1e-9))*zoom;
  const project=p=>{const[x,y,z]=p.map((v,i)=>(v-center[i])*(i===2?vertical*sign:1)),a=x*cy-y*sy,b=x*sy+y*cy;return [w/2+a*scale,h/2+(b*sp-z*cp)*scale,b*cp+z*sp];};
  if(m.grid){
   const faces=[];
   const addSurface=surface=>{for(let i=0;i<surface.y.length-1;i++)for(let j=0;j<surface.x.length-1;j++){
    const points=[[surface.x[j],surface.y[i],surface.grid[i][j]],[surface.x[j+1],surface.y[i],surface.grid[i][j+1]],[surface.x[j+1],surface.y[i+1],surface.grid[i+1][j+1]],[surface.x[j],surface.y[i+1],surface.grid[i+1][j]]];
    faces.push({screen:points.map(project),z:points.reduce((v,p)=>v+p[2],0)/4});
   }};
   addSurface(m);if(common&&m===full)addSurface(local);
   faces.sort((a,b)=>a.screen.reduce((v,p)=>v+p[2],0)-b.screen.reduce((v,p)=>v+p[2],0)).forEach(f=>{ctx.beginPath();f.screen.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fillStyle=color(f.z);ctx.fill();});
  }else m.points.map(p=>({s:project(p),z:p[2]})).sort((a,b)=>a.s[2]-b.s[2]).forEach(p=>{ctx.fillStyle=color(p.z);ctx.fillRect(p.s[0],p.s[1],2.8,2.8);});
  if(section){const axis=q('[data-section-axis]').value;ctx.beginPath();section.coords.forEach((v,i)=>{const p=project(axis==='X'?[v,section.coordinate,section.z[i]]:[section.coordinate,v,section.z[i]]);i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]);});ctx.strokeStyle='#202f29';ctx.lineWidth=2;ctx.stroke();}
  if(common){
   const plane=common.reference_height_mm;
   const line=(points,color,dashed=false)=>{ctx.beginPath();points.map(project).forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.strokeStyle=color;ctx.lineWidth=1.6;ctx.setLineDash(Array.isArray(dashed)?dashed:dashed?[6,4]:[]);ctx.stroke();ctx.setLineDash([]);};
   const rectangle=(xr,yr,z)=>[[xr[0],yr[0],z],[xr[1],yr[0],z],[xr[1],yr[1],z],[xr[0],yr[1],z],[xr[0],yr[0],z]];
   const label=(point,text,color,dy=-8)=>{const p=project(point);ctx.font='12px "Microsoft YaHei",sans-serif';ctx.fillStyle=color;ctx.fillText(text,Math.max(5,Math.min(w-ctx.measureText(text).width-5,p[0])),Math.max(38,Math.min(h-20,p[1]+dy)));};
   if(q('[data-common-plane]').checked){line(rectangle(m.bounds[0],m.bounds[1],plane),'#167e9e',true);label([m.x.at(-1),m.y.at(-1),plane],`经验参考面 H=${Number(plane).toFixed(5)} mm`,'#13667e');}
   if(m===full&&q('[data-common-roi]').checked){line(rectangle(common.reference_x_range_mm,common.reference_y_range_mm,plane),'#bd6a16');label([(common.reference_x_range_mm[0]+common.reference_x_range_mm[1])/2,m.y[0],plane],'前200列经验参考区','#9a5511',-18);}
   for(let i=0;i<local.y.length;i+=Math.max(1,Math.floor(local.y.length/8)))line(local.x.map((x,j)=>[x,local.y[i],local.grid[i][j]]),'#844e9e');
   for(let j=0;j<local.x.length;j+=Math.max(1,Math.floor(local.x.length/12)))line(local.y.map((y,i)=>[local.x[j],y,local.grid[i][j]]),'#844e9e');
   line([...local.x.map((x,j)=>[x,local.y[0],local.grid[0][j]]),...local.y.map((y,i)=>[local.x.at(-1),y,local.grid[i].at(-1)]),...local.x.map((x,j)=>[x,local.y.at(-1),local.grid.at(-1)[j]]).reverse(),...local.y.map((y,i)=>[local.x[0],y,local.grid[i][0]]).reverse()],'#723d8c');
   const deepest=local.points.reduce((a,b)=>a[2]>b[2]?a:b);line([[deepest[0],deepest[1],plane],deepest],'#9b337d');
   if(m===full)label([local.x[0],local.y[0],local.grid[0][0]],'局部共同形貌','#723d8c',18);
   if(m===local){const p=project(deepest),text=`经验最大深度 ${fmt(common.max_depth_mm)} mm`,tx=Math.max(100,w-ctx.measureText(text).width-18),ty=h-45;ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(tx,ty-8);ctx.strokeStyle='#8f276f';ctx.stroke();ctx.fillStyle='#8f276f';ctx.fillText(text,tx,ty);}
   const withinView=box=>{if(!box)return null;const x=[Math.max(box.x[0],m.bounds[0][0]),Math.min(box.x[1],m.bounds[0][1])],y=[Math.max(box.y[0],m.bounds[1][0]),Math.min(box.y[1],m.bounds[1][1])];return x[0]<=x[1]&&y[0]<=y[1]?{x,y}:null;};
   if(crop){const requested=withinView(crop.shown),actual=withinView(crop.actual);if(requested){line(rectangle(requested.x,requested.y,plane),'#187947',true);label([requested.x[0],requested.y[1],plane],'裁剪草稿','#187947',26);}if(actual)line(rectangle(actual.x,actual.y,plane),'#187947');}
   if(candidate){
    const samePlane=Math.abs(candidate.height-plane)<=1e-12;
    if(!samePlane||!q('[data-common-plane]').checked){line(rectangle(m.bounds[0],m.bounds[1],candidate.height),'#bc317c',[2,4]);label([m.x.at(-1),m.y[0],candidate.height],`草稿 H=${candidate.height.toFixed(5)} mm`,'#a52168',30);}
    const roi=withinView(candidate);if(roi&&!(samePlane&&candidate.columns===200&&q('[data-common-roi]').checked&&m===full))line(rectangle(roi.x,roi.y,candidate.height),'#bc317c',[2,4]);
   }
  }
  ctx.fillStyle='#405c50';ctx.font='12px "Microsoft YaHei",sans-serif';ctx.fillText(`${m.relativeDepth?'相对深度 D（向下正，红深蓝浅）':m.inwardPositive?'共用色标 H（向内正）':'Z高程'} ${fmt(zlo)} ～ ${fmt(zhi)} mm`,12,20);
  const base=[...m.bounds.map(v=>v[0])],origin=project(base),triad=[48,h-70],length=Math.max(...spans,1e-9);
  // Orientation only: keep the inward-positive H arrow legible at 5× scale.
  for(const[i,name,c]of [[0,'X','#a84635'],[1,'Y','#287644'],[2,m.relativeDepth?'D':m.inwardPositive?'H':'Z','#315f9c']]){const end=[...base];end[i]+=length;const p=project(end),norm=Math.max(Math.hypot(p[0]-origin[0],p[1]-origin[1]),1e-9),x=triad[0]+(p[0]-origin[0])/norm*35,y=triad[1]+(p[1]-origin[1])/norm*35;ctx.beginPath();ctx.moveTo(...triad);ctx.lineTo(x,y);ctx.strokeStyle=c;ctx.stroke();ctx.fillStyle=c;ctx.fillText('+'+name,x+2,y);}
  ctx.fillStyle='#405c50';ctx.fillText(`X / Y / ${m.relativeDepth?'D':m.inwardPositive?'H':'Z'}：mm`,12,h-12);
 }
 function drawSection(){
  if(!m.grid)return;
  const axis=q('[data-section-axis]').value,slider=q('[data-position-input]');
  const sectionSource=common&&m===full?common.section_grid:m;
  slider.max=(axis==='X'?sectionSource.y:sectionSource.x).length-1;
  section=pointcloudSection(sectionSource,axis,slider.value);q('[data-position]').value=fmt(section.coordinate);
  const host=q('[data-section-plot]'),w=Math.max(280,host.clientWidth||650),left=72,right=w-18,top=candidate?48:30,bottom=205;
  const lo=common?full.bounds[2][0]:m.bounds[2][0],hi=common?full.bounds[2][1]:m.bounds[2][1];
  const pad=Math.max((hi-lo)*.1,.001),low=m.relativeDepth?0:lo-pad,high=hi+pad;
  const x=v=>left+(v-section.coords[0])/(section.coords.at(-1)-section.coords[0]||1)*(right-left),z=v=>m.inwardPositive?top+(v-low)/(high-low)*(bottom-top):bottom-(v-low)/(high-low)*(bottom-top);
  const ticks=Array.from({length:4},(_,i)=>{const v=low+(high-low)*i/3;return `<text x="64" y="${z(v)+4}" text-anchor="end">${fmt(v)}</text>`;}).join('');
  const overlay=common&&m===full?coincidentSection(local,axis,section.coordinate):null;
  const roi=common&&m===full&&axis==='X'&&q('[data-common-roi]').checked?`<rect x="${x(common.reference_x_range_mm[0])}" y="${top}" width="${x(common.reference_x_range_mm[1])-x(common.reference_x_range_mm[0])}" height="${bottom-top}" fill="#bc7018" opacity=".12"/>`:'';
  const plane=common&&q('[data-common-plane]').checked?`<line x1="${left}" y1="${z(common.reference_height_mm)}" x2="${right}" y2="${z(common.reference_height_mm)}" stroke="#167e9e" stroke-dasharray="6 4"/><text x="${right}" y="18" text-anchor="end">20%经验参考面</text>`:m.relativeDepth?`<line x1="${left}" y1="${z(0)}" x2="${right}" y2="${z(0)}" stroke="#167e9e" stroke-dasharray="6 4"/><text x="${right}" y="18" text-anchor="end">D=0：原完整处理表面最高点</text>`:'';
  const localLine=overlay?`<polyline points="${overlay.coords.map((v,i)=>`${x(v)},${z(overlay.z[i])}`).join(' ')}" fill="none" stroke="#844e9e" stroke-width="2.5"/>`:'';
  const band=(box,color,opacity)=>{if(!box)return '';const cross=axis==='X'?box.y:box.x,along=axis==='X'?box.x:box.y;if(section.coordinate<cross[0]||section.coordinate>cross[1])return '';const a=Math.max(along[0],section.coords[0]),b=Math.min(along[1],section.coords.at(-1));return a>b?'':`<rect x="${x(a)}" y="${top}" width="${x(b)-x(a)}" height="${bottom-top}" fill="${color}" opacity="${opacity}"/>`;};
  const cropBand=crop?band(crop.shown,'#187947',.12):'';
  const draftBand=candidate?band(candidate,'#bc317c',.06):'';
  const draftPlane=candidate?`${Math.abs(candidate.height-common.reference_height_mm)>1e-12||!q('[data-common-plane]').checked?`<line x1="${left}" y1="${z(candidate.height)}" x2="${right}" y2="${z(candidate.height)}" stroke="#bc317c" stroke-dasharray="2 4"/>`:''}<text x="${right}" y="34" text-anchor="end" fill="#a52168">草稿（未验证）H=${candidate.height.toFixed(8)}</text>`:'';
  host.innerHTML=`<svg viewBox="0 0 ${w} 265" role="img" aria-label="${axis}方向采样剖面，${m.relativeDepth?'相对深度':'高程'}范围 ${fmt(section.min)} 到 ${fmt(section.max)} mm"><rect x="${left}" y="${top}" width="${right-left}" height="${bottom-top}" fill="none" stroke="#b8c8b4"/>${roi}${cropBand}${draftBand}${plane}${draftPlane}<polyline points="${section.coords.map((v,i)=>`${x(v)},${z(section.z[i])}`).join(' ')}" fill="none" stroke="#276e50" stroke-width="2"/>${localLine}${ticks}<text x="8" y="18">${m.relativeDepth?'D（向下正）':common?'H（向内正）':'Z高程'} / mm</text><text x="${left}" y="229">${fmt(section.coords[0])}</text><text x="${right}" y="229" text-anchor="end">${fmt(section.coords.at(-1))}</text><text x="${(left+right)/2}" y="255" text-anchor="middle">${axis} / mm</text></svg>`;
  if(m.relativeDepth){q('[data-section-status]').textContent=`${axis==='X'?'Y':'X'}=${fmt(section.coordinate)} mm；相对深度 ${fmt(section.min)} ～ ${fmt(section.max)} mm。D=原完整处理表面最高高程−h，向下为正；裁剪和切换不重新归零，不是相对未腐蚀面的总腐蚀深度。`;return;}
  q('[data-section-status]').textContent=`${axis==='X'?'Y':'X'}=${fmt(section.coordinate)} mm；剖面高程 ${fmt(section.min)} ～ ${fmt(section.max)} mm。`+(common?`共同H向内为正，图中向下；青虚线为已验证20%经验面。${m===full?(overlay?'紫线为同坐标局部形貌；':'此剖面未穿过局部共同网格节点；'):''}此剖面相对已验证20%面的经验深度范围 ${fmt(section.min-common.reference_height_mm)} ～ ${fmt(section.max-common.reference_height_mm)} mm，保留符号；草稿不改变该读数。`:'连接的是已有抽样网格节点；竖向放大显示，不作绝对深度或剩余厚度解释。');
 }
 q('[data-scale]').addEventListener('change',e=>{vertical=Number(e.target.value);q('[data-scale-label]').textContent=vertical===1?'真实比例 1×':'竖向放大 5×';draw();});
 q('[data-position-input]')?.addEventListener('input',()=>{drawSection();draw();});
 q('[data-section-axis]')?.addEventListener('change',()=>{q('[data-position-input]').value=0;drawSection();draw();});
 if(common){
  const selectFocus=()=>{const coordinate=section?.coordinate,axis=q('[data-section-axis]').value;m=q('[data-common-focus]').value==='local'?local:full;
   const source=m===full?common.section_grid:m,transverse=axis==='X'?source.y:source.x,index=transverse.findIndex(v=>coordinate!=null&&Math.abs(v-coordinate)<=1e-8);
   q('[data-position-input]').max=transverse.length-1;q('[data-position-input]').value=index<0?Math.floor(transverse.length/2):index;zoom=1;
   q('[data-focus-note]').textContent=coordinate!=null&&index<0?'原剖面坐标不在当前视野的已有网格节点内，已显示当前视野中线；未插值猜测。':'';
   q('[data-common-roi]').disabled=m===local;
   q('[data-bounds]').textContent=`当前共同坐标：X ${m.bounds[0].map(fmt).join(' ～ ')} mm；Y ${m.bounds[1].map(fmt).join(' ～ ')} mm。`;
   q('[data-sampling]').textContent=m===full?`三维完整扫描 ${full.points.length}/${full.total} 点＋局部 ${local.points.length}/${local.total} 点；剖面使用完整原网格。`:`局部共同形貌 ${local.points.length}/${local.total} 点；坐标与完整扫描一致，未重新找平。`;
   drawSection();draw();};
  q('[data-common-focus]').addEventListener('change',selectFocus);
  q('[data-common-plane]').addEventListener('change',()=>{drawSection();draw();});
  q('[data-common-roi]').addEventListener('change',()=>{drawSection();draw();});
  const defaults={length:50,width:Number((full.y.at(-1)-full.y[0]).toFixed(6)),centerX:Number(((local.x[0]+local.x.at(-1))/2).toFixed(6)),centerY:Number(((full.y[0]+full.y.at(-1))/2).toFixed(6)),columns:200,ratio:.2};
  const scheduleDraftDraw=()=>{if(draftFrame!=null)return;draftFrame=requestAnimationFrame(()=>{draftFrame=null;if(canvas.isConnected){drawSection();draw();}});};
  const updateDrafts=()=>{
   crop=null;candidate=null;
   const cropOn=q('[data-crop-enabled]').checked,referenceOn=q('[data-reference-enabled]').checked;
   for(const key of ['length','width','centerX','centerY'])q(`[data-draft="${key}"]`).disabled=!cropOn;
   for(const key of ['columns','ratio'])q(`[data-draft="${key}"]`).disabled=!referenceOn;
   const cropStatus=q('[data-crop-status]'),referenceStatus=q('[data-reference-status]');cropStatus.className=referenceStatus.className='pc3d-draft-status';
   if(cropOn){try{crop=cropSelection(common.section_grid,Object.fromEntries(['length','width','centerX','centerY'].map(key=>[key,q(`[data-draft="${key}"]`).value])));
     cropStatus.textContent=`几何覆盖 ${fmt(crop.coverage*100)}%；包含 ${crop.rows}×${crop.columns}=${crop.pointCount} 个原节点。`+(crop.actual?`实际X ${crop.actual.x.map(fmt).join('～')}，Y ${crop.actual.y.map(fmt).join('～')} mm。`:'未包含任何原网格节点。')+(crop.exportable?'':'X或Y不足2节点，按现有规则不可导出。')+(crop.coverage<1-1e-12?'请求超出实测覆盖，不补点。':'');
    }catch(e){cropStatus.textContent=e.message;cropStatus.classList.add('error-hint');}}
   else cropStatus.textContent='启用后联动实际裁剪参数；确认后另存，不修改源表面。';
   if(referenceOn){try{candidate=draftReference(common.section_grid,q('[data-draft="columns"]').value,q('[data-draft="ratio"]').value);
     const delta=candidate.height-common.reference_height_mm;
     referenceStatus.textContent=`草稿 H=${candidate.height.toFixed(8)} mm；ΔH=${fmt(delta)} mm。H_min=${fmt(candidate.min)}，H_max=${fmt(candidate.max)} mm。`+(Math.abs(delta)<=1e-12?'与已验证面重合，原值保留。':'未验证，不替换20%经验面。');
    }catch(e){referenceStatus.textContent=e.message;referenceStatus.classList.add('error-hint');}}
   else referenceStatus.textContent='从完整矩阵前N列计算候选高度；不受裁剪框影响，未重新校准。';
   const parameters=Object.fromEntries(['length','width','centerX','centerY'].map(key=>[key,q(`[data-draft="${key}"]`).value]));
   let snapshot=null,error='请先启用裁剪草稿，再确认当前范围。';
   if(cropOn){try{snapshot=commonCropSnapshot(data,parameters);}catch(e){error=e.message;}}
   cropLink?.update({parameters,snapshot,error});
   scheduleDraftDraw();
  };
  const resetDrafts=()=>{for(const[key,value]of Object.entries(defaults))q(`[data-draft="${key}"]`).value=value;q('[data-crop-enabled]').checked=false;q('[data-reference-enabled]').checked=false;updateDrafts();};
  q('.pc3d-drafts').addEventListener('input',updateDrafts);
  q('[data-reset-drafts]').addEventListener('click',resetDrafts);
  cropLink=cropExport?.connect({data,onParameters:parameters=>{for(const[key,value]of Object.entries(parameters))q(`[data-draft="${key}"]`).value=value;q('[data-crop-enabled]').checked=true;updateDrafts();},onStatus:state=>{q('[data-crop-confirm]').disabled=!state.canConfirm;q('[data-crop-export]').disabled=!state.canExport;const output=q('[data-export-status]');output.textContent=state.message;for(const file of state.files||[]){const a=document.createElement('a');a.href=file.href;a.download='';a.textContent=' 下载 '+file.name;output.append(a);}}})||null;
  if(!cropLink)q('[data-export-status]').textContent='当前入口仅支持预览；实际联动请从点云工作流打开已保存的共同坐标视图。';
  q('[data-crop-confirm]').addEventListener('click',()=>cropLink?.confirm());
  q('[data-crop-export]').addEventListener('click',()=>cropLink?.export());
  resetDrafts();
  selectFocus();
 }
 container.querySelector('.pc3d').addEventListener('input',e=>e.stopPropagation());container.querySelector('.pc3d').addEventListener('change',e=>e.stopPropagation());
 const reset=view=>{[yaw,pitch]=({iso:[-.6,.65],top:[0,Math.PI/2],front:[0,0]})[view];zoom=1;draw();};
 container.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>reset(b.dataset.view)));
 container.querySelectorAll('[data-zoom]').forEach(b=>b.addEventListener('click',()=>{zoom=Math.max(.3,Math.min(4,zoom*Number(b.dataset.zoom)));draw();}));
 canvas.addEventListener('pointerdown',e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);canvas.focus();});
 canvas.addEventListener('pointermove',e=>{if(!drag)return;yaw+=(e.clientX-drag[0])*.008;pitch=Math.max(-Math.PI/2,Math.min(Math.PI/2,pitch+(e.clientY-drag[1])*.008));drag=[e.clientX,e.clientY];draw();});
 for(const name of ['pointerup','pointercancel'])canvas.addEventListener(name,()=>drag=null);
 canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.3,Math.min(4,zoom*Math.exp(-e.deltaY*.001)));draw();},{passive:false});
 canvas.addEventListener('keydown',e=>{if(e.key==='Home'){e.preventDefault();reset('iso');}else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();yaw+=e.key==='ArrowLeft'?-.1:e.key==='ArrowRight'?.1:0;pitch=Math.max(-Math.PI/2,Math.min(Math.PI/2,pitch+(e.key==='ArrowDown'?.1:e.key==='ArrowUp'?-.1:0)));draw();}});
 const observer=new ResizeObserver(()=>{if(!canvas.isConnected){observer.disconnect();return;}drawSection();draw();});observer.observe(canvas);
 if(m.grid&&!common){q('[data-section-axis]').value=viewState?.axis==='Y'?'Y':'X';const transverse=q('[data-section-axis]').value==='X'?m.y:m.x,index=transverse.findIndex(v=>viewState?.sectionCoordinate!=null&&Math.abs(v-viewState.sectionCoordinate)<=1e-8);q('[data-position-input]').min=0;q('[data-position-input]').max=transverse.length-1;q('[data-position-input]').value=index<0?Math.floor(transverse.length/2):index;drawSection();}
 const dispose=()=>{observer.disconnect();cropLink?.disconnect();if(draftFrame!=null)cancelAnimationFrame(draftFrame);};
 dispose.viewState=()=>({yaw,pitch,zoom,vertical,axis:q('[data-section-axis]')?.value||viewState?.axis||'X',sectionCoordinate:section?.coordinate??viewState?.sectionCoordinate??null});
 draw();return dispose;
}

export function mountSavedPointcloud(root,{get,post,cropExport=null,processedViewer=null}){
 root.innerHTML=`<div class="card"><h3>点云三维查看（只读）</h3><p class="help-line">直接读取已完成任务保存的扫描或表面，不运行MATLAB、不修改数据。原始和独立找平表面分别查看；共同坐标对照仅复用已有验证缓存，不重新配准或校准。</p><div class="pc3d-controls"><label>已完成点云任务<select data-job aria-label="三维点云来源任务"></select></label><label>查看数据<select data-kind aria-label="三维点云数据类型"><option value="detail_processed">局部处理后表面</option><option value="common_reference">共同坐标参考区＋局部对照（已验证）</option><option value="reference_processed">完整参考表面（独立找平）</option><option value="reference_raw">完整原始扫描</option><option value="detail_raw">局部原始扫描</option></select></label><button class="button secondary" type="button" data-refresh>刷新点云任务</button><button class="button primary" type="button" data-load>显示三维</button></div><p class="help-line" role="status" data-status></p><div data-viewer></div></div>`;
 const q=s=>root.querySelector(s),cache=new Map();let token=0,dispose=()=>{};
 async function load(){
  const id=q('[data-job]').value;if(!id)return;
  const current=++token,view=q('[data-kind]').value,key=id+':'+view;
  root.dispatchEvent(new CustomEvent('pointcloud-preview-loading',{bubbles:true}));
  q('[data-status]').textContent='读取已保存数据…';q('[data-load]').disabled=true;dispose();q('[data-viewer]').replaceChildren();
  try{const data=cache.get(key)||await post('/api/pointcloud/preview',{source_job_id:id,view});if(current!==token)return;cache.set(key,data);
   if(view==='detail_processed'&&processedViewer){const range=data.bounds_mm[2];dispose=processedViewer(q('[data-viewer]'),{jobId:id,surface:{point_count:data.point_count,preview_xyz:data.points,value_range_mm:range,corrosion_depth_range_mm:[0,range[1]-range[0]]}}).dispose;}
   else dispose=mountPointcloud3D(q('[data-viewer]'),data,{cropExport});
   root.dispatchEvent(new CustomEvent('pointcloud-preview-ready',{bubbles:true,detail:data}));q('[data-status]').textContent='来源 '+id+' · '+q('[data-kind]').selectedOptions[0].textContent+' · 原数据只读，裁剪确认后另存。';}
  catch(e){if(current===token)q('[data-status]').textContent=e.message;}
  finally{if(current===token)q('[data-load]').disabled=false;}
 }
 async function refresh(){try{const old=q('[data-job]').value,data=await get('/api/pointcloud/source-jobs');q('[data-job]').innerHTML=data.jobs.map(j=>`<option value="${esc(j.id)}">${esc(j.display_name||j.name||j.id)}</option>`).join('');if(data.jobs.some(j=>j.id===old))q('[data-job]').value=old;if(data.jobs.length)await load();else q('[data-status]').textContent='尚无已完成点云任务；上传原始扫描后也可直接查看三维散点。';}catch(e){q('[data-status]').textContent=e.message;}}
 q('[data-job]').addEventListener('change',load);q('[data-kind]').addEventListener('change',load);q('[data-load]').addEventListener('click',load);q('[data-refresh]').addEventListener('click',refresh);
 refresh();
}
