FROM ubuntu

RUN apt update
RUN DEBIAN_FRONTEND=noninteractive apt install curl gpg -y

RUN curl -fsSL https://artifacts.elastic.co/GPG-KEY-elasticsearch | gpg --dearmor -o /usr/share/keyrings/elastic.gpg
RUN echo "deb [signed-by=/usr/share/keyrings/elastic.gpg] https://artifacts.elastic.co/packages/7.x/apt stable main" | tee -a /etc/apt/sources.list.d/elastic-7.x.list

RUN apt update
RUN DEBIAN_FRONTEND=noninteractive apt install elasticsearch python3 python3-pip git nodejs npm -y

RUN mkdir -p /etc/elasticsearch/jvm.options.d
RUN echo "-Xms1g" >> /etc/elasticsearch/jvm.options.d/custom.options
RUN echo "-Xmx1g" >> /etc/elasticsearch/jvm.options.d/custom.options

RUN npm install elasticdump -g

RUN mkdir /subsearch
WORKDIR /subsearch
COPY * .

RUN /etc/init.d/elasticsearch start && \
	sleep 60 && \
	elasticdump --input=my_index_mapping.json --output=http://localhost:9200/subsearch --limit 1000 --type=mapping && \
	elasticdump --input=my_index.json --output=http://localhost:9200/subsearch --limit 1000 --type=data


RUN python3 -m pip install -r requirements.txt
RUN python3 -m pip install -U pip setuptools wheel
RUN python3 -m pip install --force-reinstall https://github.com/yt-dlp/yt-dlp/archive/master.tar.gz

CMD /etc/init.d/elasticsearch start && sleep 60 && ./api.py
