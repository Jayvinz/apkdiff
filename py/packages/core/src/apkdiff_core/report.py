"""Render diff results for humans: console / JSON / HTML / Markdown.

diff.py produces Change objects; this module turns them into four outputs:

    console   terminal tables with + / - / ~ markers
    JSON      complete structured data for tools
    HTML      self-contained page with search, sorting and status filters
    Markdown  tables for a repository or PR diff

All formats share DiffResult and the size formatters (human_size/human_delta),
so the same number reads identically everywhere.

JSON stores exact integer byte counts; only human-facing console/HTML/Markdown
convert to KB with two decimals.
"""

from __future__ import annotations

import html
import json
import unicodedata
from pathlib import Path

from .diff import ADDED, DELETED, MODIFIED, RENAMED, STATUS_LABEL, Change, DiffResult
from .util import human_delta, human_size

STATUS_MARK = {ADDED: "+", DELETED: "-", MODIFIED: "~", RENAMED: ">"}


def _metric_unit(metric: str) -> str:
    return "APK 压缩字节" if metric == "compressed" else "未压缩字节"


def _write_text(path: str, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _display_width(text))


def _by_impact(changes: list[Change], metric: str) -> list[Change]:
    return sorted(changes, key=lambda c: abs(c.size_for(metric)), reverse=True)


