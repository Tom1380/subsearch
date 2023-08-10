#!/usr/bin/python3

import json
import os
from contextlib import *
from yt_dlp import *
from pathlib import *
import uuid
from elasticsearch import Elasticsearch
import warnings
from elasticsearch.exceptions import ElasticsearchWarning
from datetime import datetime
import xml.etree.ElementTree as ET
import io
from tqdm import tqdm


# TODO fix the root cause, don't just filter the error.
warnings.simplefilter('ignore', ElasticsearchWarning)


def generate_uuid():
    return str(uuid.uuid4())


# TODO It doesn't make sense to check all files if we're just going to return the first match.
def find_file(uuid):
    prefixed = [
        filename
        for filename in os.listdir('.')
        if filename.startswith(uuid)
    ]

    try:
        return prefixed[0]
    except:
        return None


class DownloadInfo:
    def __init__(self, filename, info_dict):
        self.filename = filename
        self.info_dict = info_dict

    def url(self):
        return self.info_dict.get('url', None)

    def title(self):
        return self.info_dict.get('title', None)

    def upload_date(self):
        return self.info_dict.get('upload_date', None)

    def channel(self):
        return self.info_dict.get('uploader', None)

    def id(self):
        return self.info_dict.get('id', None)


def download_subs(youtube_id):
    uuid = generate_uuid()

    ctx = {
        "outtmpl": uuid,
        'logtostderr': True,
        'skip_download': True,
        'writeautomaticsub': True,
        'writesubtitles': True,
        'sub_langs': 'en.*',
        'subtitlesformat': 'ttml',
    }

    with YoutubeDL(ctx) as ydl:
        info_dict = ydl.extract_info(
            youtube_id,
            download=True,
            process=True
        )

    if (filename := find_file(uuid)) is not None:
        return DownloadInfo(filename, info_dict)
    else:
        return None


def save_to_es(es, doc, id):
    assert id is not None
    es.index(index="new2-index", document=doc, id=id)


def trim_newlines(text):
    if len(text) != 0:
        if text[0] == '\n':
            text = text[1:]

    if len(text) != 0:
        if text[-1] == '\n':
            text = text[:-1]

    return text


def extract_text(paragraph_element):
    text = paragraph_element.text
    if text is None:
        text = ''
    else:
        text = trim_newlines(text)

    # https://stackoverflow.com/a/61718777/6878890
    for subelem in paragraph_element:
        tail = subelem.tail
        if tail is None:
            continue

        othertext = trim_newlines(tail)
        if len(othertext) != 0:
            text += ' '
            text += othertext

    return text


def build_doc(filename):
    tree = ET.parse(filename)
    root = tree.getroot()

    paragraphs = root.findall('.//{http://www.w3.org/ns/ttml}p')

    return {
        'title': info.title(),
        'channel': info.channel(),
        'upload_date': info.upload_date(),
        'subs':
            '\n'.join([
                extract_text(paragraph_element)
                for paragraph_element in paragraphs
            ]),
    }


es = Elasticsearch(
    hosts="http://localhost:9200",
    basic_auth=('elastic', 'changeme'),
    verify_certs=False
)

urls = [
    'https://youtu.be/8i4EEb5QMgU',
    'https://youtu.be/X1SffRGMBEU',
    'https://youtu.be/aR8q3uDSdb4',
]


for url in tqdm(urls):
    info = download_subs(url)

    if info is None:
        print('No subtitles available?')
        continue

    print(info.url)
    print(info.title)

    doc = build_doc(info.filename)

    print(doc)

    json.dump(
        doc,
        io.open(f'{info.filename}.json', mode='w', encoding='utf-8'),
        ensure_ascii=False
    )

    os.remove(info.filename)

    save_to_es(es, doc, id=info.id())
