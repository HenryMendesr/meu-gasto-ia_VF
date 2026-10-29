"""Check the generated JavaScript without executing or exporting financial data."""
from pathlib import Path
import re
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
html=(root/'templates/index.html').read_text(encoding='utf-8')
script='\n'.join(re.findall(r'<script>(.*?)</script>',html,re.S))
if not script:raise SystemExit('JavaScript do painel ausente')
with tempfile.TemporaryDirectory() as folder:
    target=Path(folder)/'dashboard.js'
    target.write_text(script,encoding='utf-8')
    subprocess.run(['node','--check',str(target)],check=True)
print('JavaScript do painel validado')
