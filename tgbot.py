import requests
import logging
from telegram.ext import Application, MessageHandler, filters, CommandHandler, CallbackQueryHandler
from telegram import ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Bot
from math import cos, sin, pi, sqrt, atan2
import openai
from keys import ORG_KEY, BOT_KEY, GPT_KEY, YND_KEY

# Запускаем логгирование

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG
)

logger = logging.getLogger(__name__)
MAP_ZOOM = 8
ORG_TOKEN = ORG_KEY
BOT_TOKEN = BOT_KEY
YND_TOKEN = YND_KEY
openai.api_key = GPT_KEY
bot = Bot(BOT_TOKEN)
search_org = False
lastpos = []


def get_coords(place):
    geocoder_request = "https://geocode-maps.yandex.ru/1.x/?apikey=" + YND_TOKEN + "&format=json&geocode=" + place
    response = requests.get(geocoder_request)
    json_response = response.json()
    if json_response["response"]["GeoObjectCollection"]["metaDataProperty"]["GeocoderResponseMetaData"]["found"] == '0':
        return False
    toponym = json_response["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]
    toponym_coodrinates = toponym["Point"]["pos"].split()
    return toponym_coodrinates


async def setmode(update, context):
    try:
        if len(update.message.text.split()) < 2:
            await update.message.reply_text('После функции вы должны ввести тип карты')
            return
        mode = update.message.text.split()[1].lower()
        if mode == 'спутник':
            context.user_data['mode'] = 'sat'
        elif mode == 'схема':
            context.user_data['mode'] = 'map'
        elif mode == 'гибрид':
            context.user_data['mode'] = 'sat%2Cskl'
        else:
            await update.message.reply_text('Пожалуйста, введите один из типов карт (схема, спутник или гибрид)')
            return
        await update.message.reply_text('Тип карты изменён на ' + mode)
    except:
        await update.message.reply_text('Произошла непредвиденная ошибка')


async def setzoom(update, context):
    try:
        if len(update.message.text.split()) < 2:
            await update.message.reply_text('После функции вы должны ввести уровень увеличения карты')
            return
        zoom = update.message.text.split()[1]
        if zoom.isdigit():
            if 0 <= int(zoom) <= 17:
                context.user_data['zoom'] = int(zoom)
                await update.message.reply_text('Zoom ' + str(zoom) + ' установлен')
                return
        await update.message.reply_text('Нужно ввести число от 0 до 17')
    except:
        await update.message.reply_text('Произошла непредвиденная ошибка')


def make_map_img(update, context, coords):
    zoom = 9
    mode = 'map'
    if 'mode' in context.user_data:
        mode = context.user_data['mode']
    if 'zoom' in context.user_data:
        zoom = context.user_data['zoom']
    geocoder_img = requests.get(
        'https://static-maps.yandex.ru/1.x/?l=' + mode + '&ll=' + str(coords[0]) + '%2C'
        + str(coords[1]) + '&z=' + str(zoom)
    ).content

    with open("output.png", "wb") as f:
        f.write(geocoder_img)


async def showmap(update, context, repeat=False):
    try:
        if len(update.message.text.split()) < 2 and not repeat:
            await update.message.reply_text('После функции вы должны указать название места')
            return
        if 'lastplace' not in context.user_data or not repeat:
            place = ' '.join(update.message.text.split()[1:])
            context.user_data['lastplace'] = place
        else:
            place = context.user_data['lastplace']
        place = place.replace('/showmap', '')
        if place[0] == ' ':
            place = place[1:]
        user = update.message.chat_id
        req = get_coords(place)
        if not req:
            await update.message.reply_text('Похоже, такого места на карте нет')
            return
        await update.message.reply_text('Отправляю карту по запросу "' + place + '"')
        await bot.send_chat_action(chat_id=update.message.chat_id, action='upload_photo')
        make_map_img(update, context, req)
        await context.bot.send_photo(user, open('output.png', 'rb'), reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Повторить запрос", switch_inline_query_current_chat='/showmap ' + place)]]))
    except:
        await update.message.reply_text('Произошла непредвиденная ошибка')


async def repeat_last_place(update, context):
    if 'lastplace' not in context.user_data:
        await update.message.reply_text('Вы еще не запрашивали карту определенного места')
        return
    await showmap(update, context, True)


async def distance(update, context):
    user = update.message.chat_id
    request = update.message.text.replace('/distance', '').split(';')
    try:
        if len(request) != 2:
            await update.message.reply_text('Вы должны ввести названия двух географических объектов через знак-разделитель ";"')
            return
        objcords1 = get_coords(request[0].strip())
        objcords2 = get_coords(request[1].strip())
        if not objcords1 or not objcords2:
            await update.message.reply_text('Похоже, этого объекта нет на карте')
            return

        dist = meas_distance(float(objcords1[1]), float(objcords1[0]), float(objcords2[1]), float(objcords2[0]))
        if dist < 1000:
            await update.message.reply_text(
                'Расстояние между "' + request[0].strip() + '" и "' + request[1].strip() + '" равняется ' + str(
                    round(dist, 1)) + ' (в метрах)')
        else:
            await update.message.reply_text(
                'Расстояние между "' + request[0].strip() + '" и "' + request[1].strip() + '" равняется ' + str(
                    round(dist / 1000, 1)) + ' (в км)')
        await bot.send_chat_action(chat_id=update.message.chat_id, action='upload_photo')
        geocoder_img = requests.get(
            'https://static-maps.yandex.ru/1.x/?l=map&pt=' + objcords1[0] + '%2C' + objcords1[1] + '%2Corg~' + objcords2[0] + '%2C' + objcords2[1] + '%2Corg'
        ).content
        if geocoder_img:
            with open("output.png", "wb") as f:
                f.write(geocoder_img)
            await context.bot.send_photo(user, open('output.png', 'rb'))
    except:
        await update.message.reply_text('Произошла непредвиденная ошибка')


def meas_distance(lt1, lg1, lt2, lg2):
    pi80 = pi / 180.0
    lat1 = lt1 * pi80
    lng1 = lg1 * pi80
    lat2 = lt2 * pi80
    lng2 = lg2 * pi80

    r = 6372797.0
    dlat = (lat2 - lat1) / 2
    dlng = (lng2 - lng1) / 2
    a = sin(dlat) * sin(dlat) + cos(lat1) * cos(lat2) * sin(dlng) * sin(dlng)
    c = 2.0 * atan2(sqrt(a), sqrt(1.0 - a))
    dist = r * c
    return dist


async def start(update, context):
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет {user.mention_html()}! Это бот, " +
        "который показывает карты. Для ознакомления с функционалом воспользуйтесь командой /help",
        reply_markup=ReplyKeyboardMarkup(
        [[KeyboardButton('Отправить геопозицию', request_location=True)]])
    )


async def help(update, context):
    await update.message.reply_text("""Для того чтобы посмотреть карту, введите команду /showmap
и название места которое вы хотели бы увидеть через пробел.

Для изменения масштаба карты введите команду /setzoom и число от 0 до 17 через пробел.

Для изменения режима просмотра карты введите команду /setmode и название одного из режимов просмотра
('схема', 'спутник' или 'гибрид') через пробел.

Если же вы хотите поторить запрос предыдущего места, но не хотите заново писать команду - воспользуйтесь командой /r,
она не принимает никаких аргументов.

Чтобы узнать расстояние между двумя географическими объектами введите команду /distance и, после пробела, 
два географических объета через знак-разделитель ";".

Также, нажав кнопку 'отправить геопозицию', вы можете после отправки геопозиции задать запрос для поиска организаций
рядом с вами. А после можете выбрать кнопку с номреом организации которая вамподходит, бот отправит вам карту, 
на которой будет отмечено ваше текущее местоположение и местоположение выбранной организации

Чтобы посмотреть иформацию о какой-либо достопримечательности или определенном географическом объекте, вы
можете использовать команду /infoaboutsight
""")


async def echo(update, context):
    global search_org
    if search_org:
        try:
            orgsearch_request = 'https://search-maps.yandex.ru/v1/?text=' \
                                + update.message.text +'&ll=' \
                                + str(lastpos[0]) + '%2C' + str(lastpos[1]) \
                                +'&spn=0.063575, 0.063575&lang=ru_RU&apikey=' + ORG_TOKEN
            response = requests.get(orgsearch_request)
            json_response = response.json()
            res = []
            butmass = []
            callbackres = []
            for i in range(len(json_response['features'])):
                temporgcords = [json_response['features'][i]['geometry']['coordinates'][0],
                                json_response['features'][i]['geometry']['coordinates'][1]]
                res.append(str(i + 1) + '.' + json_response['features'][i]['properties']['name']
                           + ' - ' +
                           str(round(meas_distance(lastpos[0], lastpos[1],
                           temporgcords[0], temporgcords[1])))
                           + 'м')
                butmass.append(InlineKeyboardButton(str(i + 1), callback_data=str([temporgcords, update.message.chat_id])))
            cnt = 1
            numofgrp = 0
            newbutmass = [[]]
            for i in butmass:
                if cnt % 5 == 0:
                    numofgrp += 1
                    newbutmass.append(list())
                newbutmass[numofgrp].append(i)
                cnt += 1
            await update.message.reply_text('\n'.join(res), reply_markup=InlineKeyboardMarkup(newbutmass))
            search_org = False
        except:
            await update.message.reply_text('Произошла непредвиденная ошибка')
    elif '@MapsYandexBot' in update.message.text[:14]:
        command = update.message.text[14:]
        print(command)
        if command.split()[0] == '/showmap':
            await showmap(update, context, False)


async def location(update, context):
    global lastpos
    global search_org
    lastpos = (update.message.location.longitude, update.message.location.latitude)
    await update.message.reply_text('Введите запрос для поиска по организациям рядом с вами')
    search_org = True


async def info_about_sight(update, context):
    sight = update.message.text.replace('/info_about_sight', '')
    if get_coords(sight.strip()):
        #try:
        await bot.send_chat_action(chat_id=update.message.chat_id, action='typing')
        response = openai.Completion.create(
            model="text-davinci-003",
            prompt='Расскажи о географическом объекте "' + sight + '"',
            temperature=0.9,
            max_tokens=4000,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.6,
            stop=[" Human:", " AI:"]
        )
        await update.message.reply_text('Формирую описание георгафического объекта "' + sight + '"')
        await update.message.reply_text(response['choices'][0]['text'])
        #except:
            #await update.message.reply_text('Произошла непредвиденная ошибка')
    else:
        await update.message.reply_text('Не удалось найти такого георгафического объекта')


async def perform(update, context):
    pos = eval(update.callback_query.data)[0]
    user = eval(update.callback_query.data)[1]
    try:
        await bot.send_chat_action(chat_id=user, action='upload_photo')
        geocoder_img = requests.get(
            'https://static-maps.yandex.ru/1.x/?l=map&pt=' + str(lastpos[0]) + '%2C' + str(lastpos[1]) + '%2Cya_ru~'
            + str(pos[0]) + '%2C' + str(pos[1]) + '%2Cpm2dol'
        ).content
        if geocoder_img:
            with open("output.png", "wb") as f:
                f.write(geocoder_img)
            await context.bot.send_photo(user, open('output.png', 'rb'))
    except:
        await bot.send_message(chat_id=user, text='Произошла непредвиденная ошибка')


def main():
    print(meas_distance(0, 0, 0.063575, 0.063575))
    application = Application.builder().token(BOT_TOKEN).build()

    text_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, echo)
    application.add_handler(text_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("showmap", showmap))
    application.add_handler(CommandHandler("setzoom", setzoom))
    application.add_handler(CommandHandler("setmode", setmode))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("r", repeat_last_place))
    application.add_handler(CommandHandler("distance", distance))
    application.add_handler(CommandHandler("infoaboutsight", info_about_sight))
    application.add_handler(CallbackQueryHandler(perform))
    application.add_handler(MessageHandler(filters.LOCATION, location))
    application.run_polling()


if __name__ == '__main__':
    main()