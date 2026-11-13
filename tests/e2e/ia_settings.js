const { chromium } = require('playwright'); const B='http://localhost:8069'; const res=[]; const ok=(n,c,x='')=>res.push([c?'OK  ':'FALLA',n,x]);
(async()=>{const b=await chromium.launch(); const p=await (await b.newContext()).newPage(); p.errors=[]; p.on('pageerror',e=>p.errors.push(e.message));
 await p.goto(B+'/campus/login'); await p.fill('#login','administrador.prueba@pi.edu.co'); await p.fill('#password','Oddo123456'); await Promise.all([p.waitForNavigation(),p.click('button[type=submit]')]);
 await p.goto(B+'/campus/admin/ia'); ok('página proveedor IA', /Proveedor de inteligencia artificial/.test(await p.textContent('h1')));
 ok('sin proveedor activo', /Sin IA/.test(await p.textContent('body')));
 await p.selectOption('select[name=provider]','gemini'); await p.fill('input[name=key_gemini]','AIzaTESTLOCAL999'); 
 await Promise.all([p.waitForNavigation(), p.click('form.cp-form button')]);
 ok('guardado', /Configuración guardada/.test(await p.textContent('body')));
 ok('activo Gemini', /Gemini \(Google\)/.test(await p.textContent('body')));
 ok('clave enmascarada', /…L999/.test(await p.textContent('body')) && !(await p.content()).includes('AIzaTESTLOCAL999'));
 await Promise.all([p.waitForNavigation(), p.click('text=Probar conexión')]);
 ok('probar conexión responde', /✔ Respondió/.test(await p.textContent('body')), (await p.textContent('.cp-alert')).slice(0,120));
 await p.goto(B+'/campus/admin/crear-curso'); ok('crear curso muestra proveedor', /Proveedor de IA activo: Gemini/.test(await p.textContent('body')));
 // clave inválida -> error claro
 await p.goto(B+'/campus/admin/ia'); await p.fill('input[name=key_gemini]','xxxxxxxxBAD'); await Promise.all([p.waitForNavigation(), p.click('form.cp-form button')]);
 await Promise.all([p.waitForNavigation(), p.click('text=Probar conexión')]); ok('clave inválida muestra error', /✘ Falló/.test(await p.textContent('body')));
 // borrar
 await p.check('input[name=clear_gemini]'); await p.selectOption('select[name=provider]',''); await p.fill('input[name=base_url]','');
 await Promise.all([p.waitForNavigation(), p.click('form.cp-form button')]); ok('clave borrada → sin IA', /Sin IA/.test(await p.textContent('body')));
 const d=await (await b.newContext()).newPage(); await d.goto(B+'/campus/login'); await d.fill('#login','docente.prueba@pi.edu.co'); await d.fill('#password','Oddo123456'); await Promise.all([d.waitForNavigation(),d.click('button[type=submit]')]);
 ok('docente no accede', (await d.goto(B+'/campus/admin/ia')).status()===404);
 ok('sin errores JS', p.errors.length===0);
 await b.close(); res.forEach(r=>console.log(r.join(' | '))); console.log('FALLAS:',res.filter(r=>r[0]!=='OK  ').length,'/',res.length);})();
