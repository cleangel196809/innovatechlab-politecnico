// E2E del agente de creación de cursos. Uso: node agent_e2e.js http://localhost:8069 <etiqueta>
const { chromium } = require('playwright');
const B = process.argv[2] || 'http://localhost:8069';
const TAG = process.argv[3] || 'run';
const res = []; const ok = (n, c, x = '') => { res.push([c ? 'OK  ' : 'FALLA', n, x]); };

async function login(browser, user) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } }); const p = await ctx.newPage();
  p.errors = []; p.on('pageerror', e => p.errors.push(e.message));
  await p.goto(B + '/campus/login'); await p.fill('#login', user); await p.fill('#password', 'Oddo123456');
  await Promise.all([p.waitForNavigation(), p.click('button[type=submit]')]); return p;
}

async function submit(a, file, name, opts = {}) {
  await a.goto(B + '/campus/admin/crear-curso');
  await a.fill('input[name=name]', name);
  await a.setInputFiles('input[name=syllabus]', file);
  await a.fill('input[name=date_start]', opts.start || '2027-02-01');
  await a.fill('input[name=date_end]', opts.end || '2027-05-30');
  if (opts.cert) await a.selectOption('select[name=certification_id]', opts.cert);
  const t = await a.$('input[name=teacher_ids]'); if (t) await t.check();
  const s = await a.$('input[name=student_ids]'); if (s) await s.check();
  if (opts.instructions) await a.fill('textarea[name=instructions]', opts.instructions);
  await Promise.all([a.waitForNavigation({ timeout: 60000 }), a.click('form.cp-form button.cp-btn-lg')]);
  return a.url();
}

async function waitJob(a, maxS = 300) {
  for (let i = 0; i < maxS; i++) {
    const done = await a.$eval('#cp-job-done', e => !e.hidden).catch(() => false);
    const err = await a.$eval('#cp-job-error', e => !e.hidden).catch(() => false);
    if (done || err) return done ? 'done' : 'error';
    await a.waitForTimeout(1000);
  }
  return 'timeout';
}

async function checkCourse(a, courseUrl, label) {
  await a.goto(B + courseUrl);
  const secs = await a.$$eval('.cp-section-card', x => x.length);
  const links = [...new Set(await a.$$eval('.cp-activity', as => as.map(x => x.getAttribute('href'))))];
  ok(label + ': secciones ≥ 6', secs >= 6, String(secs));
  ok(label + ': lecciones ≥ 35', links.length >= 35, String(links.length));
  ok(label + ': fuentes del curso visibles', !!(await a.$('.cp-sources')));
  let empty = [], types = {};
  for (const l of links) {
    await a.goto(B + l);
    const info = await a.evaluate(() => {
      const eb = (document.querySelector('.cp-eyebrow') || {}).textContent || '';
      const has = s => !!document.querySelector(s);
      return { t: (eb.split('·')[1] || '').trim(), mat: has('.cp-video') || has('.cp-infographic') || has('.cp-deck .cp-slide') || has('.cp-practice') || has('.cp-empty') || has('.cp-guide') || has('.cp-figure'),
               txt: ((document.querySelector('.cp-lesson') || {}).innerText || '').length };
    });
    types[info.t] = (types[info.t] || 0) + 1;
    if (/Infograf|Video|Presentaci|Cuestionario/.test(info.t) && !info.mat) empty.push(l + ' ' + info.t);
    if (info.txt < 150) empty.push(l + ' corto ' + info.txt);
  }
  ok(label + ': todas las lecciones con material', empty.length === 0, empty.slice(0, 5).join(' | '));
  ok(label + ': tipos completos', ['Lectura', 'Presentación interactiva', 'Infografía', 'Video', 'Sesión sincrónica virtual', 'Sesión presencial asistida por IA', 'Cuestionario'].every(t => types[t] > 0), JSON.stringify(types));
  return links;
}

