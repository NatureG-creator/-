const $ = (selector) => document.querySelector(selector);
const state = {defaults: null, currentJob: null, timer: null, uploads: {reference: null, detail: null}};
const fetchJson = async (url, options = {}) => { const response = await fetch(url, options); const data = await response.json(); if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`); return data; };
const input = (label, key, value, help, type = 'number') => `<div class="parameter"><label>${label}</label><small>${help || key}</small><input data-key="${key}" type="${type}" value="${value ?? ''}" ${type === 'number' ? 'step="any"' : ''}></div>`;
const setMessage = (id, text, error = false) => { const node = $(id); node.hidden = !text; node.textContent = text || ''; node.classList.toggle('error', error); };
const deepClone = (value) => JSON.parse(JSON.stringify(value));

async function boot() {
  state.defaults = await fetchJson('/api/defaults');
  $('#health-text').textContent = '本地服务已连接'; $('#health-dot').parentElement.classList.add('ok');
  $('#capability').textContent = state.defaults.capabilities.taichi ? 'NumPy / Taichi' : 'NumPy';
  $('#sim-backend').textContent = state.defaults.capabilities.taichi ? 'NumPy / Taichi 可用' : '当前仅 NumPy';
  renderSimulation(state.defaults.simulation); renderPointcloud(state.defaults.pointcloud);
  bind(); await refreshHistory();
}

function renderSimulation(config) {
  $('#sim-seed').value = config.GA_CONFIG.seed;
  $('#targets').value = JSON.stringify(config.ACTIVE_STAGE_TARGET_DATA, null, 2);
  const fields = [
    ['网格宽度','GEOMETRY_CONFIG.grid_w','几何网格 X 方向元胞数'],['网格长度','GEOMETRY_CONFIG.grid_l','几何网格 Y 方向元胞数'],['深度层数','GEOMETRY_CONFIG.grid_n','CA 深度层数'],['Z层间距 μm','GEOMETRY_CONFIG.space_z_um','深度方向元胞物理间距'],['CA步数 F','STAGE_GA_CONFIG.F','每个个体的 CA 演化步数'],['种群规模','STAGE_GA_CONFIG.nind','每代个体数'],['选择个体数','STAGE_GA_CONFIG.selected_count','遗传操作的选择数'],['最大代数','STAGE_GA_CONFIG.maxgen','GA最大迭代代数']
  ];
  $('#sim-fields').innerHTML = fields.map(([label, path, help]) => { const [group, key] = path.split('.'); return input(label, path, config[group][key], help); }).join('');
}

function renderPointcloud(catalog) {
  const groups = new Map();
  catalog.forEach((item) => { if (!groups.has(item.group)) groups.set(item.group, []); groups.get(item.group).push(item); });
  $('#pointcloud-fields').innerHTML = [...groups.entries()].filter(([group]) => !['input','output'].includes(group)).map(([group, items]) => `<div class="parameter-group"><h4>${group}</h4>${items.map((item) => input(item.key, `${group}.${item.key}`, Array.isArray(item.value) ? item.value.join(',') : item.value, item.help, typeof item.value === 'number' ? 'number' : 'text')).join('')}</div>`).join('');
}

function readSimulationConfig() {
  const config = deepClone(state.defaults.simulation); config.mode = $('#sim-mode').value; config.GA_CONFIG.seed = Number($('#sim-seed').value); config.ACTIVE_STAGE_TARGET_DATA = JSON.parse($('#targets').value);
  document.querySelectorAll('#sim-fields [data-key]').forEach((node) => { const [group, key] = node.dataset.key.split('.'); config[group][key] = Number(node.value); });
  config.TAICHI_CONFIG.use_taichi = config.mode === 'fast'; if (config.mode === 'strict') config.STAGE_GA_CONFIG.parallel_workers = 1; return config;
}

function readPointcloudConfig() { const config = {}; document.querySelectorAll('#pointcloud-fields [data-key]').forEach((node) => { const [group, key] = node.dataset.key.split('.'); config[group] ||= {}; config[group][key] = node.type === 'number' ? Number(node.value) : node.value; }); return config; }

async function uploadFile(file) { const response = await fetch(`/api/uploads?name=${encodeURIComponent(file.name)}`, {method:'POST', body:file}); return response.json(); }
async function bindUpload(kind, node, preview) { const file = node.files[0]; if (!file) return; try { const record = await uploadFile(file); state.uploads[kind] = record; const data = await fetchJson(`/api/uploads/${record.id}/inspect?kind=pointcloud`); $(preview).textContent = `${record.name} · ${data.points.toLocaleString()}点 · ${data.size_mm[0].toFixed(3)} × ${data.size_mm[1].toFixed(3)} mm`; } catch (error) { $(preview).textContent = error.message; } }

function bind() {
  document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => { document.querySelectorAll('.tab').forEach((item) => item.classList.toggle('active', item === tab)); document.querySelectorAll('.panel').forEach((panel) => panel.classList.toggle('active', panel.id === tab.dataset.panel)); }));
  $('#sim-mode').addEventListener('change', () => { if ($('#sim-mode').value === 'strict') $('#sim-backend').textContent = 'NumPy · 支持恢复'; else $('#sim-backend').textContent = state.defaults.capabilities.taichi ? 'Taichi · 不支持严格恢复' : 'Taichi 未安装'; });
  $('#sim-reset').addEventListener('click', () => renderSimulation(state.defaults.simulation)); $('#pointcloud-reset').addEventListener('click', () => renderPointcloud(state.defaults.pointcloud));
  $('#reference-file').addEventListener('change', () => bindUpload('reference', $('#reference-file'), '#reference-preview')); $('#detail-file').addEventListener('change', () => bindUpload('detail', $('#detail-file'), '#detail-preview'));
  $('#run-simulation').addEventListener('click', submitSimulation); $('#run-pointcloud').addEventListener('click', submitPointcloud); $('#refresh-history').addEventListener('click', refreshHistory);
  $('#export-config').addEventListener('click', () => { const blob = new Blob([JSON.stringify(readSimulationConfig(), null, 2)], {type:'application/json'}); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'simulation-config.json'; link.click(); URL.revokeObjectURL(link.href); });
  $('#import-config').addEventListener('change', async (event) => { try { const config = JSON.parse(await event.target.files[0].text()); renderSimulation({...state.defaults.simulation, ...config}); setMessage('#sim-message', '配置已载入，请检查目标矩阵后提交。'); } catch (error) { setMessage('#sim-message', error.message, true); } });
}

async function submitSimulation() { try { const button = $('#run-simulation'); button.disabled = true; const job = await fetchJson('/api/jobs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({kind:'simulation', run_mode: JSON.parse($('#targets').value).length === 1 ? 'single' : 'staged', targets: JSON.parse($('#targets').value), config: readSimulationConfig()})}); state.currentJob = job.id; showJob(job); startPolling(); setMessage('#sim-message', '任务已提交，正在运行。'); } catch (error) { setMessage('#sim-message', error.message, true); } finally { $('#run-simulation').disabled = false; } }
async function submitPointcloud() { try { if (!state.uploads.reference || !state.uploads.detail) throw new Error('请先上传190 mm参考点云和细节点云'); const job = await fetchJson('/api/jobs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({kind:'pointcloud', reference_id:state.uploads.reference.id, detail_id:state.uploads.detail.id, pointcloud_config:readPointcloudConfig()})}); state.currentJob = job.id; showJob(job); startPolling(); setMessage('#pointcloud-message', 'MATLAB任务已提交，读取、计算、导出会分别计时。'); } catch (error) { setMessage('#pointcloud-message', error.message, true); } }

function startPolling() { clearInterval(state.timer); state.timer = setInterval(async () => { if (!state.currentJob) return; try { showJob(await fetchJson(`/api/jobs/${state.currentJob}`)); } catch (error) { clearInterval(state.timer); } }, 1500); }
function showJob(job) { $('#result-state').textContent = job.state; $('#result-state').className = `badge ${job.state === 'completed' ? '' : 'neutral'}`; $('#result-subtitle').textContent = `${job.kind === 'simulation' ? '多阶段模拟' : '点云六指标'} · ${job.id}`; const result = job.result || {}; const percent = result.stages_completed && result.total_stages ? (result.stages_completed / result.total_stages) * 100 : (job.state === 'completed' ? 100 : 8); $('#progress-bar').style.width = `${percent}%`; $('#progress-text').textContent = job.state === 'completed' ? `完成 · ${job.elapsed_seconds ?? ''} 秒` : `${job.state} · ${job.error || '等待计算进度'}`; if (job.state === 'completed') { $('#result-content').innerHTML = `<div class="result-card"><h4>结果文件</h4><table>${(job.files || []).map((file) => `<tr><td>${file.name}</td><td><a href="/api/jobs/${job.id}/download/${file.name}">下载</a></td></tr>`).join('')}</table></div><div class="result-card"><h4>任务信息</h4><p>结果已先保存数值文件，再生成过程图。若绘图失败，数值结果仍可下载。</p></div>`; } }

async function refreshHistory() { try { const jobs = await fetchJson('/api/jobs'); $('#job-count').textContent = jobs.length; $('#history-list').innerHTML = jobs.length ? jobs.map((job) => `<div class="history-item"><div><strong>${job.kind === 'simulation' ? '多阶段模拟' : '实测点云 → 六指标'} · ${job.id}</strong><small>${job.state} · ${new Date(job.created_at * 1000).toLocaleString()}</small></div><div class="history-actions"><button class="button ghost" data-open="${job.id}">查看</button>${job.state === 'interrupted' || job.state === 'failed' ? `<button class="button secondary" data-resume="${job.id}">恢复</button>` : ''}</div></div>`).join('') : '<p class="preview">暂无任务记录。</p>'; document.querySelectorAll('[data-open]').forEach((button) => button.addEventListener('click', async () => { state.currentJob = button.dataset.open; showJob(await fetchJson(`/api/jobs/${state.currentJob}`)); document.querySelector('[data-panel="results-panel"]').click(); })); document.querySelectorAll('[data-resume]').forEach((button) => button.addEventListener('click', async () => { await fetchJson(`/api/jobs/${button.dataset.resume}/resume`, {method:'POST'}); state.currentJob = button.dataset.resume; showJob(await fetchJson(`/api/jobs/${state.currentJob}`)); startPolling(); })); } catch (error) { $('#history-list').textContent = error.message; } }

boot().catch((error) => { $('#health-text').textContent = error.message; $('#health-dot').parentElement.classList.remove('ok'); });
