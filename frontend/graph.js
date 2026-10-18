/* Content relationships and a bounded force layout; no account actions or requests. */
(function (root) {
  'use strict';
  const aliases = new Map(Object.entries({
    'AI工具':'AI应用','人工智能工具':'AI应用','AI工具应用':'AI应用','编程教程':'编程开发',
    '程序设计':'编程开发','编程':'编程开发','硬件测评':'硬件评测','数码测评':'数码评测',
    '游戏测评':'游戏评测','Cosplay':'Cos创作','cosplay':'Cos创作','COS':'Cos创作',
    '翻唱':'音乐翻唱','游戏直播切片':'直播切片','Vlog':'生活记录','vlog':'生活记录',
    '邦邦':'BanG Dream','BanGDream':'BanG Dream','宠物记录':'宠物日常','校园记录':'校园生活',
    '职业发展':'职业规划','钓鱼记录':'钓鱼'
  }));
  const generic = new Set(['游戏','科技','音乐','生活','知识','动画','二次元','其他','未标注','待分析','综合内容','娱乐']);
  function normalizeTag(value) {
    const tag=String(value).normalize('NFKC').replace(/\s+/g,'').trim();
    return aliases.get(tag)||tag;
  }
  const weightCache = new WeakMap();
  function tagWeights(row) {
    if (weightCache.has(row)) return weightCache.get(row);
    let source;
    if (Array.isArray(row.graph_tags) && row.graph_tags.length) {
      source = row.graph_tags.map(item => typeof item === 'string' ? {tag:item,weight:1} : item);
    } else {
      const list = Array.isArray(row.tags) && row.tags.length ? row.tags : String(row.label||'').split(/[、，,/|·；;]/);
      source = list.map(tag => ({tag,weight:1}));
    }
    const map = new Map();
    for (const item of source) {
      const tag = normalizeTag(item.tag ?? item);
      if (!tag || generic.has(tag)) continue;
      const weight = Math.max(.2, Math.min(1, Number(item.weight) || 1));
      map.set(tag, Math.max(map.get(tag) || 0, weight));
    }
    weightCache.set(row, map);
    return map;
  }
  function contentTags(row) { return [...tagWeights(row).keys()]; }
  function weightOf(row, tag) { return tagWeights(row).get(normalizeTag(tag)) || 0; }
  function buildEdges(rows, maxDegree=4) {
    // 只取权重最高的 6 个标签做相似度：6-10 个标签全用时，长尾唯一标签会把余弦稀释掉。
    const bags=rows.map(row=>new Map([...tagWeights(row)].sort((a,b)=>b[1]-a[1]).slice(0,6)));
    const index=new Map();
    bags.forEach((bag,i)=>bag.forEach((weight,tag)=>{
      if(!index.has(tag))index.set(tag,[]);
      index.get(tag).push({i,weight});
    }));
    const weights=new Map([...index].map(([tag,members])=>[tag,Math.pow(1+Math.log((rows.length+1)/(members.length+1)),2)]));
    const totals=bags.map(bag=>[...bag].reduce((sum,[tag,weight])=>sum+weight*weights.get(tag),0));
    const pairs=new Map();
    for(const [tag,members] of index) {
      if(members.length>Math.max(8,rows.length*.6))continue;
      const idf=weights.get(tag);
      for(let a=0;a<members.length;a++)for(let b=a+1;b<Math.min(members.length,members.length>700?a+49:members.length);b++) {
        const ma=members[a],mb=members[b],i=ma.i,j=mb.i,key=i+':'+j;
        if(!pairs.has(key))pairs.set(key,{i,j,shared:[],weight:0});
        const edge=pairs.get(key);edge.shared.push(tag);edge.weight+=Math.min(ma.weight,mb.weight)*idf;
      }
    }
    const candidates=[...pairs.values()].map(edge=>({...edge,score:edge.weight/Math.sqrt(totals[edge.i]*totals[edge.j])}))
      .filter(edge=>edge.score>=.06).sort((a,b)=>b.score-a.score||a.i-b.i||a.j-b.j);
    const degree=new Uint16Array(rows.length), edges=[];
    for(const edge of candidates)if(degree[edge.i]<maxDegree&&degree[edge.j]<maxDegree){
      edges.push(edge);degree[edge.i]++;degree[edge.j]++;
    }
    return edges;
  }
  function relax(nodes,edges,{iterations=160,mode='galaxy',contains=null,pinned=null,tagGroups=null}={}) {
    const count=nodes.length,fx=new Float64Array(count),fy=new Float64Array(count);
    const anchor=mode==='brain'?.038:.012,limit=mode==='brain'?92:190;
    for(let step=0;step<iterations;step++) {
      fx.fill(0);fy.fill(0);
      for(const edge of edges) {
        const a=nodes[edge.i],b=nodes[edge.j],dx=b.tx-a.tx,dy=b.ty-a.ty,dist=Math.hypot(dx,dy)||.01;
        const rest=18+(1-edge.score)*35,force=(dist-rest)*(.018+edge.score*.085);
        fx[edge.i]+=dx/dist*force;fy[edge.i]+=dy/dist*force;
        fx[edge.j]-=dx/dist*force;fy[edge.j]-=dy/dist*force;
      }
      // A spatial grid keeps local repulsion cheap, including large imported lists.
      const grid=new Map(),cell=28;
      nodes.forEach((n,i)=>{const key=Math.floor(n.tx/cell)+':'+Math.floor(n.ty/cell);if(!grid.has(key))grid.set(key,[]);grid.get(key).push(i);});
      nodes.forEach((a,i)=>{
        const gx=Math.floor(a.tx/cell),gy=Math.floor(a.ty/cell);
        for(let ox=-1;ox<=1;ox++)for(let oy=-1;oy<=1;oy++)for(const j of grid.get((gx+ox)+':'+(gy+oy))||[])if(j>i){
          const b=nodes[j];let dx=b.tx-a.tx,dy=b.ty-a.ty,dist=Math.hypot(dx,dy);
          if(dist>=25)continue;
          if(dist<.01){dx=Math.cos(i*2.399+j);dy=Math.sin(i*2.399+j);dist=1;}
          const force=(25-dist)*.13;
          fx[i]-=dx/dist*force;fy[i]-=dy/dist*force;fx[j]+=dx/dist*force;fy[j]+=dy/dist*force;
        }
      });
      // Tag gravity: each account is pulled toward the centroid of every tag it carries.
      // The rest distance keeps a tag from collapsing into one point.
      if(tagGroups)for(const group of tagGroups) {
        const members=group.members;
        if(!members||members.length<2)continue;
        const tagWeightsList=group.weights||[];
        let cx=0,cy=0,sw=0;
        for(let k=0;k<members.length;k++){
          const weight=tagWeightsList[k]??1,m=members[k];
          cx+=nodes[m].tx*weight;cy+=nodes[m].ty*weight;sw+=weight;
        }
        if(sw<=0)continue;
        cx/=sw;cy/=sw;
        for(let k=0;k<members.length;k++){
          const weight=tagWeightsList[k]??1,m=members[k];
          const dx=cx-nodes[m].tx,dy=cy-nodes[m].ty,dist=Math.hypot(dx,dy)||.01;
          const rest=14+10*(1-weight);
          if(dist<=rest)continue;
          const force=(dist-rest)*(.004+.010*weight);
          fx[m]+=dx/dist*force;fy[m]+=dy/dist*force;
        }
      }
      nodes.forEach((n,i)=>{
        if(n===pinned)return;
        const hx=n.hx??n.tx,hy=n.hy??n.ty;
        let x=n.tx+Math.max(-5,Math.min(5,fx[i]+(hx-n.tx)*anchor));
        let y=n.ty+Math.max(-5,Math.min(5,fy[i]+(hy-n.ty)*anchor));
        const distance=Math.hypot(x-hx,y-hy);
        if(distance>limit){x=hx+(x-hx)*limit/distance;y=hy+(y-hy)*limit/distance;}
        if(!contains||contains(x,y)){n.tx=x;n.ty=y;}
      });
    }
    return nodes;
  }
  const api=Object.freeze({normalizeTag,contentTags,tagWeights,weightOf,buildEdges,relax});
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.ContentGraph=api;
})(globalThis);
