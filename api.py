#!/usr/bin/python3

from flask import Flask, Response
import multiprocessing
from downloader import downloader_routine
from search import search_subs


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

spawn_workers(4, queue)


@app.route('/request_download/<id>', methods=['POST'])
def request_download(id):
    queue.put_nowait(id)
    return Response(status=200)


@app.route('/search/<text>', methods=['GET'])
def search(text):
    if (search_result := search_subs(text)) is None:
        return Response(status=404)

    return search_result


app.run(debug=True, host='0.0.0.0', port=2000, threaded=True)
