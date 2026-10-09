"""Real TeX/BibTeX/package/SyncTeX smoke check; Windows helpers must stay hidden."""
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from editor import compile_tex, synctex_records
from obsidian_tex import kpsewhich

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    main = root / 'main.tex'
    build = root / 'build'
    build.mkdir()
    source = '\\documentclass{article}\n\\begin{document}\nBackground compile fixture \\cite{fixture}.\n\\bibliographystyle{plain}\n\\bibliography{refs}\n\\end{document}\n'
    main.write_text(source, encoding='utf-8')
    (root / 'refs.bib').write_text('@book{fixture,author={Fixture},title={Test},year={2026}}', encoding='utf-8')
    with patch('subprocess.run', wraps=subprocess.run) as calls:
        ok, log, engine = compile_tex(main, build, source)
        assert ok, log[-2000:]
        pdf = build / 'main.pdf'
        assert pdf.read_bytes().startswith(b'%PDF-')
        records = synctex_records(['view', '-i', '3:1:' + str(main), '-o', str(pdf)], root)
        assert records and int(records[0]['Page']) >= 1, records
        assert kpsewhich('article.cls')
        if os.name == 'nt':
            assert all(call.kwargs.get('creationflags') == subprocess.CREATE_NO_WINDOW for call in calls.call_args_list), calls.call_args_list
        else:
            assert all(call.kwargs.get('creationflags', 0) == 0 for call in calls.call_args_list)
        tools = {Path(call.args[0][0]).stem.lower() for call in calls.call_args_list}
        assert {'bibtex', 'synctex', 'kpsewhich'} <= tools, tools
        print(f'PASS: {engine}, BibTeX, package discovery and SyncTeX; {len(calls.call_args_list)} background calls; PDF generated.')
