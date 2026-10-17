import glob
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
rows = json.loads((BASE / "combined.json").read_text(encoding="utf-8"))

done = set()
for lf in ("unfollow_log.json", "retry_log.json"):
    log = BASE / lf
    if log.exists():
        for r in json.loads(log.read_text(encoding="utf-8")):
            if r.get("ok"):
                done.add(str(r["mid"]))
rows = [r for r in rows if str(r["mid"]) not in done]

an = {}
for f in sorted(glob.glob(str(BASE / "analyze_out_*.json"))):
    for r in json.loads(Path(f).read_text(encoding="utf-8")):
        an[str(r["mid"])] = r

PROTECT_TOP = 50

for r in rows:
    a = an.get(str(r["mid"]), {})
    r["type"] = a.get("type", 0)
    r["type_name"] = a.get("type_name", "未分类")
    r["priority"] = a.get("priority", "低")
    r["unfollow"] = a.get("unfollow", False)
    r["why"] = a.get("reason", "")
    r.pop("reco", None)
    vr = r.get("visit_rank")
    r["protected"] = vr is not None and vr <= PROTECT_TOP
    if r["protected"]:
        r["unfollow"] = False
        note = f"最常访问 #{vr}（前 {PROTECT_TOP}）· 保护，不建议取关"
        r["why"] = (r["why"] + "；" + note) if r["why"] else note

