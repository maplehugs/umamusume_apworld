"""UmaPS Admin Panel: a browser desktop (VivloToolkit's design) for editing the
private server's Global and JP saves.

    python3 -m admin_panel                  # http://localhost:8189
    python3 -m admin_panel --port 9000 --no-browser

The web process is plain stdlib. Every save edit runs in a per-region worker
process (admin_panel/worker.py, started with UMA_REGION=global|jp) because the
server's master.mdb connection and many of its lookups are fixed to one region
per process. Workers reuse the server's own handlers plus admin.py / career.py,
so an edit made here follows the same rules as the CLI tools.
"""
