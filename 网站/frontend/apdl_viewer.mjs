const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function viewerOptions(jobs,preferredId){
 return {html:jobs.map(job=>`<option value="${esc(job.id)}"${job.id===preferredId?' selected':''}>${esc(job.name)} · ${esc(job.id)}</option>`).join(''),selected:jobs.find(job=>job.id===preferredId)||jobs[0]};
}

export async function mountApdlViewer(root,{get,post,preferredId}){
 if(!root||root.querySelector('[data-apdl-viewer]'))return;
 const box=document.createElement('section');box.className='card wide';box.dataset.apdlViewer='';
 box.innerHTML=`<div class="card-heading"><div><h3>在 APDL 中交互查看构件</h3><p>选择已有任务和图像，打开本机 Mechanical APDL 图形界面；可旋转、缩放和继续切换显示。</p></div><span class="badge neutral">本机软件</span></div><div class="grid two"><label>选择构件 / 任务<select data-viewer-job aria-label="选择查看的构件任务"></select></label><label>初始图像<select data-viewer-view aria-label="选择APDL图像类型"></select></label></div><p class="help-line" data-viewer-explanation></p><div class="actions"><button type="button" class="button primary" data-viewer-open disabled>在 APDL 中查看</button><button type="button" class="button secondary" data-viewer-refresh>刷新可查看任务</button></div><p class="help-line">每次打开独立查看会话，读取源数据库和最后保存的结果集；关闭时选择不保存。大型构件载入需要时间，并占用本机内存和 ANSYS 许可证。</p><p role="status" data-viewer-note></p>`;
 root.prepend(box);
 const guide=document.createElement('p');guide.className='help-line';guide.textContent='APDL 顶部快捷按钮：MODEL 构件外形、MESH 网格、DEFORM 变形对照、DISP 总位移、STRESS 等效应力、PLASTIC 等效塑性应变（有相应结果时显示）。';box.append(guide);
 const q=s=>box.querySelector(s),task=q('[data-viewer-job]'),view=q('[data-viewer-view]'),open=q('[data-viewer-open]'),refresh=q('[data-viewer-refresh]'),note=q('[data-viewer-note]');
 let jobs=[],available=false,busy=false;
 function explain(){const job=jobs.find(j=>j.id===task.value),field=job?.views.find(v=>v.id===view.value);q('[data-viewer-explanation]').textContent=[field?.note,job?.note].filter(Boolean).join('。');}
 function select(){const job=jobs.find(j=>j.id===task.value);view.innerHTML=(job?.views||[]).map(v=>`<option value="${esc(v.id)}">${esc(v.label)}</option>`).join('');if(job?.views.some(v=>v.id==='stress'))view.value='stress';open.disabled=busy||!available||!job;explain();}
 async function load(){refresh.disabled=true;open.disabled=true;note.textContent='正在检查本机可查看任务…';try{const report=await get('/api/apdl/viewer/jobs');if(!box.isConnected)return;jobs=report.jobs||[];available=report.available;task.innerHTML=viewerOptions(jobs,task.value||preferredId).html;select();note.textContent=!available?'未发现本机 MAPDL，请先安装或配置 MAPDL_BIN。':jobs.length?'已列出保留数据库的任务。':'暂无保留 corrosion.db 的已结束任务；先生成并运行有限元模型。';}catch(error){note.textContent=error.message;}finally{refresh.disabled=false;}}
 task.addEventListener('change',select);view.addEventListener('change',explain);refresh.addEventListener('click',load);
 open.addEventListener('click',async()=>{if(busy||open.disabled)return;busy=true;open.disabled=true;refresh.disabled=true;task.disabled=true;view.disabled=true;note.textContent='正在启动本机 APDL 图形会话…';try{const result=await post(`/api/apdl/jobs/${encodeURIComponent(task.value)}/viewer`,{view:view.value});note.textContent=`已请求启动 APDL（进程 ${result.pid}）。请查看系统中的 APDL 窗口；载入完成后显示所选图像。查看目录：${result.session_directory}`;}catch(error){note.textContent=error.message;}finally{busy=false;refresh.disabled=false;task.disabled=false;view.disabled=false;select();}});
 await load();
}
