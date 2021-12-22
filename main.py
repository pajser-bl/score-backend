from collections import OrderedDict
from datetime import timedelta, datetime
from enum import Enum
from random import getrandbits, randrange, choice, sample
from uuid import uuid4

import uvicorn
from operator import itemgetter
from fastapi import FastAPI
from fastapi_socketio import SocketManager
from pytz import utc
from starlette.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

events_store = {}

app = FastAPI()

origins = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'localhost:3000'
    '127.0.0.1:3000'
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

socket_manager = SocketManager(app=app,
                               async_mode="asgi")


class EventStatus(str, Enum):
    NOT_STARTED = 'NOT_STARTED'
    LIVE = 'LIVE'
    STOPPED = 'STOPPED'
    FINISHED = 'FINISHED'


class EventPeriod(int, Enum):
    NOT_STARTED = 0
    FIRST_HALF_TIME = 1
    SECOND_HALF_TIME = 2


class UpdateEventMessages(str, Enum):
    NEW_EVENT = 'NEW_EVENT'
    SCORE_UPDATE = 'SCORE_UPDATE'
    PERIOD_UPDATE = 'PERIOD_UPDATE'
    STATUS_UPDATE = 'STATUS_UPDATE'
    REMOVE_EVENT = 'REMOVE_EVENT'


teams = ['FC Bayern Munich',
         'SV Werder Bremen',
         'Borussia Dortmund',
         'VfB Stuttgart',
         'Hamburger SV',
         'Borussia Mönchengladbach',
         'Eintracht Frankfurt',
         'FC Schalke 04',
         'FC Köln',
         'FC Kaiserslautern',
         'Bayer 04 Leverkusen',
         'Hertha BSC',
         'VfL Bochum',
         'FC Nürnberg',
         'Hannover 96',
         'MSV Duisburg',
         'VfL Wolfsburg',
         'Fortuna Düsseldorf',
         'Karlsruher SC',
         'SC Freiburg',
         'Eintracht Braunschweig',
         'TSV 1860 München',
         'Arminia Bielefeld',
         'FSV Mainz 05',
         'TSG 1899 Hoffenheim',
         'KFC Uerdingen 05',
         'F.C. Hansa Rostock',
         'FC Augsburg',
         'FC St. Pauli',
         'SV Waldhof Mannheim',
         'Kickers Offenbach',
         'Rot-Weiss Essen',
         'RB Leipzig',
         'FC Energie Cottbus',
         'FC Saarbrücken',
         'SV Darmstadt 98',
         'Alemannia Aachen',
         'Dynamo Dresden',
         'SG Wattenscheid 09',
         'Rot-Weiß Oberhausen',
         'FC Union Berlin',
         'FC 08 Homburg',
         'Wuppertaler SV',
         'Borussia Neunkirchen',
         'SpVgg Greuther Fürth',
         'SC Paderborn 07',
         'FC Ingolstadt 04',
         'SpVgg Unterhaching',
         'Stuttgarter Kickers',
         'Tennis Borussia Berlin',
         'SSV Ulm 1846',
         'VfB Leipzig',
         'Blau-Weiß 1890 Berlin',
         'SC Fortuna Köln',
         'SC Tasmania 1900 Berlin',
         'SC Preußen Münster']


@socket_manager.on('join')
def join_room(sio, room_name, *args, **kwargs):
    socket_manager.enter_room(sid=sio, room=room_name)


@socket_manager.on('leave')
def leave_room(sio, room_name, *args, **kwargs):
    socket_manager.leave_room(sid=sio, room=room_name)


def generate_competitors():
    return sample(teams, 2)


def generate_new_event(time):
    home, away = generate_competitors()
    return dict(id=str(uuid4()),
                competitors=dict(home=home, away=away),
                scheduled=str(time),
                score=dict(home=0, away=0),
                status=EventStatus.NOT_STARTED,
                period=EventPeriod.NOT_STARTED)


