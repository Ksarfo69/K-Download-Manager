# K-Download Manager

I built a trashy download manager. If you would like to make it better, send in a contribution. Enjoy!

# Features
- Pause (Just send a SIGINT signal).
- Resume (Will resume automatically if URL produces the same hash).
- Can specify chunk size (in bytes).
- Can specify max number of connections.
- Can cap downloaded bytes (I don't know why I added this).

# Usage
- Start app. 
    ```bash
    pip install -r requirements.txt
    uvicorn app.main:app
    ```

- Download
     ```bash
     curl -X 'POST' \
  'http://localhost:8000/api/download' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "url": "https://example.com/download?file=some_video.mp4"
  }'
     ```

- View download status SSE
     ```
     http://localhost:8000/api/events
     ```

- View 'Docs'.
    ```
    Visit 'http://localhost:8000/api/docs' in browser.
    ```