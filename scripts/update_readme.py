#!/usr/bin/env python3
"""Update README.md by adding a paper link under a given section.

Usage:
  python3 scripts/update_readme.py <url> <section> [--title TITLE]

If the section exists, the script inserts a markdown bullet with the link
under that section. If the section doesn't exist, it appends the section
and the link at the end of the file. If the link already exists in the
section, nothing is changed.
"""
import argparse
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import json


def find_section(lines, section_name):
    pattern = re.compile(r'^(#{1,6})\s*' + re.escape(section_name) + r'\b.*$', re.IGNORECASE)
    for idx, line in enumerate(lines):
        # match at start of line (preserve leading spaces handling)
        if pattern.match(line.rstrip('\n')):
            m = pattern.match(line.rstrip('\n'))
            level = len(m.group(1))
            return idx, level
    return None, None


def find_section_end(lines, start_idx, level):
    header_pattern = re.compile(r'^(#{1,' + str(level) + r'})\s+')
    for idx in range(start_idx + 1, len(lines)):
        if header_pattern.match(lines[idx]):
            return idx
    return len(lines)


def already_present(lines, start, end, url):
    for line in lines[start:end]:
        if url in line:
            return True
    return False


def insert_link_in_section(lines, insert_idx, url, title=None):
    text = title if title else url
    bullet = f'- [{text}]({url})\n'
    # ensure there is a blank line before lists if not present
    if insert_idx > 0 and lines[insert_idx - 1].strip() != "":
        lines.insert(insert_idx, "\n")
        insert_idx += 1
    lines.insert(insert_idx, bullet)


def append_section_with_link(lines, section_name, url, title=None):
    lines.append('\n')
    lines.append(f'## {section_name}\n')
    lines.append('\n')
    text = title if title else url
    lines.append(f'- [{text}]({url})\n')


def format_author(name):
    parts = name.split()
    if len(parts) == 0:
        return name
    last = parts[-1].rstrip(',')
    initials = ''.join([p[0] + '.' for p in parts[:-1] if p])
    if initials:
        return f'{last}, {initials}'
    return last


def format_authors_list(names):
    formatted = [format_author(n) for n in names]
    if not formatted:
        return ''
    if len(formatted) == 1:
        return f'*{formatted[0]}.*'
    if len(formatted) == 2:
        return f'*{formatted[0]}, & {formatted[1]}.*'
    return '*'+', '.join(formatted[:-1]) + ', & ' + formatted[-1] + '.*'


def fetch_arxiv_metadata(url):
    # accept urls like https://arxiv.org/abs/ID or https://arxiv.org/pdf/ID.pdf
    m = re.search(r'arxiv\.org/(abs|pdf)/([0-9A-Za-z.\-_/]+)', url)
    if not m:
        return None
    arxiv_id = m.group(2).replace('.pdf', '')
    api = f'http://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}'
    try:
        with urllib.request.urlopen(api, timeout=10) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entry = root.find('atom:entry', ns)
        if entry is None:
            return None
        title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
        authors = [a.find('atom:name', ns).text.strip() for a in entry.findall('atom:author', ns)]
        published = entry.find('atom:published', ns).text.strip()
        year = published.split('-')[0]
        return {'title': title, 'authors': authors, 'venue': 'arXiv', 'year': year}
    except Exception:
        return None


def fetch_crossref_metadata(url):
    # try to extract DOI and query crossref
    # doi.org/<doi>
    doi = None
    parsed = urllib.parse.urlparse(url)
    if 'doi.org' in parsed.netloc:
        doi = parsed.path.lstrip('/')
    else:
        # try to find doi in url path
        m = re.search(r'10\.[0-9]+/.+', url)
        if m:
            doi = m.group(0)
    if not doi:
        return None
    api = f'https://api.crossref.org/works/{urllib.parse.quote(doi)}'
    try:
        with urllib.request.urlopen(api, timeout=10) as resp:
            data = json.load(resp)
        item = data.get('message', {})
        title = item.get('title', [''])[0]
        authors = []
        for a in item.get('author', []):
            given = a.get('given', '')
            family = a.get('family', '')
            name = (given + ' ' + family).strip()
            if name:
                authors.append(name)
        journal = item.get('container-title', [''])[0]
        year = ''
        if 'published-print' in item and 'date-parts' in item['published-print']:
            year = str(item['published-print']['date-parts'][0][0])
        elif 'published-online' in item and 'date-parts' in item['published-online']:
            year = str(item['published-online']['date-parts'][0][0])
        return {'title': title, 'authors': authors, 'venue': journal or '', 'year': year}
    except Exception:
        return None


def fetch_metadata(url):
    # try arXiv first
    meta = fetch_arxiv_metadata(url)
    if meta:
        return meta
    meta = fetch_crossref_metadata(url)
    if meta:
        return meta
    return None


def main():
    parser = argparse.ArgumentParser(description="Add a paper link to README.md under a section")
    parser.add_argument('url', help='Paper URL')
    parser.add_argument('section', help='Section name to add the link under')
    parser.add_argument('--title', '-t', help='Optional link title to show in README')
    parser.add_argument('--file', '-f', default='README.md', help='Path to README file (default: README.md)')
    args = parser.parse_args()

    readme_path = args.file
    if not os.path.exists(readme_path):
        print(f'Error: {readme_path} does not exist', file=sys.stderr)
        sys.exit(2)

    with open(readme_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    sec_idx, level = find_section(lines, args.section)
    # fetch metadata if possible
    meta = fetch_metadata(args.url)
    title_text = args.title or (meta['title'] if meta and meta.get('title') else args.url)
    authors_text = None
    venue_text = None
    if meta:
        if meta.get('authors'):
            authors_text = format_authors_list(meta['authors'])
        venue = meta.get('venue', '') or 'arXiv'
        year = meta.get('year', '')
        venue_text = f'{venue}, {year}.' if year else f'{venue}.'

    if sec_idx is not None:
        end_idx = find_section_end(lines, sec_idx, level)
        # check if url already present
        if already_present(lines, sec_idx + 1, end_idx, args.url):
            print('Link already present in section; no changes made.')
            return
        # prepare entry lines
        entry_lines = []
        entry_lines.append(f'- **{title_text}** \n')
        if authors_text:
            entry_lines.append('\t' + authors_text + ' \n')
        entry_lines.append('\t' + (venue_text or f'arXiv.'))
        entry_lines[-1] = entry_lines[-1] + f' [[Paper]]({args.url})\n\n'
        # ensure blank line before
        if end_idx > 0 and lines[end_idx - 1].strip() != "":
            lines.insert(end_idx, "\n")
            end_idx += 1
        for i, l in enumerate(entry_lines):
            lines.insert(end_idx + i, l)
    else:
        # append new section with formatted entry
        lines.append('\n')
        lines.append(f'## {args.section}\n')
        lines.append('\n')
        lines.append(f'- **{title_text}** \n')
        if authors_text:
            lines.append('\t' + authors_text + ' \n')
        lines.append('\t' + (venue_text or f'arXiv.'))
        lines[-1] = lines[-1] + f' [[Paper]]({args.url})\n'

    with open(readme_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print('README updated.')


if __name__ == '__main__':
    main()
