# Subsearch

Subsearch is an API for indexing Youtube subtitles and searching them.

## How it works

Given a Youtube video, the TTML subtitles are downloaded via yt-dlp.

They are parsed, translated to a JSON document and fed into Elasticsearch.

When searching for a phrase, the ES index is queried. Looking at the ID, highlights and timestamps, the relevant video and timestamp is found and a link is built.

There's also an external crawler that uses Google Trends to find hot topics and keywords to feed to the API.

## Functionality

First of all, start the API.

```bash
./api.py
```

### Searching for a phrase

```bash
curl "localhost:2000/search/emancipate"
```

### Requesting downloads
#### Videos

```bash
curl -XPOST "localhost:2000/request_download/jNQXAC9IVRw"
```

#### Channels

```bash
curl -XPOST "localhost:2000/request_download/@TheOffice"
```

#### Youtube search results
This downloads the subs from the first *10* results for the query `query`.
You can change the 10 if you want a different number of videos to be downloaded.
```bash
curl -XPOST "localhost:2000/request_download/ytsearch10:query"
```
