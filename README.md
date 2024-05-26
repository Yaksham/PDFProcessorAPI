# PDFconvertAPI
An API to convert pdf files into text using FastAPI
### Features
1. Two endpoints - Webhook and Polling
2. API rate limiting and file size restrictions to prevent abuse
3. Uses Celery for task processing
4. API token authentication
5. Sanitized file uploads to ensure only valid files are processed
6. Unit tests and logging
7. Redis server to store processed pdf files

## Installation

1. Clone this repository 
2. Install python 3.12.3 (other versions might work, but haven't been tested)
3. (Optional) Create a virtual python environment
    ``` 
    $ python -m venv .venv
    $ source .venv/bin/activate
    ```

4. Install dependencies:
    ```
      pip install -r requirements.txt
    ```
## Running the Server

1. Export your API key
    ```
    export API_KEY=<your key here>
    ```
2. Run Redis Server
    ```
    redis-server
    ```
3. Run Celery
    ```
    celery -A main.celery_app worker --loglevel=INFO
    ```
4. Run the FastAPI server
    ```
    fastapi dev main.py
    ```

## Hitting Endpoints
### Through Swagger UI
You can visit http://localhost:8000/docs after running the fastapi server to hit the endpoints using a GUI.
### Through cURL
1. Webhook - returns a file_id
    ```
    curl -X POST "http://localhost:8000/webhook" -H "api_key: <api_key>" -F "file=@/path/to/file.pdf"
    ```
2. Polling - returns a processing status or the text contents of the pdf if processing has been completed.
    ```
    curl -X GET "http://localhost:8000/polling/{file_id}" -H "api_key: <api_key>"
    ```

## Documentation
Documentation is available through Swagger UI at http://localhost:8000/docs and details what each endpoint does and the reponses for various scenarios.

## Testing
You can run unit tests for the API using pytest. Remember to export your API key environment variable.
  ```
  pytest test_main.py
  ```
