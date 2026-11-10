const fs = require('fs');
const path = require('path');
for (const [name, expected] of [['bale',24],['needle',10]]) {
  const mdl = fs.readFileSync(path.join(__dirname, '..','models','seno_field',`${name}.mdl`));
  if (mdl.toString('ascii',0,4) !== 'IDST' || mdl.readInt32LE(4) !== 10 || mdl.readInt32LE(72) !== mdl.length)
    throw Error(`${name}: invalid MDL v10 header or file length`);
  if (mdl.readInt32LE(180) !== 1) throw Error(`${name}: expected one embedded texture`);
  const smd = fs.readFileSync(path.join(__dirname,`${name}_ref.smd`),'utf8').split('\n');
  const start = smd.indexOf('triangles') + 1;
  let count=0, peak=0;
  for(let i=start;i<smd.length && smd[i]!=='end';i+=4) {
    count++;
    for(let j=1;j<=3;j++) {
      const v=smd[i+j].trim().split(/\s+/).slice(1,4).map(Number);
      peak=Math.max(peak,...v.map(Math.abs));
    }
  }
  if (peak !== expected) throw Error(`${name}: unexpected source bounds ${peak}`);
  console.log(`${name}: MDL v10, ${mdl.length} bytes, 1 embedded texture, ${count} triangles, max extent ${peak}`);
}
