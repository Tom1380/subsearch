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


# Playlist in yt-dlp's jargon, so not just YT playlists, but also
# channels and YT search results.
def is_playlist(url):
    return url.startswith('ytsearch') or is_channel(url) or is_youtube_playlist(url)


# Is it a Youtube channel URL?
def is_channel(url):
    # Youtube video IDs don't contain @.
    return '@' in url


# Actual YT playlists.
def is_youtube_playlist(url):
    # They contain a list parameter in their URL.
    return '?list=' in url or '&list=' in url


def get_video_ids_from_playlist(playlist_url):
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
        ydl.download([playlist_url])

    ids = open(filename, 'r').readlines()
    os.remove(filename)

    return ids


def handle_playlist(es, url):
    # Turn e.g. @lucy into https://www.youtube.com/@lucy/videos
    # so yt-dlp can work with it.
    if url.startswith('@'):
        url = f'https://www.youtube.com/{url}/videos'

    ids = get_video_ids_from_playlist(url)

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
        'compat_opts': {'no-live-chat'},
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
        filename = pick_subtitles(info_dict)
        return DownloadInfo(filename, info_dict)
    except:
        # If the video is younger than 15 days, the automatic subs might still be processing.
        if video_is_older_than_15_days(info_dict):
            print('This video doesn\'t have subtitles and it\'s old')
            return DownloadInfo(None, info_dict)
        print('No subtitles available yet')
        return None


def pick_subtitles(info_dict):
    requested_subtitles = info_dict['requested_subtitles']
    suitable_subtitles = [
        key
        for key, value in requested_subtitles.items()
        if value['ext'] == 'ttml'
    ]

    if len(suitable_subtitles) == 0:
        # Cleanup.
        delete_subtitle_files(requested_subtitles)
        raise BaseException("No suitable subtitles found.")
    # I don't know if this situation can happen,
    # I'd like to only download the "best" subtitle file available.
    elif len(suitable_subtitles) != 1:
        print('More than one suitable subtitle file found.')

    chosen_subtitles = requested_subtitles.pop(suitable_subtitles[0])
    # The chosen one was popped, so the remaining ones,
    # if there are any, are the ignored ones.
    delete_subtitle_files(requested_subtitles)

    return chosen_subtitles['filepath']


def delete_subtitle_files(subtitles):
    for s in subtitles.values():
        os.remove(s['filepath'])


def video_is_older_than_15_days(info_dict):
    upload_date = info_dict['upload_date']
    upload_date = datetime.strptime(upload_date, "%Y%m%d")
    now = datetime.now()
    return (now - upload_date) > timedelta(days=15)


def save_to_es(es, doc, id):
    assert id is not None
    es.index(index="new2-index", document=doc, id=id)


def extract_text(paragraph_element):
    text = paragraph_element.text
    if text is None:
        text = ''
    else:
        text = text.strip('\n')

    # https://stackoverflow.com/a/61718777/6878890
    for subelem in paragraph_element:
        subelem_text = subelem.text
        if subelem_text is not None:
            othertext = subelem_text.strip('\n')
            if len(othertext) != 0:
                text += othertext

        tail = subelem.tail
        if tail is not None:
            othertext = tail.strip('\n')
            if len(othertext) != 0:
                text += ' '
                text += othertext

    return text


def build_subs_and_timestamps(paragraphs):
    index_in_text = 0
    timestamps = list()
    subs = []
    for p in paragraphs:
        # Strip everything, not just newlines this time.
        phrase = extract_text(p).strip()
        if phrase == '':
            continue

        subs.append(phrase)
        timestamps.append((p.get('begin'), index_in_text))
        # Because a newline will be added when the list is joined.
        index_in_text += len(phrase) + 1

    subs = '\n'.join(subs)

    return subs, timestamps


def build_doc(info):
    if info.filename is None:
        # Return an empty doc to save in the index.
        # It's saved to keep the ID so that we can skip
        # downloading this video the next time we're asked to.
        return {}

    paragraphs = get_paragraphs_from_ttml(info.filename)
    os.remove(info.filename)
    subs, timestamps = build_subs_and_timestamps(paragraphs)

    return {
        'title': info.title(),
        'channel': info.channel(),
        'channel_id': info.channel_id(),
        'upload_date': info.upload_date(),
        'language': info.language(),
        'timestamps': timestamps,
        'subs': subs,
    }


def get_paragraphs_from_ttml(filename):
    ttml = open(filename).read()

    # We need to remove the this character because it's invalid.
    # https://stackoverflow.com/q/5742543/6878890
    # I found the character in this video's TTML:
    # https://youtu.be/a1rfL-ms_3o
    ttml = ttml.replace('\x0c', '')

    # A lot of videos seem to use ’,
    # but it's better to be consistent for searches.
    ttml = ttml.replace('’', '\'')

    ttml = ET.fromstring(ttml)
    return ttml.findall('.//{http://www.w3.org/ns/ttml}p')


def downloader_routine(queue):
    es = Elasticsearch(
        hosts="http://localhost:9200",
        basic_auth=('elastic', 'changeme'),
        verify_certs=False
    )

    while True:
        url = queue.get(block=True)
        if is_playlist(url):
            print(f"Downloading videos from playlist! URL: {url}")
            handle_playlist(es, url)
        else:
            handle_video(es, url)
