#!/usr/bin/python3

import os
from contextlib import *
from yt_dlp import *
from pathlib import *
import uuid


def generate_uuid():
    return str(uuid.uuid4())


def find_file(uuid):
    prefixed = [
        filename
        for filename in os.listdir('.')
        if filename.startswith(uuid)
    ]

    return prefixed[0]


def get_subs(youtube_id):
    uuid = generate_uuid()

    ctx = {
        "outtmpl": uuid,
        'logtostderr': True,
        'skip_download': True,
        'writeautomaticsub': True,
        'writesubtitles': True,
        'sub_langs': 'en.*',
    }

    with YoutubeDL(ctx) as foo:
        foo.download([youtube_id])

    filename = find_file(uuid)
    contents = open(filename, 'r').read()
    os.remove(filename)

    return contents
