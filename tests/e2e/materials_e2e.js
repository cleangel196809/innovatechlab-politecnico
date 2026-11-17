// E2E de presentaciones institucionales, paquete del núcleo y carga de usuarios por Excel.
// Uso: node materials_e2e.js http://localhost:8069   (necesita estudiantes.xlsx en esta carpeta; se crea si falta)
const { chromium } = require('playwright');
const fs = require('fs');
const B = process.argv[2] || 'http://localhost:8069';
const res = []; const ok = (n, c, x = '') => res.push([c ? 'OK  ' : 'FALLA', n, x]);

async function login(browser, user) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, acceptDownloads: true }); const p = await ctx.newPage();
  p.errors = []; p.on('pageerror', e => p.errors.push(e.message));
  await p.goto(B + '/campus/login'); await p.fill('#login', user); await p.fill('#password', 'Oddo123456');
  await Promise.all([p.waitForNavigation(), p.click('button[type=submit]')]); return p;
}

(async () => {
  const browser = await chromium.launch();
  const s = await login(browser, 'prueba.estudiante@pi.edu.co');
  await s.goto(B + '/campus/curso/2/leccion/45');
  ok('deck institucional', await s.$('.cp-deck-pi .cp-sl-top img') !== null || await s.$('.cp-deck-pi .cp-sl-cover') !== null);
  ok('deck: narración en data-say', (await s.$eval('.cp-slide', e => e.dataset.say || '')).length > 20);
  await s.click('[data-deck=cc]');
  ok('deck: subtítulos visibles', await s.$eval('.cp-deck-caption', e => !e.hidden && e.textContent.length > 10));
  const pptx = await s.request.get(B + '/campus/leccion/45/pptx');
  ok('PPTX descargable por el estudiante', pptx.status() === 200 && (await pptx.body()).length > 20000, String(pptx.status()));
  const voz = await s.request.get(B + '/campus/leccion/45/voz/0');
  ok('voz: MP3 o 503 (respaldo del navegador)', [200, 503].includes(voz.status()), String(voz.status()));
  const sec = await s.request.get(B + '/campus/seccion/1/paquete');
  ok('paquete: prohibido al estudiante', sec.status() === 404, String(sec.status()));
  ok('importar usuarios: prohibido al estudiante', (await s.request.get(B + '/campus/admin/usuarios/plantilla.xlsx', { maxRedirects: 0 })).status() >= 300);
  ok('estudiante: errores JS', s.errors.length === 0, s.errors.join(';'));

  const a = await login(browser, 'administrador.prueba@pi.edu.co');
  await a.goto(B + '/campus/curso/2/leccion/45');
  const link = await a.$('a[href*="/paquete"]');
  ok('docente/admin: enlace al paquete', !!link);
  if (link) {
    const z = await a.request.get(B + await link.getAttribute('href'));
    ok('paquete .zip', z.status() === 200 && (await z.body()).slice(0, 2).toString() === 'PK', String(z.status()));
  }
  const tpl = await a.request.get(B + '/campus/admin/usuarios/plantilla.xlsx');
  ok('plantilla Excel', tpl.status() === 200 && (await tpl.body()).slice(0, 2).toString() === 'PK');
  if (!fs.existsSync(__dirname + '/estudiantes.xlsx')) fs.writeFileSync(__dirname + '/estudiantes.xlsx', await tpl.body());
  await a.goto(B + '/campus/admin/cursos');
  await a.selectOption('select[name=role]', 'student');
  await a.setInputFiles('input[name=file]', __dirname + '/estudiantes.xlsx');
  await Promise.all([a.waitForNavigation(), a.click('form[action$="/importar"] button')]);
  ok('carga Excel: resultado', /personas procesadas/.test(await a.content()));
  ok('carga Excel: credenciales descargables', await a.$('a[download="credenciales_campus.xlsx"]') !== null);
  ok('admin: errores JS', a.errors.length === 0, a.errors.join(';'));
  await browser.close();
  for (const r of res) console.log(r.join(' | '));
  console.log('FALLAS:', res.filter(r => r[0] !== 'OK  ').length, '/', res.length);
})();
