// Simula el WAF de Render: rechaza (403) cualquier solicitud cuyo cuerpo tenga patrones de ataque.
const { chromium } = require('playwright');
const B = 'http://localhost:8069', C = process.argv[2] || '12';
const BAD = [/'\s*OR\s+1=1/i, /<script/i, /UNION\s+SELECT/i, /\/etc\/passwd/i];
const res = []; const ok = (n, c, x = '') => res.push([c ? 'OK  ' : 'FALLA', n, x]);
(async () => {
  const b = await chromium.launch(); const p = await b.newPage(); let blocked = 0;
  await p.route('**/*', route => {
    const body = route.request().postDataBuffer();
    const txt = body ? body.toString('latin1') : decodeURIComponent(route.request().url());
    if (BAD.some(r => r.test(txt))) { blocked++; return route.fulfill({ status: 403, body: '403 - Prohibido (WAF simulado)' }); }
    return route.continue();
  });
  await p.goto(B + '/campus/login'); await p.fill('#login', 'administrador.prueba@pi.edu.co'); await p.fill('#password', 'Oddo123456');
  await Promise.all([p.waitForNavigation(), p.click('button[type=submit]')]);
  // 1) Importar banco GIFT con contenido de ciberseguridad
  await p.goto(B + '/campus/curso/' + C + '/simulador');
  await p.$$eval('details', ds => ds.forEach(d => d.open = true));
  await p.setInputFiles('form[data-cp-encode="gift"] input[type=file]', 'waf.gift.txt');
  await Promise.all([p.waitForNavigation(), p.click('form[data-cp-encode="gift"] button[type=submit]')]);
  const txt = await p.textContent('body');
  ok('importación GIFT no bloqueada', !/Prohibido/.test(txt), p.url());
  ok('se importaron las 3 preguntas (o ya existían)', /gift=ok/.test(p.url()), (txt.match(/Se importaron[^.]*/) || [''])[0]);
  // 2) Tutor IA con una pregunta sobre inyección SQL
  await p.goto(B + '/campus/curso/' + C + '/tutor-ia');
  await p.fill('#cp-chat-input', "¿Por qué ' OR 1=1 -- permite entrar sin contraseña y cómo evito <script>alert(1)</script>?");
  await p.press('#cp-chat-input', 'Enter');
  await p.waitForFunction(() => !document.querySelector('.cp-typing'), null, { timeout: 120000 });
  const last = await p.$$eval('.cp-msg-ai', e => e[e.length - 1].textContent);
  ok('tutor responde (no bloqueado)', !/Error|No fue posible/.test(last), last.slice(0, 120));
  ok('el tutor recibió el texto original', /OR 1=1/.test(last), last.slice(0, 120));
  ok('ninguna solicitud bloqueada por el WAF simulado', blocked === 0, 'bloqueadas: ' + blocked);
  await b.close();
  res.forEach(r => console.log(r.join(' | '))); console.log('FALLAS:', res.filter(r => r[0] === 'FALLA').length, '/', res.length);
})();
