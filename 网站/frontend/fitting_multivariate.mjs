const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function renderMultivariateResult(summary = {}) {
  const groups = summary.groups || [];
  return `<div class="card wide"><div class="section-overline">MULTIVARIATE RESPONSE SURFACE</div><h3>双自变量拟合结果</h3><p class="help-line">模型形式为 Y = f(X1, X2)。推荐仅针对本次候选模型和交叉验证规则，不代表外推物理规律。</p>${groups.map(group => `<section class="fitting-group"><h4>${esc(group.label || '全部数据')}</h4><p class="notice">${group.recommended_id ? `推荐：${esc(group.recommended_id)}。` : '暂无可靠推荐。'}${esc(group.reason || '')}</p><div class="table-wrap"><table><thead><tr><th>候选模型</th><th>公式</th><th>状态</th><th>CV RMSE</th><th>参数</th><th>说明</th></tr></thead><tbody>${(group.candidates || []).map(candidate => `<tr${candidate.id === group.recommended_id ? ' class="fitting-recommended"' : ''}><td>${esc(candidate.label || candidate.id)}</td><td><code>${esc(candidate.formula)}</code></td><td>${esc(candidate.status || '')}</td><td>${candidate.metrics?.cv_rmse == null ? '—' : Number(candidate.metrics.cv_rmse).toPrecision(6)}</td><td>${Object.entries(candidate.parameters || {}).map(([key, value]) => `${esc(key)}=${Number(value).toPrecision(6)}`).join('<br>') || '—'}</td><td>${esc(candidate.error || '')}</td></tr>`).join('')}</tbody></table></div></section>`).join('')}</div>`;
}

