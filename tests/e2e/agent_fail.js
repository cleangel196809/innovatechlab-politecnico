const { chromium } = require('playwright');
const B='http://localhost:8069'; const res=[]; const ok=(n,c,x='')=>res.push([c?'OK  ':'FALLA',n,x]);
const ctl = (body)=>fetch('http://127.0.0.1:9911/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
(async()=>{
  const b=await chromium.launch(); const a=await (await b.newContext()).newPage();
  await a.goto(B+'/campus/login'); await a.fill('#login','administrador.prueba@pi.edu.co'); await a.fill('#password','Oddo123456');
  await Promise.all([a.waitForNavigation(), a.click('button[type=submit]')]);
  async function run(file,name){ await a.goto(B+'/campus/admin/crear-curso'); await a.fill('input[name=name]',name); await a.setInputFiles('input[name=syllabus]',file);
    await a.fill('input[name=date_start]','2027-02-01'); await a.fill('input[name=date_end]','2027-03-01');
    await Promise.all([a.waitForNavigation(), a.click('form.cp-form button.cp-btn-lg')]);
    for(let i=0;i<120;i++){ const d=await a.$eval('#cp-job-done',e=>!e.hidden); const er=await a.$eval('#cp-job-error',e=>!e.hidden); if(d) return 'done'; if(er) return 'error'; await a.waitForTimeout(1000);} return 'timeout'; }
  await ctl({fail_research:true, fail_nucleo:3});
  let st=await run('ciber.docx','Fallos IA'); let log=await a.$eval('#cp-job-log',e=>e.textContent);
  ok('IA con fallos: el curso igual se crea', st==='done', st);
  ok('registra fallo de investigación', /investigación falló/.test(log));
  ok('núcleo 3 cae a contenido base', /Núcleo 3: la IA falló/.test(log));
  await ctl({fail_research:false, fail_nucleo:null});
  st=await run('roto.docx','Archivo roto'); log=await a.$eval('#cp-job-log',e=>e.textContent);
  console.log('URL', a.url(), st); await a.screenshot({path:'roto.png'}); ok('archivo dañado: estado error con mensaje', st==='error', st+' '+(await a.textContent('#cp-job-error')||'').slice(0,160));
  ok('botón reintentar visible', !!(await a.$('#cp-job-error form button')));
  // dos agentes en paralelo
  const p2=await (await b.newContext({storageState: await a.context().storageState()})).newPage();
  const go=async(pg,name)=>{await pg.goto(B+'/campus/admin/crear-curso'); await pg.fill('input[name=name]',name); await pg.setInputFiles('input[name=syllabus]','web.docx');
    await pg.fill('input[name=date_start]','2027-02-01'); await pg.fill('input[name=date_end]','2027-06-01'); await Promise.all([pg.waitForNavigation(), pg.click('form.cp-form button.cp-btn-lg')]);};
  await Promise.all([go(a,'Paralelo A'), go(p2,'Paralelo B')]);
  const wait=async pg=>{for(let i=0;i<120;i++){ if(await pg.$eval('#cp-job-done',e=>!e.hidden)) return 'done'; if(await pg.$eval('#cp-job-error',e=>!e.hidden)) return 'error'; await pg.waitForTimeout(1000);} return 'timeout';};
  const [s1,s2]=await Promise.all([wait(a),wait(p2)]);
  ok('dos agentes en paralelo terminan', s1==='done'&&s2==='done', s1+' '+s2);
  // permisos
  const d=await (await b.newContext()).newPage(); await d.goto(B+'/campus/login'); await d.fill('#login','docente.prueba@pi.edu.co'); await d.fill('#password','Oddo123456');
  await Promise.all([d.waitForNavigation(), d.click('button[type=submit]')]);
  ok('docente no ve el agente', (await d.goto(B+'/campus/admin/agente/1')).status()===404);
  const r=await d.request.post(B+'/campus/admin/agente/1/estado',{data:{jsonrpc:'2.0',method:'call',params:{}}}); const j=await r.json();
  ok('docente no consulta estado', !!j.error);
  await b.close(); res.forEach(r=>console.log(r.join(' | '))); console.log('FALLAS:',res.filter(r=>r[0]!=='OK  ').length,'/',res.length);
})();
