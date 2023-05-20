#import config
from . import config
import logging
import asyncio
import base64
import hashlib
import hmac
import time
import json

okxlogger = logging.getLogger(__name__)
okxlogger.setLevel(logging.DEBUG)

fh = logging.FileHandler('app.log', mode = 'a')
fh.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

formatter = logging.Formatter(fmt = '{asctime} {name} {levelname}: {message}', style = '{')
fh.setFormatter(formatter)
ch.setFormatter(formatter)

okxlogger.addHandler(fh)
okxlogger.addHandler(ch)

async def okx_response_handler(websocket, bot):
    async for msg in websocket:        
        try:
            if config.RUN == True:
                resp = json.loads(msg)
                
                if 'event' in resp:
                    okxlogger.debug(msg)
                    match resp['event']:
                        case 'login':
                            okxlogger.info(f'{resp["event"]} for {bot.username}')
                        case 'subscribe':                            
                            okxlogger.info(f'{resp["event"]} for {resp["arg"]["channel"]} {resp["arg"]["instId"]}')
                        case 'error':
                            okxlogger.error(f'{resp["msg"]}')
                            await websocket.close()
                elif 'data' in resp:
                    price_data = resp['data'][0]                
                    instId = price_data['instId']
                    markPx = price_data['markPx'][:price_data['markPx'].index('.')+3]
                    
                    for chat_period in config.SUBSCRIPTIONS[instId]:
                        await bot.send_message(chat_id=chat_period[0], text=f'{instId} {markPx}')
                        okxlogger.debug(f'{bot.username} {chat_period[0]} {instId} {markPx}')
                        config.SUBSCRIPTIONS[instId].remove(chat_period)
                        
                        task = asyncio.create_task(timer_for_subscribtions(instId, chat_period))
                        config.CHAT_TASKS[chat_period[0]].append(task)
                        okxlogger.debug(f'asyncio timer task {task.get_name()} created')
            else:                
                break

        except Exception as exc:
            okxlogger.error(exc)            
            break
        
    return

async def okx_subscribe(websocket, instId):    
    # Mark price channel    
    subscribe_args = {'channel' : 'mark-price', 'instId' : instId}

    req = {'op' : 'subscribe', 'args' : [subscribe_args]}

    await websocket.send(json.dumps(req))

    return

async def okx_login_request(websocket):    
    timestamp = str(int(time.time()))
    
    msg = '{0}GET/users/self/verify'.format(timestamp)    
    
    sign = base64.standard_b64encode(hmac.new(config.secretkey.encode('latin-1'), bytes(msg, 'latin-1'), hashlib.sha256).digest())
    #config.apikey.encode('utf-8')
    
    login_args = {'apiKey' : config.apikey,
                  'passphrase' : config.passphrase,
                  'timestamp' : timestamp,
                  'sign' : sign.decode(encoding = 'utf-8')}
    req = {'op' : 'login', 'args' : [login_args]}    

    await websocket.send(json.dumps(req))

    return

async def timer_for_subscribtions(instId, chat_period):
    try:
        await asyncio.sleep(chat_period[1])
        
        config.SUBSCRIPTIONS[instId].append(chat_period)
    
    except asyncio.CancelledError as err:
        okxlogger.debug(f'{instId} for {chat_period[1] // 60} min subscription was cancelled.')

    return