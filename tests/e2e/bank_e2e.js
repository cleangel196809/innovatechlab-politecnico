const { chromium } = require('playwright');
const B='http://localhost:8069', C=process.argv[2]||'9'; const res=[]; const ok=(n,c,x='')=>res.push([c?'OK  ':'FALLA',n,x]);
async function login(b,u){const p=await (await b.newContext()).newPage(); p.errors=[]; p.on('pageerror',e=>p.errors.push(e.message));
 await p.goto(B+'/campus/login'); await p.fill('#login',u); await p.fill('#password','Oddo123456'); await Promise.all([p.waitForNavigation(),p.click('button[type=submit]')]); return p;}
(async()=>{const b=await chromium.launch();
 const a=await login(b,'administrador.prueba@pi.edu.co');
 await a.goto(B+`/campus/curso/${C}/simulador`);
 await a.$eval('#importar', d=>d.open=true); await a.setInputFiles('input[name=gift]','banco_security_plus_v8.gift.txt');
 await Promise.all([a.waitForNavigation(), a.click('#importar button[type=submit]')]);
 let msg=await a.textContent('#importar .cp-alert'); ok('importa 110 preguntas', /110 de 110/.test(msg), msg.trim());
 ok('simulador muestra 110 disponibles', /\(110 disponibles\)/.test(await a.textContent('.cp-facts')));
 await a.$eval('#importar', d=>d.open=true); await a.setInputFiles('input[name=gift]','banco_security_plus_v8.gift.txt');
 await Promise.all([a.waitForNavigation(), a.click('#importar button[type=submit]')]);
 msg=await a.textContent('#importar .cp-alert'); ok('reimportar no duplica', /\b0 de 110/.test(msg), msg.trim());
 await a.$eval('#importar', d=>d.open=true); await a.setInputFiles('input[name=gift]','web.txt');
 await Promise.all([a.waitForNavigation(), a.click('#importar button[type=submit]')]);
 ok('archivo sin preguntas → mensaje', /No se encontraron/.test(await a.textContent('#importar')));
 const s=await login(b,'prueba.estudiante@pi.edu.co');
 const r=await s.request.post(B+`/campus/curso/${C}/preguntas/importar`,{multipart:{gift:{name:'x.txt',mimeType:'text/plain',buffer:Buffer.from('::a::P {=a ~b}')}}});
 ok('estudiante no puede importar', r.status()>=400, String(r.status()));
 ok('estudiante no ve el formulario', !(await (await s.goto(B+`/campus/curso/${C}/simulador`)) && await s.$('#importar')));
 // práctica del núcleo 2 usa preguntas de su dominio
 await s.goto(B+`/campus/curso/${C}`);
 const ql=await s.$$eval('.cp-section-card', cs=>{const c=cs[2]; const a=[...c.querySelectorAll('.cp-activity')].find(x=>/Cuestionario|Evaluación/.test(x.textContent)); return a&&a.getAttribute('href');});
 await s.goto(B+ql); const qs=await s.$$eval('.cp-practice-q p', ps=>ps.map(p=>p.textContent));
 ok('práctica del núcleo 2 con 5 preguntas', qs.length===5, String(qs.length));
 // simulacro completo
 await s.goto(B+`/campus/curso/${C}/simulador`);
 await Promise.all([s.waitForNavigation(), s.click('form[action$="/iniciar"] button')]);
 const radios=await s.$$('input[type=radio]'); const seen=new Set(); let n=0;
 for(const rd of radios){const nm=await rd.getAttribute('name'); if(!seen.has(nm)){seen.add(nm); await rd.check(); n++;}}
 ok('simulacro con 45 preguntas', n===45, String(n));
 await Promise.all([s.waitForNavigation(), s.$eval('#cp-sim-form', f=>f.submit())]);
 const txt=await s.textContent('body');
 const doms=['Conceptos generales','Amenazas','Arquitectura de seguridad','Operaciones de seguridad','Gestión y supervisión'].filter(d=>txt.includes(d));
 ok('resultado por los 5 dominios', doms.length===5, doms.join(', '));
 ok('retroalimentación visible en resultado', /Correcto:|No:/.test(txt));
 ok('sin errores JS', a.errors.length+s.errors.length===0);
 await b.close(); res.forEach(r=>console.log(r.join(' | '))); console.log('FALLAS:',res.filter(r=>r[0]!=='OK  ').length,'/',res.length);})();
