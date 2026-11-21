/** The self-contained HTML report template, identical to the Python/JVM implementations. */
export const HTML_TEMPLATE = String.raw`<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>APK Diff Report</title>
<style>
  :root { --bg:#f7f8fa; --card:#fff; --text:#1f2329; --muted:#646a73; --border:#e5e6eb;
          --red:#d92c20; --green:#0f9d58; --blue:#2563eb; --accent:#f2f3f5; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }
  .wrap { max-width:1280px; margin:0 auto; padding:28px 24px 64px; }
  h1 { font-size:24px; margin:0 0 4px; }
  h2 { font-size:17px; margin:28px 0 12px; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:20px; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }
  .card .label { color:var(--muted); font-size:12px; }
  .card .value { font-size:20px; font-weight:600; margin-top:4px; }
  .card .delta { font-size:13px; margin-top:2px; }
  .up { color:var(--red); } .down { color:var(--green); } .flat { color:var(--muted); }
  .panel { background:var(--card); border:1px solid var(--border); border-radius:10px; margin-top:16px; overflow:hidden; }
  .toolbar { display:flex; gap:10px; padding:12px 14px; border-bottom:1px solid var(--border); align-items:center; flex-wrap:wrap; }
  .toolbar input { flex:1; min-width:200px; padding:7px 10px; border:1px solid var(--border); border-radius:6px; font-size:13px; background:#fff; color:var(--text); }
  .pill { padding:4px 10px; border-radius:99px; background:var(--accent); font-size:12px; cursor:pointer; border:1px solid transparent; }
  .pill.active { background:var(--blue); color:#fff; }
  table { width:100%; border-collapse:collapse; }
  th,td { padding:8px 12px; text-align:left; border-bottom:1px solid var(--border); vertical-align:top; }
  th { font-size:12px; color:var(--muted); font-weight:500; background:#fafbfc; position:sticky; top:0; cursor:pointer; user-select:none; }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
  tr:hover td { background:#fafbfc; }
  .tag { display:inline-block; min-width:44px; text-align:center; padding:1px 7px; border-radius:4px; font-size:12px; }
  .tag.added { background:#e8f7ee; color:var(--green); }
  .tag.deleted { background:#fdecea; color:var(--red); }
  .tag.modified { background:#fff4e5; color:#b76e00; }
  .tag.renamed { background:#eef2ff; color:var(--blue); }
  .name { font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:12.5px; word-break:break-all; }
  .detail { color:var(--muted); font-size:11.5px; margin-top:2px; }
  .bar { height:4px; border-radius:2px; margin-top:4px; background:var(--accent); }
  .bar i { display:block; height:100%; border-radius:2px; }
  .warn { background:#fff8e6; border:1px solid #ffe0a3; border-radius:8px; padding:10px 14px; margin-top:16px; font-size:12.5px; }
  footer { color:var(--muted); font-size:12px; margin-top:24px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>APK Diff Report</h1>
  <div class="sub">旧: __OLD__ &nbsp;·&nbsp; 新: __NEW__ &nbsp;·&nbsp; 指标: __METRIC__</div>
  <div class="cards">__CARDS__</div>
  <div class="panel">__CLASS_TABLE__</div>
  <div class="panel">__RES_TABLE__</div>
  __WARNINGS__
  <footer>由 apkdiff 生成 · 类体积为 DEX 归属字节，压缩值按各 dex 压缩率估算</footer>
</div>
<script>
function bindTable(inputId, tableId, pills) {
  const input = document.getElementById(inputId);
  const table = document.getElementById(tableId);
  const tbody = table.querySelector('tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  let status = 'all';
  function apply() {
    const q = input.value.toLowerCase();
    rows.forEach(r => {
      const text = r.dataset.search.toLowerCase();
      const okStatus = status === 'all' || r.dataset.status === status;
      r.style.display = (okStatus && text.includes(q)) ? '' : 'none';
    });
  }
  input.addEventListener('input', apply);
  pills.forEach(p => p.addEventListener('click', () => {
    document.querySelectorAll('[data-pill-group="' + tableId + '"]').forEach(x => x.classList.remove('active'));
    p.classList.add('active'); status = p.dataset.status; apply();
  }));
  table.querySelectorAll('th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const idx = Array.from(th.parentNode.children).indexOf(th);
      const dir = th.dataset.dir === 'asc' ? -1 : 1;
      th.dataset.dir = dir === 1 ? 'asc' : 'desc';
      const sorted = rows.slice().sort((a,b) => {
        const av=a.children[idx].dataset.v, bv=b.children[idx].dataset.v;
        const an=Number(av), bn=Number(bv);
        if (!isNaN(an) && !isNaN(bn)) return (an-bn)*dir;
        return av.localeCompare(bv)*dir;
      });
      sorted.forEach(r => tbody.appendChild(r));
    });
  });
}
__JS_BIND__
</script>
</body>
</html>
`;
