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


def find_file(uuid):
    prefixed = [
        filename
        for filename in os.listdir('.')
        if filename.startswith(uuid)
    ]

    # I don't know if this situation can happen,
    # I'd like to only download the "best" subtitle file available.
    if len(prefixed) > 1:
        print('More than one subtitle file found.')

    try:
        return prefixed[0]
    except:
        return None


class DownloadInfo:
    def __init__(self, filename, info_dict):
        self.filename = filename
        self.info_dict = info_dict

    def get(self, keyword):
        return self.info_dict.get(keyword, None)

    def url(self):
        return self.get('url')

    def title(self):
        return self.get('title')

    def upload_date(self):
        return self.get('upload_date')

    def channel(self):
        return self.get('uploader')

    def id(self):
        return self.get('id')


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


def build_subs_and_timestamps(paragraphs):
    index_in_text = 0
    timestamps = list()
    subs = []
    for p in paragraphs:
        phrase = extract_text(p)
        subs.append(phrase)
        timestamps.append((p.get('begin'), index_in_text))
        # Because a newline will be added when the list is joined.
        index_in_text += len(phrase) + 1

    subs = '\n'.join(subs)

    return subs, timestamps


def build_doc(info):
    tree = ET.parse(info.filename)
    root = tree.getroot()

    paragraphs = root.findall('.//{http://www.w3.org/ns/ttml}p')

    subs, timestamps = build_subs_and_timestamps(paragraphs)

    return {
        'title': info.title(),
        'channel': info.channel(),
        'upload_date': info.upload_date(),
        'timestamps': timestamps,
        'subs': subs,
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

    doc = build_doc(info)

    print(doc)

    os.remove(info.filename)

    save_to_es(es, doc, id=info.id())
