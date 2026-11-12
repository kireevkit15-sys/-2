const {test}=require('node:test');
const assert=require('node:assert/strict');
const {impose,build,ordered}=require('../static/booklet.js');
const samples=n=>Array.from({length:n},(_,i)=>({id:i+1,code:`GC-2026-${String(i+1).padStart(5,'0')}`,site:'Участок',profile:'ПР-01',point:`Т-${i+1}`,material:'Почва',collector:'',latitude:null,longitude:null}));
const opts={mode:'booklet',perPage:2,base:'http://192.168.1.10:8000',date:'12.11.2026'};
test('Duplex sheets have correct front/back page pairs and every page once',()=>{
 assert.deepEqual(impose(4),[[3,0],[1,2]]);
 assert.deepEqual(impose(8),[[7,0],[1,6],[5,2],[3,4]]);
 for(const n of [4,8,12,16])assert.deepEqual(impose(n).flat().sort((a,b)=>a-b),Array.from({length:n},(_,i)=>i));
 assert.throws(()=>impose(5));
});
test('Booklet includes each sample once and pads to complete signatures',()=>{
 for(const n of [1,2,3,5,28,29,100])for(const perPage of [1,2]){
  const r=build(samples(n),{...opts,perPage});
  assert.equal(r.pages%4,0);assert.equal(r.sides,r.pages/2);
  const ids=[...r.html.matchAll(/data-sample="(\d+)"/g)].map(m=>Number(m[1])).sort((a,b)=>a-b);
  assert.deepEqual(ids,Array.from({length:n},(_,i)=>i+1));
  const pages=[...r.html.matchAll(/data-page="(\d+)"/g)].map(m=>Number(m[1])).sort((a,b)=>a-b);
  assert.deepEqual(pages,Array.from({length:r.pages},(_,i)=>i+1));
  for(const m of r.html.matchAll(/data-pages="(\d+),(\d+)"/g))assert.equal(Math.floor((Number(m[1])-1)/16),Math.floor((Number(m[2])-1)/16));
 }
});
test('Natural profile/point ordering, separate profiles, escaping, A5 mode',()=>{
 const input=samples(3);input[0].profile='ПР-10';input[1].point='Т-10';input[2].point='Т-2';
 assert.deepEqual(ordered(input).map(s=>s.id),[3,2,1]);
 const r=build(input,{...opts,mode:'a5'});assert.equal(r.pages,4);assert.equal(r.sides,4);assert.ok(!r.html.includes('class="sheet-side"'));
 input[0].site='<script>alert(1)</script>';
 assert.ok(!build(input,opts).html.includes('<script>'));
 assert.throws(()=>build([],opts));assert.throws(()=>build(samples(101),opts));assert.throws(()=>build(samples(2),{...opts,base:'javascript:alert(1)'}));
});
