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

for r in rows:
    a = an.get(str(r["mid"]), {})
    r["type"] = a.get("type", 0)
    r["type_name"] = a.get("type_name", "未分类")
    r["priority"] = a.get("priority", "低")
    r["unfollow"] = a.get("unfollow", False)
    r["why"] = a.get("reason", "")
    r.pop("reco", None)

(BASE / "combined.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

cnt = Counter(r["type_name"] for r in rows)
print("类型分布：")
for k, n in cnt.most_common():
    print(f"  {n:4}  {k}")
uf = sum(1 for r in rows if r["unfollow"])
print(f"建议取关合计 {uf} / {len(rows)}")

data = json.dumps(rows, ensure_ascii=False)
html = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>B站关注筛选</title>
<style>
 body{font-family:system-ui,'Microsoft YaHei',sans-serif;margin:0;background:#f5f6f8;color:#111}
 header{position:sticky;top:0;background:#fff;padding:10px 14px;box-shadow:0 1px 6px #0001;z-index:2;line-height:2}
 input[type=search]{width:240px;padding:7px 10px;border:1px solid #ccc;border-radius:8px;font-size:14px}
 select{padding:7px;border:1px solid #ccc;border-radius:8px;font-size:13px;max-width:200px}
 button{padding:6px 11px;margin-left:5px;border:1px solid #ccc;border-radius:8px;background:#fff;cursor:pointer;font-size:13px}
 button.primary{background:#fb7299;color:#fff;border-color:#fb7299}
 button.reco{background:#fff1e6;border-color:#f60;color:#a40}
 #count{font-weight:600;color:#fb7299;margin-left:8px}
 label.fl{margin-left:8px;font-size:13px}
 ul{list-style:none;margin:0;padding:0}
 li{display:flex;gap:10px;align-items:flex-start;padding:9px 14px;border-bottom:1px solid #eee;background:#fff}
 li:nth-child(even){background:#fafafa} li.sel{background:#fff0f5}
 .chk{margin-top:3px;transform:scale(1.25)}
 .name{font-weight:600} .mid{color:#999;font-size:12px}
 .sign{color:#777;font-size:12px;margin-top:1px;word-break:break-word}
 .vids{color:#555;font-size:12px;margin-top:3px}
 .vids span{display:inline-block;background:#f0f1f5;border-radius:6px;padding:1px 6px;margin:1px 4px 1px 0}
 .lab{display:inline-block;font-size:12px;font-weight:600;padding:1px 8px;border-radius:8px;background:#e7f0ff;color:#1a5fb4;margin-right:6px}
 .tag{display:inline-block;font-size:11px;padding:1px 6px;border-radius:6px;background:#eef;color:#446;margin-left:5px}
 .tp{display:inline-block;font-size:11px;font-weight:600;padding:1px 7px;border-radius:6px;margin-left:6px;background:#e8f8e8;color:#2a7}
 .tp.unf{background:#ffe0e6;color:#c00}
 .pr{display:inline-block;font-size:11px;padding:0 6px;border-radius:6px;margin-left:4px;border:1px solid #ccc;color:#666}
 .pr.高{background:#ffdede;color:#c00;border-color:#fbb}
 .pr.中{background:#fff3d6;color:#a80;border-color:#ee4}
 .why{color:#c00;font-size:12px;margin-top:2px}
 a{color:#4a90d9;text-decoration:none;font-size:12px}
 #bar{color:#666;font-size:13px;margin-left:8px}
</style></head><body>
<header>
  <input id="q" type="search" placeholder="搜索 名称/内容/签名/视频…">
  <select id="cat"></select>
  <select id="typ"></select>
  <select id="pri"><option value="">全部优先级</option><option>高</option><option>中</option><option>低</option></select>
  <label class="fl"><input type="checkbox" id="onlyReco"> 只看建议取关</label>
  <button onclick="selVis(1)">全选(可见)</button>
  <button onclick="selVis(0)">清空(可见)</button>
  <button class="reco" onclick="selReco(1)">勾选全部建议</button>
  <button onclick="sortBy('priority')">按优先级</button>
  <button onclick="sortBy('last_days')">按停更</button>
  <button onclick="sortBy('fans')">按粉丝</button>
  <span id="count">已选 0</span>
  <button class="primary" onclick="exportSel()">导出选中 unfollow.txt</button>
  <span id="bar"></span>
</header><ul id="list"></ul>
<script>
const DATA=__DATA__;
let order=DATA.map((_,i)=>i), selected=new Set();
const cats=[...new Set(DATA.map(r=>r.label))].sort((a,b)=>DATA.filter(r=>r.label===b).length-DATA.filter(r=>r.label===a).length);
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
  const hay=(r.uname+' '+(r.sign||'')+' '+(r.official||'')+' '+r.label+' '+r.type_name+' '+r.mid+' '+r.videos.join(' ')).toLowerCase();
  return hay.includes(q);}
function render(){const ul=document.getElementById('list');ul.innerHTML='';let shown=0;
  for(const idx of order){const r=DATA[idx];if(!match(r))continue;shown++;
    const li=document.createElement('li');if(selected.has(r.mid))li.className='sel';
    li.innerHTML=`<input class="chk" type="checkbox" ${selected.has(r.mid)?'checked':''}>
      <div>
        <div><span class="lab">${esc(r.label)}</span><span class="name">${esc(r.uname)}</span> <span class="mid">uid ${r.mid} · 粉丝 ${fmtFans(r.fans)}${r.level!=null?' · Lv'+r.level:''}${r.last_days!=null?' · 停更'+r.last_days+'天':''}</span>${r.official?`<span class="tag">${esc(r.official)}</span>`:''}<span class="tp ${r.unfollow?'unf':''}">${r.type} ${esc(r.type_name)}</span><span class="pr ${r.priority}">${esc(r.priority)}</span></div>
        ${r.why?`<div class="why">↳ ${esc(r.why)}</div>`:''}
        ${r.sign?`<div class="sign">${esc(r.sign)}</div>`:''}
        <div class="vids">${r.videos.map(t=>`<span>${esc(t)}</span>`).join('')||'<i>(没有抓到投稿)</i>'}</div>
        <a href="${r.space}" target="_blank">空间</a>
      </div>`;
    li.querySelector('.chk').addEventListener('change',e=>{if(e.target.checked){selected.add(r.mid);li.classList.add('sel')}else{selected.delete(r.mid);li.classList.remove('sel')}upd()});
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