(async () => {
  const browser = await chromium.launch();
  const a = await login(browser, 'administrador.prueba@pi.edu.co');
  // --- validaciones del formulario
  let u = await submit(a, 'syl.xlsx', 'Formato malo');
  ok('rechaza formato no admitido', (await a.content()).includes('Formato no admitido'));
  u = await submit(a, 'vacio.txt', 'Vacío');
  ok('rechaza syllabus vacío', (await a.content()).includes('está vacío'));
  u = await submit(a, 'ciber.docx', 'Fechas', { start: '2027-05-01', end: '2027-01-01' });
  ok('rechaza fechas invertidas', (await a.content()).includes('fecha de fin'));

  // --- ejecución principal (DOCX ciberseguridad, certificación automática)
  u = await submit(a, 'ciber.docx', 'Ciberseguridad ' + TAG, { cert: 'auto', instructions: 'Énfasis en MiPymes colombianas' });
  ok('redirige a la página de avance', /\/campus\/admin\/agente\/\d+$/.test(u), u);
  const t0 = Date.now(); const st = await waitJob(a);
  ok('agente termina (DOCX)', st === 'done', st + ' en ' + Math.round((Date.now() - t0) / 1000) + ' s');
  const log = await a.$eval('#cp-job-log', e => e.textContent);
  ok('bitácora: certificación detectada', /Security\+ V8/.test(log));
  ok('bitácora: curso listo', /Curso listo/.test(log));
  ok('barra al 100 %', (await a.$eval('#cp-job-pct', e => e.textContent)).startsWith('100'));
  const courseUrl = await a.$eval('#cp-job-link', e => e.getAttribute('href'));
  const links = await checkCourse(a, courseUrl, 'DOCX');
  // simulador con preguntas
  await a.goto(B + courseUrl + '/simulador');
  const bank = await a.$eval('.cp-facts', e => e.textContent).catch(() => '');
  ok('simulador muestra banco', /\(\d+ disponibles\)/.test(bank), bank.replace(/\s+/g, ' ').slice(0, 120));
  fs = require('fs'); fs.writeFileSync('/tmp/last_course_' + TAG + '.txt', courseUrl + '\n' + log);

  // --- publicar y ver como estudiante inscrito
  await a.goto(B + '/campus/admin/cursos');
  const cid = courseUrl.split('/').pop();
  const form = await a.$(`form[action="/campus/admin/curso/${cid}/guardar"]`);
  if (form) {
    await (await form.$('select[name=state]')).selectOption('published');
    await Promise.all([a.waitForNavigation(), (await form.$('button')).click()]);
  }
  const s = await login(browser, 'prueba.estudiante@pi.edu.co');
  const r = await s.goto(B + courseUrl);
  ok('estudiante inscrito ve el curso publicado', r.status() === 200, String(r.status()));
  if (r.status() === 200) {
    const quiz = links.find(Boolean);
    await s.goto(B + courseUrl);
    const qlink = await s.$$eval('.cp-activity', as => as.filter(x => /Cuestionario|Evaluación/.test(x.textContent)).map(x => x.getAttribute('href'))[1]);
    if (qlink) {
      await s.goto(B + qlink);
      const q = await s.$('.cp-practice-q');
      if (q) {
        await (await q.$('.cp-practice-opt')).click();
        await s.waitForFunction(() => document.querySelector('.cp-practice-fb').textContent.length > 3, null, { timeout: 8000 }).catch(() => {});
        ok('estudiante responde práctica', /Correcto|No es correcta/.test(await q.$eval('.cp-practice-fb', e => e.textContent)));
      } else ok('cuestionario del núcleo muestra práctica o aviso', !!(await s.$('.cp-empty')), 'sin preguntas (modo sin IA)');
    }
  }

  // --- otros formatos
  for (const [file, label] of [['ciber.pdf', 'PDF'], ['web.txt', 'TXT']]) {
    await submit(a, file, label + ' ' + TAG, { cert: 'auto' });
    const st2 = await waitJob(a);
    ok('agente termina (' + label + ')', st2 === 'done', st2);
    if (st2 === 'done') {
      const lg = await a.$eval('#cp-job-log', e => e.textContent);
      const m = lg.match(/· (\d+) núcleos/); ok(label + ': núcleos detectados ≥ 4', m && +m[1] >= 4, m ? m[1] : lg.slice(0, 300));
    }
  }
  ok('admin sin errores JS', a.errors.length === 0, a.errors.join(';'));
  await browser.close();
  res.forEach(r => console.log(r.join(' | ')));
  console.log('FALLAS:', res.filter(r => r[0] !== 'OK  ').length, '/', res.length);
})().catch(e => { console.error(e); res.forEach(r => console.log(r.join(' | '))); process.exit(1); });
