import {feedback, field} from '../components/common/fields.js';
import {empty, metrics, panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {ARRANGE, PLAN, PRIORITY} from '../constants/enums.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, h, link, p} from '../utils/dom.js';
import {date} from '../utils/format.js';

const RULES = [
  '工具只从期末在管清册出，借出与退役工具不可排。',
  '日期重叠的场次不共用同一件工具，同一场内一件工具也只算一次。',
  '任一需求缺一件，整场待排；替用品按登记顺序递补缺口。',
  '重点场先于普通场排期，同级按开始日期与登记顺序。',
  '确认方案时按其他已确认方案已占的工具重算，确认后场次锁定。',
  '新盘点完成后重算待排场次；已确认安排遇新借出或退役标记冲突，原安排保留。',
];

const runName = id => workspace.runs.find(run => run.id === id)?.name || `运行 ${id}`;
const nextMonth = () => { const day = new Date(); day.setMonth(day.getMonth() + 1); return day.getMonth() + 1; };

function createForm() {
  const error = feedback();
  const submit = button('新建方案', {type:'submit', class:'primary', 'data-testid':'create-plan'});
  const completed = workspace.runs.filter(run => run.status === 'complete');
  return el('form', {class:'fields', onSubmit:handler(submit, error, async event => {
    const data = new FormData(event.target);
    const item = await workspace.createPlan({name:data.get('plan_name'), run_id:Number(data.get('run_id'))});
    location.hash = `#plan/${item.id}`;
  })},
    field({key:'plan_name', label:'方案名称', type:'string', max_length:120}, `${nextMonth()}月活动排借`),
    el('label', {class:'field', for:'plan-run'}, el('span', {}, '期末盘点来源'),
      el('select', {id:'plan-run', name:'run_id', required:true},
        completed.map(run => el('option', {value:run.id}, `${run.name} · ${date(run.finished_at)}`)))),
    el('div', {class:'actions'}, submit), error);
}

function plansTable(plans) {
  return table([
    {label:'方案', render:item => link(item.name, `#plan/${item.id}`)},
    {label:'状态', render:item => pill(PLAN[item.status], item.status)},
    {label:'已排·待排·冲突', render:item => `${item.scheduled} · ${item.pending} · ${item.conflict}`},
    {label:'待排原因', render:item => item.first_pending_reason || '—'},
    {label:'来源盘点', render:item => link(runName(item.run_id), `#results/${item.run_id}`)},
  ], plans, {caption:'排借方案', empty:'还没有排借方案。'});
}

export async function plansPanel() {
  const plans = await workspace.plans();
  const completed = workspace.runs.filter(run => run.status === 'complete');
  const creator = session.canWrite && completed.length > 0 && el('details', {class:'schedule-fields'},
    el('summary', {}, '新建排借方案'),
    p('从一次已完成的期末盘点取在管清册，为下月活动逐场排借。', 'subtle'), createForm());
  return panel('排借方案', plansTable(plans), creator);
}

const needs = event => event.lines.map(line =>
  `${line.tool}×${line.quantity}${line.substitutes.length ? `（替用：${line.substitutes.join('、')}）` : ''}`).join('；');

function arrangement(event) {
  const tools = event.assignments.map(item =>
    `${item.asset_id} ${item.asset_name}${item.via ? '（替）' : ''}`).join('、');
  if (event.status === 'scheduled') return tools;
  if (event.status === 'conflict') return `${event.reason}。原安排：${tools}`;
  return event.reason || '—';
}

function eventForm(plan, refresh, error) {
  const submit = button('登记场次', {type:'submit', class:'primary', 'data-testid':'add-event'});
  const rows = el('div', {class:'line-rows'});
  const more = button('添加需求行', {class:'quiet'});
  const makeRow = () => {
    const remove = button('移除', {class:'quiet'});
    const row = el('div', {class:'form-grid line-row'},
      el('label', {class:'field'}, el('span', {}, '工具名称'),
        el('input', {name:'tool', type:'text', required:true, maxlength:120, list:'pool-names'})),
      el('label', {class:'field'}, el('span', {}, '件数'),
        el('input', {name:'quantity', type:'number', min:1, max:99, step:1, required:true, value:1})),
      el('label', {class:'field'}, el('span', {}, '替用品（可空，逗号分隔）'),
        el('input', {name:'substitutes', type:'text', maxlength:600, placeholder:'按递补顺序填写'})),
      el('div', {class:'actions'}, remove));
    remove.addEventListener('click', () => { if (rows.children.length > 1) row.remove(); });
    return row;
  };
  rows.append(makeRow());
  more.addEventListener('click', () => { if (rows.children.length < 20) rows.append(makeRow()); });
  return el('form', {class:'fields', 'data-testid':'event-form', onSubmit:handler(submit, error, async event => {
    const data = new FormData(event.target);
    const quantities = data.getAll('quantity'), substitutes = data.getAll('substitutes');
    const lines = data.getAll('tool').map((tool, index) => ({
      tool:tool.trim(), quantity:Number(quantities[index]),
      substitutes:substitutes[index].split(/[,，、;；]+/).map(name => name.trim()).filter(Boolean),
    })).filter(line => line.tool);
    if (!lines.length) throw new Error('请至少填写一行工具需求');
    await workspace.addEvent(plan.id, {name:data.get('event_name'), start_date:data.get('start_date'),
      end_date:data.get('end_date'), priority:data.get('priority'), lines});
    await refresh();
  })},
    el('datalist', {id:'pool-names'}, plan.pool.map(item => el('option', {value:item.asset_name}))),
    field({key:'event_name', label:'场次名称', type:'string', max_length:120}),
    el('div', {class:'form-grid'},
      field({key:'start_date', label:'开始日期', type:'date'}),
      field({key:'end_date', label:'结束日期', type:'date'}),
      el('label', {class:'field', for:'event-priority'}, el('span', {}, '优先级'),
        el('select', {id:'event-priority', name:'priority'},
          el('option', {value:'normal', selected:true}, '普通'), el('option', {value:'key'}, '重点')))),
    rows, el('div', {class:'actions'}, more, submit));
}

function detailView(plan, refresh) {
  const error = feedback();
  const editable = plan.status === 'draft' && session.canWrite;
  const columns = [
    {label:'场次', render:event => event.name},
    {label:'日期', render:event => `${event.start_date} 至 ${event.end_date}`},
    {label:'优先级', render:event => PRIORITY[event.priority]},
    {label:'需求', render:event => needs(event)},
    {label:'状态', render:event => pill(ARRANGE[event.status], event.status)},
    {label:'安排 / 待排原因', render:event => arrangement(event)},
  ];
  if (editable) columns.push({label:'操作', render:event => {
    const remove = button('移除', {class:'quiet'});
    remove.addEventListener('click', handler(remove, error, async () => {
      await workspace.removeEvent(plan.id, event.id);
      await refresh();
    }));
    return remove;
  }});
  const confirm = button('确认排借方案', {class:'primary', 'data-testid':'confirm-plan'});
  confirm.addEventListener('click', handler(confirm, error, async () => {
    await workspace.confirmPlan(plan.id);
    await refresh();
  }));
  return el('div', {class:'two-col'},
    el('div', {class:'wide-panel'},
      el('section', {class:'panel result-head'},
        p(`排借方案 · ${PLAN[plan.status]}`, 'eyeline'), h(2, plan.name),
        el('div', {class:'actions'}, pill(PLAN[plan.status], plan.status),
          link(`来源盘点：${plan.run_name}`, `#results/${plan.run_id}`, {class:'quiet'})),
        p(`盘点截止日 ${plan.as_of_date} · ${plan.author} 创建于 ${date(plan.created_at)}`
          + (plan.confirmed_at ? ` · 确认于 ${date(plan.confirmed_at)}` : ''), 'subtle'),
        metrics([{label:'已排场次', value:plan.scheduled}, {label:'待排场次', value:plan.pending},
          {label:'冲突场次', value:plan.conflict}])),
      panel('场次与排借安排',
        table(columns, plan.events, {caption:'场次与排借安排', empty:'还没有场次，请在下方登记。'}),
        editable && eventForm(plan, refresh, error),
        editable && plan.events.length > 0 && el('div', {class:'actions'}, confirm,
          el('span', {class:'subtle'}, '确认后场次与安排锁定；若与其他方案同时确认，后确认的方案按已占工具重算。')),
        plan.status === 'draft' && !session.canWrite && p('方案拟定中，等待分析员完善并确认。', 'subtle'),
        plan.status === 'confirmed' && p('方案已确认。新盘点完成后待排场次自动重算；遇新借出的安排标记冲突并保留原安排。', 'subtle'),
        error)),
    el('aside', {class:'sidebar-panel'},
      panel('期末在管清册',
        table([{key:'asset_name', label:'工具名称'}, {key:'in_custody', label:'在管件数'}], plan.pool,
          {caption:'期末在管清册', empty:'期末没有在管工具。'}),
        p(`来自「${plan.run_name}」截止 ${plan.as_of_date} 的盘点，借出与退役工具不可排。`, 'subtle')),
      panel('排借口径', el('ul', {class:'method-list'}, RULES.map(text => el('li', {}, text))))));
}

async function listView() {
  const plans = await workspace.plans();
  const completed = workspace.runs.filter(run => run.status === 'complete');
  return el('div', {class:'two-col'},
    el('div', {class:'wide-panel'}, panel('排借方案', plansTable(plans))),
    el('aside', {class:'sidebar-panel'},
      session.canWrite && (completed.length
        ? panel('新建排借方案', createForm())
        : panel('新建排借方案', empty('先完成一次期末盘点，再新建排借方案。', '#run', '前往盘点'))),
      panel('排借口径', el('ul', {class:'method-list'}, RULES.map(text => el('li', {}, text))))));
}

export async function planPage(route, refresh) {
  if (!route.id) return listView();
  const plan = await workspace.plan(route.id);
  return detailView(plan, refresh);
}
