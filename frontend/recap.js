/* Snapshot-based highlights. A visit rank is never treated as a visit count. */
(() => {
  'use strict';
  function number(value) {
    if(value===null||value===undefined||value==='')return null;
    const n=Number(value);return Number.isFinite(n)?n:null;
  }
  function rank(node) {
    const n=number(node.row.visit_rank);
    return Number.isInteger(n)&&n>0?n:null;
  }
  function fans(node) {const n=number(node.row.fans);return n!==null&&n>0?n:null;}
  function format(n) {return n>=10000?(n/10000).toFixed(1)+'万':Math.round(n).toLocaleString('zh-CN');}
  function discovery(accounts,feature) {
    if(!feature||typeof feature.title!=='string'||!feature.title.trim()||typeof feature.text!=='string'||!feature.text.trim()||!Array.isArray(feature.evidence)||!feature.evidence.length)return null;
    const node=accounts.find(n=>n.row.mid===String(feature.mid));
    if(!node||!feature.evidence.some(ref=>ref&&String(ref.mid)===node.row.mid))return null;
    for(const ref of feature.evidence){
      if(!ref||typeof ref!=='object')return null;
      const row=accounts.find(n=>n.row.mid===String(ref.mid))?.row;
      if(!row)return null;
      for(const key of ['label','priority','visit_rank'])if(key in ref&&ref[key]!==row[key])return null;
      if(!Array.isArray(ref.video_titles)||!ref.video_titles.length||!ref.video_titles.every(title=>row.videos.includes(title)))return null;
    }
    return {kind:'discovery',kicker:'一个有意思的发现',title:feature.title,detail:feature.text,note:'',node,duration:4200};
  }
  function build(accounts,topics,feature=null) {
    if(!accounts.length)return [];
    const ranked=accounts.filter(n=>rank(n)!==null).sort((a,b)=>rank(a)-rank(b));
    const groups=topics.map(topic=>({topic,members:accounts.filter(n=>n.topic===topic.topic)})).filter(g=>g.members.length);
    groups.sort((a,b)=>b.members.length-a.members.length||a.topic.topic-b.topic.topic);
    const home=groups[0],cards=[];
    if(home)cards.push({
      kind:'circle',kicker:'你关注最多的领域',
      title:home.topic.name,
      detail:`${home.members.length} 位 UP 主 · 占关注的 ${(home.members.length/accounts.length*100).toFixed(1)}%`,
      note:'按 UP 主内容标签归类 · 以关注数量统计',node:home.topic
    });
    const first=ranked[0];
    if(first)cards.push({
      kind:'favorite',kicker:rank(first)===1?'最常访问第 1 名':'常访问名单里的熟面孔',title:first.label,
      detail:first.row.label||'未标注',note:`最常访问 #${rank(first)}${fans(first)!==null?' · '+format(fans(first))+' 粉丝':''}`,node:first
    });
    const pick=discovery(accounts,feature);
    if(pick)cards.push(pick);
    return cards.sort((a,b)=>({favorite:0,circle:1,discovery:2}[a.kind])-({favorite:0,circle:1,discovery:2}[b.kind]));
  }
  globalThis.FollowingRecap=Object.freeze({build});
})();
