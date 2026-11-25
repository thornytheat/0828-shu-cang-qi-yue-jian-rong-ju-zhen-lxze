import {element, request} from './client.js';

const root = document.querySelector('#release-area');

function announce(text, failed = false) {
  const node = document.querySelector('#release-notice');
  if (!node) return;
  node.textContent = text;
  node.dataset.failure = String(failed);
}

function codeBadge(code) {
  return element('span', code, {class: 'release-code', title: code});
}

function fieldViolations(check) {
  const wrap = element('div', '', {class: 'release-violations'});
  const violations = check?.violations || {};
  const blocking = check?.blocking_read_versions || [];
  if (!blocking.length) {
    wrap.append(element('span', check ? '所有在用读版本兼容' : '尚未核对'));
    return wrap;
  }
  for (const reader of blocking) {
    const details = violations[reader] || {};
    const codes = Object.entries(details).map(([field, reasons]) => `${field}: ${reasons.join(', ')}`).join('；');
    wrap.append(element('p', `${reader} 不兼容${codes ? ` · ${codes}` : ''}`));
  }
  return wrap;
}

function renderTable(table) {
  const card = element('article', '', {class: 'release-card', 'data-table': table.id});
  const head = element('header', '', {class: 'release-card-head'});
  head.append(
    element('h3', table.id),
    element('span', table.effective_write_version ? `生效写版本：${table.effective_write_version}` : '尚无生效写版本', {
      class: 'release-effective',
      'data-effective': Boolean(table.effective_write_version),
    }),
  );
  card.append(head);

  const writes = element('div', '', {class: 'release-versions'});
  writes.append(element('h4', '候选写版本'));
  for (const write of table.write_versions || []) {
    const row = element('div', '', {class: 'release-version-row'});
    row.append(element('code', write.version));
    const checkButton = element('button', '核对', {type: 'button', 'data-action': 'check', 'data-write': write.version});
    row.append(checkButton);
    writes.append(row);
  }
  card.append(writes);

  const readers = element('div', '', {class: 'release-versions'});
  readers.append(element('h4', '仍在用 / 已退役读版本'));
  for (const reader of table.read_versions || []) {
    const row = element('div', '', {class: 'release-version-row'});
    row.append(element('code', reader.version), element('span', reader.status, {
      class: 'release-status', 'data-status': reader.status,
    }));
    const action = reader.status === 'ACTIVE' ? 'retire' : 'restore';
    const button = element('button', reader.status === 'ACTIVE' ? '退役' : '恢复', {
      type: 'button', 'data-action': action, 'data-version': reader.version,
    });
    row.append(button);
    readers.append(row);
  }
  if (!(table.read_versions || []).length) readers.append(element('p', '暂无读版本'));
  card.append(readers);

  const checks = table.checks || [];
  const latest = checks[checks.length - 1] || table.latest_check;
  if (latest) {
    const fresh = latest.read_generation === table.read_generation;
    const state = !fresh ? 'STALE' : latest.compatible ? 'COMPATIBLE' : 'INCOMPATIBLE';
    const summary = element('div', '', {class: 'release-check', 'data-check-state': state});
    summary.append(element('strong', `最近结论：${state}`));
    summary.append(fieldViolations(latest));
    if (!fresh) summary.append(element('p', '读版本在核对后发生退役/恢复，请重新核对。'));
    card.append(summary);

    const canSign = fresh && latest.compatible;
    const sign = element('button', '签发这张表', {
      type: 'button', class: 'action release-sign', 'data-check': latest.id,
    });
    sign.disabled = !canSign;
    card.append(sign);
  } else {
    card.append(element('p', '请先选择候选写版本进行核对。'));
  }

  card.addEventListener('click', event => handleCardClick(event, table));
  return card;
}

async function handleCardClick(event, table) {
  const button = event.target.closest('button[data-action], button[data-check]');
  if (!button) return;
  button.disabled = true;
  try {
    if (button.dataset.check) {
      await request(`/api/release/checks/${button.dataset.check}/sign`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
      announce(`${table.id} 已签发`);
    } else if (button.dataset.action === 'check') {
      const result = await request(`/api/release/tables/${encodeURIComponent(table.id)}/checks`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({write_version: button.dataset.write}),
      });
      announce(result.compatible ? `${table.id} 核对兼容` : `${table.id} 存在不兼容读版本`, !result.compatible);
    } else if (button.dataset.action === 'retire' || button.dataset.action === 'restore') {
      await request(`/api/release/tables/${encodeURIComponent(table.id)}/read-versions/${encodeURIComponent(button.dataset.version)}/${button.dataset.action}`, {method: 'POST'});
      announce(`读版本已${button.dataset.action === 'retire' ? '退役，原结论已失效' : '恢复，原结论已失效'}`);
    }
    await load();
  } catch (error) {
    announce(error.message, true);
    button.disabled = false;
  }
}

function renderBatch(result) {
  const target = document.querySelector('#release-batch-result');
  target.replaceChildren();
  if (!result) return;
  const reports = result.batches || [result];
  for (const batch of reports) {
    const box = element('section', '', {class: 'release-batch'});
    box.append(element('h4', `${batch.id} · ${batch.status} · ${batch.released}/${batch.total} 张表签发`));
    const list = element('ul');
    for (const item of batch.items || []) {
      const li = element('li');
      li.append(element('code', `${item.table}@${item.write_version || ''}`), element('span', item.status));
      if (item.code) li.append(codeBadge(item.code));
      list.append(li);
    }
    box.append(list);
    target.append(box);
  }
}

async function load() {
  if (!root) return;
  const data = await request('/api/release/tables');
  const cards = document.querySelector('#release-cards');
  cards.replaceChildren();
  for (const table of data.items || []) cards.append(renderTable(table));
  if (!(data.items || []).length) {
    cards.append(element('p', '尚未登记表版本。点击“载入版本演练”查看核对、失效和并发签发。'));
  }
}

async function demo() {
  announce('正在载入演练数据…');
  await request('/api/release/demo', {method: 'POST'});
  await load();
  announce('已载入：dw.orders 有一个不兼容旧读版本');
}

async function concurrentDemo() {
  announce('正在让两个批次并发提交同表候选版本…');
  const result = await request('/api/release/demo-concurrent', {method: 'POST'});
  renderBatch(result);
  await load();
  announce('并发演练完成：同表仅一个候选生效，其他表独立签发');
}

if (root) {
  document.querySelector('#release-demo').addEventListener('click', () => demo().catch(error => announce(error.message, true)));
  document.querySelector('#release-concurrent').addEventListener('click', () => concurrentDemo().catch(error => announce(error.message, true)));
  document.querySelector('#release-refresh').addEventListener('click', () => load().catch(error => announce(error.message, true)));
  load().catch(error => announce(error.message, true));
}
