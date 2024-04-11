# K-Download Manager

I built a trashy download manager. If you would like to make it better, send in a contribution. Enjoy!

# Features
- Pause (Just send a SIGINT signal).
- Resume (Will resume automatically if URL produces the same hash).
- Can specify chunk size (in bytes).
- Can specify max number of connections.
- Can cap downloaded bytes (I don't know why I added this).

# Usage
- Run. 
    ```bash
    python download_manager.py https://some-url
    ```
  
- View 'Docs'.
    ```bash
    python download_manager.py --help
    ```