const {test}=require('node:test');
const assert=require('node:assert/strict');
const graph=require('../frontend/graph.js');

test('shared content links across primary categories; cleanup ratings do not affect links',()=>{
  const rows=[{tags:['游戏开发','编程开发'],type:0},{tags:['独立游戏','编程教程'],type:12},{tags:['音乐翻唱']}];
  const edges=graph.buildEdges(rows);
  assert.equal(edges.length,1);
  assert.deepEqual(edges[0].shared,['编程开发']);
  assert.deepEqual(graph.buildEdges(rows.map(r=>({...r,type:7,unfollow:true}))),edges);
});
test('broad categories alone do not fabricate content similarity',()=>{
  assert.deepEqual(graph.buildEdges([{tags:['游戏']},{tags:['游戏']}]),[]);
  assert.deepEqual(graph.buildEdges([{tags:['音乐翻唱']},{tags:['AI应用']}]),[]);
});
test('sparse edges respect a maximum degree of four with no duplicate pairs',()=>{
  const edges=graph.buildEdges(Array.from({length:8},()=>({tags:['独立游戏','游戏评测']})));
  const degree=Array(8).fill(0),pairs=new Set();
  for(const e of edges){degree[e.i]++;degree[e.j]++;pairs.add(e.i+':'+e.j);assert.ok(e.score>0&&e.score<=1);}
  assert.ok(edges.length>0);assert.ok(degree.every(d=>d<=4));assert.equal(pairs.size,edges.length);
});
test('actual spring attraction shortens the distance between related accounts',()=>{
  const nodes=[{tx:-100,ty:0,hx:-100,hy:0},{tx:100,ty:0,hx:100,hy:0}];
  graph.relax(nodes,[{i:0,j:1,score:1}],{iterations:180});
  assert.ok(Math.hypot(nodes[0].tx-nodes[1].tx,nodes[0].ty-nodes[1].ty)<60);
});
test('unconnected overlapping accounts separate and a dragged account stays pinned',()=>{
  const nodes=[{tx:0,ty:0,hx:0,hy:0},{tx:0,ty:0,hx:0,hy:0}];
  graph.relax(nodes,[],{pinned:nodes[0]});
  assert.equal(nodes[0].tx,0);assert.equal(nodes[0].ty,0);
  assert.ok(Math.hypot(nodes[1].tx,nodes[1].ty)>15);
});
test('brain bounds and home displacement remain finite under distant cross-cluster links',()=>{
  const nodes=[{tx:-45,ty:0,hx:-45,hy:0},{tx:45,ty:0,hx:45,hy:0}];
  graph.relax(nodes,[{i:0,j:1,score:.5}],{mode:'brain',contains:(x,y)=>Math.abs(x)<=50&&Math.abs(y)<=50});
  for(const n of nodes){assert.ok(Number.isFinite(n.tx)&&Number.isFinite(n.ty));assert.ok(Math.abs(n.tx)<=50&&Math.abs(n.ty)<=50);}
});


test('tag gravity pulls accounts carrying the same tag together',()=>{
  const nodes=[{tx:-80,ty:0,hx:-80,hy:0},{tx:80,ty:0,hx:80,hy:0}];
  graph.relax(nodes,[],{iterations:120,tagGroups:[{members:[0,1],weights:[1,1]}]});
  const before=160, after=Math.hypot(nodes[0].tx-nodes[1].tx,nodes[0].ty-nodes[1].ty);
  assert.ok(after<before-15, after);
});
