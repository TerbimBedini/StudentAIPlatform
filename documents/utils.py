from pathlib import Path
from zipfile import BadZipFile, ZipFile
import re
import xml.etree.ElementTree as ET


class TextExtractionError(Exception):
    pass


def extract_text_from_pdf(pdf_path):
    text_parts = []

    try:
        import fitz

        with fitz.open(pdf_path) as pdf:
            for page in pdf:
                text_parts.append(page.get_text('text', sort=True))
    except ImportError as exc:
        raise TextExtractionError(
            'Paketa PyMuPDF mungon. Instalo dependencies me: pip install -r requirements.txt'
        ) from exc
    except Exception as exc:
        raise TextExtractionError(
            'Nuk u lexua dot teksti nga PDF-i.'
        ) from exc

    return clean_extracted_text('\n'.join(text_parts))


def extract_text_from_document(file_path):
    suffix = Path(file_path).suffix.lower()

    if suffix == '.pdf':
        return extract_text_from_pdf(file_path)

    if suffix == '.docx':
        return extract_text_from_docx(file_path)

    raise TextExtractionError(
        'Ky format dokumenti nuk mbeshtetet. Ngarko nje PDF ose DOCX.'
    )


def clean_document_text(text):
    text = clean_extracted_text(text or '')
    lines = [
        line.strip()
        for line in text.split('\n')
        if line.strip()
    ]

    line_counts = {}
    for line in lines:
        if len(line) <= 90:
            line_counts[line] = line_counts.get(line, 0) + 1

    cleaned_lines = []
    for line in lines:
        looks_like_repeated_header = (
            line_counts.get(line, 0) >= 3
            and not re.search(r'[.!?]$', line)
        )
        if looks_like_repeated_header:
            continue
        cleaned_lines.append(line)

    paragraphs = []
    current = []

    for line in cleaned_lines:
        if current and re.match(r'^(#{1,6}\s+|\d+[\).]\s+|[-*]\s+)', line):
            paragraphs.append(' '.join(current))
            current = [line]
            continue

        if current and len(line) > 80 and current[-1].endswith(('.', '?', '!', ':')):
            paragraphs.append(' '.join(current))
            current = [line]
            continue

        current.append(line)

    if current:
        paragraphs.append(' '.join(current))

    cleaned = '\n\n'.join(paragraphs)
    cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned.strip()


def get_document_text(document):
    cached_text = getattr(document, 'extracted_text', '') or ''

    if cached_text.strip():
        return clean_document_text(cached_text)

    text = extract_text_from_document(document.file.path)
    cleaned_text = clean_document_text(text)

    if hasattr(document, 'extracted_text'):
        document.extracted_text = cleaned_text
        document.save(update_fields=['extracted_text'])

    return cleaned_text


def extract_text_from_docx(docx_path):
    try:
        with ZipFile(docx_path) as docx:
            xml_content = docx.read('word/document.xml')
    except (BadZipFile, KeyError, OSError) as exc:
        raise TextExtractionError(
            'Nuk u lexua dot teksti nga DOCX.'
        ) from exc

    namespace = {
        'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    }

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise TextExtractionError(
            'DOCX ka permbajtje te pavlefshme.'
        ) from exc

    paragraphs = []

    for paragraph in root.findall('.//w:p', namespace):
        parts = [
            node.text
            for node in paragraph.findall('.//w:t', namespace)
            if node.text
        ]

        if parts:
            paragraphs.append(''.join(parts))

    return clean_extracted_text('\n'.join(paragraphs))


def clean_extracted_text(text):
    symbol_replacements = {
        '\x00': '',
        '\uf020': ' ',
        '\uf02b': '+',
        '\uf02c': ',',
        '\uf02d': '-',
        '\uf02e': '.',
        '\uf02f': '/',
        '\uf030': '0',
        '\uf031': '1',
        '\uf032': '2',
        '\uf033': '3',
        '\uf03a': ':',
        '\uf03b': ';',
        '\uf03c': '<',
        '\uf03d': '=',
        '\uf03e': '>',
        '\uf028': '(',
        '\uf029': ')',
        '\uf044': 'Delta',
        '\uf04e': 'N',
        '\uf05b': '[',
        '\uf05d': ']',
        '\uf055': 'U',
        '\uf052': 'R',
        '\uf061': 'alpha',
        '\uf064': 'delta',
        '\uf070': 'pi',
        '\uf07b': '{',
        '\uf07d': '}',
        '\uf0a3': '<=',
        '\uf0a5': 'infinity',
        '\uf0ae': '->',
        '\uf0b3': '>=',
        '\uf0b9': '!=',
        '\uf0bb': '~',
        '\uf0cd': ' subset ',
        '\uf0ce': 'in',
        '\uf0d7': '*',
        '\uf0db': '<=>',
        '\uf0de': 'superset',
    }

    for old, new in symbol_replacements.items():
        text = text.replace(old, new)

    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[\uf000-\uf0ff]', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)

    lines = [
        line.strip()
        for line in text.split('\n')
        if line.strip()
    ]

    paragraphs = []
    current = ''

    for line in lines:
        if re.fullmatch(r'-?\s*\d+\s*-?', line):
            continue

        if not current:
            current = line
            continue

        should_join = (
            len(line) <= 4
            or len(current) <= 4
            or not current.endswith(('.', ':', ';', '?', '!', ')'))
        )

        if should_join:
            current = f'{current} {line}'
        else:
            paragraphs.append(current)
            current = line

    if current:
        paragraphs.append(current)

    cleaned = '\n\n'.join(paragraphs)
    cleaned = re.sub(r"\n'", "\n", cleaned)
    cleaned = re.sub(r"(^|\s)'([A-ZÇË])", r'\1\2', cleaned)
    cleaned = re.sub(r"\s+'\s+'", ' ', cleaned)
    cleaned = re.sub(r'\b(in|subset|superset)([A-Z])', r'\1 \2', cleaned)
    cleaned = re.sub(r' {2,}', ' ', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned.strip()
