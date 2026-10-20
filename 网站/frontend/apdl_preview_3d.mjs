// Pre-solve geometry only; the APDL deck remains authoritative for node selection.
const fmt=n=>Number(n).toLocaleString('zh-CN',{maximumSignificantDigits:6});
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function previewGeometry(result){
 const o=result.options,s=result.stats,p=result.preview,top=p.top_depth,bottom=p.bottom_depth;
 const x0=Number(o.origin_x_mm||0),y0=Number(o.origin_y_mm||0),t=Number(o.thickness_mm);
 // Older servers used stride sampling. Do not stretch a truncated grid to its full span.
 const x=p.x_mm||top[0].map((_,j)=>x0+j*Math.max(1,Math.ceil(s.nx/80))*o.dx_mm);
 const y=p.y_mm||top.map((_,i)=>y0+i*Math.max(1,Math.ceil(s.ny/80))*o.dy_mm);
 const bounds=[[x0,x0+Number(s.length_mm)],[y0,y0+Number(s.width_mm)],[0,t]];
 const axis=o.tensile_direction==='Y'?1:0,transverse=1-axis,dof=axis?'UY':'UX',tdof=axis?'UX':'UY';
 const [first,last]=bounds[axis],clamped=o.boundary_mode==='clamped_grips';
 const fixed=[first,first+(clamped?Number(o.grip_length_fixed_mm||0):0)];
 const loaded=[last-(clamped?Number(o.grip_length_loaded_mm||0):0),last];
 const point=(far=false,upper=false)=>{
  const i=axis?0:(far?y.length-1:0),j=axis?(far?x.length-1:0):0;
  return [x[j],y[i],upper?t-top[i][j]:bottom[i][j]];
 };
 const corners=[];
 if(!clamped){
  if(o.boundary_mode==='legacy_recommended'){
   corners.push({name:'A',point:point(true),rule:`${tdof}=0`},{name:'B',point:point(true,true),rule:`${tdof}=0，UZ=0`});
  }else{
   const a=point(),b=point(true),dz=b[2]-a[2],span=bounds[transverse][1]-bounds[transverse][0];
   corners.push({name:'A',point:a,rule:`${tdof}=0，UZ=0`},{name:'B',point:b,rule:dz===0?'UZ=0':`${fmt(span)} × UZ − (${fmt(dz)}) × ${tdof}=0（耦合约束）`});
  }
 }
 return {o,top,bottom,x,y,t,bounds,axis,dof,tdof,fixed,loaded,clamped,corners,
  complete:x.at(-1)===bounds[0][1]&&y.at(-1)===bounds[1][1]};
}

export function previewSummary(m){
 const range=a=>a.map(fmt).join(' ～ '),axis=m.axis?'Y':'X';
 return `<div class="apdl-3d-facts"><p><strong>实际坐标 / mm</strong><br>X：${range(m.bounds[0])}（尺寸 ${fmt(m.bounds[0][1]-m.bounds[0][0])}）<br>Y：${range(m.bounds[1])}（尺寸 ${fmt(m.bounds[1][1]-m.bounds[1][0])}）<br>初始厚度 Z：0 ～ ${fmt(m.t)}；顶面 Z=${fmt(m.t)}−正面深度，底面 Z=反面深度。</p>
 <p><strong>蓝色固定区</strong><br>${axis} ∈ [${range(m.fixed)}] mm<br>${m.dof}=0${m.clamped?`，${m.tdof}=0，UZ=0`:'；其余自由度由角点约束消除刚体运动。'}</p>
 <p><strong>橙色加载区</strong><br>${axis} ∈ [${range(m.loaded)}] mm<br>${m.dof}=+${fmt(m.o.target_displacement_mm)} mm${m.clamped?`，${m.tdof}=0，UZ=0`:'；横向收缩自由。'}</p>
 </div>${m.corners.length?`<p class="help-line">角点附加约束：${m.corners.map(c=>`${c.name} (${c.point.map(fmt).join(', ')}) mm：${esc(c.rule)}`).join('；')}。</p>`:''}
 <p class="help-line">约束区域覆盖另两个方向的试件节点；范围框表示坐标选择包络，实际选点遵循命令流与选择容差。${m.clamped?'零夹持长度表示端面。':'蓝色端面仅施加轴向约束，并非整面锁死。'}箭头表示正向<strong>位移控制</strong>，不是力值。</p>`;
}