def _print_table(title: str, changes: list[Change], metric: str, limit: int) -> None:
    print()
    print(f"{title}  (共 {len(changes)} 项，显示前 {min(limit, len(changes))} 项)")
    if not changes:
        print("  （无）")
        return
    shown = _by_impact(changes, metric)[:limit]
    name_w = min(72, max(_display_width(c.key) for c in shown))
    name_w = max(name_w, 12)
    old_w, new_w, delta_w = 11, 11, 13
    header = (
        f"  {'':2} {'状态':<6} {_pad('名称', name_w)} "
        f"{_pad('旧', old_w)} {_pad('新', new_w)} {_pad('Δ', delta_w)}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for c in shown:
        name = c.key
        if _display_width(name) > name_w:
            name = name[: name_w - 3] + "..."
        old = c.old_for(metric)
        new = c.new_for(metric)
        delta = c.size_for(metric)
        print(
            f"  {STATUS_MARK.get(c.status, '?')}  {_pad(STATUS_LABEL.get(c.status, c.status), 6)} "
            f"{_pad(name, name_w)} {_pad(human_size(old), old_w)} "
            f"{_pad(human_size(new), new_w)} {_pad(human_delta(delta), delta_w)}"
        )
        if c.status == RENAMED and c.detail.get("renamed_from"):
            print(f"       └─ 原路径: {c.detail['renamed_from']}")
        if c.detail.get("breakdown_delta"):
            parts = [
                f"{k} {human_delta(v)}" for k, v in c.detail["breakdown_delta"].items() if v
            ]
            if parts:
                print(f"       └─ 明细: {' '.join(parts)}")


def print_console(result: DiffResult, metric: str = "compressed", top: int = 30,
                  full: bool = False) -> None:
    s = result.summary
    limit = 10**9 if full else top
    unit = _metric_unit(metric)

    print("=" * 78)
    print("APK DIFF REPORT")
    print("=" * 78)
    print(f"  旧版本: {result.old.path}")
    print(f"  新版本: {result.new.path}")
    print(f"  排序/主指标: {unit}")
    print()
    print("  ── 包体总览 ──")
    print(
        f"  APK 文件          {human_size(s['old_apk_size'])} → "
        f"{human_size(s['new_apk_size'])}   Δ {human_delta(s['apk_size_delta'])}"
    )
    print(
        f"  代码(DEX,估算压缩) {human_size(s['old_class_compressed'])} → "
        f"{human_size(s['new_class_compressed'])}   Δ {human_delta(s['class_compressed_delta'])}"
    )
    print(
        f"  代码(DEX,归属原始) {human_size(s['old_class_bytes'])} → "
        f"{human_size(s['new_class_bytes'])}   Δ {human_delta(s['class_bytes_delta'])}"
    )
    print(
        f"  资源(压缩)        {human_size(s['old_resource_compressed'])} → "
        f"{human_size(s['new_resource_compressed'])}   Δ {human_delta(s['resource_compressed_delta'])}"
    )
    print(
        f"  资源(原始)        {human_size(s['old_resource_bytes'])} → "
        f"{human_size(s['new_resource_bytes'])}   Δ {human_delta(s['resource_bytes_delta'])}"
    )
    print()
    print("  ── 变更统计 ──")
    print(
        f"  类:   新增 {s['class_added']:>4}  删除 {s['class_deleted']:>4}  "
        f"修改 {s['class_modified']:>4}   (旧 {s['class_count_old']} → 新 {s['class_count_new']})"
    )
    print(
        f"  资源: 新增 {s['resource_added']:>4}  删除 {s['resource_deleted']:>4}  "
        f"修改 {s['resource_modified']:>4}  重命名 {s['resource_renamed']:>4}"
    )

    _print_table("代码类变更", result.classes, metric, limit)
    _print_table("资源文件变更", result.resources, metric, limit)

    warnings = result.old.warnings + result.new.warnings
    if warnings:
        print()
        print(f"  ⚠ 解析警告 {len(warnings)} 条:")
        for w in warnings[:20]:
            print(f"    - {w}")
        if len(warnings) > 20:
            print(f"    ... 另有 {len(warnings) - 20} 条")


def build_json(result: DiffResult, metric: str) -> dict:
    return {
        "schema_version": 1,
        "metric": metric,
        "old": {"path": result.old.path, "file_size": result.old.file_size,
                "warnings": result.old.warnings},
        "new": {"path": result.new.path, "file_size": result.new.file_size,
                "warnings": result.new.warnings},
        "summary": result.summary,
        "classes": [c.as_dict() for c in _by_impact(result.classes, metric)],
        "resources": [c.as_dict() for c in _by_impact(result.resources, metric)],
    }


def write_json(result: DiffResult, path: str, metric: str) -> None:
    _write_text(path, json.dumps(build_json(result, metric), ensure_ascii=False, indent=2))


def write_markdown(result: DiffResult, path: str, metric: str) -> None:
    s = result.summary
    lines = [
        "# APK Diff Report",
        "",
        f"- 旧版本: `{result.old.path}`",
        f"- 新版本: `{result.new.path}`",
        f"- 主指标: {_metric_unit(metric)}",
        "",
        "## 总览",
        "",
        "| 指标 | 旧 | 新 | Δ |",
        "| --- | ---: | ---: | ---: |",
    ]
    rows = [
        ("APK 文件", s["old_apk_size"], s["new_apk_size"], s["apk_size_delta"]),
        ("代码 (DEX 归属, 原始)", s["old_class_bytes"], s["new_class_bytes"], s["class_bytes_delta"]),
        ("代码 (DEX 归属, 压缩估算)", s["old_class_compressed"], s["new_class_compressed"], s["class_compressed_delta"]),
        ("资源 (原始)", s["old_resource_bytes"], s["new_resource_bytes"], s["resource_bytes_delta"]),
        ("资源 (压缩)", s["old_resource_compressed"], s["new_resource_compressed"], s["resource_compressed_delta"]),
    ]
    for name, old, new, delta in rows:
        lines.append(f"| {name} | {human_size(old)} | {human_size(new)} | {human_delta(delta)} |")
    lines += [
        "",
        "## 统计",
        "",
        f"- 类: 新增 {s['class_added']} / 删除 {s['class_deleted']} / 修改 {s['class_modified']}",
        f"- 资源: 新增 {s['resource_added']} / 删除 {s['resource_deleted']} / "
        f"修改 {s['resource_modified']} / 重命名 {s['resource_renamed']}",
        "",
    ]

    def table(title: str, changes: list[Change]) -> None:
        lines.extend([f"## {title}", ""])
        if not changes:
            lines.append("（无）")
            return
        lines.extend(["| 状态 | 名称 | 旧 | 新 | Δ |", "| --- | --- | ---: | ---: | ---: |"])
        for c in _by_impact(changes, metric):
            old = c.old_for(metric)
            new = c.new_for(metric)
            name = c.key.replace("|", "\\|")
            extra = f" ← `{c.detail['renamed_from']}`" if c.detail.get("renamed_from") else ""
            lines.append(
                f"| {STATUS_LABEL.get(c.status, c.status)} | `{name}`{extra} | "
                f"{human_size(old)} | {human_size(new)} | {human_delta(c.size_for(metric))} |"
            )
        lines.append("")

    table("代码类变更", result.classes)
    table("资源文件变更", result.resources)
    _write_text(path, "\n".join(lines))


_HTML_TEMPLATE = r"""<!DOCTYPE html>
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
"""


def _html_rows(changes: list[Change], metric: str) -> str:
    if not changes:
        return '<tr><td colspan="6" class="detail">（无变更）</td></tr>'
    max_impact = max(abs(c.size_for(metric)) for c in changes) or 1
    parts = []
    for c in _by_impact(changes, metric):
        old = c.old_for(metric)
        new = c.new_for(metric)
        delta = c.size_for(metric)
        cls = "up" if delta > 0 else ("down" if delta < 0 else "flat")
        bar_color = "var(--red)" if delta > 0 else "var(--green)"
        width = max(2, round(abs(delta) / max_impact * 100))
        detail_parts = []
        if c.detail.get("renamed_from"):
            detail_parts.append(f"原路径 {html.escape(c.detail['renamed_from'])}")
        if c.detail.get("breakdown_delta"):
            detail_parts.append(" ".join(
                f"{k} {human_delta(v)}" for k, v in c.detail["breakdown_delta"].items() if v
            ))
        if c.detail.get("dex"):
            detail_parts.append(f"dex: {html.escape(str(c.detail['dex']))}")
        detail = " · ".join(detail_parts)
        detail_html = f'<div class="detail">{detail}</div>' if detail else ""
        parts.append(
            f'<tr data-status="{c.status}" data-search="{html.escape(c.key.lower())}">'
            f'<td><span class="tag {c.status}">{STATUS_LABEL.get(c.status, c.status)}</span></td>'
            f'<td><div class="name">{html.escape(c.key)}</div>{detail_html}'
            f'<div class="bar"><i style="width:{width}%;background:{bar_color}"></i></div></td>'
            f'<td class="num" data-v="{old}">{human_size(old)}</td>'
            f'<td class="num" data-v="{new}">{human_size(new)}</td>'
            f'<td class="num {cls}" data-v="{delta}">{human_delta(delta)}</td>'
            f'<td class="num" data-v="{abs(delta)}">{human_size(abs(delta))}</td>'
            f'</tr>'
        )
    return "".join(parts)


def _html_table(table_id: str, title: str, changes: list[Change], metric: str) -> str:
    counts = {s: sum(1 for c in changes if c.status == s)
              for s in (ADDED, DELETED, MODIFIED, RENAMED)}
    pills = "".join(
        f'<span class="pill {"active" if s == "all" else ""}" data-pill-group="{table_id}" '
        f'data-status="{s}">{label} {counts[s] if s in counts else len(changes)}</span>'
        for s, label in [("all", "全部"), (ADDED, "新增"), (DELETED, "删除"),
                         (MODIFIED, "修改"), (RENAMED, "重命名")]
    )
    return f"""
  <h2>{title} <span class="sub" style="display:inline">({len(changes)} 项)</span></h2>
  <div class="panel">
    <div class="toolbar">
      <input id="q_{table_id}" type="text" placeholder="搜索类名 / 文件名…">
      {pills}
    </div>
    <table id="{table_id}">
      <thead><tr>
        <th data-sort>状态</th><th data-sort>名称</th>
        <th class="num" data-sort>旧</th><th class="num" data-sort>新</th>
        <th class="num" data-sort>Δ</th><th class="num" data-sort>Δ 大小</th>
      </tr></thead>
      <tbody>{_html_rows(changes, metric)}</tbody>
    </table>
  </div>"""


def write_html(result: DiffResult, path: str, metric: str) -> None:
    s = result.summary
    cards = [
        ("APK 文件", s["old_apk_size"], s["new_apk_size"], s["apk_size_delta"]),
        ("代码 (压缩估算)", s["old_class_compressed"], s["new_class_compressed"], s["class_compressed_delta"]),
        ("代码 (原始归属)", s["old_class_bytes"], s["new_class_bytes"], s["class_bytes_delta"]),
        ("资源 (压缩)", s["old_resource_compressed"], s["new_resource_compressed"], s["resource_compressed_delta"]),
        ("资源 (原始)", s["old_resource_bytes"], s["new_resource_bytes"], s["resource_bytes_delta"]),
    ]
    card_html = ""
    for label, old, new, delta in cards:
        cls = "up" if delta > 0 else ("down" if delta < 0 else "flat")
        card_html += (
            f'<div class="card"><div class="label">{label}</div>'
            f'<div class="value">{human_size(new)}</div>'
            f'<div class="delta {cls}">{human_delta(delta)} &nbsp;(旧 {human_size(old)})</div></div>'
        )

    warnings = result.old.warnings + result.new.warnings
    warn_html = ""
    if warnings:
        items = "".join(f"<li>{html.escape(w)}</li>" for w in warnings[:50])
        warn_html = f'<div class="warn"><b>解析警告 ({len(warnings)})</b><ul>{items}</ul></div>'

    body = _HTML_TEMPLATE
    body = body.replace("__OLD__", html.escape(result.old.path))
    body = body.replace("__NEW__", html.escape(result.new.path))
    body = body.replace("__METRIC__", _metric_unit(metric))
    body = body.replace("__CARDS__", card_html)
    body = body.replace("__CLASS_TABLE__", _html_table("classes", "代码类变更", result.classes, metric))
    body = body.replace("__RES_TABLE__", _html_table("resources", "资源文件变更", result.resources, metric))
    body = body.replace("__WARNINGS__", warn_html)
    body = body.replace("__JS_BIND__",
        "bindTable('q_classes','classes',document.querySelectorAll('[data-pill-group=classes]'));\n"
        "bindTable('q_resources','resources',document.querySelectorAll('[data-pill-group=resources]'));")

    _write_text(path, body)