(BASE / "combined.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

cnt = Counter(r["type_name"] for r in rows)
print("类型分布：")
for k, n in cnt.most_common():
    print(f"  {n:4}  {k}")
uf = sum(1 for r in rows if r["unfollow"])
pr = sum(1 for r in rows if r.get("protected"))
print(f"建议取关合计 {uf} / {len(rows)}（其中最常访问前 {PROTECT_TOP} 保护 {pr} 个）")

data = json.dumps(rows, ensure_ascii=False).replace("<", "\\u003c")
html = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B站关注筛选</title>
<style>
 :root{color-scheme:light;--bg:#fafaf8;--surface:#fff;--ink:#20262d;--muted:#737b87;--line:#e4e5e6;--accent:#7955a4;--hover:#f0edf6;--selected:#e9def8;--stripe:#f7f8fa;--label:#1468bc;--label-bg:#e6f0ff;--positive:#16814b;--positive-bg:#e4f6e9;--warning:#cf243d;--warning-bg:#ffe3e9;--medium:#896600;--medium-bg:#fff4c2;--medium-line:#dfc453;--tag:#65528f;--tag-bg:#eeeafd;--preview:#5c6370;font-family:Inter,'Segoe UI','Microsoft YaHei',sans-serif;font-synthesis:none}
 @media(prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;--bg:#090b10;--surface:#11131b;--ink:#eceef3;--muted:#9aa2b0;--line:#292d38;--accent:#c4a6ff;--hover:#222033;--selected:#392b51;--stripe:#151822;--label:#83baff;--label-bg:#172e4c;--positive:#7ce0a3;--positive-bg:#123526;--warning:#ff899b;--warning-bg:#3a1925;--medium:#f2d35e;--medium-bg:#3b3211;--medium-line:#79652c;--tag:#c4afff;--tag-bg:#2a2340;--preview:#b8bfcc}}
 :root[data-theme=dark]{color-scheme:dark;--bg:#090b10;--surface:#11131b;--ink:#eceef3;--muted:#9aa2b0;--line:#292d38;--accent:#c4a6ff;--hover:#222033;--selected:#392b51;--stripe:#151822;--label:#83baff;--label-bg:#172e4c;--positive:#7ce0a3;--positive-bg:#123526;--warning:#ff899b;--warning-bg:#3a1925;--medium:#f2d35e;--medium-bg:#3b3211;--medium-line:#79652c;--tag:#c4afff;--tag-bg:#2a2340;--preview:#b8bfcc}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);font-size:13px;line-height:1.7}
 button,input,select{font:inherit;color:inherit}
 button,input[type=checkbox],select{cursor:pointer}
 button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
 header{position:sticky;top:0;z-index:2;border-bottom:1px solid var(--line);background:var(--bg)}
 .toolbar{max-width:1600px;margin:auto;padding:12px 24px 10px}
 .filters,.actions,.button-group{display:flex;align-items:center;flex-wrap:wrap;gap:10px}
 .actions{margin-top:8px;gap:12px}
 .button-group{gap:6px}
 input[type=search]{flex:1 1 260px;min-width:160px;padding:7px 10px;border:1px solid var(--line);border-radius:5px;background:var(--surface)}
 input[type=search]::placeholder{color:var(--muted)}
 select{padding:7px 10px;max-width:240px;border:1px solid var(--line);border-radius:5px;background:var(--surface);font-size:12px}
 button{padding:5px 10px;border:1px solid var(--line);border-radius:5px;background:var(--surface);font-size:12px;transition:background .15s,border-color .15s}
 button:hover{background:var(--hover);border-color:var(--accent)}
 button.primary{background:var(--ink);color:var(--bg);border-color:var(--ink)}
 button.primary:hover{background:var(--accent);border-color:var(--accent);color:var(--surface)}
 button.reco{color:var(--accent)}
 #count{margin-left:auto;color:var(--accent);font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap}
 label.fl{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:12px;white-space:nowrap;cursor:pointer}
 input[type=checkbox]{accent-color:var(--accent)}
 #bar{display:block;margin-top:6px;color:var(--muted);font-size:11px}
 ul{list-style:none;max-width:1600px;margin:0 auto;padding:0 24px 32px}
 li{display:grid;grid-template-columns:17px minmax(0,1fr);gap:11px;align-items:start;padding:9px 12px;border-bottom:1px solid var(--line);border-radius:4px;background:var(--surface);cursor:pointer;transition:background .15s,box-shadow .15s}
 li:nth-child(even){background:var(--stripe)}
 li:hover{background:var(--hover)}
 li.sel{background:var(--selected);box-shadow:inset 3px 0 var(--accent)}
 li:has(.chk:focus-visible){outline:2px solid var(--accent);outline-offset:-2px}
 .chk{width:16px;height:16px;margin:4px 0 0}
 .account-heading{display:flex;align-items:center;flex-wrap:wrap;gap:3px 8px;min-height:24px}
 .name{font-size:15px;font-weight:600;line-height:1.5;overflow-wrap:anywhere}
 .mid{color:var(--muted);font-size:11px;font-variant-numeric:tabular-nums;white-space:nowrap}
 .row-extras{display:flex;align-items:flex-start;gap:8px;margin-top:3px}
 .row-preview{display:flex;gap:14px;flex:1;min-width:0;color:var(--preview);font-size:11px;line-height:1.6}
 .sign{flex:0 1 30%;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .vids{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .vids span+span::before{content:' · ';color:var(--muted)}
 .expand-row{flex:none;padding:0 3px;border:0;background:none;color:var(--accent);font-size:10px;line-height:1.8}
 .expand-row:hover{background:none;text-decoration:underline}
 .is-expanded .row-preview{display:block}
 .is-expanded .sign{white-space:normal;overflow:visible;overflow-wrap:anywhere}
 .is-expanded .vids{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;white-space:normal;overflow:visible}
 .is-expanded .vids span{padding:1px 5px;border:1px solid var(--line);border-radius:3px;overflow-wrap:anywhere;max-width:100%}
 .is-expanded .vids span+span::before{content:none}
 .lab,.tag,.tp,.pr,.prot{display:inline-block;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:400;line-height:1.8}
 .lab{color:var(--label);background:var(--label-bg);font-weight:600}
 .tag{color:var(--tag);background:var(--tag-bg);border:1px solid transparent}
 .tp{color:var(--positive);background:var(--positive-bg);font-weight:600}
 .tp.unf,.pr.高{color:var(--warning);background:var(--warning-bg);font-weight:600}
 .pr{color:var(--muted);border:1px solid var(--line)}
 .pr.高{border-color:color-mix(in srgb,var(--warning) 35%,transparent)}
 .pr.中{color:var(--medium);background:var(--medium-bg);border-color:var(--medium-line)}
 .prot{color:var(--positive);background:var(--positive-bg);border:1px solid color-mix(in srgb,var(--positive) 35%,transparent)}
 .why{color:var(--warning);font-size:12px;line-height:1.6;margin-top:2px;overflow-wrap:anywhere}
 .is-recommended .why{color:var(--warning)}
 a{color:var(--label);text-decoration:none;font-size:11px}
 a:hover{text-decoration:underline}
 .profile-link{margin-left:auto;padding:0 0 0 8px;white-space:nowrap}
 @media(max-width:700px){.toolbar{padding:10px 14px}.filters{gap:6px}input[type=search]{flex-basis:100%;width:100%}select{min-width:0;max-width:100%;flex:1 1 90px}.fl{flex-basis:100%}.actions{gap:8px}.actions .button-group{gap:5px}button{padding:5px 8px;font-size:11px}#count{margin-left:0}ul{padding:0 8px 24px}li{padding:8px;gap:9px}.name{font-size:14px}.profile-link{margin-left:0}.account-heading{gap:3px 6px}.mid{flex-basis:100%;font-size:10px}.row-preview{display:block}.sign{display:none}.is-expanded .sign{display:block}}
 @media(prefers-reduced-motion:reduce){li,button{transition:none}}
</style></head><body>
<header>
 <div class="toolbar">
 <div class="filters">
  <input id="q" type="search" placeholder="搜索名称 / 内容 / 签名 / 视频" aria-label="搜索账号">
  <select id="cat" aria-label="内容分类"></select>
  <select id="typ" aria-label="清理类型"></select>
  <select id="pri" aria-label="优先级"><option value="">全部优先级</option><option>高</option><option>中</option><option>低</option></select>
  <label class="fl"><input type="checkbox" id="onlyReco"> 只看建议取关</label>
 </div>
 <div class="actions">
 <div class="button-group">
  <button onclick="selVis(1)">全选(可见)</button>
  <button onclick="selVis(0)">清空(可见)</button>
  <button class="reco" onclick="selReco(1)">勾选全部建议</button>
 </div>
 <div class="button-group">
  <button onclick="sortBy('priority')">按优先级</button>
  <button onclick="sortBy('last_days')">按停更</button>
  <button onclick="sortBy('fans')">按粉丝</button>
 </div>
  <span id="count" role="status" aria-live="polite">已选 0</span>
  <button class="primary" onclick="exportSel()">导出选中 unfollow.txt</button>
 </div>
  <span id="bar"></span>
 </div>
</header><ul id="list"></ul>
<script>
const DATA=__DATA__;
let order=DATA.map((_,i)=>i), selected=new Set(), expanded=new Set();
const cats=[...new Set(DATA.map(r=>r.label||''))].sort((a,b)=>DATA.filter(r=>r.label===b).length-DATA.filter(r=>r.label===a).length);
cat.innerHTML='<option value="">全部内容</option>'+cats.map(c=>`<option>${esc(c)} (${DATA.filter(r=>r.label===c).length})</option>`).join('');
const types=[...new Set(DATA.map(r=>r.type+':'+r.type_name))].sort((a,b)=>a.localeCompare(b));
typ.innerHTML='<option value="">全部类型</option>'+types.map(t=>{const[id,nm]=t.split(':');const c=DATA.filter(r=>r.type===+id).length;return `<option value="${id}">${id} ${esc(nm)} (${c})</option>`}).join('');
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function fmtFans(n){if(n==null)return '?';if(n>=100000000)return (n/100000000).toFixed(1)+'亿';if(n>=10000)return (n/10000).toFixed(1)+'万';return ''+n;}
function match(r){const q=document.getElementById('q').value.trim().toLowerCase();
  if(document.getElementById('onlyReco').checked&&!r.unfollow)return false;
  if(cat.value&&!cat.value.startsWith(r.label+' ('))return false;
  if(typ.value!==''&&String(r.type)!==typ.value)return false;
  if(pri.value&&r.priority!==pri.value)return false;
  if(!q)return true;
  const hay=(r.uname+' '+(r.sign||'')+' '+(r.official||'')+' '+r.label+' '+r.type_name+' '+r.mid+' '+(r.videos||[]).join(' ')).toLowerCase();
  return hay.includes(q);}
function render(){const ul=document.getElementById('list');ul.innerHTML='';let shown=0;
  for(const idx of order){const r=DATA[idx];if(!match(r))continue;shown++;
    const li=document.createElement('li');li.dataset.mid=String(r.mid);li.classList.toggle('sel',selected.has(r.mid));li.classList.toggle('is-recommended',!!r.unfollow);li.classList.toggle('is-expanded',expanded.has(r.mid));
    li.innerHTML=`<input class="chk" type="checkbox" aria-label="选择 ${esc(r.uname)}" ${selected.has(r.mid)?'checked':''}>
      <div>
        <div class="account-heading"><span class="name">${esc(r.uname)}</span><span class="lab">${esc(r.label)}</span>${r.official?`<span class="tag">${esc(r.official)}</span>`:''}<span class="tp ${r.unfollow?'unf':''}">${r.type} ${esc(r.type_name)}</span><span class="pr ${r.priority}">${esc(r.priority)}</span>${r.protected?`<span class="prot">保护 #${r.visit_rank}</span>`:''}<span class="mid">UID ${r.mid} · 粉丝 ${fmtFans(r.fans)}${r.level!=null?' · Lv'+r.level:''}${r.last_days!=null?' · 停更'+r.last_days+'天':''}</span><a class="profile-link" href="${r.space}" target="_blank" rel="noopener noreferrer">空间 ↗</a></div>
        ${r.why?`<div class="why">↳ ${esc(r.why)}</div>`:''}
        <div class="row-extras"><div class="row-preview" id="details-${r.mid}">${r.sign?`<div class="sign">${esc(r.sign)}</div>`:''}<div class="vids">${(r.videos||[]).map(t=>`<span>${esc(t)}</span>`).join('')||'<i>(没有抓到投稿)</i>'}</div></div><button class="expand-row" aria-label="展开或收起 ${esc(r.uname)} 的签名和投稿" aria-controls="details-${r.mid}" aria-expanded="${expanded.has(r.mid)}">${expanded.has(r.mid)?'收起':'展开'}</button></div>
      </div>`;
    const checkbox=li.querySelector('.chk');
    const setSelected=value=>{checkbox.checked=value;value?selected.add(r.mid):selected.delete(r.mid);li.classList.toggle('sel',value);upd()};
    checkbox.addEventListener('change',()=>setSelected(checkbox.checked));
    li.querySelector('.expand-row').addEventListener('click',e=>{
      const open=!expanded.has(r.mid);open?expanded.add(r.mid):expanded.delete(r.mid);li.classList.toggle('is-expanded',open);
      e.currentTarget.setAttribute('aria-expanded',String(open));e.currentTarget.textContent=open?'收起':'展开';
    });
    li.addEventListener('click',e=>{
      if(e.target.closest('input,a,button,label,select,textarea,[contenteditable]'))return;
      const selection=window.getSelection();if(selection&&!selection.isCollapsed&&li.contains(selection.anchorNode))return;
      setSelected(!checkbox.checked);
    });
    ul.appendChild(li);}
  document.getElementById('bar').textContent=`显示 ${shown} / 共 ${DATA.length}`;upd();}
function upd(){document.getElementById('count').textContent='已选 '+selected.size}
function selVis(v){for(const r of DATA){if(match(r)){v?selected.add(r.mid):selected.delete(r.mid)}}render()}
function selReco(v){for(const r of DATA){if(r.unfollow){v?selected.add(r.mid):selected.delete(r.mid)}}render()}
function sortBy(k){const ord={"高":0,"中":1,"低":2};
  order=[...order].sort((a,b)=>{const x=DATA[a][k],y=DATA[b][k];
    if(k==='priority')return ord[x]-ord[y];
    if(typeof x==='number'||typeof y==='number')return (y??-1)-(x??-1);
    return String(x||'').localeCompare(String(y||''),'zh')});render()}
function exportSel(){if(!selected.size){alert('还没选任何账号');return}
  const lines=[...selected];
  const blob=new Blob([lines.join('\n')+'\n'],{type:'text/plain'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='unfollow.txt';a.click();
  navigator.clipboard?.writeText(lines.join('\n')).then(()=>alert('已导出 unfollow.txt 并复制到剪贴板（'+lines.length+'）')).catch(()=>alert('已导出 unfollow.txt（'+lines.length+'）'))}
['q','cat','typ','pri','onlyReco'].forEach(id=>document.getElementById(id).addEventListener('input',render));
render();
</script></body></html>"""
(BASE / "selector.html").write_text(html.replace("__DATA__", data), encoding="utf-8")
print("已更新 selector.html")