export function mountApdl3DPreview(container,result){
 const m=previewGeometry(result);
 container.innerHTML=`<figure class="apdl-3d-preview"><h4>三维几何与边界条件核对</h4><div class="apdl-3d-controls" role="group" aria-label="三维视角"><button type="button" class="button secondary" data-view="iso">等轴测 / 复位</button><button type="button" class="button secondary" data-view="top">XY 俯视</button><button type="button" class="button secondary" data-view="front">XZ 正视</button><button type="button" class="button secondary" data-view="side">YZ 侧视</button><button type="button" class="button secondary" data-zoom="1.2" aria-label="放大三维模型">＋</button><button type="button" class="button secondary" data-zoom="0.833333" aria-label="缩小三维模型">−</button></div><canvas tabindex="0" aria-label="可旋转的求解前试件三维图；拖动旋转，滚轮缩放，方向键旋转，Home复位"></canvas><figcaption>拖动旋转 · 滚轮或＋/−缩放 · 方向键旋转 · Home复位。真实比例，Z 未放大；绿色顶面、棕色底面、蓝色固定区、橙色加载区、紫色角点。仅为求解前采样几何，未显示变形、应力或实际有限元网格。</figcaption>${previewSummary(m)}${m.complete?'':'<p class="help-line">当前后端未返回完整边缘坐标，采样面可能未覆盖末行/末列。请更新并重启服务后重新预检；边界范围仍按完整试件显示。</p>'}</figure>`;
 const canvas=container.querySelector('canvas'),ctx=canvas.getContext('2d');
 let yaw=-.6,pitch=.65,zoom=1,drag=null;
 const center=m.bounds.map(a=>(a[0]+a[1])/2),span=Math.max(...m.bounds.map(a=>a[1]-a[0]));
 const faces=[];
 const vertex=(i,j,upper)=>[m.x[j],m.y[i],upper?m.t-m.top[i][j]:m.bottom[i][j]];
 const add=(points,color)=>faces.push({points,color});
 for(let i=0;i<m.y.length-1;i++)for(let j=0;j<m.x.length-1;j++){
  for(const upper of [false,true])add([vertex(i,j,upper),vertex(i,j+1,upper),vertex(i+1,j+1,upper),vertex(i+1,j,upper)],upper?'#7fa993':'#bda27e');
 }
 for(let j=0;j<m.x.length-1;j++)for(const i of [0,m.y.length-1])add([vertex(i,j,false),vertex(i,j+1,false),vertex(i,j+1,true),vertex(i,j,true)],'#c4c9bc');
 for(let i=0;i<m.y.length-1;i++)for(const j of [0,m.x.length-1])add([vertex(i,j,false),vertex(i+1,j,false),vertex(i+1,j,true),vertex(i,j,true)],'#c4c9bc');
 function draw(){
  const w=canvas.clientWidth||760,h=420,dpr=globalThis.devicePixelRatio||1;
  canvas.width=Math.round(w*dpr);canvas.height=h*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.fillStyle='#f6f8f4';ctx.fillRect(0,0,w,h);
  const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
  // Fit the rotated bounding box while preserving the physical aspect ratio.
  const extentX=(m.bounds[0][1]-m.bounds[0][0])*Math.abs(cy)+(m.bounds[1][1]-m.bounds[1][0])*Math.abs(sy);
  const extentY=((m.bounds[0][1]-m.bounds[0][0])*Math.abs(sy)+(m.bounds[1][1]-m.bounds[1][0])*Math.abs(cy))*Math.abs(sp)+m.t*Math.abs(cp);
  const scale=Math.min(w*.7/Math.max(extentX,1e-9),h*.6/Math.max(extentY,1e-9))*zoom;
  function project(p){const [x,y,z]=p.map((v,i)=>v-center[i]),a=x*cy-y*sy,b=x*sy+y*cy;return [w/2+a*scale,h/2+(b*sp-z*cp)*scale,b*cp+z*sp];}
  function line(a,b,color,width=1){ctx.beginPath();ctx.moveTo(...project(a).slice(0,2));ctx.lineTo(...project(b).slice(0,2));ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();}
  function label(p,text,color='#334a40',dx=5,dy=-6){const q=project(p);ctx.fillStyle=color;ctx.font='13px "Microsoft YaHei",sans-serif';ctx.fillText(text,Math.max(4,Math.min(w-ctx.measureText(text).width-4,q[0]+dx)),Math.max(14,Math.min(h-6,q[1]+dy)));}
  function polygon(points,color,stroke){const ps=points.map(project);ctx.beginPath();ps.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fillStyle=color;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1;ctx.stroke();}}
  faces.map(f=>({...f,depth:f.points.reduce((v,p)=>v+project(p)[2],0)/4})).sort((a,b)=>a.depth-b.depth).forEach(f=>polygon(f.points,f.color));
  for(const [range,color] of [[m.fixed,'#2468ad'],[m.loaded,'#bf602e']]){
   const box=(a)=>m.axis?[[m.bounds[0][0],a,0],[m.bounds[0][1],a,0],[m.bounds[0][1],a,m.t],[m.bounds[0][0],a,m.t]]:[[a,m.bounds[1][0],0],[a,m.bounds[1][1],0],[a,m.bounds[1][1],m.t],[a,m.bounds[1][0],m.t]];
   const a=box(range[0]),b=box(range[1]);polygon(a,color+'33',color);if(range[0]!==range[1]){polygon(b,color+'33',color);for(let i=0;i<4;i++)line(a[i],b[i],color,2);}
  }
  for(const c of m.corners){const p=project(c.point);ctx.beginPath();ctx.arc(p[0],p[1],4,0,Math.PI*2);ctx.fillStyle='#824d9a';ctx.fill();label(c.point,c.name,'#703589');}
  function arrow(a,b,text,color){const p=project(a),q=project(b);if(Math.hypot(q[0]-p[0],q[1]-p[1])<1){ctx.beginPath();ctx.arc(q[0],q[1],4,0,Math.PI*2);ctx.strokeStyle=color;ctx.stroke();label(b,text+'（垂直视图）',color);return;}line(a,b,color,2);const angle=Math.atan2(q[1]-p[1],q[0]-p[0]);ctx.beginPath();ctx.moveTo(q[0],q[1]);ctx.lineTo(q[0]-10*Math.cos(angle-.4),q[1]-10*Math.sin(angle-.4));ctx.moveTo(q[0],q[1]);ctx.lineTo(q[0]-10*Math.cos(angle+.4),q[1]-10*Math.sin(angle+.4));ctx.strokeStyle=color;ctx.stroke();label(b,text,color);}
  const a=[...center],b=[...center];a[m.axis]=m.loaded[1];b[m.axis]=m.loaded[1]+(m.bounds[m.axis][1]-m.bounds[m.axis][0])*.16;arrow(a,b,`+${m.axis?'Y':'X'} 位移 ${fmt(m.o.target_displacement_mm)} mm`,'#a84b21');
  const base=[m.bounds[0][0],m.bounds[1][0],0],offset=span*.1;
  const xa=[base[0],base[1]-offset,0],xb=[m.bounds[0][1],base[1]-offset,0];line(xa,xb,'#475c50');label(xa,`X 尺寸 ${fmt(m.bounds[0][1]-base[0])} mm`,'#334a40',0,18);
  const ya=[base[0]-offset,base[1],0],yb=[base[0]-offset,m.bounds[1][1],0];line(ya,yb,'#475c50');label(yb,`Y 尺寸 ${fmt(m.bounds[1][1]-base[1])} mm`);
  label([m.bounds[0][1],m.bounds[1][1],m.t],`初始厚度 ${fmt(m.t)} mm`);
  // A screen-space orientation triad remains readable even for a thin specimen.
  const triadOrigin=[75,h-90];
  const triad=p=>{const q=project(p),origin=project(base);return [triadOrigin[0]+(q[0]-origin[0])/scale*55/span,triadOrigin[1]+(q[1]-origin[1])/scale*55/span];};
  ctx.fillStyle='#435447';ctx.font='12px "Microsoft YaHei",sans-serif';ctx.fillText('全局坐标方向',16,407);
  for(const [i,name,color] of [[0,'X','#a84635'],[1,'Y','#287644'],[2,'Z','#315f9c']]){const p=[...base];p[i]+=span;const end=triad(p);ctx.beginPath();ctx.moveTo(...triadOrigin);ctx.lineTo(...end);ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke();ctx.fillStyle=color;ctx.fillText('+'+name,end[0]+3,end[1]);}
 }
 function reset(view){zoom=1;[yaw,pitch]=({iso:[-.6,.65],top:[0,Math.PI/2],front:[0,0],side:[-Math.PI/2,0]})[view];draw();}
 container.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>reset(b.dataset.view)));
 container.querySelectorAll('[data-zoom]').forEach(b=>b.addEventListener('click',()=>{zoom=Math.min(4,Math.max(.3,zoom*Number(b.dataset.zoom)));draw();}));
 canvas.addEventListener('pointerdown',e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);canvas.focus();});
 canvas.addEventListener('pointermove',e=>{if(!drag)return;yaw+=(e.clientX-drag[0])*.008;pitch=Math.min(Math.PI/2,Math.max(-Math.PI/2,pitch+(e.clientY-drag[1])*.008));drag=[e.clientX,e.clientY];draw();});
 canvas.addEventListener('pointerup',()=>drag=null);canvas.addEventListener('pointercancel',()=>drag=null);
 canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.min(4,Math.max(.3,zoom*Math.exp(-e.deltaY*.001)));draw();},{passive:false});
 canvas.addEventListener('keydown',e=>{if(e.key==='Home'){e.preventDefault();reset('iso');return;}if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();yaw+=e.key==='ArrowLeft'?-.1:e.key==='ArrowRight'?.1:0;pitch=Math.min(Math.PI/2,Math.max(-Math.PI/2,pitch+(e.key==='ArrowDown'?.1:e.key==='ArrowUp'?-.1:0)));draw();});
 // One observer per mounted canvas; disconnect when a new precheck replaces it.
 const observer=new ResizeObserver(()=>{if(!container.isConnected||!canvas.isConnected){observer.disconnect();return;}draw();});observer.observe(canvas);
 draw();return ()=>observer.disconnect();
}
