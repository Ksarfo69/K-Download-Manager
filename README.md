# K-Download Manager

I built a trashy download manager. If you would like to make it better, send in a contribution. Enjoy!

# Features
- Pause.
- Resume.
- Can specify chunk size (in bytes).
- Can specify max number of connections.

# Usage
- Start backend. 
    ```bash
    pip install -r requirements.txt
    uvicorn app.main:app
    ```
  
- Start frontend. 
    ```bash
    npm i
    npm start
    ```

- View App.
    ```
    Visit 'http://localhost:3000' in browser.
    ```