export async function mountMultivariate({ get, post, openJob }) {
  const root = document.querySelector('#multivariate-panel');
  if (!root) return;
  root.innerHTML = `<div class="section-heading"><div><div class="section-overline">05 / MULTIVARIATE FITTING</div><h2>双自变量响应面</h2><p>输入 X1、X2 和 Y，先预检推荐，再运行二元模型并输出三维曲面、切片和 Origin XYZ 数据。</p></div><span class="badge neutral">Y = f(X1, X2)</span></div><div class="card"><div class="grid two"><div class="field"><label for="mv-file">上传表格（CSV / TXT / TSV / XLSX / MAT）</label><input id="mv-file" type="file" accept=".csv,.txt,.tsv,.xlsx,.mat"><small id="mv-file-note">也可以直接粘贴表格。</small></div><div class="field"><label for="mv-text">粘贴表格</label><textarea id="mv-text" rows="7" spellcheck="false">X1,X2,Y\n1,1,6.5\n2,1,8\n1,2,9\n2,2,13</textarea></div></div><button id="mv-inspect" class="button secondary">读取数据预览</button><div id="mv-preview" class="preview">尚未读取数据。</div><div class="grid four"><label class="field">X1列<select id="mv-x1"><option>请先读取</option></select></label><label class="field">X2列<select id="mv-x2"><option>请先读取</option></select></label><label class="field">Y列<select id="mv-y"><option>请先读取</option></select></label><label class="field">分组列（可选）<select id="mv-group"><option value="">不分组</option></select></label></div></div><div class="card"><h3>候选响应面</h3><div id="mv-models" class="fitting-models">正在读取模型目录…</div><div class="grid three"><label class="field">评价指标<select id="mv-metric"><option value="cv_rmse">验证 RMSE</option><option value="cv_mae">验证 MAE</option><option value="aicc">AICc</option><option value="bic">BIC</option><option value="r2">R²</option></select></label><label class="field">交叉验证折数<input id="mv-folds" type="number" min="2" max="5" value="5"></label><label class="field">随机种子<input id="mv-seed" type="number" min="0" value="42"></label></div><p class="help-line">自动模式先给出候选、数据范围和推荐指标；点击确认后才运行。</p><div class="actions"><button id="mv-precheck" class="button secondary">预检并给出推荐</button><button id="mv-run" class="button primary">确认并运行 →</button></div><div id="mv-message" class="message" role="status" aria-live="polite" hidden></div><div id="mv-check" class="preview"></div></div>`;
  let upload = null; let table = null; let catalog = null; let busy = false; let lastPayload = null;
  const $ = id => root.querySelector(id);
  const source = () => upload ? { upload_id: upload.id } : { text: $('#mv-text').value };
  const selectedModels = () => [...root.querySelectorAll('[data-mv-model]:checked')].map(node => node.dataset.mvModel);
  function fillColumns(data) {
    table = data;
    $('#mv-preview').innerHTML = `<p>共 ${esc(data.row_count ?? data.rows?.length ?? 0)} 行、${esc(data.columns?.length || 0)} 列</p><div class="table-wrap"><table><thead><tr>${(data.columns || []).map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${(data.rows || []).slice(0, 10).map(row => `<tr>${row.map(value => `<td>${esc(value ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    for (const [id, optional] of [['mv-x1', false], ['mv-x2', false], ['mv-y', false], ['mv-group', true]]) {
      $(`#${id}`).innerHTML = `<option value="">${optional ? '不分组' : '请选择'}</option>` + (data.columns || []).map((name, index) => `<option value="${index}">${index + 1} · ${esc(name)}</option>`).join('');
    }
  }
  function payload() {
    if (!table) throw new Error('请先读取数据预览');
    if (['#mv-x1', '#mv-x2', '#mv-y'].some(id => $(id).value === '')) throw new Error('请选择 X1、X2 和 Y 列');
    const selection = { mode: 'multivariate2', x1_column: Number($('#mv-x1').value), x2_column: Number($('#mv-x2').value), y_column: Number($('#mv-y').value), group_column: $('#mv-group').value === '' ? null : Number($('#mv-group').value), missing_policy: 'reject' };
    if ([selection.x1_column, selection.x2_column, selection.y_column].some(Number.isNaN)) throw new Error('请选择 X1、X2 和 Y 列');
    return { mode: 'multivariate2', source: source(), selection, options: { models: selectedModels(), metric: $('#mv-metric').value, folds: Number($('#mv-folds').value), seed: Number($('#mv-seed').value) }, plot: { title: '双自变量响应面', dpi: 300 } };
  }
  async function inspect() {
    const data = await post('/api/fitting/inspect', source());
    fillColumns(data);
  }
  $('#mv-text').addEventListener('input', () => { if (!$('#mv-text').value.trim()) return; upload = null; $('#mv-file-note').textContent = '当前使用粘贴文本。'; table = null; });
  $('#mv-file').onchange = async () => { const file = $('#mv-file').files[0]; if (!file) return; $('#mv-file-note').textContent = '正在上传…'; const response = await fetch(`/api/uploads?name=${encodeURIComponent(file.name)}`, { method: 'POST', body: file }); const data = await response.json(); if (!response.ok) throw new Error(data.error || '上传失败'); upload = data; $('#mv-file-note').textContent = `当前文件：${file.name}`; await inspect(); };
  $('#mv-inspect').onclick = async () => { try { await inspect(); } catch (error) { $('#mv-message').hidden = false; $('#mv-message').textContent = error.message; } };
  $('#mv-precheck').onclick = async () => { try { lastPayload = payload(); const result = await post('/api/fitting/precheck', lastPayload); $('#mv-check').innerHTML = `<p>有效数据 ${result.dataset.row_count} 行，${result.dataset.group_count} 组。</p><p><strong>数据画像：</strong>${esc(result.profile?.type || '未识别')}。${esc(result.profile?.reason || '')}</p><p><strong>推荐图形：</strong>${(result.profile?.recommended_plots || []).map(esc).join('、') || '三维响应面、切片图、残差图'}。</p><p><strong>评价建议：</strong>${esc(result.recommendation.reason)}</p>`; } catch (error) { $('#mv-message').hidden = false; $('#mv-message').textContent = error.message; } };
  $('#mv-run').onclick = async () => { if (busy) return; try { busy = true; lastPayload = payload(); await post('/api/fitting/precheck', lastPayload); const job = await post('/api/fitting/jobs', lastPayload); await openJob(job.id); } catch (error) { $('#mv-message').hidden = false; $('#mv-message').textContent = error.message; } finally { busy = false; } };
  try { catalog = await get('/api/fitting/catalog'); $('#mv-models').innerHTML = (catalog.multivariate_models || []).filter(model => model.id !== 'custom2').map(model => `<label class="fitting-model"><input type="checkbox" data-mv-model="${esc(model.id)}" checked><span><strong>${esc(model.label)}</strong><code>${esc(model.formula)}</code></span></label>`).join(''); } catch (error) { $('#mv-models').textContent = `模型目录读取失败：${error.message}`; }
}
