const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function renderTaskFiles(id,files,open=false){
 const link=name=>'/api/jobs/'+encodeURIComponent(id)+'/download/'+name.split('/').map(encodeURIComponent).join('/');
 return '<details class="card wide" id="task-files"'+(open?' open':'')+'><summary>任务文件（'+files.length+'）</summary><p class="help-line">点击文件旁的下载链接获取成果；失败任务也可能保留部分输出。</p>'+
  (files.length?'<div class="file-list">'+files.map(file=>'<div class="file-row"><span>'+esc(file.name)+
   ((file.size??file.bytes)!=null?' <small class="muted">'+esc(((file.size??file.bytes)/1024).toFixed(2))+' KB</small>':'')+
   '</span><a href="'+esc(link(file.name))+'" download>下载 ↓</a></div>').join('')+'</div>':'<p class="preview">尚无导出文件。</p>')+'</details>';
}
