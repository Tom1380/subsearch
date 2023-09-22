from elasticsearch import Elasticsearch, ElasticsearchWarning
import warnings
from datetime import datetime

warnings.simplefilter('ignore', ElasticsearchWarning)

es = Elasticsearch(
    hosts="http://localhost:9200",
    basic_auth=('elastic', 'changeme'),
    verify_certs=False
)


def search_in_es(text, exact_match, channel_id, es):
    if exact_match:
        must_list = [{
            "match_phrase": {"subs":  text}
        }]
    else:
        must_list = [{
            "match": {"subs":  text}
        }]

    if channel_id is not None:
        must_list.append({
            "match_phrase": {"channel_id":  channel_id}
        })

    return es.search(
        index="subsearch",
        query={
            "bool": {
                "must": must_list
            }
        },
        highlight={
            "fields": {
                "subs": {
                    "type": "fvh",
                }
            }
        },
        size=3,
    )


def find_timestamp(timestamps, index_to_find):
    previous_timestamp, previous_index = timestamps[0]

    for current_timestamp, current_index in timestamps[1:]:
        if previous_index <= index_to_find < current_index:
            return previous_timestamp

        previous_timestamp, previous_index = current_timestamp, current_index

    return previous_timestamp


def search_subs(text, exact_match, channel_id):
    resp = search_in_es(text, exact_match, channel_id, es)

    return [
        build_video_object(hit)
        for hit in resp['hits']['hits']
    ]


def build_video_object(hit):
    highlights = hit['highlight']['subs']
    source = hit['_source']

    id = hit['_id']
    subs = source['subs']
    timestamps = source['timestamps']
    title = source['title']
    channel = source['channel']

    video_matches = [
        build_match_object(highlight, id, subs, timestamps)
        for highlight in highlights
    ]

    return {
        'id': id,
        'title': title,
        'channel': channel,
        'matches': video_matches
    }


def build_match_object(highlight, id, subs, timestamps):
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

    link = f'https://youtube.com/watch?v={id}&t={seconds}'

    return {
        'matching_text': matching_text,
        'time': timestamp,
        'link': link
    }


# TODO don't return the same timestamp when highlights have the same text.
