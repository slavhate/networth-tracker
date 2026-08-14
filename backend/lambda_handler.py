from mangum import Mangum

from main import app

# lifespan="off": this app has no genuine ASGI-lifespan-dependent state (no
# shutdown cleanup, no startup-built connection pool). Mangum's default
# lifespan="auto" would otherwise re-run FastAPI's full startup/shutdown
# cycle on every single invocation (not just cold start), which is needless
# overhead and would re-run demo-data seeding on every request if
# CREATE_DEMO_DATA is ever set to true.
handler = Mangum(app, lifespan="off")
