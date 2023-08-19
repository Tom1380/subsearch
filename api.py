#!/usr/bin/python3

from flask import Flask, Response
import multiprocessing
from downloader import downloader_routine


def spawn_worker(queue):
    multiprocessing.Process(
        target=downloader_routine,
        args=(queue,)
    ).start()


app = Flask(__name__)
queue = multiprocessing.Queue()

spawn_worker(queue)


@app.route('/request_download/<id>', methods=['POST'])
def request_download(id):
    queue.put_nowait(id)
    return Response(status=200)


app.run(debug=True, host='0.0.0.0', port=2000, threaded=True)
