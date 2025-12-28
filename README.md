# Bot Manager

This bot orchestrates tasks locally on a single instance (e.g., Koyeb).

## Setup

1.  **Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Binary**:
    Ensure the `port` binary is in the same directory as `bot.py` and is executable (`chmod +x port`).

3.  **Run**:
    ```bash
    python bot.py
    ```

## Docker (Koyeb)

```bash
docker build -t bot .
docker run -d bot
```

## Commands
- `/deploy <host> <port> <time>`: Start only local session.
- `/stop_session`: Stop active sessions.
- `/grant <id> <days>`: Approve user access.
