// Tutor IA por rol y proveedor. Uso: node tutor_e2e.js <modo: ia|sinia> <curso>
const { chromium } = require('playwright');
const B='http://localhost:8069', MODE=process.argv[2]||'ia', C=process.argv[3]||'2'; const res=[]; const ok=(n,c,x='')=>res.push([c?'OK  ':'FALLA',n,x]);
async function login(b,u){const p=await (await b.newContext()).newPage(); p.errors=[]; p.on('pageerror',e=>p.errors.push(e.message));
 await p.goto(B+'/campus/login'); await p.fill('#login',u); await p.fill('#password','Oddo123456'); await Promise.all([p.waitForNavigation(),p.click('button[type=submit]')]); return p;}
async function ask(p, text){ const n=await p.$$eval('#cp-chat .cp-msg-ai', x=>x.length);
 await p.fill('#cp-chat-input', text); await p.click('#cp-chat-form button');
 await p.waitForFunction(n0=>{const m=[...document.querySelectorAll('#cp-chat .cp-msg-ai')]; return m.length>n0 && !m[m.length-1].classList.contains('cp-typing');}, n, {timeout:60000});
 return p.$eval('#cp-chat .cp-msg-ai:last-child', e=>e.textContent); }
(async()=>{const b=await chromium.launch();
 const s=await login(b,'prueba.estudiante@pi.edu.co'); await s.goto(B+`/campus/curso/${C}/tutor-ia`);
 ok('estudiante: saludo pregunta qué no entiende', /no entiendes o te cuesta entender/.test(await s.textContent('#cp-chat')));
 ok('estudiante: no ve panel del docente', !(await s.$('text=¿Qué les cuesta entender a los estudiantes?')));
 ok('estudiante: formulario con «¿Qué no entiendes…?»', /Qué no entiendes o te cuesta entender/.test(await s.textContent('body')));
 const q1 = MODE==='ia' ? 'No entiendo la diferencia entre cifrado simétrico y asimétrico' : 'No entiendo qué es una API REST y los códigos de estado HTTP';
 const q2 = MODE==='ia' ? '¿Qué es el principio de mínimo privilegio?' : '¿Cómo funciona el manejador global de excepciones en Spring Boot?';
 const a1=await ask(s,q1), a2=await ask(s,q2);
 ok('respuestas distintas para preguntas distintas', a1.trim()!==a2.trim(), a1.slice(0,90)+' || '+a2.slice(0,90));
 if (MODE==='ia') { ok('respuesta 1 concordante', a1.includes('cifrado simétrico')); ok('respuesta 2 concordante', a2.includes('mínimo privilegio')); ok('modo estudiante en el prompt', a1.includes('(estudiante)')); }
 else { ok('sin IA: respuesta 1 cita contenido relacionado', /HTTP|REST|API|estado/i.test(a1), a1.slice(0,160)); ok('sin IA: respuesta 2 cita contenido relacionado', /excepci|manejador|Advice/i.test(a2), a2.slice(0,160));
   const a3=await ask(s,'Hazme 3 preguntas tipo examen'); ok('sin IA: genera preguntas del banco', /Practica con estas preguntas/.test(a3), a3.slice(0,100));
   const a4=await ask(s,'Hazme 3 preguntas tipo examen'); ok('sin IA: no repite las mismas preguntas', a3!==a4); }
 for (const [u,label] of [['docente.prueba@pi.edu.co','docente'],['administrador.prueba@pi.edu.co','administrador']]) {
   const t=await login(b,u); await t.goto(B+`/campus/curso/${C}/tutor-ia`);
   ok(label+': título del asistente', new RegExp('Asistente IA del '+label).test(await t.textContent('h2')));
   ok(label+': saludo orientado a preparar clases', /preparar, explicar o revisar/.test(await t.textContent('#cp-chat')));
   ok(label+': panel «¿Qué les cuesta entender a los estudiantes?»', !!(await t.$('text=¿Qué les cuesta entender a los estudiantes?')));
   ok(label+': ve preguntas recientes del estudiante', (await t.textContent('body')).includes(q1.slice(0,30)));
   const r=await ask(t,'Redacta 5 preguntas tipo examen con respuesta correcta y retroalimentación');
   if (MODE==='ia') ok(label+': respuesta en modo docente', r.includes('(docente)'), r.slice(0,80));
   else ok(label+': sin IA entrega preguntas con respuesta', /Respuesta:/.test(r), r.slice(0,120));
   ok(label+': sin errores JS', t.errors.length===0, t.errors.join(';'));
 }
 ok('estudiante sin errores JS', s.errors.length===0, s.errors.join(';'));
 await b.close(); res.forEach(r=>console.log(r.join(' | '))); console.log('FALLAS:',res.filter(r=>r[0]!=='OK  ').length,'/',res.length);})();
