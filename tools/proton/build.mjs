// app/proton.js 만들기: npm ci && npm run build
// 묶인 패키지의 라이선스 고지를 파일 맨 위에 넣음 (드라이브 SDK MIT · 암호 라이브러리 GPL-3.0 · openpgp LGPL-3.0+ 등).
import { build } from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';

const r = await build({
  entryPoints: ['entry.js'], bundle: true, minify: true, format: 'iife', target: 'es2022',
  platform: 'browser', metafile: true, write: false, legalComments: 'none', logLevel: 'warning',
});
const pkgs = new Map();
for (const f of Object.keys(r.metafile.inputs)) {
  const m = f.match(/node_modules\/((?:@[^/]+\/)?[^/]+)\//);
  if (!m || pkgs.has(m[1])) continue;
  const dir = path.join('node_modules', m[1]);
  const pj = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'));
  const lic = fs.readdirSync(dir).find(x => /^(licen[cs]e|copying)/i.test(x));
  pkgs.set(m[1], `${pj.name}@${pj.version} (${pj.license || '?'})${lic ? '\n' + fs.readFileSync(path.join(dir, lic), 'utf8').trim() : ''}`);
}
const head = `/*! 봇카이브 프로톤 드라이브 공개 링크 받기 — 원본: tools/proton/entry.js (AGPL-3.0, 봇카이브와 같음)\n묶인 패키지와 라이선스:\n\n${[...pkgs.values()].join('\n\n').replace(/\*\//g, '* /')}\n*/\n`;
fs.writeFileSync('../../app/proton.js', head + r.outputFiles[0].text);
console.log(`app/proton.js ${(fs.statSync('../../app/proton.js').size / 1024).toFixed(0)}KB · 패키지 ${pkgs.size}개`);
