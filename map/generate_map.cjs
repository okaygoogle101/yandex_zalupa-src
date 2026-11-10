// Self-contained Valve 220 source; no neighbouring map geometry.
const fs=require('fs'),path=require('path');
const checkOnly=process.argv.includes('--check');
if(process.argv.slice(2).some(x=>x!=='--check'))throw Error('Usage: node map/generate_map.cjs [--check]');
const world=[],entities=[],solids=[];
const T={ground:'SN_WHEAT',dirt:'SN_DIRT',wood:'SN_WOOD',stone:'SN_STONE',tile:'SN_TILE',gold:'SN_GOLD',trim:'SN_TRIM',barn:'SN_BARN',beam:'SN_BEAM',hay:'SN_HAY',door:'SN_DOOR',sack:'SN_SACK',grain:'SN_GRAIN',rock:'SN_ROCK',crystal:'SN_CRYSTAL',hell:'SN_HELL',lava:'SN_LAVA'};
const round=x=>Math.round(x*1000)/1000;
const rect=(x0,y0,x1,y1)=>[[x0,y0],[x1,y0],[x1,y1],[x0,y1]];
const hex=(r,cx=0,cy=0,ph=0)=>Array.from({length:6},(_,i)=>[round(cx+r*Math.cos(ph+i*Math.PI/3)),round(cy+r*Math.sin(ph+i*Math.PI/3))]);
const disc=(r,cx,cy,n=16)=>Array.from({length:n},(_,i)=>[round(cx+r*Math.cos(2*Math.PI*i/n)),round(cy+r*Math.sin(2*Math.PI*i/n))]);
function face(p,q,r,tex,scale=1,axis=null){
 const a=q.map((v,i)=>v-p[i]),b=r.map((v,i)=>v-p[i]);
 const n=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
 const flat=Math.abs(n[2])>Math.max(Math.abs(n[0]),Math.abs(n[1]));
 const ax=(flat&&axis)||(flat?'[ 1 0 0 0 ] [ 0 -1 0 0 ]':Math.abs(n[0])>Math.abs(n[1])?'[ 0 1 0 0 ] [ 0 0 -1 0 ]':'[ 1 0 0 0 ] [ 0 0 -1 0 ]');
 return [p,q,r].map(v=>'( '+v.map(round).join(' ')+' )').join(' ')+` ${tex} ${ax} 0 ${scale} ${scale}`;
}
function prism(name,poly,z0,z1,tex,list=world,kind='world',scale=1,axis=null){
 if(poly.length<3||z0>=z1)throw Error('Invalid prism '+name);
 const low=poly.map(p=>[...p,z0]),hi=poly.map(p=>[...p,z1]);
 const faces=[face(low[0],low[1],low[2],tex,scale,axis),face(hi[0],hi[2],hi[1],tex,scale,axis)];
 poly.forEach((p,i)=>faces.push(face(low[i],hi[i],hi[(i+1)%poly.length],tex,scale,axis)));
 list.push('{\n'+faces.join('\n')+'\n}');solids.push({name,poly,z0,z1,kind});
}
function prismY(name,poly,y0,y1,tex,list=world,scale=1,kind='world'){
 if(poly.length<3||y0>=y1)throw Error('Invalid prismY '+name);
 const low=poly.map(([x,z])=>[x,y0,z]),hi=poly.map(([x,z])=>[x,y1,z]);
 // Y extrusion mirrors handedness versus prism(): winding must be reversed.
 const faces=[face(low[0],low[2],low[1],tex,scale),face(hi[0],hi[1],hi[2],tex,scale)];
 poly.forEach((p,i)=>faces.push(face(low[i],hi[(i+1)%poly.length],hi[i],tex,scale)));
 list.push('{\n'+faces.join('\n')+'\n}');
 const xs=poly.map(p=>p[0]),zs=poly.map(p=>p[1]);
 solids.push({name,poly:rect(Math.min(...xs),y0,Math.max(...xs),y1),z0:Math.min(...zs),z1:Math.max(...zs),kind});
}
function box(name,min,max,tex,list=world,kind='world',scale=1){prism(name,rect(min[0],min[1],max[0],max[1]),min[2],max[2],tex,list,kind,scale);}
// Tapered prism (different radius top/bottom): stalagmites, stalactites, spikes, bowls.
function frustum(name,cx,cy,r0,r1,z0,z1,tex,list=world,kind='detail',n=8){
 if(r0<=0||r1<=0||z0>=z1)throw Error('Invalid frustum '+name);
 const lo=disc(r0,cx,cy,n).map(p=>[...p,z0]),hi=disc(r1,cx,cy,n).map(p=>[...p,z1]);
 const faces=[face(lo[0],lo[1],lo[2],tex),face(hi[0],hi[2],hi[1],tex)];
 for(let i=0;i<n;i++)faces.push(face(lo[i],hi[i],hi[(i+1)%n],tex));
 list.push('{\n'+faces.join('\n')+'\n}');
 const rr=Math.max(r0,r1);
 solids.push({name,poly:disc(rr,cx,cy,n),z0,z1,kind});
}
// Angular rock prism: 5..7 sided, per-vertex radius variation and a small rotation,
// so a formation reads as faceted stone instead of a round cylinder.
function faceted(name,cx,cy,r0,r1,z0,z1,tex,list,n,rot=0,vary=0.15){
 if(n<5||n>7||r0<=0||r1<=0||z0>=z1)throw Error('Invalid faceted '+name);
 const ring=r=>Array.from({length:n},(_,i)=>{const a=rot+i*2*Math.PI/n,rr=r*(1+vary*Math.sin(1.7+2.9*i));return [round(cx+rr*Math.cos(a)),round(cy+rr*Math.sin(a))];});
 const rw=Math.max(r0,r1),lo=ring(r0).map(p=>[...p,z0]),hi=ring(r1).map(p=>[...p,z1]);
 const faces=[face(lo[0],lo[1],lo[2],tex),face(hi[0],hi[2],hi[1],tex)];
 for(let i=0;i<n;i++)faces.push(face(lo[i],hi[i],hi[(i+1)%n],tex));
 list.push('{\n'+faces.join('\n')+'\n}');
 solids.push({name,poly:ring(rw),z0,z1,kind:'detail'});
}
// Rectangle in a rotated local frame (u = radial/outward, v = lateral).
function rotRect(name,cx,cy,ang,u0,v0,u1,v1,z0,z1,tex,list=world,kind='detail'){
 const c=Math.cos(ang),s=Math.sin(ang);
 prism(name,[[u0,v0],[u1,v0],[u1,v1],[u0,v1]].map(([u,v])=>[round(cx+u*c-v*s),round(cy+u*s+v*c)]),z0,z1,tex,list,kind);
}
function ent(keys,brushes=[]){entities.push({keys,brushes});}
// func_detail: decorative brushes kept out of the BSP/VIS cutting hull, still solid (zhlt_noclip unset).
function detailGroup(targetname){const brushes=[];ent({classname:'func_detail',targetname},brushes);return brushes;}
function hexRing(name,inner,outer,z0,z1,tex,cx=0,cy=0,ph=0,list=world,kind='world'){const a=hex(inner,cx,cy,ph),b=hex(outer,cx,cy,ph);for(let i=0;i<6;i++){const j=(i+1)%6;prism(name+i,[a[i],b[i],b[j],a[j]],z0,z1,tex,list,kind);}}
function clip(poly,a,b,inside){
 const val=p=>(b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]);const out=[];
 for(let i=0;i<poly.length;i++){const p=poly[i],q=poly[(i+1)%poly.length],vp=val(p),vq=val(q),ip=inside?vp>=-1e-7:vp<=1e-7,iq=inside?vq>=-1e-7:vq<=1e-7;if(ip)out.push(p);if(ip!==iq){const t=vp/(vp-vq);out.push(p.map((v,k)=>round(v+(q[k]-v)*t)));}}
 return out.filter((p,i)=>i===0||Math.hypot(p[0]-out[i-1][0],p[1]-out[i-1][1])>.01);
}
function outsideHex(name,r,z0,z1,tex){let remain=rect(-1024,-1024,1024,1024);const h=hex(r);for(let i=0;i<6;i++){const cut=clip(remain,h[i],h[(i+1)%6],false);if(cut.length>=3)prism(name+i,cut,z0,z1,tex);remain=clip(remain,h[i],h[(i+1)%6],true);}}
// Permanent enclosure survives opening every lid; lower shell reaches the final hall.
box('shell_bottom',[-1024,-1024,-2624],[1024,1024,-2592],T.stone);
box('shell_west',[-1056,-1056,-2592],[-1024,1056,1184],'sky');
box('shell_east',[1024,-1056,-2592],[1056,1056,1184],'sky');
box('shell_south',[-1024,-1056,-2592],[1024,-1024,1184],'sky');
box('shell_north',[-1024,1024,-2592],[1024,1056,1184],'sky');
box('shell_top',[-1024,-1024,1152],[1024,1024,1184],'sky');
outsideHex('terrain',672,-352,48,T.ground);
// Clean dirt working ring, wheat starts at R640 and runs to the fence/shell.
hexRing('field_dirt',400,640,48,64,T.dirt);
outsideHex('field_wheat',640,48,64,T.ground);
// Stage 1 lid and relay keep their original names.
const lid=[];prism('reward_lid',hex(400),48,64,T.wood,lid,'lid');
ent({classname:'func_breakable',targetname:'seno_reward_lid',spawnflags:'1',health:'1',material:'1',explodemagnitude:'0',renderamt:'255'},lid);
ent({classname:'trigger_relay',targetname:'seno_finish',target:'seno_reward_lid',triggerstate:'1'});
// Room 2 (hayloft trial): floor ring, flush breakable lid, barn walls, hayloft dressing.
hexRing('room2_floor',400,640,-528,-512,T.dirt);
const lid2=[];
prism('reward_lid_2',hex(400),-528,-512,T.wood,lid2,'lid');
// Underside lining for room 3: shares the lid's bottom plane, R<400 only.
prism('reward_lid_2_panel',hex(400),-532,-528,T.stone,lid2,'lid');
ent({classname:'func_breakable',targetname:'seno_reward_lid_2',spawnflags:'1',health:'1',material:'1',explodemagnitude:'0',renderamt:'255'},lid2);
ent({classname:'trigger_relay',targetname:'seno_finish_2',target:'seno_reward_lid_2',triggerstate:'1'});
hexRing('room2_stone_base',640,672,-528,-512,T.stone);
hexRing('room2_wall',640,672,-512,48,T.barn);
// Decorative ceiling beam ring: func_detail, keeps the barn silhouette without cutting VIS.
const room2Trim=detailGroup('d_room2_trim');
hexRing('room2_ring_beam',612,640,32,48,T.beam,0,0,0,room2Trim,'detail');
// Barn ceiling under the wheat field; R<400 stays open for the stage-1 lid.
hexRing('room2_ceiling',400,640,44,48,T.barn);
const room2Timber=detailGroup('d_room2_timber');
const room2Dressing=detailGroup('d_room2_dressing');
for(const a of [0,Math.PI/3,2*Math.PI/3]){
 const c=Math.cos(a),s=Math.sin(a);
 const p=[[-12,-620],[12,-620],[12,620],[-12,620]].map(([u,v])=>[round(u*c-v*s),round(u*s+v*c)]);
 // Timber runs along (v) => (-s,c); keep U on the plank grain for the flat faces.
 const axis=`[ ${round(-s)} ${round(c)} 0 0 ] [ ${round(c)} ${round(s)} 0 0 ]`;
 prism('room2_beam_'+round(a*180/Math.PI),p,32,48,T.beam,room2Timber,'detail',1,axis);
}
for(let i=0;i<6;i++){
 const a=i*Math.PI/3,x=round(600*Math.cos(a)),y=round(600*Math.sin(a));
 box('room2_post_'+i,[x-14,y-14,-512],[x+14,y+14,48],T.beam,room2Timber,'detail');
}
for(let i=0;i<6;i++){
 const a=(i+.5)*Math.PI/3,x=round(520*Math.cos(a)),y=round(520*Math.sin(a));
 box('room2_hay_'+i,[x-24,y-24,-512],[x+24,y+24,-464],T.hay,room2Dressing,'detail');
 if(i%2===0)box('room2_hay_top_'+i,[x-18,y-18,-464],[x+18,y+18,-428],T.hay,room2Dressing,'detail');
}
for(let i=0;i<6;i++){
 const a=(i+.5)*Math.PI/3,x=round(460*Math.cos(a)),y=round(460*Math.sin(a));
 box('room2_lamp_'+i,[x-8,y-8,24],[x+8,y+8,32],T.gold,room2Dressing,'detail');
 ent({classname:'light',origin:`${x} ${y} 8`,_light:'255 214 150 190'});
}
// Four warm side lights for the stage-2 hay stack: one per flat side, outside the bale
// volume (stack is +-192) at mid-height, so the stack is lit from the sides, not only
// from above. The six ceiling lamps and their count stay untouched.
for(const deg of [0,90,180,270]){
 const a=deg*Math.PI/180,x=round(310*Math.cos(a)),y=round(310*Math.sin(a));
 ent({classname:'light',origin:`${x} ${y} -264`,_light:'255 196 128 340'});
}
// Room 3 (mill basement) below room 2: ring floor, own breakable lid over the final hall.
hexRing('room3_floor',400,640,-1104,-1088,T.tile);
const lid3=[];
prism('reward_lid_3',hex(400),-1104,-1088,T.stone,lid3,'lid');
// Underside lining for the cave (room 4): shares the lid's bottom plane, R<400 only.
prism('reward_lid_3_panel',hex(400),-1108,-1104,T.rock,lid3,'lid');
ent({classname:'func_breakable',targetname:'seno_reward_lid_3',spawnflags:'1',health:'1',material:'1',explodemagnitude:'0',renderamt:'255'},lid3);
ent({classname:'trigger_relay',targetname:'seno_finish_3',target:'seno_reward_lid_3',triggerstate:'1'});
hexRing('room3_stone_base',640,672,-1136,-1088,T.stone);
hexRing('room3_tile_wall',640,672,-1088,-528,T.tile);
hexRing('room3_ceiling',400,640,-532,-528,T.stone);
// Room 4 (deep cave) between the mill basement and the final hall.
hexRing('room4_floor',400,640,-1680,-1664,T.rock);
const lid4=[];
prism('reward_lid_4',hex(400),-1680,-1664,T.rock,lid4,'lid');
// Underside lining for the hell room (room 5): shares the lid's bottom plane, R<400 only.
prism('reward_lid_4_panel',hex(400),-1684,-1680,T.hell,lid4,'lid');
ent({classname:'func_breakable',targetname:'seno_reward_lid_4',spawnflags:'1',health:'1',material:'1',explodemagnitude:'0',renderamt:'255'},lid4);
ent({classname:'trigger_relay',targetname:'seno_finish_4',target:'seno_reward_lid_4',triggerstate:'1'});
// Wall spans -1680..-1136: butts the room-4 floor bottom and the room-3 stone base, no overlap.
hexRing('room4_wall',640,672,-1680,-1136,T.rock);
hexRing('room4_ceiling',400,640,-1108,-1104,T.rock);
// Room 5 (hell) below room 4: lava channel cut into the floor ring at R580..620.
hexRing('room5_floor_in',400,580,-2256,-2240,T.hell);
hexRing('room5_floor_out',620,640,-2256,-2240,T.hell);
hexRing('room5_lava',580,620,-2256,-2244,T.lava);
const lid5=[];
prism('reward_lid_5',hex(400),-2256,-2240,T.hell,lid5,'lid');
// Underside lining for the final hall: shares the lid's bottom plane, R<400 only.
prism('reward_lid_5_panel',hex(400),-2260,-2256,T.stone,lid5,'lid');
ent({classname:'func_breakable',targetname:'seno_reward_lid_5',spawnflags:'1',health:'1',material:'1',explodemagnitude:'0',renderamt:'255'},lid5);
ent({classname:'trigger_relay',targetname:'seno_finish_5',target:'seno_reward_lid_5',triggerstate:'1'});
// Wall bottom meets the room-6 wall top at -2256 (no overlap, no gap).
hexRing('room5_wall',640,672,-2256,-1680,T.hell);
hexRing('room5_ceiling',400,640,-1684,-1680,T.hell);
// Room 6 (final hall) under the room-5 lid: hex R640 floor top -2560, stone walls with
// two flush gold bands, ceiling formed by the room-5 floor underside plus the lid-5 stone panel.
prism('room6_floor_base',hex(640),-2592,-2576,T.stone);
prism('room6_floor',hex(640),-2576,-2560,T.stone);
hexRing('room6_wall_low',640,672,-2592,-2420,T.stone);
hexRing('room6_band_low',640,672,-2420,-2412,T.gold);
hexRing('room6_wall_mid',640,672,-2412,-2350,T.stone);
hexRing('room6_band_high',640,672,-2350,-2342,T.gold);
hexRing('room6_wall_high',640,672,-2342,-2256,T.stone);
// Stone lining ring so the outer ceiling annulus reads SN_STONE like the lid-5 panel (which is breakable).
hexRing('room6_ceiling_ring',400,640,-2260,-2256,T.stone);
// Central pedestal: hex R96, z -2560..-2480 (80 high); gold cap plate 4 units, top exactly -2480.
prism('room6_pedestal',hex(96),-2560,-2484,T.stone);
prism('room6_pedestal_plate',hex(96),-2484,-2480,T.gold);
// Short flight on one side only (NE hex edge), four 16-unit risers up to the pedestal top.
const r6A=hex(96)[0],r6B=hex(96)[1],r6N=[Math.cos(Math.PI/6),Math.sin(Math.PI/6)];
for(let k=0;k<4;k++){
 const d0=k*20,d1=(k+1)*20;
 // CCW winding (same as rect/hex) keeps the brush normals outward.
 prism('room6_step_'+k,[[round(r6A[0]+r6N[0]*d0),round(r6A[1]+r6N[1]*d0)],[round(r6A[0]+r6N[0]*d1),round(r6A[1]+r6N[1]*d1)],[round(r6B[0]+r6N[0]*d1),round(r6B[1]+r6N[1]*d1)],[round(r6B[0]+r6N[0]*d0),round(r6B[1]+r6N[1]*d0)]],-2560,-2496-k*16,T.stone);
}
// Four fire bowls near the corners of the hall, warm light, no trial.
const room6Bowls=detailGroup('d_room6_bowls');
for(const [i,deg] of [45,135,225,315].entries()){
 const a=deg*Math.PI/180,x=round(510*Math.cos(a)),y=round(510*Math.sin(a));
 frustum('room6_bowl_stem_'+i,x,y,12,9,-2560,-2496,T.stone,room6Bowls,'detail',8);
 prism('room6_bowl_rim_'+i,disc(16,x,y,8),-2496,-2486,T.gold,room6Bowls,'detail');
 prism('room6_bowl_fire_'+i,disc(8,x,y,8),-2486,-2480,T.lava,room6Bowls,'detail');
 ent({classname:'light',origin:`${x} ${y} -2464`,_light:'255 150 70 230'});
}
ent({classname:'light',origin:'0 0 -2400',_light:'255 226 190 60'});
// Mill-basement dressing: millstones, barrels, sack stacks, grain chute, crates, pendant lamps.
// Everything stands on the ring floor (top -1088), outside hex R470, clear of the stage-3 stack.
const room3Mill=detailGroup('d_room3_mill');
const room3Store=detailGroup('d_room3_store');
const R3F=-1088;
function r3Quad(cx,cy,a,u0,u1,v0,v1){const c=Math.cos(a),s=Math.sin(a);return [[u0,v0],[u1,v0],[u1,v1],[u0,v1]].map(([u,v])=>[round(cx+u*c-v*s),round(cy+u*s+v*c)]);}
function barrel(name,deg,r,h,list){
 const a=deg*Math.PI/180,cx=round(r*Math.cos(a)),cy=round(r*Math.sin(a));
 prism(name,disc(26,cx,cy,12),R3F,R3F+h,T.wood,list,'detail');
 prism(name+'_hoop_lo',disc(27.5,cx,cy,12),R3F+8,R3F+14,T.trim,list,'detail');
 prism(name+'_hoop_hi',disc(27.5,cx,cy,12),R3F+h-14,R3F+h-8,T.trim,list,'detail');
}
function sackPile(name,cx,cy,deg,list){
 const a=deg*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
 const put=(suffix,u,v,z0,h)=>{const x=round(cx+u*c-v*s),y=round(cy+u*s+v*c);prism(name+suffix,r3Quad(x,y,a,-20,20,-15,15),z0,z0+h,T.sack,list,'detail');};
 [[-26,2],[0,-20],[26,4]].forEach(([u,v],i)=>put('_b'+i,u,v,R3F,26));
 [[-12,-8],[14,10]].forEach(([u,v],i)=>put('_t'+i,u,v,R3F+26,26));
}
// Plain millstone by the north wall; grooved second stone (8 raised ribs = radial grooves).
prism('room3_millstone_a',disc(62,0,478,20),R3F,R3F+30,T.stone,room3Mill,'detail');
const msB=[-397,-229];
prism('room3_millstone_b',disc(40,msB[0],msB[1],20),R3F,R3F+30,T.stone,room3Mill,'detail');
for(let i=0;i<8;i++){
 const a=i*Math.PI/4;
 prism('room3_millstone_b_rib'+i,r3Quad(msB[0],msB[1],a,12,34,-3.5,3.5),R3F+30,R3F+34,T.stone,room3Mill,'detail');
}
// Grain chute from the south-west wall (r552) to the grooved millstone (r500).
const chuteA=210*Math.PI/180,chuteC=[round(526*Math.cos(chuteA)),round(526*Math.sin(chuteA))];
prism('room3_grain_chute',r3Quad(chuteC[0],chuteC[1],chuteA,-26,26,-22,22),R3F,R3F+8,T.wood,room3Mill,'detail');
prism('room3_grain_chute_rail_a',r3Quad(chuteC[0],chuteC[1],chuteA,-26,26,-22,-16),R3F+8,R3F+20,T.wood,room3Mill,'detail');
prism('room3_grain_chute_rail_b',r3Quad(chuteC[0],chuteC[1],chuteA,-26,26,16,22),R3F+8,R3F+20,T.wood,room3Mill,'detail');
prism('room3_grain_chute_fill',r3Quad(chuteC[0],chuteC[1],chuteA,-24,24,-14,14),R3F+8,R3F+10,T.grain,room3Store,'detail');
// Five coopered barrels along the north-east wall.
for(const [i,[deg,r,h]] of [[0,570,60],[15,535,64],[30,515,56],[45,530,62],[60,570,58]].entries())barrel('room3_barrel_'+i,deg,r,h,room3Store);
// Two sack stacks against the walls (west and south).
sackPile('room3_sacks_a',-420,243,60,room3Store);
sackPile('room3_sacks_b',0,-485,0,room3Store);
// Four crates of different sizes.
box('room3_crate_0',[-292,452,R3F],[-252,492,R3F+40],T.wood,room3Store,'detail');
box('room3_crate_1',[-280,452,R3F+40],[-252,480,R3F+68],T.wood,room3Store,'detail');
box('room3_crate_2',[-296,-490,R3F],[-248,-454,R3F+30],T.wood,room3Store,'detail');
box('room3_crate_3',[267,-498,R3F],[293,-472,R3F+26],T.wood,room3Store,'detail');
for(const a of [0,Math.PI/3,2*Math.PI/3]){
 const c=Math.cos(a),s=Math.sin(a);
 const p=[[-12,-620],[12,-620],[12,620],[-12,620]].map(([u,v])=>[round(u*c-v*s),round(u*s+v*c)]);
 prism('room3_beam_'+round(a*180/Math.PI),p,-548,-532,T.beam,room3Mill,'detail');
}
// Grain spills on the floor (flat, do not block the ring).
for(const [i,[x,y]] of [[120,420],[-260,380],[300,-300],[-120,-440],[-330,-300]].entries()){
 prism('room3_grain_'+i,disc(24,x,y,10),R3F,R3F+2,T.grain,room3Store,'detail');
}
// Three pendant lamps: chain from the ceiling, gold shade, bulb and warm light.
for(const [i,deg] of [30,150,270].entries()){
 const a=deg*Math.PI/180,x=round(470*Math.cos(a)),y=round(470*Math.sin(a));
 box('room3_lamp_chain_'+i,[x-4,y-4,-566],[x+4,y+4,-532],T.trim,room3Mill,'detail');
 frustum('room3_lamp_shade_'+i,x,y,26,9,-584,-562,T.gold,room3Mill,'detail',8);
 prism('room3_lamp_bulb_'+i,disc(7,x,y,8),-590,-584,T.gold,room3Mill,'detail');
 ent({classname:'light',origin:`${x} ${y} -596`,_light:'255 205 150 200'});
}
// Cave dressing: stalagmites/stalactites/boulders in one group, crystal druses in another.
const room4Cave=detailGroup('d_room4_cave');
const room4Crystal=detailGroup('d_room4_crystal');
// Hex ring is not a circle: apothem at 30+60k is 554, so wall decor keeps <=550 from origin.
// All stone formations are faceted 5..7-gon prisms with varied radii and a small rotation.
const stalagmites=[[0,585,16,150],[60,585,13,110],[120,585,16,190],[180,585,12,95],[240,585,14,130],[300,585,15,170],[30,500,11,80],[150,500,13,140],[270,500,12,105]];
for(const [i,[deg,r,rad,h]] of stalagmites.entries()){
 const a=deg*Math.PI/180,x=round(r*Math.cos(a)),y=round(r*Math.sin(a));
 faceted('room4_stalagmite_'+i,x,y,rad,rad*0.25,-1664,-1664+h,T.rock,room4Cave,5+i%3,i*0.41,0.16);
}
const stalactites=[[20,470,26,140],[70,470,22,120],[120,470,28,150],[170,470,20,110],[220,470,24,130],[270,470,26,145],[320,470,22,100]];
for(const [i,[deg,r,rad,len]] of stalactites.entries()){
 const a=deg*Math.PI/180,x=round(r*Math.cos(a)),y=round(r*Math.sin(a));
 faceted('room4_stalactite_'+i,x,y,2,rad,-1108-len,-1108,T.rock,room4Cave,5+i%3,i*0.37+0.2,0.13);
}
const boulders=[[15,525,26,44],[75,525,28,52],[135,525,22,36],[195,525,26,48],[255,525,24,40]];
for(const [i,[deg,r,rad,h]] of boulders.entries()){
 const a=deg*Math.PI/180,x=round(r*Math.cos(a)),y=round(r*Math.sin(a));
 faceted('room4_boulder_'+i,x,y,rad,rad*0.84,-1664,-1664+h,T.rock,room4Cave,5+i%3,i*0.55,0.18);
}
// Six wall torches, one per hex face normal: wood bracket, gold bowl, lava flame, warm light.
const room4Torches=detailGroup('d_room4_torches');
for(const [i,deg] of [30,90,150,210,270,330].entries()){
 const a=deg*Math.PI/180,c=Math.cos(a),s=Math.sin(a),wx=round(554*c),wy=round(554*s);
 rotRect('room4_torch_bracket_'+i,wx,wy,a,-32,-7,-3,7,-1510,-1496,T.wood,room4Torches);
 frustum('room4_torch_bowl_'+i,round(528*c),round(528*s),7,13,-1496,-1484,T.gold,room4Torches,'detail',8);
 frustum('room4_torch_flame_'+i,round(528*c),round(528*s),8,2,-1484,-1462,T.lava,room4Torches,'detail',6);
 ent({classname:'light',origin:`${round(514*c)} ${round(514*s)} -1448`,_light:'255 168 92 230'});
}
for(const [i,deg] of [90,210,330].entries()){
 const a=deg*Math.PI/180,x=round(500*Math.cos(a)),y=round(500*Math.sin(a));
 for(const [j,[dx,dy,rad,h]] of [[0,0,9,80],[-12,6,7,58],[10,-8,8,68],[-4,-12,6,46]].entries())
  frustum('room4_crystal_'+i+'_'+j,x+dx,y+dy,rad,1.5,-1664,-1664+h,T.crystal,room4Crystal,'detail',5);
 ent({classname:'light',origin:`${x} ${y} -1578`,_light:'150 205 255 255'});
}
for(const deg of [45,135,225,315]){const a=deg*Math.PI/180,x=round(470*Math.cos(a)),y=round(470*Math.sin(a));ent({classname:'light',origin:`${x} ${y} -1404`,_light:'120 180 255 210'});}
// Hell dressing: obsidian spikes and fire bowls seated in the lava channel (two groups).
const room5Spikes=detailGroup('d_room5_spikes');
const room5Bowls=detailGroup('d_room5_bowls');
const spikes=[[0,555,12,90],[60,555,14,130],[120,555,11,110],[180,555,13,140],[240,555,12,100],[300,555,10,120],[30,485,10,80]];
for(const [i,[deg,r,rad,h]] of spikes.entries()){
 const a=deg*Math.PI/180,x=round(r*Math.cos(a)),y=round(r*Math.sin(a));
 frustum('room5_spike_'+i,x,y,rad,1.5,-2240,-2240+h,T.hell,room5Spikes,'detail',6);
}
// Bowls stand on the lava chord band (hex 580..620 is 502..537 at edge-midpoint angles).
for(const [i,deg] of [30,90,150,210].entries()){
 const a=deg*Math.PI/180,x=round(520*Math.cos(a)),y=round(520*Math.sin(a));
 frustum('room5_bowl_stem_'+i,x,y,12,9,-2244,-2180,T.hell,room5Bowls,'detail',8);
 prism('room5_bowl_rim_'+i,disc(14,x,y,8),-2180,-2168,T.hell,room5Bowls,'detail');
 prism('room5_bowl_fire_'+i,disc(7,x,y,8),-2168,-2162,T.lava,room5Bowls,'detail');
 ent({classname:'light',origin:`${x} ${y} -2130`,_light:'255 120 50 230'});
}
for(const deg of [0,120,240]){const a=deg*Math.PI/180,x=round(430*Math.cos(a)),y=round(430*Math.sin(a));ent({classname:'light',origin:`${x} ${y} -2020`,_light:'255 60 40 130'});}
// Room 5 wall breach on the south-east face (330 deg): an eight-facet ragged mouth over a
// lava back wall, seven rock reveal faces, a molten stream down the wall and a pool that
// bridges the lava ring channel.
const room5Breach=detailGroup('d_room5_breach');
const brA=330*Math.PI/180,brC=[Math.cos(brA),Math.sin(brA)],brT=[-Math.sin(brA),Math.cos(brA)],brW=[round(554*brC[0]),round(554*brC[1])];
const brXY=(u,v)=>[round(brW[0]+u*brC[0]+v*brT[0]),round(brW[1]+u*brC[1]+v*brT[1])];
const brP=(u,v,z)=>[...brXY(u,v),z];
// Convex [v,z] contour extruded u0..u1 along the wall normal (u grows toward the wall).
function brSlab(name,pts,u0,u1,tex,list=room5Breach,kind='detail'){
 const lo=pts.map(([v,z])=>brP(u0,v,z)),hi=pts.map(([v,z])=>brP(u1,v,z));
 const faces=[face(lo[0],lo[1],lo[2],tex),face(hi[0],hi[2],hi[1],tex)];
 pts.forEach((p,i)=>faces.push(face(lo[i],hi[i],hi[(i+1)%pts.length],tex)));
 list.push('{\n'+faces.join('\n')+'\n}');
 const zs=pts.map(p=>p[1]),vs=pts.map(p=>p[0]);
 solids.push({name,poly:[brXY(u0,Math.min(...vs)),brXY(u1,Math.min(...vs)),brXY(u1,Math.max(...vs)),brXY(u0,Math.max(...vs))],z0:Math.min(...zs),z1:Math.max(...zs),kind});
}
// Ragged mouth: ~158 wide, 200 tall, eight slanted edges.
const brMouth=[[-62,-2132],[42,-2140],[78,-2112],[70,-2030],[48,-1948],[-34,-1940],[-80,-2006],[-74,-2098]];
const brCtr=[brMouth.reduce((a,p)=>a+p[0],0)/brMouth.length,brMouth.reduce((a,p)=>a+p[1],0)/brMouth.length];
// Lava back wall 16..24 in from the wall plane, slightly oversized so no wall sliver shows.
const brBack=brMouth.map(([v,z])=>[round(brCtr[0]+(v-brCtr[0])*1.1),round(brCtr[1]+(z-brCtr[1])*1.1)]);
brSlab('room5_breach_back',brBack,-24,-16,T.lava);
// Seven rock reveal faces, each mouth edge carried 38..56 out with an edge normal, no bottom lip.
const brDepth=[0,38,52,45,40,56,48,43];
for(let i=1;i<brMouth.length;i++){
 const p=brMouth[i],q=brMouth[(i+1)%brMouth.length],dx=q[0]-p[0],dy=q[1]-p[1],len=Math.hypot(dx,dy),ux=dx/len,uy=dy/len,d=brDepth[i],e=7;
 brSlab('room5_breach_rim_'+i,[[p[0]-ux*e+uy*d,p[1]-uy*e-ux*d],[q[0]+ux*e+uy*d,q[1]+uy*e-ux*d],q,p],-38,-1,T.rock);
}
// Molten stream: 63 wide at the lip, 96 at the floor.
brSlab('room5_breach_stream',[[-33,-2120],[-48,-2237],[48,-2237],[30,-2114]],-14,-3,T.lava);
// Pool radius 120, tangent to the wall, spanning the R580..620 lava channel.
const brPool=brP(-120,0,-2240);
prism('room5_breach_pool',disc(120,brPool[0],brPool[1],20),-2240,-2237,T.lava,world,'world');
for(const p of [brP(-30,-22,-2004),brP(-28,26,-2072)])ent({classname:'light',origin:p.join(' '),_light:'255 132 48 235'});
// Hanging rock shards under the room-5 ceiling, varied lengths.
const room5Hang=detailGroup('d_room5_hang');
const hang=[[30,470,16,150],[70,505,13,120],[110,500,18,180],[150,435,10,100],[190,520,15,160],[230,535,12,130],[270,455,11,110],[310,510,17,170],[350,540,9,90],[90,480,14,140]];
for(const [i,[deg,r,rad,len]] of hang.entries()){
 const a=deg*Math.PI/180,x=round(r*Math.cos(a)),y=round(r*Math.sin(a));
 faceted('room5_hang_'+i,x,y,1.5,rad,-1684-len,-1684,T.hell,room5Hang,5+i%2,i*0.63,0.12);
}
// Gumno floor stays whole; the stone teleport podium stands on top of it.
// Thin decorative rings and trims: func_detail, still solid, no VIS splits.
const gumnoDetail=detailGroup('d_gumno_rings');
hexRing('gumno',400,580,64,66,T.dirt,0,0,0,gumnoDetail,'detail');
hexRing('gumno_trim',400,408,64,68,T.trim,0,0,0,gumnoDetail,'detail');
hexRing('outer_gumno_trim',572,580,66,70,T.wood,0,0,0,gumnoDetail,'detail');
// v5: the four dirt approach strips (path_w/path_e/path_s/path_n) are gone; approach is on ground.
// The gumno, its rings and the podium apron keep their geometry; the thin rings are func_detail.
// Wooden perimeter fence at +-960: posts every 256 and two rails, no walls.
const fenceDetail=detailGroup('d_fence');
for(const sign of [-1,1]){
 for(const z of [112,152]){
  box('rail_x'+sign+'_'+z,[sign<0?-968:952,-960,z],[sign<0?-952:968,960,z+12],T.wood,fenceDetail,'detail');
  box('rail_y'+sign+'_'+z,[-960,sign<0?-968:952,z],[960,sign<0?-952:968,z+12],T.wood,fenceDetail,'detail');
 }
 for(let t=-896;t<=896;t+=256){
  box('post_x'+sign+'_'+t,[sign*960-14,t-14,64],[sign*960+14,t+14,184],T.wood,fenceDetail,'detail');
  box('post_y'+sign+'_'+t,[t-14,sign*960-14,64],[t+14,sign*960+14,184],T.wood,fenceDetail,'detail');
 }
}
for(const x of [-960,960])for(const y of [-960,960])box('post_corner_'+x+'_'+y,[x-14,y-14,64],[x+14,y+14,184],T.wood,fenceDetail,'detail');
// Stone teleport podium in the free south-west corner of the field, centred on (-560,-560).
// Whole podium moved as one: hex base, gold plate with trim inlay, steps on the north-east
// face (rises 5/3/4) heading toward the map centre, five standing stones with gold caps, lamps.
// The hex is turned by 15 degrees so one face normal points exactly at the map centre (45 deg);
// the stair is then cut square to that face and heads north-east, rises 5/3/4.
const tpC=[-560,-560],tpA=Math.PI/4,tpPh=Math.PI/12;
prism('teleport_base',hex(104,tpC[0],tpC[1],tpPh),64,72,T.stone);
prism('teleport_plate',hex(88,tpC[0],tpC[1],tpPh),72,76,T.gold);
hexRing('teleport_inlay',76,88,76,77,T.trim,tpC[0],tpC[1],tpPh);
rotRect('teleport_step_1',tpC[0],tpC[1],tpA,126,-44,158,44,64,69,T.stone,world,'world');
rotRect('teleport_step_2',tpC[0],tpC[1],tpA,90.1,-34,126,34,64,72,T.stone,world,'world');
// Stone courtyard under the podium and its steps: hex R136 on the same phase as the base,
// bottom flush with the wheat top (64), top 2 units proud, so the steps and base sit on stone.
prism('teleport_courtyard',hex(136,tpC[0],tpC[1],tpPh),64,66,T.stone);
// Five standing stones; the 45-degree (NE, approach) slot stays empty.
for(const deg of [105,165,225,285,345]){
 const a=deg*Math.PI/180,x=round(tpC[0]+120*Math.cos(a)),y=round(tpC[1]+120*Math.sin(a));
 box('teleport_stone_'+deg,[x-8,y-8,64],[x+8,y+8,120],T.stone);
 box('teleport_stone_cap_'+deg,[x-10,y-10,120],[x+10,y+10,128],T.gold);
}
// Only the centre of the plate teleports: 48x48 footprint, from the plate top up.
const tp=[];box('teleport_trigger',[-584,-584,76],[-536,-536,140],'AAATRIGGER',tp,'trigger');
ent({classname:'trigger_teleport',targetname:'seno_teleport',target:'seno_tp_dest',spawnflags:'0'},tp);
for(const p of [[-500,-620,150],[-620,-500,150]])ent({classname:'light',origin:p.join(' '),_light:'255 196 120 220'});
for(const p of [[0,0,520],[120,120,520],[-120,120,520],[120,-120,520],[-120,-120,520]])ent({classname:'info_teleport_destination',targetname:'seno_tp_dest',origin:p.join(' '),angles:'0 0 0'});
// Windmill moved near the stack: barn tower, real door, windows, layered roof and sails.
prism('mill_base',hex(108,600,600),64,80,T.stone);
prism('mill_plinth',hex(100,600,600),80,96,T.stone);
prism('mill_tower',hex(72,600,600),96,384,T.barn);
const millDetail=detailGroup('d_mill');
prism('mill_eave',hex(84,600,600),376,392,T.beam,millDetail,'detail');
prism('mill_cap',hex(92,600,600),392,408,T.trim,millDetail,'detail');
prism('mill_roof_low',hex(84,600,600),408,424,T.wood);
prism('mill_roof_mid',hex(60,600,600),424,440,T.wood);
prism('mill_roof_high',hex(32,600,600),440,452,T.wood);
box('mill_finial',[592,592,452],[608,608,472],T.gold,millDetail,'detail');
box('mill_threshold',[560,528,92],[640,550,96],T.stone,millDetail,'detail');
box('mill_door_jamb_l',[560,530,96],[568,546,224],T.trim,millDetail,'detail');
box('mill_door_jamb_r',[632,530,96],[640,546,224],T.trim,millDetail,'detail');
box('mill_door_lintel',[560,530,224],[640,546,236],T.trim,millDetail,'detail');
box('mill_door_leaf',[568,536,96],[632,544,224],T.door,millDetail,'detail');
box('mill_door_handle',[616,528,112],[624,536,128],T.gold,millDetail,'detail');
for(const [i,deg] of [30,150,210,330].entries()){
 const a=deg*Math.PI/180,r=63,x=round(600+r*Math.cos(a)),y=round(600+r*Math.sin(a));
 box('mill_window_frame_'+i,[x-16,y-8,240],[x+16,y+8,288],T.trim,millDetail,'detail');
 box('mill_window_dark_'+i,[x-12,y-10,244],[x+12,y+10,284],T.beam,millDetail,'detail');
}
box('mill_hub',[584,500,284],[616,528,316],T.gold,millDetail,'detail');
function verticalSail(name,poly,y0,y1,list=world,kind='world'){
 const low=poly.map(([x,z])=>[x,y0,z]),hi=poly.map(([x,z])=>[x,y1,z]);
 const faces=[face(low[0],low[2],low[1],T.wood),face(hi[0],hi[1],hi[2],T.wood)];
 poly.forEach((p,i)=>faces.push(face(low[i],hi[(i+1)%poly.length],hi[i],T.wood)));
 list.push('{\n'+faces.join('\n')+'\n}');
 const xs=poly.map(p=>p[0]),zs=poly.map(p=>p[1]);
 solids.push({name,poly:rect(Math.min(...xs),y0,Math.max(...xs),y1),z0:Math.min(...zs),z1:Math.max(...zs),kind});
}
for(let i=0;i<4;i++){
 const a=Math.PI/4+i*Math.PI/2,c=Math.cos(a),s=Math.sin(a);
 const at=(r,t)=>[round(600+r*c-t*s),round(300+r*s+t*c)];
 verticalSail('mill_sail'+i,[[24,-8],[176,-20],[176,20],[24,8]].map(([r,t])=>at(r,t)),504,512,millDetail,'detail');
 verticalSail('mill_sail_web'+i,[[40,-5],[168,-11],[168,11],[40,5]].map(([r,t])=>at(r,t)),512,516,millDetail,'detail');
 verticalSail('mill_sail_bar'+i,[[148,-22],[156,-22],[156,22],[148,22]].map(([r,t])=>at(r,t)),500,518,millDetail,'detail');
 verticalSail('mill_sail_brace'+i,[[52,-22],[60,-22],[60,22],[52,22]].map(([r,t])=>at(r,t)),500,518,millDetail,'detail');
}
// Hay cart near the stack: four spoked wheels (front/rear axle, both sides), plank bed, shafts, hay load.
const cartDetail=detailGroup('d_cart');
box('cart_axle',[426,-616,84],[614,-500,92],T.wood,cartDetail,'detail');
function wheel(name,cx,cz,y0,y1,rOuter,rInner,list=world,kind='world'){
 const seg=12;
 for(let i=0;i<seg;i++){
  const a0=2*Math.PI*i/seg,a1=2*Math.PI*(i+1)/seg,p=(r,a)=>[round(cx+r*Math.cos(a)),round(cz+r*Math.sin(a))];
  prismY(name+'_rim'+i,[p(rOuter,a0),p(rOuter,a1),p(rInner,a1),p(rInner,a0)],y0,y1,T.trim,list,1,kind);
 }
 for(const deg of [0,60,120]){
  const a=deg*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
  const rank=[[-rInner,-2],[rInner,-2],[rInner,2],[-rInner,2]].map(([u,v])=>[round(cx+u*c-v*s),round(cz+u*s+v*c)]);
  prismY(name+'_spoke'+deg,rank,y0,y1,T.wood,list,1,kind);
 }
 prismY(name+'_hub',Array.from({length:12},(_,i)=>[round(cx+5*Math.cos(i*Math.PI/6)),round(cz+5*Math.sin(i*Math.PI/6))]),y0-1,y1+1,T.gold,list,1,kind);
}
wheel('cart_wheel_front_s',442,90,-622,-614,26,17,cartDetail,'detail');
wheel('cart_wheel_rear_s',598,90,-622,-614,26,17,cartDetail,'detail');
wheel('cart_wheel_front_n',442,90,-502,-494,26,17,cartDetail,'detail');
wheel('cart_wheel_rear_n',598,90,-502,-494,26,17,cartDetail,'detail');
for(let i=0;i<6;i++){const y0=-606+i*16;box('cart_plank_'+i,[420,y0,96],[620,y0+12,108],T.wood,cartDetail,'detail');}
box('cart_side_s',[420,-614,108],[620,-602,144],T.wood,cartDetail,'detail');
box('cart_side_n',[420,-514,108],[620,-502,144],T.wood,cartDetail,'detail');
box('cart_end_w',[420,-614,108],[432,-502,144],T.wood,cartDetail,'detail');
box('cart_end_e',[608,-614,108],[620,-502,144],T.wood,cartDetail,'detail');
box('cart_shaft_s',[620,-606,86],[736,-596,98],T.wood,cartDetail,'detail');
box('cart_shaft_n',[620,-520,86],[736,-510,98],T.wood,cartDetail,'detail');
box('cart_hay_low',[432,-598,108],[608,-518,140],T.hay,cartDetail,'detail');
box('cart_hay_high',[448,-586,140],[592,-530,158],T.hay,cartDetail,'detail');
const scarecrowDetail=detailGroup('d_scarecrow');
box('scarecrow_post',[-568,512,64],[-552,528,224],T.wood,scarecrowDetail,'detail');
box('scarecrow_arms',[-624,512,164],[-496,528,180],T.wood,scarecrowDetail,'detail');
box('scarecrow_head',[-580,500,204],[-540,540,244],T.ground,scarecrowDetail,'detail');
box('scarecrow_hat',[-592,488,240],[-528,552,248],T.wood,scarecrowDetail,'detail');
// ---------------------------------------------------------------------------
// Photo panels: 21 YZ_PHOTO_* prints plus the YZ_CREDITS plaque, one thin
// 1-unit brush each in a single func_detail group (d_photos). The world hull,
// the 192 world brush count and VIS are untouched. A hex wall face is the R640
// chord, apothem 640*cos30 = 554.26; each panel centre sits at radius 552.5
// (552..553), leaving a 1.26-unit gap so nothing z-fights.
const photos=detailGroup('d_photos');
const PHOTO_PX=256,WALL_SCALE=192/PHOTO_PX,HEAD_SCALE=40/PHOTO_PX;
const num=x=>Number(x.toFixed(6));
// Valve 220 face with fully explicit U/V axes, texel offsets and scales.
function tface(p,q,r,tex,U,V,uo,vo,su,sv){
 const axis=`[ ${num(U[0])} ${num(U[1])} ${num(U[2])} ${num(uo)} ] [ ${num(V[0])} ${num(V[1])} ${num(V[2])} ${num(vo)} ]`;
 return [p,q,r].map(v=>'( '+v.map(round).join(' ')+' )').join(' ')+` ${tex} ${axis} 0 ${num(su)} ${num(sv)}`;
}
// Radial wall panel. Local frame: u = outward wall normal, v = tangent. The u0
// face looks into the room and is the readable one: U = viewer right
// (sin a, -cos a), V = down (0,0,-1), so the image is upright and unmirrored.
function photoPanel(name,ang,h,z0,z1,tex){
 const c=Math.cos(ang),s=Math.sin(ang);
 const W=(u,v)=>[round(u*c-v*s),round(u*s+v*c)];
 const P=(u,v,z)=>{const [x,y]=W(u,v);return [x,y,z];};
 const lp=[[552,-h],[553,-h],[553,h],[552,h]];
 const lo=lp.map(([u,v])=>P(u,v,z0)),hi=lp.map(([u,v])=>P(u,v,z1));
 const U=[s,-c,0],V=[0,0,-1],uo=h/WALL_SCALE,vo=z1/WALL_SCALE;
 const faces=[
  face(lo[0],lo[1],lo[2],tex,WALL_SCALE),
  face(hi[0],hi[2],hi[1],tex,WALL_SCALE),
  face(lo[0],hi[0],hi[1],tex,WALL_SCALE),
  tface(lo[1],hi[1],hi[2],tex,[-s,c,0],V,uo,vo,WALL_SCALE,WALL_SCALE),
  face(lo[2],hi[2],hi[3],tex,WALL_SCALE),
  tface(lo[3],hi[3],hi[0],tex,U,V,uo,vo,WALL_SCALE,WALL_SCALE)
 ];
 photos.push('{\n'+faces.join('\n')+'\n}');
 solids.push({name,poly:lp.map(([u,v])=>W(u,v)),z0,z1,kind:'detail'});
}
// 40x40 print on the scarecrow head's south face, 1 unit in front of y=500.
// Seen from the teleport (south) the viewer looks north, so image right = +X.
function photoHead(name,x0,x1,y0,y1,z0,z1,tex){
 const lo=[[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0]];
 const hi=[[x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]];
 const V=[0,0,-1],vo=z1/HEAD_SCALE;
 const faces=[
  face(lo[0],lo[1],lo[2],tex,HEAD_SCALE),
  face(hi[0],hi[2],hi[1],tex,HEAD_SCALE),
  tface(lo[0],hi[0],hi[1],tex,[1,0,0],V,-x0/HEAD_SCALE,vo,HEAD_SCALE,HEAD_SCALE),
  face(lo[1],hi[1],hi[2],tex,HEAD_SCALE),
  tface(lo[2],hi[2],hi[3],tex,[-1,0,0],V,x1/HEAD_SCALE,vo,HEAD_SCALE,HEAD_SCALE),
  face(lo[3],hi[3],hi[0],tex,HEAD_SCALE)
 ];
 photos.push('{\n'+faces.join('\n')+'\n}');
 solids.push({name,poly:rect(x0,y0,x1,y1),z0,z1,kind:'detail'});
}
// [room, mid Z, [[face normal deg, texture suffix], ...]]
const wallPhotos=[
 [2,-232,[[30,'01'],[90,'02'],[210,'03'],[270,'04']]],
 [3,-808,[[30,'05'],[90,'06'],[210,'07'],[270,'08']]],
 [4,-1384,[[30,'09'],[90,'10'],[210,'11'],[270,'12']]],
 [5,-1960,[[30,'13'],[90,'14'],[210,'15'],[270,'16']]],
 [6,-2408,[[30,'17'],[90,'19'],[150,'CREDITS'],[210,'20'],[270,'21']]]
];
for(const [room,cz,items] of wallPhotos)for(const [deg,suffix] of items){
 const z0=cz-96,z1=cz+96;
 if(room===6&&(z0<-2560||z1>-2256))throw Error('Room 6 photo outside the hall');
 photoPanel('room'+room+'_photo_'+suffix,deg*Math.PI/180,96,z0,z1,'YZ_'+(suffix==='CREDITS'?'CREDITS':'PHOTO_'+suffix));
}
photoHead('scarecrow_photo_18',-580,-540,498,499,204,244,'YZ_PHOTO_18');
for(let side=0;side<4;side++)for(let i=0;i<8;i++){const t=-504+i*144,p=side===0?[t,-768,104]:side===1?[768,t,104]:side===2?[t,768,104]:[-768,t,104];ent({classname:'info_player_start',origin:p.join(' '),angle:String([90,180,270,0][side])});}
ent({classname:'light_environment',origin:'0 0 1000',angles:'-35 30 0',pitch:'-35',_light:'255 238 206 240',_ambient:'120 145 180 60'});
const keys={classname:'worldspawn',mapversion:'220',message:'Seno Wheat - golden harvest',skyname:'yz_senowheat',wad:'D:/mapa/mapa_seno/dist/cstrike/yz_seno_wheat.wad;D:/SteamLibrary/steamapps/common/Half-Life/valve/halflife.wad',MaxRange:'8192'};
const serialize=e=>'{\n'+Object.entries(e.keys).map(([k,v])=>`"${k}" "${v}"`).join('\n')+'\n'+e.brushes.join('\n')+'\n}';
const source='// Generated by map/generate_map.cjs; editable Valve 220 source.\n'+[{keys,brushes:world},...entities].map(serialize).join('\n')+'\n';
function intersects(s,b){if(s.z1<=b.min[2]||s.z0>=b.max[2])return false;const q=rect(b.min[0],b.min[1],b.max[0],b.max[1]);const axes=[[1,0],[0,1],...s.poly.map((p,i)=>{const n=s.poly[(i+1)%s.poly.length];return [n[1]-p[1],p[0]-n[0]];})];return axes.every(a=>{const p=s.poly.map(v=>v[0]*a[0]+v[1]*a[1]),r=q.map(v=>v[0]*a[0]+v[1]*a[1]);return Math.min(Math.max(...p),Math.max(...r))-Math.max(Math.min(...p),Math.min(...r))>.01;});}
// Convex-polygon vs convex-polygon volume overlap (strict: touching faces do not count).
function polyOverlap(a,b){
 if(a.z1<=b.z0+.05||a.z0>=b.z1-.05)return false;
 const axes=[];
 for(const poly of [a.poly,b.poly])for(let i=0;i<poly.length;i++){const p=poly[i],q=poly[(i+1)%poly.length];axes.push([p[1]-q[1],q[0]-p[0]]);}
 return axes.filter(([x,y])=>Math.abs(x)+Math.abs(y)>1e-6).every(ax=>{
  const pr=poly=>poly.map(v=>v[0]*ax[0]+v[1]*ax[1]),A=pr(a.poly),B=pr(b.poly);
  return Math.min(Math.max(...A),Math.max(...B))-Math.max(Math.min(...A),Math.min(...B))>.05;
 });
}
const hay=[],layerCounts=[];
for(let l=0;l<8;l++){const n=8-l;layerCounts[l]=0;for(let x=0;x<n;x++)for(let y=0;y<n;y++){hay.push({min:[(x-n/2)*48,(y-n/2)*48,64+l*48],max:[(x+1-n/2)*48,(y+1-n/2)*48,112+l*48]});layerCounts[l]++;}}
// Both world and func_detail brushes are solid for gameplay checks.
const staticSolids=solids.filter(s=>s.kind==='world'||s.kind==='detail');
const detailEnts=entities.filter(e=>e.keys.classname==='func_detail');
const detailBrushes=detailEnts.reduce((n,e)=>n+e.brushes.length,0);
if(detailBrushes!==solids.filter(s=>s.kind==='detail').length)throw Error('Detail solid mismatch');
for(const e of detailEnts)if(!e.brushes.length)throw Error('Empty func_detail '+e.keys.targetname);
for(const s of staticSolids)for(const h of hay)if(intersects(s,h))throw Error('Hay collision '+s.name);
const spawns=entities.filter(e=>e.keys.classname==='info_player_start');
for(const s of spawns){const p=s.keys.origin.split(' ').map(Number),h={min:[p[0]-16,p[1]-16,p[2]-36],max:[p[0]+16,p[1]+16,p[2]+36]};for(const b of staticSolids)if(intersects(b,h))throw Error('Blocked spawn '+p+' '+b.name);}
if(hay.length!==204||spawns.length!==32)throw Error('Count mismatch');
const named=n=>entities.filter(e=>e.keys.targetname===n);
for(const n of ['seno_finish','seno_finish_2','seno_finish_3','seno_finish_4','seno_finish_5'])if(named(n).filter(e=>e.keys.classname==='trigger_relay').length!==1)throw Error('Stage relay count mismatch '+n);
for(const n of ['seno_reward_lid','seno_reward_lid_2','seno_reward_lid_3','seno_reward_lid_4','seno_reward_lid_5'])if(named(n).filter(e=>e.keys.classname==='func_breakable').length!==1)throw Error('Lid count mismatch '+n);
// Every stage stack must be seated exactly on its own lid top.
for(const [name,base] of [['reward_lid',64],['reward_lid_2',-512],['reward_lid_3',-1088],['reward_lid_4',-1664],['reward_lid_5',-2240]]){const s=solids.find(v=>v.kind==='lid'&&v.name===name);if(!s||s.z1!==base)throw Error('Stack is not seated on lid '+name);}
// Rooms 4/5 must butt old walls without overlapping them (shared faces are fine).
const isNewRoom=s=>/^room[456]_/.test(s.name)||/^reward_lid_[45]$/.test(s.name);
const isOldRoomWall=s=>/^room[23]_/.test(s.name);
for(const a of solids.filter(isNewRoom))for(const b of solids.filter(isOldRoomWall))if(polyOverlap(a,b))throw Error('New room intersects old wall '+a.name+' / '+b.name);
// Decorative brushes must leave the R400..540 ring walkway clear in rooms 4 and 5.
const laneA=hex(400);
function laneHit(s,z0,z1,outer=540){const laneB=hex(outer);for(let i=0;i<6;i++){const j=(i+1)%6;if(polyOverlap(s,{poly:[laneA[i],laneB[i],laneB[j],laneA[j]],z0,z1}))return true;}return false;}
for(const s of solids.filter(s=>s.kind==='detail'&&s.name.startsWith('room4_')))if(laneHit(s,-1664,-1514))throw Error('Room 4 decor obstructs ring walk '+s.name);
for(const s of solids.filter(s=>s.kind==='detail'&&s.name.startsWith('room5_')))if(laneHit(s,-2240,-2090))throw Error('Room 5 decor obstructs ring walk '+s.name);
// Room 3 (mill basement): decor must miss the stage-3 stack box, the ring walk and the shells.
const room3Detail=s=>s.kind==='detail'&&s.name.startsWith('room3_');
for(const s of solids.filter(room3Detail))if(intersects(s,{min:[-280,-280,-1088],max:[280,280,-704]}))throw Error('Room 3 decor intersects stage stack '+s.name);
for(const s of solids.filter(room3Detail))if(s.z1>-1064&&laneHit(s,-1088,-988,470))throw Error('Room 3 decor obstructs ring walk '+s.name);
for(const s of solids.filter(room3Detail))if(!s.name.startsWith('room3_beam_')){
 for(const w of solids.filter(w=>w.kind==='world'&&w.name.startsWith('room3_')))if(polyOverlap(s,w))throw Error('Room 3 decor intersects shell '+s.name+' / '+w.name);
}
// Decoration may rest on floors/ceiling/lava but must not be embedded in the new room shells.
const newDetail=s=>s.kind==='detail'&&(s.name.startsWith('room4_')||s.name.startsWith('room5_'));
const newShell=s=>s.kind==='world'&&(s.name.startsWith('room4_')||s.name.startsWith('room5_'));
for(const s of solids.filter(newDetail))for(const w of solids.filter(newShell))if(polyOverlap(s,w))throw Error('New decor intersects room shell '+s.name+' / '+w.name);
// No new decoration inside the 204-bale stack volume of stages 4 and 5.
for(const base of [-1664,-2240])for(const s of solids.filter(s=>s.kind==='detail'&&(s.name.startsWith('room4_')||s.name.startsWith('room5_'))))if(intersects(s,{min:[-192,-192,base],max:[192,192,base+384]}))throw Error('New decor intersects stage stack '+s.name);
const teleports=entities.filter(e=>e.keys.classname==='trigger_teleport');
if(teleports.length!==1||teleports[0].keys.target!=='seno_tp_dest')throw Error('Teleport trigger mismatch');
const dests=named('seno_tp_dest').filter(e=>e.keys.classname==='info_teleport_destination');
if(dests.length!==5)throw Error('Teleport destination count mismatch '+dests.length);
for(const d of dests){const [x,y,z]=d.keys.origin.split(' ').map(Number);if(z<=448||Math.abs(x)>400||Math.abs(y)>400)throw Error('Bad teleport destination '+d.keys.origin);}
// Podium replaces the old flat pad; the gumno cut-out and arrows must be gone.
if(solids.some(s=>s.name.startsWith('teleport_pad')||s.name.startsWith('tp_arrow')))throw Error('Old flat teleport pad still present');
if(!solids.find(s=>s.name==='teleport_base')||!solids.find(s=>s.name==='teleport_plate'))throw Error('Teleport podium geometry missing');
const stoneCount=solids.filter(s=>/^teleport_stone_\d+$/.test(s.name)).length;
if(stoneCount!==5)throw Error('Teleport standing stone count mismatch '+stoneCount);
const bb=g=>{const xs=g.poly.map(p=>p[0]),ys=g.poly.map(p=>p[1]);return [Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)];};
const tpBase=solids.find(s=>s.name==='teleport_base'),tpPlate=solids.find(s=>s.name==='teleport_plate'),tpInlay=solids.find(s=>s.name.startsWith('teleport_inlay'));
const baseBB=bb(tpBase),plateBB=bb(tpPlate);
const cxB=(baseBB[0]+baseBB[2])/2,cyB=(baseBB[1]+baseBB[3])/2;
if(Math.abs(cxB+560)>.01||Math.abs(cyB+560)>.01)throw Error('Teleport podium is not centred on (-560,-560): '+cxB+','+cyB);
const tpRad=g=>g.poly.map(p=>Math.hypot(p[0]+560,p[1]+560));
if(tpRad(tpBase).some(r=>Math.abs(r-104)>.01)||tpRad(tpPlate).some(r=>Math.abs(r-88)>.01))throw Error('Teleport podium radius wrong');
if(Math.abs((plateBB[0]+plateBB[2])/2+560)>.01||Math.abs((plateBB[1]+plateBB[3])/2+560)>.01)throw Error('Teleport podium plate not centred');
if(!tpInlay)throw Error('Teleport inlay missing');
const trigSolid=solids.find(s=>s.name==='teleport_trigger');
if(!trigSolid)throw Error('Teleport trigger brush missing');
const trigBox=[Math.min(...trigSolid.poly.map(p=>p[0])),Math.min(...trigSolid.poly.map(p=>p[1])),Math.max(...trigSolid.poly.map(p=>p[0])),Math.max(...trigSolid.poly.map(p=>p[1]))];
if(trigBox.join()!=='-584,-584,-536,-536'||trigSolid.z0!==76||trigSolid.z1!==140)throw Error('Teleport trigger bounds mismatch '+trigBox.join()+' '+trigSolid.z0+'..'+trigSolid.z1);
if((trigBox[0]+trigBox[2])/2!==-560||(trigBox[1]+trigBox[3])/2!==-560)throw Error('Teleport trigger off podium centre');
if(88*Math.cos(Math.PI/6)<=Math.hypot(24,24))throw Error('Teleport trigger is not fully on the plate');
const tpStep1=solids.find(s=>s.name==='teleport_step_1'),tpStep2=solids.find(s=>s.name==='teleport_step_2');
if(!tpStep1||!tpStep2||tpStep1.z1-66>18||tpStep2.z1-tpStep1.z1>18||76-tpStep2.z1>18)throw Error('Teleport steps exceed 18 unit rise');
// The podium must keep clear of the other three landmarks and the perimeter fence.
const landmarks=[{name:'scarecrow',min:[-624,488,64],max:[-496,552,248]},{name:'cart',min:[420,-622,84],max:[736,-494,158]},{name:'mill',min:[492,492,64],max:[708,708,472]},{name:'fence_w',min:[-974,-960,64],max:[-946,960,184]},{name:'fence_e',min:[946,-960,64],max:[974,960,184]},{name:'fence_s',min:[-960,-974,64],max:[960,-946,184]},{name:'fence_n',min:[-960,946,64],max:[960,974,184]}];
const podiumSolid=s=>/^teleport_(base|plate|inlay|step_|stone_|trigger)/.test(s.name);
for(const s of solids.filter(podiumSolid))for(const b of landmarks)if(intersects(s,b))throw Error('Podium intersects '+b.name+' / '+s.name);
// v5: the four dirt approach strips must be gone.
if(solids.some(s=>/^path_/.test(s.name)))throw Error('Approach path brushes must be removed');
if(entities.some(e=>e.keys.classname==='trigger_push'))throw Error('trigger_push must not exist');
if(solids.some(s=>s.name.startsWith('tramp')))throw Error('Trampoline brushes must not exist');
if(solids.some(s=>s.name.startsWith('camera_')))throw Error('Old final camera brushes must be gone');
// Room 6 must be sealed: six-brush wall band at every height, full floor disk, solid ceiling.
const r6WallBands=[['room6_wall_low',-2592,-2420],['room6_band_low',-2420,-2412],['room6_wall_mid',-2412,-2350],['room6_band_high',-2350,-2342],['room6_wall_high',-2342,-2256]];
for(const [n,z0,z1] of r6WallBands){const segs=solids.filter(s=>s.name.startsWith(n));if(segs.length!==6||segs.some(s=>s.z0!==z0||s.z1!==z1))throw Error('Room 6 wall band gap '+n);}
if(r6WallBands[r6WallBands.length-1][2]!==-2256)throw Error('Room 6 wall does not reach the ceiling');
const r6Floor=solids.find(s=>s.name==='room6_floor'),r6FloorBase=solids.find(s=>s.name==='room6_floor_base');
if(!r6Floor||r6Floor.z0!==-2576||r6Floor.z1!==-2560||!r6FloorBase||r6FloorBase.z0!==-2592||r6FloorBase.z1!==-2576)throw Error('Room 6 floor plates missing');
if(r6Floor.poly.length!==6||r6Floor.poly.some(p=>Math.abs(Math.hypot(p[0],p[1])-640)>.01))throw Error('Room 6 floor is not hex R640');
const ceilRing=['room5_floor_in','room5_floor_out','room5_lava'].flatMap(n=>solids.filter(s=>s.name.startsWith(n)));
if(ceilRing.length!==18||ceilRing.some(s=>s.z0!==-2256))throw Error('Room 6 backing floor ring missing');
const r6Ceil=solids.filter(s=>s.name.startsWith('room6_ceiling_ring'));
if(r6Ceil.length!==6||r6Ceil.some(s=>s.z0!==-2260||s.z1!==-2256))throw Error('Room 6 ceiling lining missing');
const r6Panel=solids.find(s=>s.name==='reward_lid_5_panel');
if(!r6Panel||r6Panel.z1!==-2256||r6Panel.z0!==-2260)throw Error('Room 6 ceiling panel missing');
// Pedestal: 80 high, gold cap 4 thick, top exactly -2480, sits on the floor, room to stand.
const r6Ped=solids.find(s=>s.name==='room6_pedestal'),r6PedTop=solids.find(s=>s.name==='room6_pedestal_plate');
if(!r6Ped||r6Ped.z0!==-2560||r6Ped.z1!==-2484||!r6PedTop||r6PedTop.z0!==-2484||r6PedTop.z1!==-2480)throw Error('Room 6 pedestal dimensions wrong');
if(2*96*Math.cos(Math.PI/6)<48||(-2256)-(-2480)<72)throw Error('Room 6 pedestal top too small for the reward model');
const r6Steps=solids.filter(s=>/^room6_step_\d$/.test(s.name)).sort((a,b)=>a.z1-b.z1);
if(r6Steps.length!==4)throw Error('Room 6 step count mismatch');
let rise=-2560;for(const s of r6Steps){if(s.z1-rise>18)throw Error('Room 6 step rise too high');rise=s.z1;}
if(-2480-rise>18)throw Error('Room 6 last rise too high');
if(solids.filter(s=>/^room6_bowl_stem_\d$/.test(s.name)).length!==4)throw Error('Room 6 bowl count mismatch');
for(const s of solids.filter(s=>s.kind==='detail'&&s.name.startsWith('room6_')))for(const w of solids.filter(w=>w.kind==='world'&&w.name.startsWith('room6_')))if(polyOverlap(s,w))throw Error('Room 6 decor intersects shell '+s.name+' / '+w.name);
// Photo panels: 22 detail brushes (21 prints + credits plaque). Every wall panel
// must stay inside its room and clear of every existing solid (decor, doors, lava,
// torches, pedestal, lids); only the scarecrow print mounts on the head/hat.
const photoSolids=solids.filter(s=>s.kind==='detail'&&/^(room[2-6]_photo_|scarecrow_photo_)/.test(s.name));
if(photoSolids.length!==22)throw Error('Photo panel count mismatch '+photoSolids.length);
const roomRange={2:[-512,48],3:[-1088,-528],4:[-1664,-1108],5:[-2240,-1684],6:[-2560,-2256]};
for(const s of photoSolids){
 const m=/^room(\d)_photo_/.exec(s.name);
 if(m){const [lo,hi]=roomRange[m[1]];if(s.z0<lo||s.z1>hi)throw Error('Photo outside room '+s.name);}
 for(const w of staticSolids){
  if(w===s)continue;
  if(/^scarecrow_photo_/.test(s.name)&&/^scarecrow_(head|hat)$/.test(w.name))continue;
  if(polyOverlap(s,w))throw Error('Photo panel intersects '+w.name+' / '+s.name);
 }
 for(const l of solids.filter(x=>x.kind==='lid'))if(polyOverlap(s,l))throw Error('Photo panel intersects lid '+s.name);
}
if(source.includes('SN_STALK'))throw Error('Stalk texture still referenced');
if(source.includes('SN_TRAMP'))throw Error('Trampoline texture still referenced');
for(const tex of ['SN_SACK','SN_GRAIN'])if(!source.includes(tex))throw Error('Unused texture '+tex);
for(const tex of ['SN_ROCK','SN_CRYSTAL','SN_HELL','SN_LAVA'])if(!source.includes(tex))throw Error('Unused texture '+tex);
const out=path.join(__dirname,'yandex_zalupa.map');if(checkOnly){if(fs.readFileSync(out,'utf8')!==source)throw Error('Map differs from generator');}else fs.writeFileSync(out,source);
const totalBrushes=world.length+entities.reduce((n,e)=>n+e.brushes.length,0);
console.log(JSON.stringify({output:out,checkOnly,worldBrushes:world.length,detailBrushes,totalBrushes,entities:entities.length,detailGroups:Object.fromEntries(detailEnts.map(e=>[e.keys.targetname,e.brushes.length])),ctSpawns:spawns.length,hayReferenceCount:hay.length,layerCounts,bounds:{sheet:1024,fence:960,spawns:768},teleport:{triggers:teleports.length,destinations:dests.length,target:'seno_tp_dest'},lids:['seno_reward_lid','seno_reward_lid_2','seno_reward_lid_3','seno_reward_lid_4','seno_reward_lid_5'],relays:['seno_finish','seno_finish_2','seno_finish_3','seno_finish_4','seno_finish_5'],rooms:{stage4:{floor:-1664,ceiling:-1108,lid:'seno_reward_lid_4'},stage5:{floor:-2240,ceiling:-1684,lid:'seno_reward_lid_5'},final6:{z:[-2592,-2256],floorTop:-2560,radius:640,wallTop:-2256,pedestalTop:-2480}},paths:'removed',decor:{mill:[600,600],cart:[520,-560],scarecrow:[-560,520],cave4MaxRadius:601,hell5MaxRadius:567,room3Lane:'hex R400..R470 clear for standing decor'},podium:{center:[-560,-560],base:[104,64,72],plate:[88,72,76],inlay:[76,88,76,77],stepDir:'NE 45deg (hex face normal, toward map centre)',steps:[[126,158,64,69],[90.1,126,64,72]],stones:5,trigger:[-584,-536,-584,-536,76,140]},note:'Source checks only. Inspect podium/step silhouette, cave torches, room-5 breach and pedestal landing in game.'},null,2));