async def new_event(event):
    events_store[event.get('id')] = event
    await socket_manager.emit(UpdateEventMessages.NEW_EVENT, event, to='NEW_EVENT')


async def event_status_change(event, status):
    event['status'] = status
    events_store[event.get('id')] = event
    await socket_manager.emit(UpdateEventMessages.STATUS_UPDATE, dict(id=event.get('id'),
                                                                      status=event.get('status')),
                              to=event.get('id'))


async def event_score_change(event):
    home = event['score']['home']
    away = event['score']['away']
    event['score'] = dict(home=home + getrandbits(1),
                          away=away + getrandbits(1))
    events_store[event.get('id')] = event
    await socket_manager.emit(UpdateEventMessages.SCORE_UPDATE, dict(id=event.get('id'),
                                                                     score=event.get('score')),
                              to=event.get('id'))


async def event_period_change(event, event_period):
    event['period'] = event_period
    events_store[event.get('id')] = event
    await socket_manager.emit(UpdateEventMessages.PERIOD_UPDATE, dict(id=event.get('id'),
                                                                      period=event.get('period')),
                              to=event.get('id'))


async def remove_event(event):
    events_store.pop(event.get('id'))
    await socket_manager.emit(UpdateEventMessages.REMOVE_EVENT, dict(id=event.get('id')),
                              to=event.get('id'))


def schedule_new_event(_store):
    now = datetime.utcnow()
    event_announced = now + timedelta(seconds=choice([2, 4, 6, 8, 10]))
    event_start = event_announced + timedelta(seconds=choice([15, 30, 45, 60]))
    end_of_first_halftime = event_start + timedelta(seconds=120)
    start_of_second_halftime = end_of_first_halftime + timedelta(seconds=30)
    end_of_match = start_of_second_halftime + timedelta(seconds=120)
    remove_match = end_of_match + timedelta(seconds=60)

    event = generate_new_event(event_start)

    _store.add_job(new_event,
                   'date',
                   args=[event],
                   run_date=event_announced)

    _store.add_job(event_status_change,
                   'date',
                   args=[event, EventStatus.LIVE],
                   run_date=event_start)

    _store.add_job(event_period_change,
                   'date',
                   args=[event, EventPeriod.FIRST_HALF_TIME],
                   run_date=event_start)

    for i in range(5):
        if bool(getrandbits(1)):
            _store.add_job(event_score_change,
                           'date',
                           args=[event],
                           run_date=event_start + timedelta(seconds=randrange(5, 105)))

    _store.add_job(event_status_change,
                   'date',
                   args=[event, EventStatus.STOPPED],
                   run_date=end_of_first_halftime)

    _store.add_job(event_period_change,
                   'date',
                   args=[event, EventPeriod.SECOND_HALF_TIME],
                   run_date=start_of_second_halftime)

    _store.add_job(event_status_change,
                   'date',
                   args=[event, EventStatus.LIVE],
                   run_date=start_of_second_halftime)

    for i in range(5):
        if bool(getrandbits(1)):
            _store.add_job(event_score_change,
                           'date',
                           args=[event],
                           run_date=start_of_second_halftime + timedelta(seconds=randrange(5, 105)))

    _store.add_job(event_status_change,
                   'date',
                   args=[event, EventStatus.FINISHED],
                   run_date=end_of_match)

    _store.add_job(remove_event,
                   'date',
                   args=[event], run_date=remove_match)


@app.get('/')
def index():
    return '1337'


@app.get('/events')
def get_events():
    events = sorted(list(events_store.values()),
                    key=itemgetter('scheduled'),
                    reverse=True)
    return dict(total=len(events_store.keys()),
                events=events)


@app.on_event('startup')
def startup():
    store = AsyncIOScheduler(timezone=utc)
    store.add_job(schedule_new_event,
                  'interval',
                  args=[store],
                  seconds=5,
                  jitter=30)
    store.start()


if __name__ == '__main__':
    uvicorn.run("main:app",
                host='0.0.0.0',
                port=8000,
                debug=True,
                reload=True)
