#!/usr/bin/env python3
"""Render the generated report using installed LibreOffice, with no skill paths.

Requirements: LibreOffice (libreoffice or soffice on PATH) and pypdf.
Optional --pages uses Poppler's pdftoppm to export every page as a PNG for review.
This converts the document; it does not claim that human visual review occurred.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'report/report.docx')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'report')
    parser.add_argument('--pages', action='store_true')
    args = parser.parse_args()
    source = args.input.resolve()
    target = args.output_dir.resolve()
    if not source.is_file():
        parser.error('Missing DOCX. Run scripts/build_report.py first.')
    executable = shutil.which('libreoffice') or shutil.which('soffice')
    if executable is None:
        parser.error('LibreOffice is required. Install it and place libreoffice or soffice on PATH.')
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='beam_report_', dir=target) as work:
        work = Path(work)
        profile = work / 'profile'
        profile.mkdir()
        profile_argument = '-env:UserInstallation=' + profile.as_uri()
        version = subprocess.run([executable, profile_argument, '--version'], capture_output=True, text=True, check=True).stdout.strip()
        command = [executable, profile_argument,
                   '--headless', '--convert-to', 'pdf:writer_pdf_Export',
                   '--outdir', str(work), str(source)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        generated = work / (source.stem + '.pdf')
        if result.returncode or not generated.is_file():
            raise RuntimeError('LibreOffice PDF conversion failed.\n' + result.stdout + '\n' + result.stderr)
        pdf = target / 'report.pdf'
        shutil.copy2(generated, pdf)
    reader = PdfReader(pdf)
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    if len(reader.pages) < 8 or 'engineering report v1' not in text:
        raise RuntimeError('Rendered PDF content or page count is incomplete; inspect before release.')
    page_paths = []
    if args.pages:
        pdftoppm = shutil.which('pdftoppm')
        if pdftoppm is None:
            parser.error('--pages needs Poppler pdftoppm on PATH.')
        pages_dir = target / 'page_review'
        pages_dir.mkdir(exist_ok=True)
        subprocess.run([pdftoppm, '-png', '-r', '120', str(pdf), str(pages_dir / 'page')], check=True, timeout=180)
        page_paths = [str(path.relative_to(target)) for path in sorted(pages_dir.glob('page-*.png'))]
    receipt = {
        'schema': 'beam-report-render-v1',
        'renderer': version,
        'input_docx_sha256': sha(source),
        'output_pdf_sha256': sha(pdf),
        'page_count': len(reader.pages),
        'page_images': page_paths,
        'visual_review_performed': False,
        'next_action': 'Review every rendered page, then update report/visual_review.json with actual observations.'
    }
    (target / 'render_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
