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
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import io
from tqdm import tqdm


# TODO fix the root cause, don't just filter the error.
warnings.simplefilter('ignore', ElasticsearchWarning)


def generate_uuid():
    return str(uuid.uuid4())


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

    def channel_id(self):
        return self.get('uploader_id')

    def id(self):
        return self.get('id')

    def language(self):
        return self.get('language')


# Is it a Youtube channel URL?
def is_channel(url):
    # Youtube video IDs don't contain @.
    return '@' in url


def get_video_ids_from_channel(channel_url):
    uuid = generate_uuid()

    filename = f'{uuid}.txt'

    ctx = {
        'extract_flat': 'in_playlist',
        'ignoreerrors': True,
        'print_to_file': {
            'video': [('id', filename)]
        }
    }

    with YoutubeDL(ctx) as ydl:
        ydl.download([channel_url])

    ids = open(filename, 'r').readlines()
    os.remove(filename)

    return ids


def handle_channel(es, url):
    # Turn e.g. @lucy into https://www.youtube.com/@lucy/videos
    # so yt-dlp can work with it.
    if url.startswith('@'):
        url = f'https://www.youtube.com/{url}/videos'

    ids = get_video_ids_from_channel(url)

    for id in tqdm(ids):
        handle_video(es, id)


def handle_video(es, url):
    url = url.strip()
    if es.exists(index="new2-index", id=url):
        print(f'The video with id {url} is already in the DB')
        return

    info = download_subs(url)

    if info is None:
        return

    doc = build_doc(info)

    print(doc)

    save_to_es(es, doc, id=info.id())


def download_subs(youtube_id):
    ctx = {
        "outtmpl": '%(id)s',
        'logtostderr': True,
        'skip_download': True,
        'writeautomaticsub': True,
        'writesubtitles': True,
        'sub_langs': 'en.*',
        'subtitlesformat': 'ttml',
    }

    # TODO handle videos that still have to premiere.
    with YoutubeDL(ctx) as ydl:
        try:
            info_dict = ydl.extract_info(
                youtube_id,
                download=True,
            )
        except Exception as e:
            print("Exception caught:")
            print(e)
            return None

    try:
        # TODO delete the files from the ignored subtitles.
        req_subtitles = [
            sub
            for sub in info_dict['requested_subtitles'].values()
            if sub['ext'] == 'ttml'
        ]
        # I don't know if this situation can happen,
        # I'd like to only download the "best" subtitle file available.
        if len(req_subtitles) > 1:
            print('More than one subtitle file found.')

        filename = req_subtitles[0]['filepath']
        return DownloadInfo(filename, info_dict)
    except:
        # If the video is younger than 15 days, the automatic subs might still be processing.
        if video_is_older_than_15_days(info_dict):
            print('This video doesn\'t have subtitles and it\'s old')
            return DownloadInfo(None, info_dict)
        print('No subtitles available yet')
        return None


def video_is_older_than_15_days(info_dict):
    upload_date = info_dict['upload_date']
    upload_date = datetime.strptime(upload_date, "%Y%m%d")
    now = datetime.now()
    return (now - upload_date) > timedelta(days=15)


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
    if info.filename is not None:
        tree = ET.parse(info.filename)
        root = tree.getroot()
        paragraphs = root.findall('.//{http://www.w3.org/ns/ttml}p')
        subs, timestamps = build_subs_and_timestamps(paragraphs)
        os.remove(info.filename)
    else:
        subs, timestamps = None, None

    return {
        'title': info.title(),
        'channel': info.channel(),
        'channel_id': info.channel_id(),
        'upload_date': info.upload_date(),
        'language': info.language(),
        'timestamps': timestamps,
        'subs': subs,
    }


def downloader_routine(queue):
    es = Elasticsearch(
        hosts="http://localhost:9200",
        basic_auth=('elastic', 'changeme'),
        verify_certs=False
    )

    while True:
        url = queue.get(block=True)
        if is_channel(url):
            print(f"Downloading videos from channel! URL: {url}")
            handle_channel(es, url)
        else:
            handle_video(es, url)
