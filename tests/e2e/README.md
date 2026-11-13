# Pruebas end-to-end (Playwright)

```bash
npm i -g playwright   # o use el Chromium ya instalado
node tests/e2e/crawl.js http://localhost:8069   # recorre todas las páginas con los 4 usuarios de prueba
node tests/e2e/edge.js  http://localhost:8069   # 57 casos: login, permisos, carga de video/infografía, simulador, XSS…
```
`edge.js` necesita en la misma carpeta `ig.png`, `doc.pdf`, `clip.mp4`, `big.mp4` (>40 MB) y `empty.png`.
