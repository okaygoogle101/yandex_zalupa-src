// Deterministic GoldSrc SMD and 8-bit BMP sources for seno_field.
const fs = require('fs');
const path = require('path');
const root = __dirname;

function bitmap(name, palette, pixel) {
  const w = 64, h = 64, offset = 14 + 40 + 256 * 4;
  const out = Buffer.alloc(offset + w * h);
  out.write('BM'); out.writeUInt32LE(out.length, 2); out.writeUInt32LE(offset, 10);
  out.writeUInt32LE(40, 14); out.writeInt32LE(w, 18); out.writeInt32LE(h, 22);
  out.writeUInt16LE(1, 26); out.writeUInt16LE(8, 28); out.writeUInt32LE(w * h, 34);
  out.writeUInt32LE(256, 46);
  for (let i = 0; i < 256; i++) {
    const [r,g,b] = palette(i); const p = 54 + i * 4;
    out[p] = b; out[p+1] = g; out[p+2] = r;
  }
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++)
    out[offset + (h - 1 - y) * w + x] = pixel(x,y) & 255;
  fs.writeFileSync(path.join(root, name), out);
}
// Coarse straw streaks and two twine bands remain legible on a small model.
bitmap('hay.bmp', i => [Math.min(255, 71 + Math.floor(i*.68)), Math.min(255, 55 + Math.floor(i*.53)), 15 + Math.floor(i*.19)],
  (x,y) => (x >= 17 && x <= 20 || x >= 43 && x <= 46) ? 26 + ((x+y)%11) : 90 + ((x*13+y*7+(y%7)*19)%80));
bitmap('needle.bmp', i => [80 + Math.floor(i*.68), 90 + Math.floor(i*.64), 96 + Math.floor(i*.62)],
  (x,y) => 115 + Math.floor(80 * Math.abs(Math.sin(x*Math.PI/32))) - (y%13===0 ? 30 : 0));

const header = 'version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\ntriangles\n';
const skeleton = 'version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\n';
function tri(tex, a, b, c, norm, uv) {
  return tex+'\n'+[a,b,c].map((v,i)=>`0 ${v.join(' ')} ${norm.join(' ')} ${uv[i].join(' ')}`).join('\n')+'\n';
}
function quad(tex,a,b,c,d,n) {
  return tri(tex,a,b,c,n,[[0,0],[1,0],[1,1]]) + tri(tex,a,c,d,n,[[0,0],[1,1],[0,1]]);
}
function box(tex,x0,x1,y0,y1,z0,z1) {
  let s='';
  s+=quad(tex,[x1,y0,z0],[x1,y1,z0],[x1,y1,z1],[x1,y0,z1],[1,0,0]);
  s+=quad(tex,[x0,y1,z0],[x0,y0,z0],[x0,y0,z1],[x0,y1,z1],[-1,0,0]);
  s+=quad(tex,[x1,y1,z0],[x0,y1,z0],[x0,y1,z1],[x1,y1,z1],[0,1,0]);
  s+=quad(tex,[x0,y0,z0],[x1,y0,z0],[x1,y0,z1],[x0,y0,z1],[0,-1,0]);
  s+=quad(tex,[x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1],[0,0,1]);
  s+=quad(tex,[x0,y1,z0],[x1,y1,z0],[x1,y0,z0],[x0,y0,z0],[0,0,-1]);
  return s;
}
const bale=box('hay.bmp',-24,24,-24,24,-24,24);
// Four small bars make a visible eye; the body is inside the 20-unit hit box.
let needle=box('needle.bmp',-1.2,1.2,-1.2,1.2,-7,5);
needle+=box('needle.bmp',-3,-1.5,-1,1,5,9);
needle+=box('needle.bmp',1.5,3,-1,1,5,9);
needle+=box('needle.bmp',-3,3,-1,1,7.5,9);
const tip=[0,0,-10], u=[[-1.2,-1.2,-7],[1.2,-1.2,-7],[1.2,1.2,-7],[-1.2,1.2,-7]];
for(let i=0;i<4;i++) {
  const a=u[i],b=u[(i+1)%4], n=[[0,-.93,-.37],[.93,0,-.37],[0,.93,-.37],[-.93,0,-.37]][i];
  needle+=tri('needle.bmp',a,tip,b,n,[[0,0],[.5,1],[1,0]]);
}
for(const [name,geo] of [['bale',bale],['needle',needle]]) {
  fs.writeFileSync(path.join(root,`${name}_ref.smd`),header+geo+'end\n');
  fs.writeFileSync(path.join(root,`${name}_idle.smd`),skeleton);
  fs.writeFileSync(path.join(root,`${name}.qc`),`$modelname "${name}.mdl"\n$cd "."\n$cdtexture "."\n$scale 1.0\n$body studio "${name}_ref"\n$sequence idle "${name}_idle" fps 1\n`);
}
console.log('Generated hay.bmp, needle.bmp, two SMD pairs and QC scripts.');
