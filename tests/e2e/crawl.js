// Recorre el campus con cada rol y reporta errores. Uso: node crawl.js http://localhost:8069
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://localhost:8069';
const PASS = process.env.CP_PASS || 'Oddo123456';
const USERS = (process.env.CP_USERS || 'administrador.prueba@pi.edu.co,docente.prueba@pi.edu.co,prueba.estudiante@pi.edu.co,prueba.estudiante2@pi.edu.co').split(',');
const MAX = parseInt(process.env.CP_MAX || '400', 10);

(async () => {
  const browser = await chromium.launch();
  const problems = [];
  for (const login of USERS) {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    let cur = '';
    page.on('pageerror', e => problems.push([login, cur, 'JS: ' + e.message]));
    page.on('console', m => { if (m.type() === 'error' && !/favicon|fonts\.g|youtube|vimeo|drive\.google/.test(m.text())) problems.push([login, cur, 'console: ' + m.text().slice(0, 200)]); });
    page.on('response', r => { if (r.url().startsWith(BASE) && r.status() >= 400) problems.push([login, cur, r.status() + ' ' + r.url()]); });
    await page.goto(BASE + '/campus/login');
    await page.fill('#login', login); await page.fill('#password', PASS);
    await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
    if (page.url().includes('/login')) { problems.push([login, '', 'LOGIN FALLÓ']); continue; }
    const seen = new Set(); const queue = ['/campus'];
    let n = 0; const stats = {};
    while (queue.length && n < MAX) {
      const path = queue.shift(); if (seen.has(path)) continue; seen.add(path); n++;
      cur = path;
      const resp = await page.goto(BASE + path, { waitUntil: 'load' }).catch(e => { problems.push([login, path, 'nav ' + e.message]); return null; });
      if (!resp) continue;
      const ct = resp.headers()['content-type'] || '';
      if (!ct.includes('text/html')) continue;
      // lección: verificar que el material sea visible
      if (/\/leccion\/\d+$/.test(path)) {
        const info = await page.evaluate(() => {
          const eyebrow = (document.querySelector('.cp-eyebrow') || {}).textContent || '';
          const has = s => !!document.querySelector(s);
          const imgs = [...document.images].filter(i => i.complete && i.naturalWidth === 0).map(i => i.src);
          return { eyebrow, video: has('.cp-video'), ig: has('.cp-infographic'), deck: has('.cp-deck .cp-slide.active'), quiz: has('.cp-practice') || has('.cp-empty'), fig: has('.cp-figure') || has('.cp-pdf'), broken: imgs,
                   text: (document.querySelector('.cp-lesson') || {}).innerText?.length || 0 };
        });
        const t = info.eyebrow;
        stats[t.split('·')[1]?.trim()] = (stats[t.split('·')[1]?.trim()] || 0) + 1;
        if (/Infografía/.test(t) && !(info.ig || info.fig)) problems.push([login, path, 'Infografía vacía']);
        if (/Video/.test(t) && !(info.video || info.deck)) problems.push([login, path, 'Video vacío']);
        if (/Presentación/.test(t) && !(info.deck || info.fig || info.video)) problems.push([login, path, 'Presentación vacía']);
        if (/Cuestionario/.test(t) && !info.quiz) problems.push([login, path, 'Cuestionario vacío']);
        if (info.text < 200) problems.push([login, path, 'Lección casi vacía (' + info.text + ' car.)']);
        if (info.broken.length) problems.push([login, path, 'Imagen rota ' + info.broken.join(' ')]);
        if (info.deck) { await page.click('[data-deck=next]'); await page.click('[data-deck=prev]'); }
      } else {
        const broken = await page.evaluate(() => [...document.images].filter(i => i.complete && i.naturalWidth === 0).map(i => i.src));
        if (broken.length) problems.push([login, path, 'Imagen rota ' + broken.join(' ')]);
      }
      const links = await page.$$eval('a[href]', as => as.map(a => a.getAttribute('href')));
      for (let h of links) {
        if (!h || h.startsWith('http') || h.startsWith('#') || h.startsWith('mailto')) continue;
        h = h.split('#')[0];
        if (!h.startsWith('/campus') || /salir|\/pdf$|\/archivo$|\/ver$/.test(h)) continue;
        if (!seen.has(h)) queue.push(h);
      }
    }
    console.log(login, 'páginas:', n, JSON.stringify(stats));
    await ctx.close();
  }
  await browser.close();
  const uniq = [...new Set(problems.map(p => p.join(' | ')))];
  console.log('PROBLEMAS:', uniq.length); uniq.forEach(p => console.log(' -', p));
})();
