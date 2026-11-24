"""UofT Krillion backend.

Layers, inner to outer (imports only point inward):
    domain/          game rules and entities, pure Python
    application/     use cases and the ports they need
    infrastructure/  adapters for those ports (Postgres, OpenRouter)
    entrypoints/     HTTP API and CLI jobs; the composition roots
"""
