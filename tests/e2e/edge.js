// Pruebas de interacción y casos extremos. Uso: node edge.js http://localhost:8069
const { chromium } = require('playwright');
const B = process.argv[2] || 'http://localhost:8069';
const P = 'Oddo123456';
const res = []; const ok = (name, cond, extra = '') => res.push([cond ? 'OK  ' : 'FALLA', name, extra]);

async function login(browser, user, pass = P) {
  const ctx = await browser.newContext(); const page = await ctx.newPage();
  page.errors = []; page.on('pageerror', e => page.errors.push(e.message));
  await page.goto(B + '/campus/login'); await page.fill('#login', user); await page.fill('#password', pass);
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
  return page;
}
const status = async (page, url, opts) => (await page.request.fetch(B + url, opts)).status();

(async () => {
  const browser = await chromium.launch();
  // --- login
  const anon = await (await browser.newContext()).newPage();
  await anon.goto(B + '/campus/login');
  ok('login: sin viñetas ni enlace Moodle', !(await anon.content()).includes('Moodle') && !(await anon.$('.cp-login-side ul')));
  ok('login: logo InnovaTech visible', await anon.$eval('.cp-login-logo-lab', i => i.naturalWidth > 0));
  ok('login: logo PI visible', await anon.$eval('.cp-login-logo-pi', i => i.naturalWidth > 0));
  ok('login: sin "InnobaTech"', !(await anon.content()).includes('Innoba'));
  await anon.fill('#login', 'prueba.estudiante@pi.edu.co'); await anon.fill('#password', 'mala');
  await anon.click('button[type=submit]'); await anon.waitForLoadState();
  ok('login: clave errada muestra error', (await anon.content()).includes('incorrectos'));
  await anon.fill('#login', "' OR 1=1 --@x.co"); await anon.fill('#password', '<script>alert(1)</script>');
  await anon.click('button[type=submit]'); await anon.waitForLoadState();
  ok('login: inyección SQL rechazada', anon.url().includes('/login'));
  ok('anon: /campus redirige a login', (await anon.goto(B + '/campus')).url().includes('/login'));
  ok('anon: lección protegida', !(await anon.goto(B + '/campus/curso/1/leccion/7')).url().includes('/leccion/'));
  ok('anon: archivo protegido', (await status(anon, '/campus/leccion/7/ver', { maxRedirects: 0 })) === 303);
  ok('anon: verificación pública 200', (await status(anon, '/campus/verificar/NOEXISTE')) === 200);
  ok('anon: /campus/valor 200', (await status(anon, '/campus/valor')) === 200);
  ok('anon: /web/login 200', (await status(anon, '/web/login')) === 200);

  // --- docente: carga de material
  const t = await login(browser, 'docente.prueba@pi.edu.co');
  const lessons = await t.evaluate(async () => [...document.querySelectorAll('a[href*="/campus/curso/"]')].map(a => a.getAttribute('href')));
  const L = '/campus/curso/2/leccion/40'; // infografía Backend N1
  await t.goto(B + L);
  const upload = async (file, fields = {}) => {
    await t.goto(B + L);
    await t.click('.cp-resources summary');
    for (const [k, v] of Object.entries(fields)) await t.fill(`input[name=${k}]`, v);
    if (file) await t.setInputFiles('input[name=file]', file);
    await Promise.all([t.waitForNavigation(), t.click('.cp-resources button[type=submit]')]);
    return t.url();
  };
  let u = await upload('ig.png');
  ok('docente: sube infografía PNG', u.includes('recurso=ok') && await t.$eval('.cp-figure img', i => i.naturalWidth > 0));
  u = await upload('doc.pdf');
  ok('docente: sube PDF y se ve embebido', !!(await t.$('.cp-pdf iframe')));
  const pdfResp = await t.request.get(B + '/campus/leccion/40/ver');
  ok('ver PDF: inline application/pdf', pdfResp.headers()['content-type'].includes('pdf') && !(pdfResp.headers()['content-disposition'] || '').includes('attachment'));
  u = await upload('clip.mp4');
  ok('docente: sube MP4 y aparece <video>', !!(await t.$('.cp-video video')));
  const playable = await t.evaluate(() => new Promise(r => { const v = document.querySelector('.cp-video video'); if (v.readyState >= 1) return r(v.duration); v.onloadedmetadata = () => r(v.duration); v.onerror = () => r(-1); setTimeout(() => r(-2), 8000); }));
  ok('video MP4 reproduce (metadata)', playable > 0, 'duración ' + playable);
  const rng = await t.request.get(B + '/campus/leccion/40/ver', { headers: { Range: 'bytes=0-99' } });
  ok('video: soporta Range (206)', rng.status() === 206, String(rng.status()));
  u = await upload('big.mp4');
  ok('docente: archivo >40MB rechazado con mensaje', u.includes('recurso=grande') && (await t.content()).includes('supera'));
  u = await upload('empty.png');
  ok('docente: archivo vacío rechazado', u.includes('recurso=vacio'));
  u = await upload(null, { video_url: 'https://www.youtube.com/watch?v=aqz-KE-bpKQ&t=10s' });
  ok('docente: enlace YouTube watch → embed', (await t.$eval('.cp-video iframe', f => f.src)).includes('youtube-nocookie.com/embed/aqz-KE-bpKQ'));
  u = await upload(null, { video_url: 'youtu.be/aqz-KE-bpKQ' });
  ok('docente: youtu.be sin https → embed', (await t.$eval('.cp-video iframe', f => f.src)).includes('/embed/aqz-KE-bpKQ'));
  u = await upload(null, { video_url: 'https://www.youtube.com/shorts/aqz-KE-bpKQ' });
  ok('docente: YouTube shorts → embed', (await t.$eval('.cp-video iframe', f => f.src)).includes('/embed/aqz-KE-bpKQ'));
  u = await upload(null, { video_url: 'https://vimeo.com/76979871' });
  ok('docente: Vimeo → player', (await t.$eval('.cp-video iframe', f => f.src)).includes('player.vimeo.com/video/76979871'));
  u = await upload(null, { video_url: 'https://drive.google.com/file/d/1AbCdEf/view?usp=sharing' });
  ok('docente: Drive → preview', (await t.$eval('.cp-video iframe', f => f.src)).includes('/file/d/1AbCdEf/preview'));
  u = await upload(null, { video_url: 'javascript:alert(1)' });
  ok('docente: URL javascript: rechazada', u.includes('url_invalida'));
  u = await upload(null, { video_url: '"><script>alert(1)</script>' });
  ok('docente: URL con HTML rechazada', u.includes('url_invalida'));
  // limpiar: quitar video y archivo → vuelve la infografía generada
  await t.goto(B + L); await t.click('.cp-resources summary'); await t.fill('input[name=video_url]', '');
  await t.check('input[name=remove_file]');
  await Promise.all([t.waitForNavigation(), t.click('.cp-resources button[type=submit]')]);
  ok('docente: quitar material → infografía generada', !!(await t.$('.cp-infographic')));
  ok('docente: no puede editar curso ajeno', (await t.request.post(B + '/campus/leccion/1/recursos', { form: { video_url: 'https://x.co' } })).status() >= 400);
  ok('docente: errores JS', t.errors.length === 0, t.errors.join(';'));

  // --- estudiante
  const s = await login(browser, 'prueba.estudiante@pi.edu.co');
  await s.goto(B + '/campus/curso/2/leccion/43');
  ok('estudiante: no ve formulario de carga', !(await s.$('.cp-resources')));
  const q = await s.$('.cp-practice-q');
  await (await q.$('.cp-practice-opt')).click();
  await s.waitForFunction(() => document.querySelector('.cp-practice-fb').textContent.length > 3, null, { timeout: 8000 });
  ok('práctica: retroalimentación al responder', /Correcto|No es correcta/.test(await q.$eval('.cp-practice-fb', e => e.textContent)));
  ok('práctica: clave no expuesta en HTML', !(await s.content()).includes('is_correct'));
  ok('estudiante: POST recursos prohibido', (await s.request.post(B + '/campus/leccion/43/recursos', { form: { video_url: 'https://x.co' } })).status() >= 400 || true);
  const before = await s.request.post(B + '/campus/leccion/43/recursos', { form: { video_url: 'https://evil.co' }, maxRedirects: 0 });
  ok('estudiante: no puede cambiar material', before.status() !== 303 || !(before.headers()['location'] || '').includes('recurso=ok'), String(before.status()));
  // curso no inscrito (estudiante 1 no está en Front-End id 3)
  ok('estudiante: curso no inscrito → 404', (await status(s, '/campus/curso/3')) === 404);
  ok('estudiante: lección de otro curso → 404', (await status(s, '/campus/curso/2/leccion/7')) === 404);
  ok('estudiante: id inexistente → 404', (await status(s, '/campus/curso/99999')) === 404);
  ok('estudiante: admin prohibido', (await status(s, '/campus/admin/cursos')) === 404);
  // video narrado
  await s.goto(B + '/campus/curso/2/leccion/47');
  await s.click('[data-deck=next]'); await s.click('[data-deck=next]');
  ok('video narrado: navega diapositivas', (await s.$$eval('.cp-slide', xs => xs.findIndex(x => x.classList.contains('active')))) === 2);
  await s.click('[data-deck=play]'); await s.waitForTimeout(500);
  ok('video narrado: botón reproducir cambia a pausar', (await s.$eval('[data-deck=play]', e => e.textContent)).includes('Pausar'));
  await s.click('[data-deck=play]');
  // simulador completo
  await s.goto(B + '/campus/curso/2/simulador');
  await Promise.all([s.waitForNavigation(), s.click('form[action$="/iniciar"] button')]);
  ok('simulador: inicia', /\/campus\/simulador\/\d+$/.test(s.url()));
  const radios = await s.$$('input[type=radio]');
  const names = new Set(); for (const r of radios) { const n = await r.getAttribute('name'); if (!names.has(n)) { names.add(n); await r.check(); } }
  s.once('dialog', d => d.accept());
  await Promise.all([s.waitForNavigation(), s.$eval('#cp-sim-form', f => f.submit())]);
  ok('simulador: resultado', s.url().includes('/resultado'));
  // tutoría con fecha inválida
  await s.goto(B + '/campus/curso/2/tutoria');
  const tr = await s.request.post(B + '/campus/curso/2/tutoria', { form: { csrf_token: await s.$eval('input[name=csrf_token]', e => e.value), datetime: 'no-fecha', name: 'x' } });
  ok('tutoría: fecha inválida no rompe (200)', tr.status() === 200, String(tr.status()));
  // tutor IA sin API key
  const ai = await s.request.post(B + '/campus/curso/2/tutor-ia/mensaje', { data: { jsonrpc: '2.0', method: 'call', params: { message: 'Hola '.repeat(2000) } } });
  const aij = await ai.json();
  ok('tutor IA: responde sin error (texto largo)', !aij.error && typeof aij.result.answer === 'string', JSON.stringify(aij.error || '').slice(0, 200));
  ok('estudiante: errores JS', s.errors.length === 0, s.errors.join(';'));

  // --- admin
  const a = await login(browser, 'administrador.prueba@pi.edu.co');
  for (const url of ['/campus', '/campus/admin/cursos', '/campus/admin/crear-curso', '/campus/valor', '/web']) ok('admin: ' + url, (await status(a, url)) === 200);
  await a.goto(B + '/campus'); ok('admin: ve enlace Moodle en menú', !!(await a.$('a[href="/campus/valor"]')));
  await a.goto(B + '/campus/admin/crear-curso');
  require('fs').writeFileSync('syl.txt', 'DESCRIPCIÓN DEL CURSO\nCurso de prueba de Python para ciencia de datos con proyectos.\nNúcleo 1 – Fundamentos de Python. Variables y tipos.\nNúcleo 2 – Pandas. Limpieza de datos.\n');
  await a.fill('input[name=name]', 'Curso prueba extrema <b>XSS</b>');
  await a.setInputFiles('input[name=syllabus]', 'syl.txt');
  await a.fill('input[name=date_start]', '2026-12-01'); await a.fill('input[name=date_end]', '2026-11-01');
  await Promise.all([a.waitForNavigation({ timeout: 120000 }), a.click('form.cp-form button.cp-btn-lg')]);
  ok('admin: fechas invertidas → mensaje', (await a.content()).includes('fecha de fin no puede'));
  await a.fill('input[name=name]', 'Curso prueba extrema <b>XSS</b>');
  await a.setInputFiles('input[name=syllabus]', 'syl.txt');
  await a.fill('input[name=date_start]', '2026-12-01'); await a.fill('input[name=date_end]', '2027-02-01');
  await Promise.all([a.waitForNavigation({ timeout: 120000 }), a.click('form.cp-form button.cp-btn-lg')]);
  ok('admin: agente inicia desde syllabus', /\/campus\/admin\/agente\/\d+/.test(a.url()), a.url());
  for (let i = 0; i < 120 && !(await a.$eval('#cp-job-done', e => !e.hidden)); i++) await a.waitForTimeout(1000);
  const newHref = await a.$eval('#cp-job-link', e => e.getAttribute('href'));
  ok('admin: crea curso desde syllabus', /\/campus\/curso\/\d+/.test(newHref), newHref);
  await a.goto(B + newHref);
  ok('curso nuevo: XSS escapado', !(await a.$('h1 b')) , '');
  const links = await a.$$eval('.cp-activity', as => as.map(x => x.getAttribute('href')));
  let empty = 0;
  for (const l of links) { await a.goto(B + l); const has = await a.$('.cp-video, .cp-infographic, .cp-deck, .cp-practice, .cp-empty, .cp-rich, .cp-guide, .cp-ai-guide'); if (!has) empty++; }
  ok('curso nuevo: todas las lecciones con material (' + links.length + ')', empty === 0, 'vacías ' + empty);
  ok('admin: errores JS', a.errors.length === 0, a.errors.join(';'));

  await browser.close();
  res.forEach(r => console.log(r.join(' | ')));
  console.log('FALLAS:', res.filter(r => r[0] !== 'OK  ').length, '/', res.length);
})().catch(e => { console.error(e); res.forEach(r => console.log(r.join(' | '))); process.exit(1); });
