#!/usr/bin/python3

from elasticsearch import Elasticsearch, ElasticsearchWarning
import warnings
from datetime import datetime

warnings.simplefilter('ignore', ElasticsearchWarning)

es = Elasticsearch(
    hosts="http://localhost:9200",
    basic_auth=('elastic', 'changeme'),
    verify_certs=False
)


def search_in_es(text, es):
    return es.search(
        index="new2-index",
        query={
            "match_phrase": {
                "subs": {
                    "query": text,
                }
            },
        },
        highlight={
            "fields": {
                "subs": {
                    "type": "fvh",
                }
            }
        },
        size=1,
    )


def find_timestamp(timestamps, index_to_find):
    for i, (_, current_index) in enumerate(timestamps[1:]):
        # Because of the slicing
        i = i + 1
        prev_timestamp, prev_index = timestamps[i - 1]
        if prev_index <= index_to_find < current_index:
            return prev_timestamp


def search_subs(text):
    resp = search_in_es(text, es)

    try:
        hit = resp['hits']['hits'][0]
        highlight = hit['highlight']['subs'][0]
        subs = hit['_source']['subs']
        timestamps = hit['_source']['timestamps']
    except:
        return None

    h = highlight \
        .replace('<em>', '') \
        .replace('</em>', '')

    index = subs.find(h)
    # TODO remove when confident
    assert h == subs[index:index+len(h)]
    matching_text = subs[index:index+len(h)]
    timestamp = find_timestamp(timestamps, index)
    time = datetime.strptime(timestamp, "%H:%M:%S.%f")
    # Ignores milliseconds.
    seconds = time.second + 60 * time.minute + (60**2) * time.hour
    id = hit['_id']
    title = hit['_source']['title']
    link = f'https://youtube.com/watch?v={id}&t={seconds}'

    return {
        'id': id,
        'title': title,
        'time': timestamp,
        'link': link,
        'matching_text': matching_text
    }
