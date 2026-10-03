import os
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .clips import router as clips_router
from .social import router as social_router
from .queue import router as queue_router, run
from . import store

@asynccontextmanager
async def lifespan(app):
    stop=threading.Event()
    worker=None
    if store.durable() and os.getenv('SCHEDULER_ENABLED','false')=='true':
        worker=threading.Thread(target=run,args=(stop,),daemon=True)
        worker.start()
    yield
    stop.set()
    if worker: worker.join(timeout=5)

app=FastAPI(title='GameClip Publisher API',version='0.3.0',lifespan=lifespan)
app.include_router(clips_router)
app.include_router(social_router)
app.include_router(queue_router)

@app.get('/')
def root():return {'app':'GameClip Publisher','status':'ok','version':'0.3.0'}

@app.get('/health')
def health():return {'status':'healthy'}
