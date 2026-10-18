/* All data stays in this page. No requests, credentials, or account mutations. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const canvas = $('universe'), ctx = canvas.getContext('2d');
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const CLEANUP_TOTAL_MS=2000, SLIDE_MS=reduceMotion?0:380, PASSAGE_EXIT_MS=reduceMotion?0:240;
  const RECAP_STEP_MS=1800;
  const INTRO_SPEED=1.35, introMs=ms=>Math.round(ms/INTRO_SPEED);
  document.documentElement.style.setProperty('--intro-speed',INTRO_SPEED);
  const FONT = '"Segoe UI", "Microsoft YaHei", sans-serif';
  const colorPreference = matchMedia('(prefers-color-scheme: dark)');
  const SCHEMES = {
    light: {background:'#fafaf8',ink:'#30343b',muted:'#85818c',label:'#6f6a79',halo:'#fafaf8ed',selected:'#35313e',outline:'#dedfe5',colors:['#8171ac','#4b9386','#5b88b6','#ab6f8b','#a78d4b','#b67c5d','#7284ae','#839853','#9f70a9','#5d939f','#8b909b']},
    dark: {background:'#090b10',ink:'#eceef3',muted:'#8b8398',label:'#a6a0b3',halo:'#090b10c0',selected:'#f8f0ff',outline:'#b5a0ec0d',colors:['#b2a0f3','#86c6b1','#7daedb','#d797ad','#c6b57e','#d59f7d','#8fa1d5','#b5ca8c','#c591d5','#8ebfc9','#a4adb9']}
  };
  let appearance = 'auto';
  try { const saved=localStorage.getItem('bili-appearance');if(['auto','light','dark'].includes(saved))appearance=saved; } catch {}
  const prefersDark = () => appearance==='dark'||appearance==='auto'&&colorPreference.matches;
  let theme = SCHEMES[prefersDark() ? 'dark' : 'light'];
  const TOPICS = [
    {name:'游戏与电竞',short:'游戏',color:'#b2a0f3',rule:/游戏|电竞|原神|鸣潮|崩坏|星铁|明日方舟|王者|CS[2：:]?|LPL|LOL|FPS|英雄联盟|单机|主机|攻略|实况|我的世界/i,tags:['独立游戏','游戏实况','开放世界','电竞赛事','游戏设计','主机游戏']},
    {name:'科技与 AI',short:'科技',color:'#86c6b1',rule:/科技|数码|编程|代码|计算机|软件|硬件|手机|电脑|\bAI\b|AI[科工学论虚动基大开]|人工智能|开发|机器学习|机器人|开源|算法|芯片|网络维修|前端|技术讲座|人体工学椅/i,tags:['数码评测','编程开发','人工智能','硬件拆解','科技资讯','软件工具']},
    {name:'知识与人文',short:'知识',color:'#7daedb',rule:/知识|科普|历史|人文|哲学|数学|物理|学习|教育|读书|社会|社科|政治|法律|劳动|科学|心理|考研|英语|纪录|学术|科研|论文|军事|军武|精神分析|拉康|地理|地质|文学|写作|访谈/i,tags:['历史人文','科学科普','社会观察','读书分享','经济知识','哲学思考']},
    {name:'音乐与声音',short:'音乐',color:'#d797ad',rule:/音乐|歌曲|唱|乐器|钢琴|吉他|声乐|作曲|演奏|VOCALOID|音游|乐队|贝斯|电音|口琴|鼓|调声|调教|虚拟歌|翻调|音声|UTAU|SynthV|V家|音MAD|鬼畜|播客|电台/i,tags:['音乐现场','器乐演奏','独立音乐','翻唱创作','电子音乐']},
    {name:'动画与二次元',short:'动画',color:'#c6b57e',rule:/动漫|动画|番剧|二次元|漫画|虚拟|VTuber|VUP|同人|配音|声优|手书|绘画|插画|邦邦|BanG|ACG|MMD|MAD|模型|轻小说|百合|新番|galgame/i,tags:['动画杂谈','番剧推荐','绘画创作','虚拟主播','同人手书']},
    {name:'生活与日常',short:'生活',color:'#d59f7d',rule:/生活|日常|vlog|家居|穿搭|美妆|宠物|猫|狗|手工|健身|运动|旅行|户外|骑行/i,tags:['生活记录','旅行见闻','猫猫日常','手工改造','运动健身']},
    {name:'影视与故事',short:'影视',color:'#8fa1d5',rule:/影视|电影|电视剧|影评|短片|剪辑|摄影|故事|导演|拍摄/i,tags:['电影解读','摄影创作','影视剪辑','短片故事']},
    {name:'美食与味觉',short:'美食',color:'#b5ca8c',rule:/美食|做饭|料理|探店|烹饪|食谱|烘焙|吃播/i,tags:['家常料理','美食探店','烘焙日记']},
    {name:'宅舞与 Cos',short:'宅舞 / Cos',color:'#c591d5',rule:/cos|宅舞|翻跳|舞蹈|偶像|女装|男娘|WOTA|地偶|地下艺|手势舞|漫展|变装|伪娘|kigurumi/i,tags:['宅舞翻跳','Cos 创作','舞台记录']},
    {name:'财经与商业',short:'财经',color:'#8ebfc9',rule:/财经|金融|经济|商业|投资|交易|股市|美股|A股|加密|区块链|Web3|理财|FIRE/i,tags:['商业观察','财经知识','投资研究']},
    {name:'有趣的其他',short:'其他',color:'#a4adb9',rule:/.*/,tags:['搞笑整活','小众爱好','还没归类']}
  ];
  const BRAIN_LEFT = 'M -12 -300 C -51 -357 -151 -354 -198 -301 C -281 -320 -342 -253 -329 -195 C -396 -155 -396 -62 -352 -22 C -392 57 -348 145 -289 157 C -291 236 -211 280 -155 259 C -135 320 -51 328 -19 269 C -2 214 -16 161 -10 101 C -22 34 -10 -10 -15 -62 C -3 -139 -22 -194 -12 -300 Z';
  const brainLeft = new Path2D(BRAIN_LEFT);
  const brainRight = new Path2D(); brainRight.addPath(brainLeft, new DOMMatrix().scale(-1, 1));
  let rows = [], nodes = [], links = [], topics = [], tags = [], accounts = [], contentEdges = [], demo = true;
  let activeTopic = null, selected = null, hovered = null, view = 'brain';
  let width = 0, height = 0, dpr = 1, frame = 0;
  let camera = {x:0,y:0,z:1}, targetCamera = {...camera}, baseScale = 1;
  let clean = false, dragging = null, pointer = null, moved = false, toastTimer;
  let searchMatches = null;
  let graphPaused = false, phase = 'graph';
  let recapCards=[], recapIndex=0, recapTimer=0, recapSwapTimer=0, recapRevealTimer=0, recapTarget=null, spotlightReady=false;
  let introFinished=false,recapResumeOnVisible=false;

  function syncTheme() {
    theme = SCHEMES[prefersDark() ? 'dark' : 'light'];
    $('dark-theme').media=prefersDark()?'all':'not all';
    TOPICS.forEach((t,i)=>{t.color=theme.colors[i];});
    topics.forEach(t=>{t.color=theme.colors[t.topic];});
    document.querySelector('meta[name="theme-color"]').content=theme.background;
    if(selected)$('detail').style.setProperty('--topic',TOPICS[selected.topic].color);
    renderInterests(); syncCleanupTheme(); wake();
  }
  TOPICS.forEach((t,i)=>{t.color=theme.colors[i];});
  document.querySelector('meta[name="theme-color"]').content=theme.background;
  colorPreference.addEventListener('change',syncTheme);
  $('appearance').value=appearance;
  $('appearance').addEventListener('change',()=>{
    appearance=$('appearance').value;
    try{localStorage.setItem('bili-appearance',appearance);}catch{}
    syncTheme();
  });

  function seedRandom(seed) { return () => {seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t ^= t + Math.imul(t ^ t >>> 7, 61 | t); return ((t ^ t >>> 14) >>> 0) / 4294967296;}; }
  function hash(s) { let n = 2166136261; for (const c of String(s)) n = Math.imul(n ^ c.charCodeAt(0), 16777619); return n >>> 0; }
  function esc(s) {return String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function format(n) {return n == null ? '未知' : Number(n) >= 10000 ? (Number(n)/10000).toFixed(1)+'万' : String(n);}
  function toast(message) { $('toast').textContent = message; $('toast').classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(()=>$('toast').classList.remove('visible'),3500); }

  function makeDemo() {
    const counts = [160,125,80,75,65,45,35,25,62,36,20], result = [], random = seedRandom(1773);
    const names = ['橘子','不熬夜','星期六','一只小鱼','月球居民','野生电波','阿白','山间来信','慢半拍','口袋宇宙','小满','夜航船','半颗糖','云游','青苔'];
    let id = 0;
    TOPICS.forEach((topic, ti) => {for(let i=0;i<counts[ti];i++) {
      const tag = topic.tags[i % topic.tags.length];
      result.push({mid:String(900000000+id),uname:names[id%names.length]+'的'+['放映室','观察站','小角落','备忘录','实验室'][Math.floor(id/names.length)%5]+' '+String(id+1).padStart(3,'0'),label:tag,tags:[tag],sign:'这是虚构的演示账号，用于展示关注图谱。',fans:Math.round(random()*2000000),last_days:Math.round(random()*180),videos:[tag+' · 一些值得分享的新发现',tag+' · 最近在关注什么'],_topic:ti}); id++;
    }});
    return result;
  }

  function normalize(input) {
    if (!Array.isArray(input)) throw new Error('请选择 combined.json 格式的账号数组');
    if (input.length > 15000) throw new Error('当前支持最多 15000 个账号');
    const seen = new Set();
    return input.map((r,i) => {
      if (!r || typeof r !== 'object' || Array.isArray(r)) throw new Error(`第 ${i+1} 项不是有效账号`);
      const mid = String(r.mid ?? r.uid ?? '').trim();
      if(!/^\d+$/.test(mid)) throw new Error(`第 ${i+1} 项缺少有效的 mid / uid`);
      if (seen.has(mid)) return null;
      seen.add(mid);
      const label = String(r.label || '未标注');
      const graphTags = Array.isArray(r.graph_tags) && r.graph_tags.length
        ? r.graph_tags.map(item => typeof item === 'string' ? item : item?.tag).filter(Boolean) : [];
      let rawTags = graphTags.length ? graphTags : (Array.isArray(r.tags) ? r.tags : []);
      rawTags = [...new Set((rawTags.length?rawTags:label.split(/[、，,/|·；;]/)).map(ContentGraph.normalizeTag).filter(Boolean))].slice(0,10);
      const priority=[8,9,1,0,3,4,2,6,5,7];
      const primary=label.split(/[、，,/|·；;]/)[0];
      const classified=priority.find(i=>TOPICS[i].rule.test(primary)) ?? priority.find(i=>TOPICS[i].rule.test(label+' '+rawTags.join(' '))) ?? 10;
      const topic = demo && Number.isInteger(r._topic) ? r._topic : classified;
      return {...r,mid,uname:String(r.uname || r.name || `UP ${mid}`),label,tags:rawTags,_topic:topic,videos:Array.isArray(r.videos)?r.videos.map(v=>typeof v==='string'?v:String(v?.title || '')).filter(Boolean):[]};
    }).filter(Boolean);
  }

  function load(input, isDemo) {
    const oldDemo = demo; demo = isDemo;
    let next;
    try { next = normalize(input); } catch(e) {demo=oldDemo; throw e;}
    rows = next; activeTopic = null; selected = hovered = null; searchMatches = null;
    $('search').value = ''; $('results').hidden = true; $('detail').hidden = true;
    topics = TOPICS.map((t,i)=>({...t,id:`topic:${i}`,kind:'topic',topic:i,label:t.name,members:[]}));
    const tagMap = new Map();
    accounts = rows.map(row=>{
      const node = {id:`up:${row.mid}`,kind:'up',label:row.uname,topic:row._topic,row,tagNodes:[],x:0,y:0,tx:0,ty:0};
      topics[node.topic].members.push(node);
      row.tags.forEach(label=>{
        const key = label;
        if(!tagMap.has(key)) tagMap.set(key,{id:'tag:'+key,kind:'tag',label,topic:node.topic,members:[],x:0,y:0,tx:0,ty:0});
        const tag=tagMap.get(key);tag.members.push(node);node.tagNodes.push(tag);
      });
      return node;
    });
    topics = topics.filter(t=>t.members.length);
    // 只把至少两个账号共享的标签画成节点；单人标签留在账号详情里，避免图上全是孤立小点。
    tags = [...tagMap.values()].filter(t=>t.members.length>=2);
    const sharedTags = new Set(tags);
    accounts.forEach(n=>{n.tagNodes=n.tagNodes.filter(t=>sharedTags.has(t));});
    nodes = [...topics,...tags,...accounts]; links=[];
    contentEdges=ContentGraph.buildEdges(rows);
    accounts.forEach(n=>{n.neighbors=[];});
    for(const edge of contentEdges){accounts[edge.i].neighbors.push(accounts[edge.j]);accounts[edge.j].neighbors.push(accounts[edge.i]);}
    canvas.dataset.contentEdges=String(contentEdges.length);
    canvas.dataset.crossTopicEdges=String(contentEdges.filter(e=>accounts[e.i].topic!==accounts[e.j].topic).length);
    for(const tag of tags) {
      for(const ti of new Set(tag.members.map(n=>n.topic))){
        const hub = topics.find(t=>t.topic===ti);
        links.push({a:hub,b:tag,kind:'branch',topic:ti});
      }
      for(const node of tag.members) links.push({a:tag,b:node,kind:'leaf',topic:node.topic});
    }
    $('account-total').textContent=rows.length.toLocaleString('zh-CN');
    $('tag-total').textContent=new Set(tags.map(t=>t.label)).size;
    $('topic-count').textContent=topics.length+' 类';
    $('wander').disabled=!accounts.length; $('save').disabled=!accounts.length;
    renderInterests(); positionNodes(true); fit();
    setupRecap();
    if(!accounts.length) toast('这份关注列表是空的，可以导入其他 JSON 文件');
  }

  function renderInterests() {
    $('interests').replaceChildren();
    [...topics].sort((a,b)=>b.members.length-a.members.length).forEach(t=>{
      const b = document.createElement('button'); b.className='interest-row'+(activeTopic===t.topic?' active':'');
      b.style.setProperty('--topic',t.color); b.setAttribute('aria-pressed',String(activeTopic===t.topic));
      const percent = rows.length ? t.members.length/rows.length*100 : 0;
      b.innerHTML=`<span class="swatch"></span><span class="interest-name">${esc(t.name)}<span class="bar"><span style="width:${percent}%"></span></span></span><span class="percent">${percent.toFixed(1)}%</span>`;
      b.setAttribute('aria-label',`${t.name}，${t.members.length} 个账号，占 ${percent.toFixed(1)}%，点击探索`);
      b.addEventListener('click',()=>{if(activeTopic===t.topic) resetSelection();else select(t);});
      $('interests').appendChild(b);
    });
  }

  function stopRecap(restore=false,finish=true) {
    clearTimeout(recapTimer);clearTimeout(recapSwapTimer);clearTimeout(recapRevealTimer);recapTarget=null;spotlightReady=false;
    $('recap').classList.add('is-paused');$('recap').classList.remove('is-changing');
    setRecapVisible(false);
    $('recap-beacon').hidden=true;
    $('spotlight').hidden=true;$('spotlight').classList.remove('is-visible');
    if(restore&&phase==='graph')fit();
    if(finish){recapResumeOnVisible=false;introFinished=true;if(!frame)showCleanupCue();}
  }
  function setRecapVisible(visible) {
    $('recap').classList.toggle('is-ready',visible);$('recap').inert=!visible;
    $('recap').setAttribute('aria-hidden',String(!visible));
  }
  function recapViewport() {
    const v=graphViewport();
    return {...v,x:width<=700?width/2:v.x,y:width<=700?315:Math.max(220,Math.min(v.y-80,height*.4)),portrait:Math.max(88,Math.min(144,width*.07,height*.11))};
  }
  function layoutRecap() {
    const card=recapCards[recapIndex];if(!card)return;
    const v=recapViewport();
    $('app').style.setProperty('--portrait-size',v.portrait+'px');
    $('recap').style.left=v.x+'px';
    $('recap').style.top=(v.y+(card.node.kind==='up'?v.portrait/2+30:66))+'px';
    $('recap').style.width=Math.min(740,width<=700?width-44:v.w*.88)+'px';
  }
  function safeAvatar(row) {
    if(typeof row.avatar_data==='string'&&/^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(row.avatar_data))return row.avatar_data;
    try{const url=new URL(row.face);if(url.protocol==='https:'&&!url.username&&!url.password&&['hdslb.com','biliimg.com'].some(host=>url.hostname===host||url.hostname.endsWith('.'+host)))return url.href;}catch{}
    return '';
  }
  function focusRecap(card) {
    const node=card.node,v=recapViewport(),z=baseScale*(node.kind==='up'?2.25:1.4);
    targetCamera={x:v.x-node.tx*z,y:v.y-node.ty*z,z};wake();
    $('spotlight').hidden=true;$('spotlight').classList.remove('is-visible');spotlightReady=false;
    if(node.kind!=='up')return;
    const avatar=safeAvatar(node.row),image=$('spotlight-image');
    $('spotlight-name').textContent=node.label;$('spotlight-label').textContent=node.row.label;
    $('spotlight-rank').textContent=card.kicker;
    $('spotlight-initials').textContent=Array.from(node.label).slice(0,2).join('');
    $('spotlight').setAttribute('aria-label','查看'+node.label);
    image.hidden=true;$('spotlight-initials').hidden=false;
    if(avatar){image.src=avatar;image.alt=node.label+'的头像';}else{image.removeAttribute('src');image.alt='';}
    recapRevealTimer=setTimeout(()=>{
      if(recapTarget!==node)return;
      spotlightReady=true;$('spotlight').hidden=false;updateRecapBeacon();
      requestAnimationFrame(()=>{if(spotlightReady)$('spotlight').classList.add('is-visible');});
    },0);
  }
  function showRecap(index,focus=true) {
    recapIndex=index;const card=recapCards[index];
    $('recap').style.setProperty('--recap-ms',introMs(card.duration??(card.node.kind==='up'?2800:RECAP_STEP_MS))+'ms');
    $('recap').dataset.kind=card.kind;
    $('recap-step').textContent=String(index+1).padStart(2,'0')+' / '+String(recapCards.length).padStart(2,'0');
    $('recap-kicker').textContent=card.kind==='discovery'?card.node.label:card.kicker;
    $('recap-title').textContent=card.title;
    $('recap-detail').textContent=card.detail;
    $('recap-note').textContent=card.note;
    $('recap-open').setAttribute('aria-label','查看'+card.title);
    $('recap-meter').innerHTML=recapCards.map((_,i)=>`<span class="${i<index?'is-past':i===index?'is-current':''}"><i></i></span>`).join('');
    layoutRecap();
    if(focus){recapTarget=card.node;$('recap-beacon').className='recap-beacon'+(card.node.kind==='topic'?' is-region':'');
      focusRecap(card);updateRecapBeacon();}
  }
  function advanceRecap() {
    recapTimer=setTimeout(()=>{
      if(recapIndex===recapCards.length-1){stopRecap(true);return;}
      $('recap').classList.add('is-changing');$('recap-beacon').hidden=true;$('spotlight').classList.remove('is-visible');
      recapSwapTimer=setTimeout(()=>{showRecap(recapIndex+1);$('recap').classList.remove('is-changing');advanceRecap();},reduceMotion?0:introMs(180));
    },introMs(recapCards[recapIndex].duration??(recapCards[recapIndex].node.kind==='up'?2800:RECAP_STEP_MS)));
  }
  function startRecap() {
    if(!recapCards.length||phase!=='graph')return;
    if(width<=700)window.scrollTo(0,0);
    stopRecap(false,false);recapResumeOnVisible=false;hideCleanupCue();setRecapVisible(true);$('recap').classList.remove('is-paused');showRecap(0);advanceRecap();
  }
  function setupRecap() {
    stopRecap(false,false);hideCleanupCue();
    let feature=null;try{feature=JSON.parse($('recap-feature').textContent);}catch{}
    recapCards=globalThis.FollowingRecap.build(accounts,topics,feature);
    $('recap').hidden=!recapCards.length;
    if(!recapCards.length){introFinished=true;if(!frame)showCleanupCue();return;}
    recapIndex=0;showRecap(0,false);
    for(const card of recapCards){if(card.node.kind==='up'){const avatar=safeAvatar(card.node.row);if(avatar){const image=new Image();image.referrerPolicy='no-referrer';image.src=avatar;}}}
    recapTimer=setTimeout(startRecap,introMs(800));
  }
  function updateRecapBeacon() {
    const beacon=$('recap-beacon');
    if(!recapTarget||phase!=='graph'||graphPaused||clean||document.hidden){beacon.hidden=true;return;}
    const p=screen(recapTarget);
    const v=recapViewport();
    $('recap').style.left=p.x+'px';$('recap').style.top=(p.y+(recapTarget.kind==='up'?v.portrait/2+30:66))+'px';
    beacon.style.left=p.x+'px';beacon.style.top=p.y+'px';beacon.style.color=TOPICS[recapTarget.topic].color;
    beacon.hidden=false;
    if(spotlightReady&&recapTarget.kind==='up'){$('spotlight').style.left=p.x+'px';$('spotlight').style.top=p.y+'px';}
  }
  $('recap-replay').addEventListener('click',startRecap);
  $('recap-skip').addEventListener('click',()=>stopRecap(true));
  $('recap-open').addEventListener('click',()=>{const node=recapCards[recapIndex]?.node;if(node)select(node);});
  $('spotlight').addEventListener('click',()=>{if(recapTarget)select(recapTarget);});
  $('spotlight-image').addEventListener('load',()=>{$('spotlight-image').hidden=false;$('spotlight-initials').hidden=true;});
  $('spotlight-image').addEventListener('error',()=>{$('spotlight-image').hidden=true;$('spotlight-initials').hidden=false;});

  function brainPoints(count) {
    ctx.save(); ctx.resetTransform();
    const random=seedRandom(92347), points=[];
    // Stratified points prevent a random silhouette from becoming a ball of noise.
    const step = Math.sqrt(335000/Math.max(count,1));
    for(let y=-350;y<340;y+=step) for(let x=-400;x<400;x+=step) {
      const px=x+(random()-.5)*step*.7,py=y+(random()-.5)*step*.7;
      if(ctx.isPointInPath(brainLeft,px,py)||ctx.isPointInPath(brainRight,px,py)) points.push({x:px,y:py});
    }
    while(points.length<count) {const x=random()*800-400,y=random()*700-350;if(ctx.isPointInPath(brainLeft,x,y)||ctx.isPointInPath(brainRight,x,y))points.push({x,y});}
    for(let i=points.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[points[i],points[j]]=[points[j],points[i]];}
    ctx.restore(); return points.slice(0,count);
  }

  function positionNodes(initial=false) {
    const random = seedRandom(4528);
    const anchors=[[-190,-190],[175,-175],[-255,0],[250,20],[-155,180],[150,185],[-82,-40],[88,40],[-80,265],[80,265],[0,0]];
    if(view==='brain') {
      const pool=brainPoints(accounts.length);
      for(const t of [...topics].sort((a,b)=>b.members.length-a.members.length)) {
        const anchor=anchors[t.topic];pool.sort((a,b)=>Math.hypot(a.x-anchor[0],a.y-anchor[1])-Math.hypot(b.x-anchor[0],b.y-anchor[1]));
        const positions=pool.splice(0,t.members.length);
        t.members.forEach((n,i)=>{n.tx=positions[i].x;n.ty=positions[i].y;});
      }
    } else if(view==='galaxy') {
      const sorted=[...topics].sort((a,b)=>b.members.length-a.members.length);
      sorted.forEach((t,ti)=>{
        const angle=ti*2.39996-.5, distance=ti===0?0:140+Math.sqrt(ti)*74;
        const cx=Math.cos(angle)*distance,cy=Math.sin(angle)*distance*.82;
        const radius=58+Math.sqrt(t.members.length)*6;
        t.members.forEach((n,i)=>{const a=i*2.39996,r=Math.sqrt((i+.5)/t.members.length)*radius;n.tx=cx+Math.cos(a)*r;n.ty=cy+Math.sin(a)*r;});
      });
    }
    accounts.forEach(n=>{n.hx=n.tx;n.hy=n.ty;});
    relaxContent(220);
    links=links.filter(e=>e.kind!=='shared');
    for(const edge of contentEdges)links.push({a:accounts[edge.i],b:accounts[edge.j],kind:'shared',topic:accounts[edge.i].topic,score:edge.score});
    nodes.forEach(n=>{if(initial){n.x=n.tx*.76;n.y=n.ty*.76;}if(reduceMotion){n.x=n.tx;n.y=n.ty;}});
    wake();
  }

  function relaxContent(iterations=80,pinned=null) {
    // Solve in world coordinates, independent of zoom, with real spring attraction.
    ctx.save();ctx.resetTransform();
    try {
      const accountIndex=new Map(accounts.map((n,i)=>[n,i]));
      const tagGroups=tags.map(tag=>({
        members:tag.members.map(n=>accountIndex.get(n)).filter(i=>i!=null),
        weights:tag.members.map(n=>ContentGraph.weightOf(n.row,tag.label))
      })).filter(group=>group.members.length>1);
      ContentGraph.relax(accounts,contentEdges,{iterations,mode:view,pinned,tagGroups,
        contains:view==='brain'?(x,y)=>ctx.isPointInPath(brainLeft,x,y)||ctx.isPointInPath(brainRight,x,y):null});
    } finally {ctx.restore();}
    for(const node of [...tags,...topics]){
      node.tx=node.members.reduce((sum,n)=>sum+n.tx,0)/node.members.length;
      node.ty=node.members.reduce((sum,n)=>sum+n.ty,0)/node.members.length;
    }
  }

  function graphViewport() {
    if(width<=700){const inset=width<450?70:0;return {x:(width-inset)/2,y:width<=500?490:440,w:Math.max(220,width-30-inset),h:width<=500?240:320};}
    const left=width>1150?300:250,right=width>1150?350:295;
    return {x:left+(width-left-right)/2,y:height*.49+8,w:width-left-right+65,h:height-190};
  }
  function fit() {
    const v=graphViewport();
    const bound=view==='galaxy'?1080:810;
    baseScale=Math.max(.2,Math.min(v.w/bound,v.h/790));
    targetCamera={x:v.x,y:v.y,z:baseScale};
    if(!camera.z||width<1)camera={...targetCamera};
    wake();
  }
  function resize() {
    const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;dpr=Math.min(devicePixelRatio||1,2);
    canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);fit();layoutRecap();
    if(recapTarget){const v=recapViewport(),z=baseScale*(recapTarget.kind==='up'?2.25:1.4);targetCamera={x:v.x-recapTarget.tx*z,y:v.y-recapTarget.ty*z,z};}
  }
  function screen(n){return {x:n.x*camera.z+camera.x,y:n.y*camera.z+camera.y};}
  function toWorld(x,y){return {x:(x-camera.x)/camera.z,y:(y-camera.y)/camera.z};}
  function nodeVisible(n){return activeTopic===null||n.topic===activeTopic||(selected?.neighbors||[]).includes(n)||(selected?.tagNodes||[]).includes(n)||(selected?.members||[]).includes(n);}
  function wake(){if(!graphPaused&&!document.hidden&&!frame)frame=requestAnimationFrame(tick);}
  function pauseGraph(){graphPaused=true;if(frame)cancelAnimationFrame(frame);frame=0;}
  function resumeGraph(){graphPaused=false;wake();}
  function tick(){
    frame=0;if(graphPaused||document.hidden)return;let unsettled=false;
    for(const n of nodes){const dx=n.tx-n.x,dy=n.ty-n.y;if(Math.abs(dx)+Math.abs(dy)>.05)unsettled=true;n.x+=dx*(reduceMotion?1:.085);n.y+=dy*(reduceMotion?1:.085);}
    const cameraBlend=reduceMotion?1:recapTarget?1-Math.pow(.9,INTRO_SPEED):.1;
    for(const key of ['x','y','z']){const delta=targetCamera[key]-camera[key];if(Math.abs(delta)>(key==='z'?.0001:.05))unsettled=true;camera[key]+=delta*cameraBlend;}
    draw(ctx,width,height,camera,{background:true});
    if(unsettled)frame=requestAnimationFrame(tick);
    else showCleanupCue();
  }

  function draw(g,w,h,cam,options={}) {
    const exporting=!!options.exporting,scale=exporting?1:dpr;
    g.setTransform(scale,0,0,scale,0,0);
    g.clearRect(0,0,w,h);g.fillStyle=theme.background;g.fillRect(0,0,w,h);
    if(!nodes.length){g.fillStyle=theme.muted;g.font=`13px ${FONT}`;g.textAlign='center';g.fillText('导入关注数据',w/2,h/2);return;}
    const project=n=>({x:n.x*cam.z+cam.x,y:n.y*cam.z+cam.y});
    // A very faint anatomical contour makes the metaphor readable without a solid icon.
    if(view==='brain'){
      g.save();g.translate(cam.x,cam.y);g.scale(cam.z,cam.z);g.strokeStyle=theme.outline;g.lineWidth=1/cam.z;g.stroke(brainLeft);g.stroke(brainRight);g.restore();
    }
    const highlight=exporting?null:hovered||selected||recapTarget;
    const related=highlight?new Set([highlight,...(highlight.tagNodes||[]),...(highlight.members||[]),...(highlight.neighbors||[])]):null;
    for(const e of links){
      const a=project(e.a),b=project(e.b);if(Math.max(a.x,b.x)<0||Math.min(a.x,b.x)>w||Math.max(a.y,b.y)<0||Math.min(a.y,b.y)>h)continue;
      let alpha=e.kind==='shared'?.16+e.score*.24:e.kind==='branch'?.22:.075;
      if(theme===SCHEMES.light)alpha*=1.2;
      if(!exporting&&activeTopic!==null&&e.a.topic!==activeTopic&&e.b.topic!==activeTopic)alpha*=.06;
      if(highlight){if(e.a===highlight||e.b===highlight){alpha=.65;}else if(related.has(e.a)&&related.has(e.b)){alpha=.38;}else alpha*=.25;}
      g.globalAlpha=alpha;g.strokeStyle=TOPICS[e.topic].color;g.lineWidth=e.kind==='branch'?.7:.45;
      g.beginPath();g.moveTo(a.x,a.y);const bend=e.kind==='branch'?12:3;
      g.quadraticCurveTo((a.x+b.x)/2-(b.y-a.y)*.09,(a.y+b.y)/2+(b.x-a.x)*.09+bend,b.x,b.y);g.stroke();
    }
    g.globalAlpha=1;
    for(const n of nodes){
      if(n.kind==='tag'&&n.members.length===1&&cam.z<baseScale*1.8&&n!==highlight)continue;
      const p=project(n);if(p.x<-50||p.x>w+50||p.y<-50||p.y>h+50)continue;
      const color=TOPICS[n.topic].color;
      let alpha=n.kind==='up'?(theme===SCHEMES.light?.88:.72):1;
      if(!exporting&&!nodeVisible(n))alpha*=.1;
      if(searchMatches&&!exporting&&!searchMatches.has(n.id)&&n.kind==='up')alpha*=.12;
      if(highlight&&!related.has(n))alpha*=.37;
      const radius=n.kind==='topic'?3.4:n.kind==='tag'?2.3:1.35;
      const r=radius*Math.max(.65,Math.min(cam.z,2));
      if(n===highlight){g.globalAlpha=alpha*.12;g.fillStyle=color;g.beginPath();g.arc(p.x,p.y,r*3.1,0,Math.PI*2);g.fill();}
      g.globalAlpha=alpha;g.fillStyle=n===highlight?theme.selected:color;g.beginPath();g.arc(p.x,p.y,r,0,Math.PI*2);g.fill();
      if(n===highlight){g.strokeStyle=color;g.lineWidth=.7;g.beginPath();g.arc(p.x,p.y,r+6,0,Math.PI*2);g.stroke();}
    }
    g.globalAlpha=1;
    // Labels use collision rejection so zooming reveals detail without text soup.
    const occupied=[];
    const candidates=[...topics,...tags.filter(t=>t.members.length>=3),...((exporting?options.names:cam.z>baseScale*2.1)?accounts:[])];
    if(highlight&&highlight.kind==='up'&&!candidates.includes(highlight))candidates.unshift(highlight);
    for(const n of candidates){
      if(!exporting&&!nodeVisible(n))continue;
      if(highlight&&!related.has(n)&&n.kind!=='topic')continue;
      if(n.kind==='tag'&&cam.z<baseScale*1.2&&n.members.length<8)continue;
      const p=project(n);const fontSize=n.kind==='topic'?12:n.kind==='tag'?9:9;
      g.font=`${n.kind==='topic'?'500':'400'} ${fontSize}px ${FONT}`;
      const label=n.kind==='topic'?TOPICS[n.topic].short:n.label;
      const tw=g.measureText(label).width;
      const bx=p.x-tw/2-4,by=p.y+(n.kind==='topic'?13:9),bw=tw+8,bh=fontSize+7;
      if(bx<5||bx+bw>w-5||by<0||by+bh>h)continue;
      if(n!==highlight&&occupied.some(b=>bx<b.x+b.w&&bx+bw>b.x&&by<b.y+b.h&&by+bh>b.y))continue;
      occupied.push({x:bx,y:by,w:bw,h:bh});
      g.textAlign='center';g.textBaseline='top';g.lineWidth=4;g.strokeStyle=theme.halo;g.strokeText(label,p.x,by+2);
      g.fillStyle=n.kind==='topic'?TOPICS[n.topic].color:n===highlight?theme.ink:theme.label;g.globalAlpha=n.kind==='topic'?.95:.8;g.fillText(label,p.x,by+2);
    }
    g.globalAlpha=1;
    if(!exporting)updateRecapBeacon();
  }

  function select(n) {
    stopRecap();
    selected=n;activeTopic=n.topic;renderInterests();$('results').hidden=true;
    const topic=TOPICS[n.topic];$('detail').style.setProperty('--topic',topic.color);
    let html=`<div class="node-kind">${n.kind==='up'?'UP 主':n.kind==='topic'?'内容大类':'内容标签'}${demo?' · 演示':''}</div><h2>${esc(n.label)}</h2>`;
    if(n.kind==='up'){
      html+=`<div class="tags">${n.row.tags.map(t=>`<span>${esc(t)}</span>`).join('')}</div>`;
      if(n.row.sign)html+=`<p>${esc(String(n.row.sign).slice(0,180))}</p>`;
      html+=`<div class="detail-stats">粉丝 ${esc(format(n.row.fans))} · ${n.row.last_days==null?'投稿时间未知':'距上次投稿 '+esc(n.row.last_days)+' 天'}</div>`;
      if(n.row.videos.length)html+=`<p>最近投稿<br>${n.row.videos.slice(0,2).map(esc).join('<br>')}</p>`;
      if(n.neighbors?.length)html+=`<p>内容相近</p><ul>${n.neighbors.map(other=>`<li><button data-node="${esc(other.id)}">${esc(other.label)} ↗</button></li>`).join('')}</ul>`;
      if(!demo)html+=`<a class="profile-link" href="https://space.bilibili.com/${encodeURIComponent(n.row.mid)}" target="_blank" rel="noopener noreferrer">去 B 站看看 TA ↗</a>`;
      else html+='<p>虚构示例账号 · 导入真实数据后可打开 B 站空间</p>';
    }else{
      html+=`<p>${n.members.length} 个 UP 主${n.kind==='topic'?' · 占全部关注的 '+(n.members.length/rows.length*100).toFixed(1)+'%':''}</p><div class="tags"><span>${esc(topic.name)}</span></div>`;
      html+='<ul>'+n.members.slice(0,35).map(m=>`<li><button data-node="${esc(m.id)}">${esc(m.label)} ↗</button></li>`).join('')+'</ul>';
      if(n.members.length>35)html+='<p>显示前 35 位，其他账号可通过搜索查看</p>';
    }
    $('detail-content').innerHTML=html;$('detail').hidden=false;
    $('detail-content').querySelectorAll('[data-node]').forEach(b=>b.addEventListener('click',()=>select(nodes.find(n=>n.id===b.dataset.node))));
    const v=graphViewport(),z=n.kind==='up'?baseScale*3.2:baseScale*1.65;
    targetCamera={x:v.x-n.tx*z,y:v.y-n.ty*z,z};wake();
  }
  function resetSelection(){stopRecap();selected=hovered=null;activeTopic=null;$('detail').hidden=true;$('hover-tip').hidden=true;renderInterests();fit();}
  function changeView(next){view=next;resetSelection();document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view)));positionNodes();fit();}
  function pick(x,y){let found=null,best=Infinity;for(const n of nodes){if(!nodeVisible(n))continue;const p=screen(n),d=Math.hypot(p.x-x,p.y-y);const hit=n.kind==='topic'?13:n.kind==='tag'?9:7;if(d<hit&&d<best){best=d;found=n;}}return found;}
  function zoom(factor,x=graphViewport().x,y=graphViewport().y){stopRecap();const old=targetCamera.z,z=Math.max(baseScale*.45,Math.min(baseScale*8,old*factor));targetCamera={x:x-(x-targetCamera.x)*z/old,y:y-(y-targetCamera.y)*z/old,z};wake();}

  canvas.addEventListener('wheel',e=>{e.preventDefault();const r=canvas.getBoundingClientRect();zoom(Math.exp(-e.deltaY*.0012),e.clientX-r.left,e.clientY-r.top);},{passive:false});
  canvas.addEventListener('pointerdown',e=>{if(e.button!==0)return;stopRecap();const r=canvas.getBoundingClientRect();pointer={x:e.clientX-r.left,y:e.clientY-r.top,id:e.pointerId};dragging=pick(pointer.x,pointer.y);moved=false;canvas.setPointerCapture(e.pointerId);$('hover-tip').hidden=true;});
  canvas.addEventListener('pointermove',e=>{
    const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
    if(pointer&&pointer.id===e.pointerId){const dx=x-pointer.x,dy=y-pointer.y;if(Math.abs(dx)+Math.abs(dy)>2)moved=true;
      if(dragging&&moved){const p=toWorld(x,y);dragging.tx=dragging.x=p.x;dragging.ty=dragging.y=p.y;if(dragging.kind==='up'){dragging.hx=p.x;dragging.hy=p.y;relaxContent(8,dragging);}}else if(moved){targetCamera.x+=dx;targetCamera.y+=dy;camera.x+=dx;camera.y+=dy;}
      pointer.x=x;pointer.y=y;wake();return;
    }
    const next=pick(x,y);if(next!==hovered){hovered=next;wake();}
    canvas.style.cursor=next?'pointer':'grab';$('hover-tip').hidden=!next||clean;
    if(next&&!clean){$('hover-tip').textContent=next.label+ (next.members?' · '+next.members.length+' 个 UP 主':'');$('hover-tip').style.left=Math.min(width-245,Math.max(8,x+15))+'px';$('hover-tip').style.top=Math.max(8,Math.min(height-45,y-30))+'px';}
  });
  function finishPointer(e){if(!pointer||pointer.id!==e.pointerId)return;if(!moved&&dragging&&!clean)select(dragging);if(moved&&dragging?.kind==='up'){relaxContent(100,dragging);wake();}pointer=null;dragging=null;}
  canvas.addEventListener('pointerup',finishPointer);canvas.addEventListener('pointercancel',()=>{pointer=null;dragging=null;});
  canvas.addEventListener('pointerleave',()=>{hovered=null;$('hover-tip').hidden=true;wake();});
  $('search').addEventListener('input',()=>{
    const q=$('search').value.trim().toLowerCase();$('results').replaceChildren();searchMatches=null;
    if(!q){$('results').hidden=true;wake();return;}
    const matches=nodes.filter(n=>(n.label+' '+(n.row?.tags.join(' ')||'')+' '+(n.row?.mid||'')).toLowerCase().includes(q));
    searchMatches=new Set(matches.map(n=>n.id));$('results').hidden=false;
    if(!matches.length)$('results').innerHTML='<div class="empty-result">没有找到，换个词试试</div>';
    matches.slice(0,30).forEach(n=>{const b=document.createElement('button');b.innerHTML=`${esc(n.label)}<small>${n.kind==='up'?'UP 主':n.kind==='topic'?'内容大类':'内容标签'} · ${esc(TOPICS[n.topic].name)}</small>`;b.addEventListener('click',()=>{select(n);$('search').value='';searchMatches=null;});$('results').appendChild(b);});wake();
  });
  $('search').addEventListener('focus',stopRecap);
  $('file').addEventListener('change',async()=>{
    const file=$('file').files[0];if(!file)return;
    try{if(file.size>30*1024*1024)throw new Error('文件超过 30 MB');const input=JSON.parse((await file.text()).replace(/^\uFEFF/,''));load(input,false);toast('已载入 '+rows.length+' 个账号，数据仅在本页处理');}catch(e){toast('导入失败：'+e.message);}finally{$('file').value='';}
  });
  document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>changeView(b.dataset.view)));
  $('close-detail').addEventListener('click',resetSelection);
  $('fit').addEventListener('click',resetSelection);$('zoom-in').addEventListener('click',()=>zoom(1.4));$('zoom-out').addEventListener('click',()=>zoom(1/1.4));
  $('wander').addEventListener('click',()=>{const pool=accounts.filter(n=>nodeVisible(n));if(pool.length)select(pool[Math.floor(Math.random()*pool.length)]);});
  function setClean(value){clean=value;$('app').classList.toggle('is-clean',clean);$('exit-clean').hidden=!clean;$('hover-tip').hidden=true;}
  $('clean').addEventListener('click',()=>setClean(true));$('exit-clean').addEventListener('click',()=>setClean(false));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(clean)setClean(false);else if(!$('export-dialog').open)resetSelection();$('results').hidden=true;}if(e.key==='/'&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)){e.preventDefault();$('search').focus();}});
  $('save').addEventListener('click',()=>$('export-dialog').showModal());$('close-export').addEventListener('click',()=>$('export-dialog').close());
  $('download').addEventListener('click',()=>{
    const out=document.createElement('canvas');out.width=2400;out.height=1600;const g=out.getContext('2d');
    const cam={x:1350,y:790,z:view==='galaxy'?1.55:1.8};
    draw(g,2400,1600,cam,{exporting:true,names:$('export-names').checked});
    g.textAlign='left';g.textBaseline='top';g.fillStyle=theme.muted;g.font=`22px ${FONT}`;g.fillText('B 站关注内容分析',105,85);
    g.fillStyle=theme.ink;g.font=`54px ${FONT}`;g.fillText({brain:'关注图谱 · 分区布局',galaxy:'关注图谱 · 聚类布局'}[view],105,210);
    g.font=`19px ${FONT}`;g.fillStyle=theme.muted;g.fillText(`${rows.length} 个 UP 主 / ${new Set(tags.map(t=>t.label)).size} 个标签 / ${topics.length} 个内容大类`,108,300);
    let y=450;for(const t of [...topics].sort((a,b)=>b.members.length-a.members.length)){g.fillStyle=t.color;g.beginPath();g.arc(117,y+10,4,0,Math.PI*2);g.fill();g.font=`20px ${FONT}`;g.fillText(t.name,140,y);g.fillStyle=theme.muted;g.font=`17px ${FONT}`;g.fillText((t.members.length/rows.length*100).toFixed(1)+'%',385,y+2);y+=59;}
    g.font=`15px ${FONT}`;g.fillStyle=theme.muted;g.fillText((demo?'演示数据 · 虚构账号   /   ':'')+'按内容标签归类',108,1475);
    out.toBlob(blob=>{if(!blob){toast('保存失败，请重试');return;}const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`bili-${view}${demo?'-demo':''}.png`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);$('export-dialog').close();toast('已保存关注图谱');},'image/png');
  });
  const graphStage=$('graph-stage'), cleanupStage=$('cleanup-stage'), edge=$('cleanup');
  const passage=$('passage'), cleanupFrame=$('cleanup-frame');
  let edgePointer=null, edgeDistance=0, suppressEdgeClick=false, cleanupReady=false, cleanupRequested=false;
  let sceneTimer=0, readableTimer=0, loadingTimer=0, invitationTimer=0, invitationEnd=0, graphScroll=0;

  function hideCleanupCue() {
    introFinished=false;edge.hidden=true;
    clearTimeout(invitationTimer);clearTimeout(invitationEnd);graphStage.classList.remove('is-inviting');
  }
  function showCleanupCue() {
    if(!introFinished||phase!=='graph'||document.hidden||!edge.hidden||edge.dataset.selectorReady!=='true')return;
    edge.hidden=false;invitationTimer=setTimeout(invite,450);
  }
  function invite() {
    if(reduceMotion||phase!=='graph'||document.hidden||edge.hidden)return;
    graphStage.classList.remove('is-inviting');
    graphStage.classList.add('is-inviting');
    clearTimeout(invitationEnd);
    invitationEnd=setTimeout(()=>graphStage.classList.remove('is-inviting'),1000);
  }
  function clearSceneTimers() {
    clearTimeout(sceneTimer);clearTimeout(readableTimer);clearTimeout(loadingTimer);
  }
  function prepareCleanup() {
    if(cleanupRequested)return;
    cleanupRequested=true;
    const embeddedSelector=$('selector-document');
    const html=embeddedSelector?JSON.parse(embeddedSelector.textContent):null;
    cleanupFrame.addEventListener('load',()=>{
      syncCleanupTheme();
      cleanupReady=true;
      if(phase==='waiting')revealCleanup();
    },{once:true});
    if(html)cleanupFrame.srcdoc=html;
    else cleanupFrame.src=edge.href;
  }
  function syncCleanupTheme() {
    const root=$('cleanup-frame').contentDocument?.documentElement;
    if(root)root.dataset.theme=prefersDark()?'dark':'light';
  }
  function revealCleanup() {
    if(!['interlude','waiting'].includes(phase))return;
    clearSceneTimers();phase='cleanup';
    cleanupStage.hidden=false;cleanupStage.inert=false;
    graphStage.hidden=true;
    passage.classList.add('is-leaving');
    sceneTimer=setTimeout(()=>{passage.hidden=true;passage.classList.remove('is-front','is-readable','is-leaving');},PASSAGE_EXIT_MS);
    $('back-to-map').focus({preventScroll:true});
  }
  function finishPassage() {
    if(!['interlude','waiting'].includes(phase))return;
    if(cleanupReady){revealCleanup();return;}
    phase='waiting';$('passage-status').textContent='正在打开清理页…';
    loadingTimer=setTimeout(()=>{if(phase==='waiting'){$('passage-status').textContent='未能打开清理页';$('cleanup-fallback').hidden=false;}},6000);
  }
  function beginCleanup() {
    if(!introFinished||!['graph','dragging'].includes(phase)||edge.hidden)return;
    stopRecap();
    clearSceneTimers();clearTimeout(invitationTimer);clearTimeout(invitationEnd);
    graphStage.classList.remove('is-inviting','is-rebounding');
    graphScroll=window.scrollY;phase='sliding';pauseGraph();
    $('hover-tip').hidden=true;$('results').hidden=true;
    document.body.classList.add('scene-locked');
    passage.hidden=false;passage.classList.remove('is-front','is-readable','is-leaving');
    $('passage-status').textContent='';$('cleanup-fallback').hidden=true;
    prepareCleanup();
    // Freeze the graph texture; only these two scene containers take part in the transition.
    graphStage.classList.add('is-sliding');
    graphStage.style.transform='translate3d(-100%,0,0)';
    graphStage.inert=true;
    sceneTimer=setTimeout(()=>{
      if(phase!=='sliding')return;
      phase='interlude';passage.classList.add('is-front');
      readableTimer=setTimeout(()=>{passage.classList.add('is-readable');$('skip-passage').focus({preventScroll:true});},30);
      sceneTimer=setTimeout(finishPassage,CLEANUP_TOTAL_MS-SLIDE_MS-PASSAGE_EXIT_MS);
    },SLIDE_MS);
  }
  function returnToGraph() {
    clearSceneTimers();phase='graph';edgePointer=null;edgeDistance=0;suppressEdgeClick=false;
    cleanupStage.hidden=true;cleanupStage.inert=true;
    passage.hidden=true;passage.classList.remove('is-front','is-readable','is-leaving');
    graphStage.classList.remove('is-sliding','is-rebounding','is-dragging','is-inviting');
    graphStage.hidden=false;graphStage.inert=false;graphStage.style.transform='';
    document.body.classList.remove('scene-locked');
    edge.style.setProperty('--pull-progress','0');
    window.scrollTo(0,graphScroll);resumeGraph();edge.focus({preventScroll:true});
  }
  function rebound() {
    phase='graph';edgePointer=null;
    graphStage.classList.remove('is-dragging');graphStage.classList.add('is-rebounding');
    graphStage.style.transform='translate3d(0,0,0)';edge.style.setProperty('--pull-progress','0');
    passage.hidden=true;
    sceneTimer=setTimeout(()=>{graphStage.classList.remove('is-rebounding');graphStage.style.transform='';resumeGraph();},reduceMotion?0:460);
  }
  edge.addEventListener('pointerenter',()=>{if(!edgePointer)invite();});
  edge.addEventListener('pointerdown',e=>{
    if(e.button!==0||phase!=='graph')return;
    stopRecap();
    clearSceneTimers();clearTimeout(invitationTimer);clearTimeout(invitationEnd);
    graphStage.classList.remove('is-inviting','is-rebounding');
    graphStage.classList.add('is-dragging');
    edgePointer={id:e.pointerId,x:e.clientX};edgeDistance=0;suppressEdgeClick=false;phase='dragging';
    pauseGraph();passage.hidden=false;edge.setPointerCapture(e.pointerId);
  });
  edge.addEventListener('pointermove',e=>{
    if(!edgePointer||edgePointer.id!==e.pointerId||phase!=='dragging')return;
    edgeDistance=Math.max(0,Math.min(innerWidth*.95,edgePointer.x-e.clientX));
    const threshold=Math.min(210,innerWidth*.25);
    graphStage.style.transform=`translate3d(${-edgeDistance}px,0,0)`;
    edge.style.setProperty('--pull-progress',String(Math.min(1,edgeDistance/threshold)));
  });
  edge.addEventListener('pointerup',e=>{
    if(!edgePointer||edgePointer.id!==e.pointerId)return;
    edgePointer=null;graphStage.classList.remove('is-dragging');
    if(edgeDistance>=Math.min(210,innerWidth*.25)){beginCleanup();return;}
    suppressEdgeClick=edgeDistance>6;
    rebound();
  });
  edge.addEventListener('pointercancel',()=>{if(phase==='dragging')rebound();});
  edge.addEventListener('dragstart',e=>e.preventDefault());
  edge.addEventListener('click',e=>{
    e.preventDefault();
    if(suppressEdgeClick){suppressEdgeClick=false;return;}
    beginCleanup();
  });
  $('skip-passage').addEventListener('click',finishPassage);
  $('back-to-map').addEventListener('click',returnToGraph);
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape'&&phase!=='graph'){e.preventDefault();returnToGraph();}
    else if(['Enter',' '].includes(e.key)&&['interlude','waiting'].includes(phase)){e.preventDefault();finishPassage();}
  });
  document.addEventListener('visibilitychange',()=>{
    if(document.hidden){
      recapResumeOnVisible=!introFinished&&recapCards.length>0;
      stopRecap(false,false);if(frame)cancelAnimationFrame(frame);frame=0;
    }else if(phase==='graph'){
      if(recapResumeOnVisible){recapResumeOnVisible=false;setRecapVisible(true);$('recap').classList.remove('is-paused');showRecap(recapIndex);advanceRecap();}
      wake();
    }
  });
  new ResizeObserver(resize).observe($('app'));
  syncTheme();
  const embedded=$('embedded-data');
  try{const input=embedded?JSON.parse(embedded.textContent):null;load(input===null?makeDemo():input,input===null);}catch(e){toast('数据加载失败：'+e.message);}
})();
