#import config
from . import config
#from okxsocket import okx_response_handler, okx_subscribe, okx_login_request
from .okxsocket import okx_response_handler, okx_subscribe, okx_login_request

import signal
import logging
import json
import asyncio
import websockets.client
import websockets.exceptions
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup

fh = logging.FileHandler('app.log', mode = 'a')
fh.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

formatter = logging.Formatter(fmt = '{asctime} {name} {levelname}: {message}', style = '{')
fh.setFormatter(formatter)
ch.setFormatter(formatter)

#logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
botlogger = logging.getLogger(__name__)
botlogger.setLevel(logging.DEBUG)

botlogger.addHandler(fh)
botlogger.addHandler(ch)

wslogger = logging.getLogger("websockets")
wslogger.setLevel(logging.DEBUG)

#wslogger.addHandler(fh)
wslogger.addHandler(ch)

async def subscribe_quotes(update: Update, context: ContextTypes):
    if update.effective_chat.id not in config.CHAT_TASKS:
        config.CHAT_TASKS[update.effective_chat.id] = []

    keyboard = list()
    keyboard.append(list())
    
    for k in config.SUBSCRIPTIONS.keys():
        keyboard[0].append(InlineKeyboardButton(k, callback_data=f'{{"sub":"{k}"}}'))
    keyboard.append([InlineKeyboardButton('All', callback_data=f'{{"sub":"All"}}')])

    reply_markup = InlineKeyboardMarkup(keyboard)
            
    await update.message.reply_text(text='Please subscribe for quotes:', reply_markup = reply_markup)

    return

async def stop_callback(update : Update, context: ContextTypes):
    pass

async def unsubscribe_quotes(update : Update, context: ContextTypes):
    for task in config.CHAT_TASKS[update.effective_chat.id]:
        if task.done() == False:
            task.cancel()
            await task

    config.CHAT_TASKS[update.effective_chat.id] = []

    await update.message.reply_text(text='Unsubscribed')    
    
    return

async def update_subscribtions(update: Update, context: ContextTypes):
    await update.callback_query.answer()

    try:
        subscription_data = json.loads(update.callback_query.data)
    
        if 'sub' in subscription_data:
            instId = subscription_data['sub']
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton('5 min', callback_data=f'{{"instId":"{instId}", "period":"300"}}'),
                                                  InlineKeyboardButton('15 min', callback_data=f'{{"instId":"{instId}", "period":"900"}}'),
                                                  InlineKeyboardButton('1 hour', callback_data=f'{{"instId":"{instId}", "period":"3600"}}')]])
            
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Please select period for {instId}:', reply_markup=reply_markup)

        elif 'period' in subscription_data:
            instId = subscription_data['instId']            
            chat_period = (update.effective_chat.id, int(subscription_data['period']))
            if instId == 'All':
                for k in config.SUBSCRIPTIONS.keys():
                    if chat_period not in config.SUBSCRIPTIONS[k]:
                        config.SUBSCRIPTIONS[k].append(chat_period)
            elif chat_period not in config.SUBSCRIPTIONS[instId]:
                config.SUBSCRIPTIONS[instId].append(chat_period)            

            await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Subscription for {instId} {chat_period[1] // 60} min successful')
            botlogger.info(f'Subscription for {instId} {chat_period[1] // 60} min is successful')
    
    except Exception as exc:
        botlogger.error(exc)

    return

def sigint_handler(signum, frame):    
    botlogger.info('Stopping...')
    config.RUN = False

async def main():
    signal.signal(signal.SIGINT, sigint_handler)
    
    application = ApplicationBuilder().token(config.tg_token).build()
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    botlogger.info('Bot has started')    
    
    application.add_handler(CommandHandler('subscribe', subscribe_quotes))
    application.add_handler(CommandHandler('unsubscribe', unsubscribe_quotes))
    application.add_handler(CallbackQueryHandler(update_subscribtions))
    #application.add_handler(CommandHandler('start', subscribe_data))
    #application.add_handler(CommandHandler('stop', stop_callback))
    
    async for websocket in websockets.client.connect(config.wsslink):
        try:
            await okx_login_request(websocket)
            
            async with asyncio.TaskGroup() as  tg:
                for k in config.SUBSCRIPTIONS.keys():
                    tg.create_task(okx_subscribe(websocket, k))
            
            await okx_response_handler(websocket, application.bot)

            if config.RUN == False:
                await websocket.close()
                break

        except websockets.exceptions.ConnectionClosedError:
            continue
    
    await application.updater.stop()
    await application.stop()
    await application.shutdown()
    botlogger.info('Bot has stopped')

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        botlogger.error(exc)