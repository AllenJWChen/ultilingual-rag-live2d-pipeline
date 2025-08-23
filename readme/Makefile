init:
	pip install -r requirements.txt

ingest:
	python services/ingest/01_extract.py && \
	python services/ingest/02_build_index.py

api:
	uvicorn services.api.server:app --reload --port 8000

tts:
	python services/live2d/tts_stub.py "你好，這是多語音示範。"
