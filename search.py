#!/usr/bin/python3

from elasticsearch import Elasticsearch

search = input('Your search: ')

es = Elasticsearch(
    hosts="http://localhost:9200",
    basic_auth=('elastic', 'changeme'),
    verify_certs=False
)

resp = es.search(
    index="test-index",
    query={
        "query_string": {
            "query": search
        }
    }
)

print(resp)
for hit in resp['hits']['hits']:
    print(hit)


print("\n\nThese were", len(resp['hits']['hits']), "hits")
