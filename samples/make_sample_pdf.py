"""Build a demo policy PDF (with real headings) from remote_work_expense_policy.txt.

    cd backend && .venv/bin/python ../samples/make_sample_pdf.py
    # or: docker compose run --rm --no-deps -v "$PWD/samples:/samples" backend python /samples/make_sample_pdf.py
"""
from pathlib import Path

import pymupdf

here = Path(__file__).parent
doc = pymupdf.open()
page, y = None, 0.0
for line in (here / 'remote_work_expense_policy.txt').read_text().splitlines():
    if line.startswith('Page '):
        page, y = doc.new_page(), 72.0
        page.insert_text((72, y), line.split(':', 1)[1].strip(), fontsize=18)
        y += 30
    elif page is not None and line.strip():
        page.insert_textbox(pymupdf.Rect(72, y, 540, y + 200), line, fontsize=11)
        y += 60
out = here / 'remote_work_expense_policy.pdf'
doc.save(out)
print(f'Wrote {out}')
