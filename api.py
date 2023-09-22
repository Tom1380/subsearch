#!/usr/bin/python3

from flask import Flask, Response, request, jsonify
import multiprocessing
from downloader import downloader_routine
from search import search_subs

from elasticsearch import Elasticsearch, NotFoundError
import warnings
from elasticsearch.exceptions import ElasticsearchWarning
# TODO fix the root cause, don't just filter the error.
warnings.simplefilter('ignore', ElasticsearchWarning)


# Check if the index exists.
# If it doesn't, create it with the correct mappings.
# If it does, assert that the mappings are correct.
def setup_elasticsearch():
    es = Elasticsearch(
        hosts="http://localhost:9200",
        basic_auth=('elastic', 'changeme'),
        verify_certs=False
    )

    name = 'subsearch'

    desired_mappings = {
        "properties": {
            "subs": {
                "type": "text",
                "term_vector": "with_positions_offsets"
            },
            "timestamps": {
                "type": "object",
                "enabled": False
            }
        }
    }

    try:
        info = es.indices.get(index=name)
    except NotFoundError:
        print(f'The {name} Elasticsearch index wasn\'t found.')
        print('Creating it...')
        es.indices.create(index=name, mappings=desired_mappings)
        return

    actual_mappings = info[name]['mappings']

    desired_properties = desired_mappings['properties']
    actual_properties = actual_mappings['properties']

    # If the desired properties are not a subset of the actual ones,
    # there are conflicts.
    # You're allowed to have other fields,
    # but the 'subs' and 'timestamps' fields need to be set correctly.
    if not desired_properties.items() <= actual_properties.items():
        print(
            f'The mappings for the {name} Elasticsearch index are incorrect.'
        )
        exit(1)


def spawn_worker(queue):
    multiprocessing.Process(
        target=downloader_routine,
        args=(queue,)
    ).start()


def spawn_workers(n, queue):
    for _ in range(n):
        spawn_worker(queue)


app = Flask(__name__)
queue = multiprocessing.Queue()

spawn_workers(8, queue)


@app.route('/request_download/<id>', methods=['POST'])
def request_download(id):
    queue.put_nowait(id)
    return Response(status=200)


@app.route('/search/<text>', methods=['GET'])
def search(text):
    # Should we only match if we find the exact phrase?
    # In other words,
    # should we "match_phrase" or just "match" on the subs field?
    exact_match = request.args.get('exact')
    exact_match = False if exact_match == 'f' else True

    channel_id = request.args.get('channel_id')

    search_results = search_subs(text, exact_match, channel_id)

    return jsonify(search_results)


@app.route('/backlog', methods=['GET'])
def backlog():
    return {'size': queue.qsize()}


setup_elasticsearch()
app.run(debug=True, host='0.0.0.0', port=2000, threaded=True)
