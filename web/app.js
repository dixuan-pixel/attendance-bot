const titles=['昨日下班未打卡','今天请假','今天迟到','今天缺勤'];
const $=id=>document.getElementById(id);
const format=s=>new Date(s).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
let runs=[];
function element(tag,text,className){const el=document.createElement(tag);if(text!=null)el.textContent=text;if(className)el.className=className;return el;}
function render(){
 const run=runs.find(r=>String(r.id)===$('records').value),report=run?.report;
 $('status').textContent=run?.conclusion==='failure'?'运行失败':run?.status==='completed'?'运行已完成':run?'正在运行':'等待记录';
 $('status').className='run-status'+(run?.conclusion==='failure'?' failed':'');
 $('cards').replaceChildren(...titles.map((title,i)=>{const card=element('article',null,'metric metric-'+i),top=element('div',null,'metric-top'),value=element('div',report?String(report.groups[i].length):'—','metric-value');top.append(element('span',title),element('span','0'+(i+1),'metric-index'));value.append(element('small','人'));card.append(top,value,element('div',null,'metric-rule'));return card;}));
 $('date').textContent=run?format(run.created_at)+' 的考勤通报':'每日名单将在这里显示';$('total').textContent=report?.total!=null?'统计成员 '+report.total+' 人':'';
 const rows=report?.groups.flatMap((names,i)=>names.map(name=>({name,kind:i})))||[];
 if(!report||!rows.length){const empty=element('div',null,'empty');empty.append(element('h3',report?'本次没有考勤异常':'暂无通报结果'),element('p',report?'四类名单均为空。':run?.reason||'还没有可查看的记录。'));$('result').replaceChildren(empty);return;}
 const table=element('table'),head=element('thead'),tr=element('tr');['员工姓名','考勤情况','统计日期'].forEach((v,i)=>tr.append(element('th',v,i===2?'scope-col':'')));head.append(tr);const body=element('tbody');rows.forEach(r=>{const row=element('tr'),name=element('td'),person=element('div',null,'person');person.append(element('span',r.name.slice(-2),'avatar'),element('strong',r.name));name.append(person);const kind=element('td');kind.append(element('span',titles[r.kind],'tag tag-'+r.kind));row.append(name,kind,element('td',r.kind===0?'上一个统计日':'通报当日','scope-col muted'));body.append(row);});table.append(head,body);$('result').replaceChildren(table);
}
async function load(){
 $('refresh').disabled=true;
 try{const response=await fetch('./data.json?v='+Date.now(),{cache:'no-store'});if(!response.ok)throw Error();const data=await response.json();runs=data.runs;const old=$('records').value;$('records').replaceChildren(...runs.map(r=>{const option=element('option',format(r.created_at)+(r.conclusion==='failure'?' · 运行失败':''));option.value=String(r.id);return option;}));if(runs.some(r=>String(r.id)===old))$('records').value=old;$('updated').textContent='数据更新时间：'+format(data.updated);render();}
 catch{const empty=element('div',null,'empty');empty.append(element('h3','暂时无法读取考勤结果'),element('p','请稍后点击刷新重试。'));$('result').replaceChildren(empty);}
 finally{$('refresh').disabled=false;}
}
$('records').addEventListener('change',render);$('refresh').addEventListener('click',load);render();load();
