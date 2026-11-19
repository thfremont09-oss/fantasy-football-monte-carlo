// Render the brand PNGs (favicons, app icon, share image) from static/brand/mark.svg with Chromium.
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
const root = process.argv[2], tpl = process.argv[3], out = path.join(root, 'static', 'brand');
const uri = 'data:image/svg+xml;base64,' + fs.readFileSync(path.join(out, 'mark.svg')).toString('base64');
(async () => {
  const b = await chromium.launch();
  for (const [name, size] of [['icon-512.png',512],['icon-192.png',192],['apple-touch-icon.png',180],['favicon-48.png',48],['favicon-32.png',32]]) {
    const pg = await b.newPage({ viewport: { width: size, height: size } });
    await pg.setContent(`<body style="margin:0;background:transparent"><img src="${uri}" style="width:${size}px;height:${size}px;display:block">`);
    await pg.screenshot({ path: path.join(out, name), omitBackground: true });
  }
  const pg = await b.newPage({ viewport: { width: 1200, height: 630 } });
  await pg.setContent(fs.readFileSync(tpl, 'utf8').replace('{uri}', uri)); await pg.waitForTimeout(2000);
  await pg.screenshot({ path: path.join(out, 'og.png') });
  await b.close();
})();
