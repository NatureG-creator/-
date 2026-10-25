import {mountPointcloud3D,pointcloudModel} from './pointcloud_3d.mjs?v=20261025-height-depth-sync';

const fmt=n=>Number(n).toLocaleString('zh-CN',{maximumSignificantDigits:7});
const note='已保存的处理后高程；颜色为Z高程，不是腐蚀深度。只连接已有相邻网格节点，不重新插值、平滑或校准；数值沿用原CSV文本精度，MAT保持不变。';

export function processedCsvPreview(text,expectedCount){
 const lines=text.replace(/^\uFEFF/,'').trim().split(/\r?\n/),header=lines.shift().split(',');
 if(header.join(',')!=='x_mm,y_mm,height_mm,relative_corrosion_depth_mm'&&header.join(',')!=='x_mm,y_mm,z_mm,corrosion_depth_mm')throw new Error('已保存点云CSV的列定义不匹配');
 const rows=lines.filter(line=>line.trim()).map(line=>line.split(',').map(v=>v.trim()===''?NaN:Number(v)));
 if(!rows.length||rows.some(row=>row.length!==4||row.some(v=>!Number.isFinite(v))))throw new Error('点云CSV含无效坐标或深度，不能构造连续表面');
 if(expectedCount!=null&&rows.length!==expectedCount)throw new Error('完整CSV点数与保存的结果不一致');
 const data={points:rows.map(row=>row.slice(0,3)),relative_depth_mm:rows.map(row=>row[3]),point_count:rows.length,grid:true,note};
 pointcloudModel(data); // Reject holes and duplicate XY before connecting cells.
 return data;
}

export function resultQuantity(data,quantity,{referenceHeight,heightRange,depthRange}={}){
 if(quantity==='height')return {...data,value_kind:'height',inward_positive:false,color_bounds_mm:heightRange};
 if(quantity!=='depth')throw new Error('只能选择高程或相对腐蚀深度');
 const depths=data.relative_depth_mm;
 if(!Array.isArray(depths)||depths.length!==data.points.length||depths.some(v=>!Number.isFinite(v)||v<0))throw new Error('缺少有效的已保存相对深度，不能按当前区域重新推算零面');
 return {...data,points:data.points.map((p,i)=>[p[0],p[1],depths[i]]),bounds_mm:undefined,value_kind:'relative_depth',inward_positive:true,color_bounds_mm:depthRange,
  note:`D_relative=H_top−h，直接读取已保存的深度列。固定零面：原完整处理表面最高点${Number.isFinite(referenceHeight)?' H_top='+fmt(referenceHeight)+' mm':''}；裁剪不重新归零。蓝浅、红深，向下为正；不是相对未腐蚀面的总深度。5×仅放大显示，原CSV和MAT不变。`};
}

export function mountResultPointcloud3D(host,{jobId,surface}){
 host.innerHTML='<div class="pc3d-controls"><label>查看物理量<select aria-label="结果图物理量" data-result-quantity><option value="height">高程 Z（红高、蓝低）</option><option value="depth">相对腐蚀深度 D（红深、蓝浅，向下为正）</option></select></label><label>结果页显示方式<select aria-label="处理结果三维显示方式" data-result-mode><option value="surface">完整网格表面</option><option value="points">原节点散点</option></select></label></div><p class="help-line" data-result-status role="status"></p><div data-result-viewer></div>';
 const q=s=>host.querySelector(s),viewer=q('[data-result-viewer]'),status=q('[data-result-status]');
 const ranges={referenceHeight:surface.value_range_mm?.[1],heightRange:surface.value_range_mm,depthRange:surface.corrosion_depth_range_mm};
 let current=null,disposeView=()=>{},revision=0,disposed=false,loadedFull=false,currentRecord=surface;
 function display(data){
  current=data;const available=Array.isArray(data.relative_depth_mm)&&data.relative_depth_mm.length===data.points.length&&data.relative_depth_mm.every(v=>Number.isFinite(v)&&v>=0);
  q('[data-result-quantity]').options[1].disabled=!available;if(!available)q('[data-result-quantity]').value='height';
  const viewState=disposeView.viewState?.();disposeView();
  disposeView=mountPointcloud3D(viewer,{...resultQuantity(data,q('[data-result-quantity]').value,ranges),grid:q('[data-result-mode]').value==='surface'},{viewState});
 }
 function updateStatus(){const range=currentRecord.corrosion_depth_range_mm;status.textContent=`${loadedFull?'完整':'抽样'}显示 ${current.points.length} 个已保存节点；${range?`当前区域相对全幅深度范围 ${range.map(fmt).join(' ～ ')} mm，未重新归零。`:''}${q('[data-result-quantity]').value==='depth'?'图、色标与剖面均为相对深度；红深蓝浅、向下为正。零面是原完整处理表面最高点，不是原始未腐蚀面。':'图、色标与剖面均为高程；红高蓝低。'}切换不修改数据。`;}
 function fallback(record){
  const points=record.preview_xyz||[];
  if(points.length)display({points,relative_depth_mm:record.preview_depth_mm,point_count:record.point_count||points.length,grid:true,note:'当前是已保存的抽样预览；正在读取完整CSV。'+note});
 }
 async function load(file,record){
  if(disposed)return;
  const token=++revision;currentRecord=record;loadedFull=false;fallback(record);status.textContent='正在读取已保存的完整点云；不启动计算任务…';
  try{
   const url=`/api/jobs/${encodeURIComponent(jobId)}/download/${file.split('/').map(encodeURIComponent).join('/')}`;
   const response=await fetch(url);if(!response.ok)throw new Error('完整CSV读取失败（'+response.status+'）');
   const data=processedCsvPreview(await response.text(),record.point_count);
   if(disposed||token!==revision||!host.isConnected)return;
   loadedFull=true;display(data);updateStatus();
  }catch(error){if(!disposed&&token===revision&&host.isConnected)status.textContent=error.message+'；保留抽样预览，未修改数据。';}
 }
 for(const selector of ['[data-result-mode]','[data-result-quantity]'])q(selector).addEventListener('change',()=>{if(current){display(current);updateStatus();}});
 load('pointcloud/processed_pointcloud.csv',surface);
 return {showRegion(result){const file=result.files?.find(name=>name.endsWith('/processed_region.csv'));if(file)load(file,result);},dispose(){disposed=true;revision++;disposeView();}};
}
