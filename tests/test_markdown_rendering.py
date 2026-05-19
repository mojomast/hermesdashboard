import json
import subprocess
from pathlib import Path


DASHBOARD_HTML = Path(__file__).resolve().parents[1] / "templates" / "index.html"


def _run_markdown_renderer(markdown: str) -> str:
    html = DASHBOARD_HTML.read_text()
    start = html.index("        function escapeHtml(text)")
    end = html.index("        function formatSessionTranscriptContent(text)")
    functions = html[start:end]
    script = f"""
const document = {{
  createElement: () => ({{
    _text: '',
    set textContent(value) {{ this._text = String(value ?? ''); }},
    get innerHTML() {{
      return this._text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }},
  }}),
}};
{functions}
console.log(formatMessageContent({json.dumps(markdown)}));
"""
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def test_markdown_tables_render_as_real_tables_with_alignment():
    rendered = _run_markdown_renderer(
        "# Token burn\n\n| Source | Tokens | Share |\n|---|---:|:---:|\n| Cron | **1.2B** | 92% |\n| API | `98M` | 8% |"
    )

    assert '<div class="markdown-body">' in rendered
    assert '<h1>Token burn</h1>' in rendered
    assert '<table>' in rendered
    assert '<th>Source</th>' in rendered
    assert '<th class="align-right">Tokens</th>' in rendered
    assert '<th class="align-center">Share</th>' in rendered
    assert '<strong>1.2B</strong>' in rendered
    assert '<code>98M</code>' in rendered
    assert '<br>| Source | Tokens | Share |' not in rendered


def test_markdown_renderer_escapes_html_but_keeps_code_fences():
    rendered = _run_markdown_renderer("hello <script>alert(1)</script>\n\n```js\nconst x = '<safe>';\n```")

    assert '<script>' not in rendered
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in rendered
    assert '<pre><code class="language-js">const x = &#039;&lt;safe&gt;&#039;;\n</code></pre>' in rendered
