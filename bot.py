import os
import logging
import asyncio
import re
import uuid
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from decimal import Decimal
from database import Database
from games import CubeGame, GameResult, TwoDiceGame, RockPaperScissorsGame, BasketballGame, DartsGame, SlotsGame, BowlingGame
from cryptopay import CryptoPayAPI
from typing import Optional, Dict
import random
import time
import aiosqlite
import aiogram.exceptions

class AdminStates(StatesGroup):
    EDIT_USER = State()
    SEARCH_USERS = State()
    CONFIRM_DELETE = State()
    BROADCAST = State()
    BROADCAST_BUTTONS = State()
    CHECK_BALANCE = State()
    ADD_BALANCE = State()

class GameStates(StatesGroup):
    DICE_BET = State()
    DICE_TWO_BET = State()
    RPS_BET = State()
    BET_AMOUNT = State()

class BettingStates(StatesGroup):
    SELECT_GAME = State()
    SELECT_BET_TYPE = State()
    ENTER_AMOUNT = State()


load_dotenv()


logging.basicConfig(level=logging.INFO)


bot = Bot(token=os.getenv('BOT_TOKEN'), default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
db = Database()
crypto_pay = CryptoPayAPI(os.getenv('CRYPTO_PAY_TOKEN'))


CASINO_NAME = os.getenv('CASINO_NAME', 'GlacialCasino')
CASINO_EMOJI = os.getenv('CASINO_EMOJI', '🎲')


INVOICE_URL = os.getenv('INVOICE_URL')
LOGS_ID = -1002870089940
BETS_ID = -1002696966128
BETS_LINK = os.getenv('BETS_CHANNEL_LINK')


SUPPORT_LINK = os.getenv('SUPPORT_LINK')
ADAPTER_LINK = os.getenv('ADAPTER_LINK')
RULES_LINK = os.getenv('RULES_LINK')
CHAT_LINK = os.getenv('CHAT_LINK')
TUTORIAL_LINK = os.getenv('TUTORIAL_LINK')
NEWS_LINK = os.getenv('NEWS_LINK')

GIDE_LINK = os.getenv('GIDE_LINK')

async def links():
    return f"""
<a href="https://t.me/{(await bot.get_me()).username}?start=refs">🤝 Cотрудничество</a> | <a href="{GIDE_LINK}">💬 Инструкция</a> | <a href="https://t.me/{(await bot.get_me()).username}?start=">🎰 Наш бот</a> | <a href="{NEWS_LINK}">❓ Новости</a>
""".replace("\n", "")

@dp.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("❎ Сейчас нет активных действий.")
    else:
        await state.clear()
        await message.answer("❌ Все действия отменены.", reply_markup=create_main_keyboard())

def create_main_keyboard():
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [
            KeyboardButton(text="🎲 Сделать ставку")
        ],
        [
            KeyboardButton(text="👤 Профиль"),
            KeyboardButton(text="📊 Статистика")
        ],
        [
            KeyboardButton(text="👥 Реферальная система")
        ]
    ], resize_keyboard=True)
    return keyboard

def create_info_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Поддержка", url=SUPPORT_LINK),
            InlineKeyboardButton(text="Переходник", url=ADAPTER_LINK)
        ],
        [InlineKeyboardButton(text="Правила", url=RULES_LINK)],
        [InlineKeyboardButton(text="Назад", callback_data="back_in_start")]
    ])
    return keyboard

def create_user_management_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Реф.Баланс", callback_data=f"edit_ref_balance_{user_id}"),
            InlineKeyboardButton(text="Реф.Заработок", callback_data=f"edit_ref_earnings_{user_id}")
        ],
        [
            InlineKeyboardButton(text="Реф.Счетчик", callback_data=f"edit_ref_count_{user_id}"),
            InlineKeyboardButton(text="Удалить", callback_data=f"delete_user_{user_id}")
        ],
        [InlineKeyboardButton(text="Назад", callback_data="admin_users")]
    ])

@dp.message(CommandStart(), StateFilter('*'))
async def start_handler(message: types.Message, command: CommandObject, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.full_name
    args = command.args  # ← аргумент после /start=

    # 1. Выплата
    if args and len(args) == 8:
        check = await db.get_win_check_token(args)
        if not check:
            await message.answer("<b>Чек не найден или уже активирован.</b>", parse_mode="HTML")
            return
        if check['user_id'] != user_id:
            await message.answer("<b>Этот чек предназначен не для вас.</b>", parse_mode="HTML")
            return
        win_amount = check['amount']
        check_link = check['check_link']
        if check_link:
            await db.mark_win_check_token_used(args)
            await message.answer(
                f"<b>Заберите ваш выигрыш по кнопке ниже</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=f"Забрать {win_amount:.2f}$", url=check_link)]
                ])
            )
        else:
            await message.answer("Ошибка при создании чека. Обратитесь в поддержку.")
        return

    # 2. Реферальная ссылка
    if args and args.isdigit():
        referrer_id = int(args)
        user = await db.get_user(referrer_id)
        current_user = await db.get_user(user_id)
        if user and not current_user and user_id != referrer_id:
            await db.create_user(user_id, username, referrer_id)
            await db.update_ref_balance(referrer_id, user['ref_balance'])
            await message.answer("🎉 Вы зарегистрированы по реферальной ссылке!")
            await bot.send_message(
                chat_id=referrer_id,
                text=f"👤 У вас новый реферал: <code>{username}</code>",
                parse_mode="HTML"
            )

    # 3. Специальные ссылки
    elif args == "games":
        await db.create_user(user_id, username)
        await start_betting(message, state)
        return
    elif args == "refs":
        await db.create_user(user_id, username)
        await show_referral_msg(message)
        return

    # 4. Без аргументов или если пользователь уже есть
    await db.create_user(user_id, username)
    welcome_text = (
        f"🎰 <b>{username}, добро пожаловать в {CASINO_NAME}</b>\n\n"
        f"<b>BunnyCasino — здесь удача сама прискачет к Вам!</b>\n\n"
        f"<blockquote><b>❓ Выберите действие из меню ниже или пропишите одну из доступных команд:</b></blockquote>"
    )
    await message.answer_animation(
        animation=types.FSInputFile("menu.gif"),
        caption=welcome_text,
        reply_markup=create_main_keyboard(),
        parse_mode="HTML"
    )


@dp.message(Command("profile"))
@dp.message(F.text == "👤 Профиль")
async def show_profile_msg(message: types.Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    username = message.from_user.username or message.from_user.full_name

    await message.answer("👤") # Отправляем эмодзи
    await asyncio.sleep(1.5) # Ждем 1.5 секунды

    if not user:
        await message.answer("Пожалуйста, начните с команды /start, чтобы мы могли создать ваш профиль.")
        return
    
    profile_text = (
        f"<b>{ username}, -  Ваш профиль</b>\n\n"
        f"<blockquote>👤 Здесь только самая нужная информация для Вас</blockquote>\n\n"
        f"<blockquote>"
        f"• <b>ID:</b> <code>{user_id}</code>\n"
        f"• <b>Реферальный баланс:</b> <code>{user['ref_balance']:.2f}$</code>\n"
        f"• <b>Заработано с рефералов:</b> <code>{user['ref_earnings']:.2f}$</code>\n"
        f"• <b>Количество рефералов:</b> <code>{user['ref_count']}</code>"
        f"</blockquote>"
    )

    await message.answer_photo(
        photo=types.FSInputFile("profile.jpg"),
        caption=profile_text,
        reply_markup=create_main_keyboard(),
        parse_mode="HTML"
    )
@dp.message(Command("refs"))
@dp.message(F.text == "👥 Реферальная система")
async def show_referral_msg(message: types.Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    username = message.from_user.username or message.from_user.full_name

    await message.answer("👥") # Отправляем эмодзи
    await asyncio.sleep(1.5) # Ждем 1.5 секунды

    if not user:
        await message.answer("Пожалуйста, начните с команды /start, чтобы мы могли создать ваш профиль.")
        return
    
    referral_text = (
        f"<b>{ username }, - это реферальная система {CASINO_NAME}</b>\n\n"
        f"<blockquote>🎁 Приводите к нам Ваших друзей и получайте 15% от их проигрышей</blockquote>\n\n"
        f"<blockquote>"
        f"• <b>Реферальный баланс:</b> <code>{user.get('ref_balance', 0):.2f}$</code>\n"
        f"• <b>Заработано:</b> <code>{user.get('ref_earnings', 0):.2f}$</code>\n"
        f"• <b>Рефералов:</b> <code>{user.get('ref_count', 0)} чел.</code>\n"
        f"• <b><a href='https://t.me/{(await bot.get_me()).username}?start={user_id}'>Реферальная ссылка (зажмите чтобы скопировать)</a></b>\n"
        f"</blockquote>\n\n"
        f"<blockquote>"
        f"⚠ <b>Если реферал выигрывает, с Вашего баланса списывается 15% от его выигрыша.</b>\n"
        f"⚠ <b>Баланс может быть отрицательным.</b>"
        f"</blockquote>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Вывод", callback_data="withdraw_ref_balance")]
    ])
    
    await message.answer_photo(
        photo=types.FSInputFile("referal.jpg"),
        caption=referral_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
@dp.message(Command("stats"))
@dp.message(F.text == "📊 Статистика")
async def show_stats_msg(message: types.Message):
    user_id = message.from_user.id
    stats = await db.get_user_stats(user_id)
    username = message.from_user.username or message.from_user.full_name
    
    await message.answer("📊") # Отправляем эмодзи
    await asyncio.sleep(1.5) # Ждем 1.5 секунды
    
    stats_text = (
        f"<b>{ username }, - это Ваша статистика {CASINO_NAME}</b>\n\n"
        f"<blockquote>📊 Раздел для настоящих ценителей цифр</blockquote>\n\n"
        f"<blockquote>"
        f"• <b>Всего игр:</b> <code>{stats['total_games']}</code>\n"
        f"• <b>Побед:</b> <code>{stats['wins']}</code>\n"
        f"• <b>Поражений:</b> <code>{stats['losses']}</code>\n"
        f"• <b>Процент побед:</b> <code>{stats['win_rate']:.1f}%</code>\n"
        f"• <b>Оборот:</b> <code>{stats['turnover']:.2f}$</code>\n"
        f"• <b>Выиграно всего:</b> <code>{stats['total_won']:.2f}$</code>\n"
        f"• <b>Проиграно всего:</b> <code>{stats['total_lost']:.2f}$</code>"
        f"</blockquote>"
    )
    
    await message.answer_photo(
        photo=types.FSInputFile("profile.jpg"),
        caption=stats_text,
        reply_markup=create_main_keyboard(),
        parse_mode="HTML"
    )

GAMES_DATA = {
    "cube": {
        "name": "🎲 Кубик",
        "types": {
            "чет": "Чет (x1.85)", "нечет": "Нечет (x1.85)", 
            "больше": "Больше 3 (x1.85)", "меньше": "Меньше 4 (x1.85)", 
            "плинко": "Плинко (x0.3-1.95)",
            "1": "Число 1 (x4)", "2": "Число 2 (x4)", "3": "Число 3 (x4)",
            "4": "Число 4 (x4)", "5": "Число 5 (x4)", "6": "Число 6 (x4)",
            "сектор1": "Сектор 1 (x2.5)", "сектор2": "Сектор 2 (x2.5)", "сектор3": "Сектор 3 (x2.5)"
        }
    },
    "two_dice": {
        "name": "🎲🎲 Два кубика",
        "types": {"победа1": "Победа 1 (x1.85)", "победа2": "Победа 2 (x1.85)", "ничья": "Ничья (x3)"}
    },
    "rock_paper_scissors": {
        "name": "👊 КНБ",
        "types": {"камень": "👊 (x2.5)", "ножницы": "✌️ (x2.5)", "бумага": "✋ (x2.5)"}
    },
    "basketball": {
        "name": "🏀 Баскетбол",
        "types": {"гол": "Гол (x1.85)", "мимо": "Мимо (x1.4)"}
    },
    "darts": {
        "name": "🎯 Дартс",
        "types": {"белое": "Белое (x1.85)", "красное": "Красное (x1.85)", "яблочко": "Яблочко (x2.5)", "промах": "Мимо (x2.5)"}
    },
    "slots": {
        "name": "🎰 Слоты",
        "types": {"слоты": "Играть (x5-10)"}
    },
    "bowling": {
        "name": "🎳 Боулинг",
        "types": {"страйк": "Страйк (x4)", "боулпромах": "Промах (x4)", "боулинг": "Плинко (x0-4)", "боулпобеда": "Победа в дуэли (x1.85)", "боулпоражение": "Поражение в дуэли (x1.85)"}
    }
}
@dp.message(Command("games"), StateFilter('*'))
@dp.message(F.text == "🎲 Сделать ставку", StateFilter('*'))
async def start_betting(message: types.Message, state: FSMContext):
    await message.answer_dice(emoji="🎲") # Отправляем анимированный кубик
    await asyncio.sleep(1.5) # Ждем 1.5 секунды
    game_items = list(GAMES_DATA.items())
    buttons = []
    for i in range(0, len(game_items), 3):  # Изменено на 3
        row = []
        for j in range(3):  
            if i + j < len(game_items):
                row.append(InlineKeyboardButton(text=game_items[i+j][1]["name"], callback_data=f"game_{game_items[i+j][0]}"))
        buttons.append(row)

 
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        text=f"🎲 Выберите игру:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(BettingStates.SELECT_GAME)

@dp.callback_query(F.data == "cancel_bet")
async def cancel_betting(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.delete()
    await callback_query.answer("Действие отменено.")

@dp.callback_query(F.data.startswith("cancel_bet_payment"))
async def cancel_bet_payment(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.delete()
    await callback_query.answer("Создание счета отменено.")

@dp.callback_query(F.data.startswith("game_"), StateFilter(BettingStates.SELECT_GAME, BettingStates.ENTER_AMOUNT))
async def select_game(callback_query: types.CallbackQuery, state: FSMContext):
    game_key = callback_query.data.split("_", 1)[1]
    if game_key not in GAMES_DATA:
        await callback_query.answer("Неверная игра!", show_alert=True)
        return

    await state.update_data(game_key=game_key)
    
    game_types = GAMES_DATA[game_key]["types"]
    
    game_types_items = list(game_types.items())
    buttons = []
    for i in range(0, len(game_types_items), 3):
        row = []
        for j in range(3): # Изменено на 3
            if i + j < len(game_types_items):
                key, name = game_types_items[i+j]
                row.append(InlineKeyboardButton(text=name, callback_data=f"type_{key}"))
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="⬅️ Назад к играм", callback_data="back_to_games")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback_query.message.edit_text(f"<b>Игра: {GAMES_DATA[game_key]['name']}</b>\n\nВыберите исход:", reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(BettingStates.SELECT_BET_TYPE)
    await callback_query.answer()

@dp.callback_query(F.data == "back_to_games", BettingStates.SELECT_BET_TYPE)
async def back_to_games(callback_query: types.CallbackQuery, state: FSMContext):
    await state.set_state(BettingStates.SELECT_GAME)
    game_items = list(GAMES_DATA.items())
    buttons = []
    for i in range(0, len(game_items), 3):
        row = []
        for j in range(3):
            if i + j < len(game_items):
                row.append(InlineKeyboardButton(text=game_items[i+j][1]["name"], callback_data=f"game_{game_items[i+j][0]}"))
        buttons.append(row)

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback_query.message.edit_text("<b>🎲 Выберите игру:</b>", reply_markup=keyboard, parse_mode="HTML")
    await callback_query.answer()


@dp.callback_query(F.data.startswith("type_"), BettingStates.SELECT_BET_TYPE)
async def select_bet_type(callback_query: types.CallbackQuery, state: FSMContext):
    bet_type_key = callback_query.data.split("_", 1)[1]
    
    data = await state.get_data()
    game_key = data.get("game_key")

    if not game_key or bet_type_key not in GAMES_DATA[game_key]["types"]:
        await callback_query.answer("Неверный тип ставки!", show_alert=True)
        return

    await state.update_data(bet_type_key=bet_type_key)
    
    game_name = GAMES_DATA[game_key]['name']
    bet_type_name = GAMES_DATA[game_key]['types'][bet_type_key]

    await callback_query.message.edit_text(f"<b>Игра: {game_name}</b>\n<b>Исход: {bet_type_name}</b>\n\n"
                                          "Введите сумму ставки в долларах ($)\n"
                                          "<i>Минимальная сумма: 0.1$</i>", 
                                          parse_mode="HTML",
                                          reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                              [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"game_{game_key}")]
                                          ]))
    await state.set_state(BettingStates.ENTER_AMOUNT)
    await callback_query.answer()


@dp.message(BettingStates.ENTER_AMOUNT)
async def enter_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount < 0.1:
            await message.answer("Минимальная сумма ставки: 0.1$")
            return
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")
        return

    data = await state.get_data()
    game_key = data.get("game_key")
    bet_type_key = data.get("bet_type_key")
    user_id = message.from_user.id
    
    payload = f"bet_{uuid.uuid4().hex}"

    await db.add_invoice_bet(payload, user_id, game_key, bet_type_key, amount)

    invoice = await crypto_pay.create_invoice(
        asset="USDT",
        amount=str(amount),
        description=f"Ставка в {GAMES_DATA[game_key]['name']} (Payload: {payload})",
        payload=payload,
        expires_in=3600 # 1 час
    )

    if invoice and invoice.get("ok"):
        invoice_result = invoice.get("result")
        pay_url = invoice_result.get("pay_url")
        
        await message.answer(
            f"✅ <b>Ваш счет на оплату ставки создан!</b>\n\n"
            f"<b>Сумма:</b> <code>{amount:.2f} USDT</code>\n\n"
            "Нажмите кнопку ниже, чтобы перейти к оплате. Счет действителен 1 час.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Перейти к оплате", url=pay_url)],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_bet_payment")]
            ]),
            parse_mode="HTML"
        )
        await state.clear()
    else:
        await message.answer("❌ Не удалось создать счет для оплаты. Попробуйте позже или обратитесь в поддержку.")
        logging.error(f"Invoice creation failed for user {user_id}: {invoice}")
        await state.clear()

@dp.callback_query(lambda c: c.data == "info_user")
async def show_info(callback_query: types.CallbackQuery):
    await callback_query.answer(f"Инфо {CASINO_NAME}")

    info_text = (
        f"<b>Информация</b> <code>{CASINO_NAME}</code>"
    )
    
    await callback_query.message.edit_caption(
        caption=info_text,
        reply_markup=create_info_keyboard(),
        parse_mode="HTML"
    )

async def is_admin(user_id: int) -> bool:
    return str(user_id) == os.getenv("ADMIN_USER_ID")

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💰 CryptoBot", callback_data="admin_cryptobot")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="broadcast")]
    ])
    
    await message.answer("👑 <b>Админ-панель</b>", reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "admin_users")
async def show_users(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нет доступа", show_alert=True)
        return
        
    users = await db.get_all_users(limit=10)
    
    text = "<b>Управление пользователями</b>\n\n"
    for user in users:
        text += (
            f"<code>{user['user_id']}</code> | {user['username']}\n"
            f"Реф.баланс: <code>{user['ref_balance']:.2f}$</code>\n"
            f"Заработано: <code>{user['ref_earnings']:.2f}$</code>\n"
            f"Рефералов: <code>{user['ref_count']}</code>\n"
            f"Пригласил: <code>{user.get('referrer_username', 'нет')}</code>\n"
            f"Дата: <code>{user['created_at']}</code>\n\n"
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Поиск", callback_data="search_users")],
        [InlineKeyboardButton(text="Следующая", callback_data="users_next_10")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_admin")]
    ])

    await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "admin_stats")
async def show_admin_stats(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нет доступа", show_alert=True)
        return

    stats = await db.get_admin_stats()
    
    text = "<b>Статистика</b>\n\n"
    text += f"<blockquote><b>Пользователи:</b>\n"
    text += f"• Всего: <code>{stats['total_users']}</code>\n"
    text += f"• Сегодня: <code>{stats['today_users']}</code>\n"
    text += f"• За неделю: <code>{stats['week_users']}</code></blockquote>\n\n"
    
    text += f"<blockquote><b>Игры сегодня:</b>\n"
    text += f"• Всего: <code>{stats['today_games']}</code>\n"
    text += f"• Выиграно: <code>{stats['today_wins']}</code>\n"
    text += f"• Проиграно: <code>{stats['today_losses']}</code>\n"
    text += f"• Оборот: <code>{stats['today_turnover']:.2f}$</code>\n"
    text += f"• Прибыль: <code>{(stats['today_earned'] - stats['today_spent']):.2f}$</code></blockquote>\n\n"
    
    text += f"<blockquote><b>Игры за неделю:</b>\n"
    text += f"• Всего: <code>{stats['week_games']}</code>\n"
    text += f"• Выиграно: <code>{stats['week_wins']}</code>\n"
    text += f"• Проиграно: <code>{stats['week_losses']}</code>\n"
    text += f"• Оборот: <code>{stats['week_turnover']:.2f}$</code>\n"
    text += f"• Прибыль: <code>{(stats['week_earned'] - stats['week_spent']):.2f}$</code></blockquote>"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Обновить", callback_data="admin_stats")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_admin")]
    ])

    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except:
        pass

    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "back_to_admin")
async def back_to_admin_panel(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нет доступа", show_alert=True)
        return
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💰 CryptoBot", callback_data="admin_cryptobot")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="broadcast")]
    ])
    
    await callback_query.message.edit_text("👑 <b>Админ-панель</b>", reply_markup=keyboard, parse_mode="HTML")
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "search_users")
async def search_users_cmd(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        return
    
    await state.set_state(AdminStates.SEARCH_USERS)
    await callback_query.message.answer("Введите ID или username пользователя:")
    await callback_query.answer()

@dp.message(AdminStates.SEARCH_USERS)
async def process_user_search(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return

    users = await db.search_users(message.text)
    if not users:
        await message.answer("Пользователи не найдены")
        await state.clear()
        return

    text = "<b>Результаты поиска:</b>\n\n"
    for user in users:
        text += (
            f"<code>{user['user_id']}</code> | {user['username']}\n"
            f"Реф.баланс: <code>{user['ref_balance']:.2f}$</code>\n"
            f"Заработано: <code>{user['ref_earnings']:.2f}$</code>\n"
            f"Рефералов: <code>{user['ref_count']}</code>\n"
            f"Пригласил: <code>{user.get('referrer_username', 'нет')}</code>\n"
            f"Дата: <code>{user['created_at']}</code>\n\n"
        )
        keyboard = create_user_management_keyboard(user['user_id'])
        await message.answer(text, reply_markup=keyboard)

    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("edit_"))
async def handle_edit_user(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        return

    action, field, user_id = callback_query.data.split("_")
    await state.update_data(field=field, user_id=user_id)
    await state.set_state(AdminStates.EDIT_USER)
    
    field_names = {
        "balance": "баланс",
        "ref_balance": "реферальный баланс",
        "ref_earnings": "заработок с рефералов",
        "ref_count": "количество рефералов",
        "referrer": "ID пригласившего"
    }
    
    await callback_query.message.answer(
        f"✏️ Введите новое значение для поля '{field_names.get(field, field)}'"
    )
    await callback_query.answer()

@dp.message(AdminStates.EDIT_USER)
async def process_edit_user(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return

    data = await state.get_data()
    field = data['field']
    user_id = int(data['user_id'])
    
    try:
        value = float(message.text) if field != "referrer" else int(message.text)
        updates = {field: value}
        
        if await db.update_user(user_id, updates):
            await message.answer(f"✅ Значение успешно обновлено")
            

            user = await db.get_user(user_id)
            text = (
                f"👤 Пользователь <code>{user['user_id']}</code>\n"
                f"💰 Баланс: <code>{user['balance']:.2f}$</code>\n"
                f"🔄 Реф.баланс: <code>{user['ref_balance']:.2f}$</code>\n"
                f"💎 Заработано: <code>{user['ref_earnings']:.2f}$</code>\n"
                f"👥 Рефералов: <code>{user['ref_count']}</code>\n"
                f"🔗 Пригласил: <code>{user.get('referrer_id', 'нет')}</code>"
            )
            keyboard = create_user_management_keyboard(user_id)
            await message.answer(text, reply_markup=keyboard)
        else:
            await message.answer("❌ Ошибка при обновлении")
    except ValueError:
        await message.answer("❌ Неверный формат значения")
    
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("delete_user_"))
async def confirm_delete_user(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        return

    user_id = int(callback_query.data.split("_")[2])
    await state.update_data(user_id=user_id)
    await state.set_state(AdminStates.CONFIRM_DELETE)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_delete_{user_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data="cancel_delete")
        ]
    ])
    
    await callback_query.message.answer(
        f"⚠️ Вы уверены, что хотите удалить пользователя <code>{user_id}</code>?",
        reply_markup=keyboard
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith("confirm_delete_"))
async def process_delete_user(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        return

    user_id = int(callback_query.data.split("_")[2])
    if await db.delete_user(user_id):
        await callback_query.message.answer(f"✅ Пользователь {user_id} удален")
    else:
        await callback_query.message.answer("❌ Ошибка при удалении пользователя")
    
    await state.clear()
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "cancel_delete")
async def cancel_delete_user(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.answer("❌ Удаление отменено")
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith("users_next_"))
async def show_more_users(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        return

    offset = int(callback_query.data.split("_")[2])
    users = await db.get_all_users(limit=10, offset=offset)
    
    if not users:
        await callback_query.answer("Больше пользователей нет")
        return

    text = "<b>👥 Управление пользователями</b>\n\n"
    for user in users:
        text += (
            f"<code>{user['user_id']}</code> | {user['username']}\n"
            f"🔄 Реф.баланс: <code>{user['ref_balance']:.2f}$</code>\n"
            f"💎 Заработано: <code>{user['ref_earnings']:.2f}$</code>\n"
            f"👥 Рефералов: <code>{user['ref_count']}</code>\n"
            f"🔗 Пригласил: <code>{user.get('referrer_username', 'нет')}</code>\n"
            f"📅 Дата: <code>{user['created_at']}</code>\n\n"
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Поиск", callback_data="search_users")],
        [
            InlineKeyboardButton(text="◀️ Предыдущая", callback_data=f"users_next_{max(0, offset-10)}"),
            InlineKeyboardButton(text="▶️ Следующая", callback_data=f"users_next_{offset+10}")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
    ])

    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard)
    except:
        pass

    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "broadcast")
async def start_broadcast(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нет доступа", show_alert=True)
        return
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")],
    ])
    
    await callback_query.message.edit_text(
        "📨 Отправьте сообщение для рассылки.\n\n"
        "Поддерживаются все типы сообщений (текст, фото, видео и т.д.).\n"
        "После отправки сообщения, вы сможете добавить кнопки к нему.",
        reply_markup=keyboard
    )
    await state.set_state(AdminStates.BROADCAST)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "cancel_broadcast")
async def cancel_broadcast(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нет доступа", show_alert=True)
        return
        
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💰 CryptoBot", callback_data="admin_cryptobot")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="broadcast")]
    ])
    await callback_query.message.edit_text("👑 <b>Админ-панель</b>", reply_markup=keyboard, parse_mode="HTML")
    await callback_query.answer()

@dp.message(AdminStates.BROADCAST)
async def handle_broadcast_message(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
        

    await state.update_data(
        message_type=message.content_type,
        text=message.text if message.content_type == "text" else message.caption,
        file_id=getattr(message, message.content_type, {}).file_id if message.content_type != "text" else None,
        parse_mode="HTML" if message.content_type == "text" else None
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить кнопку", callback_data="add_button")],
        [
            InlineKeyboardButton(text="✅ Начать рассылку", callback_data="start_sending"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")
        ]
    ])
    
    preview_text = "📨 Предпросмотр сообщения:\n\n"
    if message.content_type == "text":
        preview_text += message.text
    else:
        preview_text += message.caption if message.caption else "Медиа-сообщение"
        
    await message.answer(preview_text, reply_markup=keyboard)
    await state.set_state(AdminStates.BROADCAST_BUTTONS)

@dp.callback_query(lambda c: c.data == "add_button")
async def add_broadcast_button(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нет доступа", show_alert=True)
        return
        
    data = await state.get_data()
    buttons = data.get('buttons', [])
    
    if len(buttons) >= 10:  
        await callback_query.answer("Достигнут лимит кнопок (10)", show_alert=True)
        return
        
    await callback_query.message.edit_text(
        "🔗 Отправьте кнопку в формате:\n"
        "<code>Текст кнопки | https://example.com</code>\n\n"
        "Пример:\n"
        "<code>Наш канал | https://t.me/channel</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_button")]
        ])
    )
    await state.set_state(AdminStates.BROADCAST_BUTTONS)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "cancel_add_button")
async def cancel_add_button(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нет доступа", show_alert=True)
        return
        
    data = await state.get_data()
    buttons = data.get('buttons', [])
    
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить кнопку", callback_data="add_button")],
        [
            InlineKeyboardButton(text="✅ Начать рассылку", callback_data="start_sending"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")
        ]
    ])
    
    preview_text = "📨 Предпросмотр сообщения:\n\n"
    if data['message_type'] == "text":
        preview_text += data['text']
    else:
        preview_text += data['text'] if data['text'] else "Медиа-сообщение"
        
    if buttons:
        preview_text += "\n\n🔗 Добавленные кнопки:"
        for btn in buttons:
            preview_text += f"\n• {btn['text']} -> {btn['url']}"
            
    await callback_query.message.edit_text(preview_text, reply_markup=keyboard)
    await callback_query.answer()

@dp.message(AdminStates.BROADCAST_BUTTONS)
async def handle_button_input(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
        
    if "|" not in message.text:
        await message.reply(
            "❌ Неверный формат. Используйте:\n"
            "<code>Текст кнопки | https://example.com</code>",
            parse_mode="HTML"
        )
        return
        
    text, url = [x.strip() for x in message.text.split("|", 1)]
    
    if not url.startswith(("http://", "https://", "t.me/", "tg://")):
        await message.reply("❌ Неверный формат ссылки. Ссылка должна начинаться с http://, https://, t.me/ или tg://")
        return
        
    data = await state.get_data()
    buttons = data.get('buttons', [])
    buttons.append({"text": text, "url": url})
    await state.update_data(buttons=buttons)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить кнопку", callback_data="add_button")],
        [
            InlineKeyboardButton(text="✅ Начать рассылку", callback_data="start_sending"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")
        ]
    ])
    
    preview_text = "📨 Предпросмотр сообщения:\n\n"
    if data['message_type'] == "text":
        preview_text += data['text']
    else:
        preview_text += data['text'] if data['text'] else "Медиа-сообщение"
        
    preview_text += "\n\n🔗 Добавленные кнопки:"
    for btn in buttons:
        preview_text += f"\n• {btn['text']} -> {btn['url']}"
        
    await message.answer(preview_text, reply_markup=keyboard, disable_web_page_preview=True)

@dp.callback_query(lambda c: c.data == "start_sending")
async def process_broadcast(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    buttons = data.get('buttons', [])
    

    inline_buttons = []
    for i in range(0, len(buttons), 2): 
        row = [InlineKeyboardButton(text=btn['text'], url=btn['url']) for btn in buttons[i:i+2]]
        inline_buttons.append(row)
    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons) if buttons else None


    users = await db.get_all_users(limit=10000)  # Increased limit for large broadcasts
    total_users = len(users)
    

    successful = 0
    failed = 0
    blocked = 0
    deleted = 0
    

    status_message = await callback_query.message.edit_text(
        "📨 Рассылка начата...\n\n"
        f"⏳ Всего пользователей: {total_users}\n"
        "✅ Отправлено: 0\n"
        "❌ Ошибок: 0\n"
        "🚫 Заблокировали: 0\n"
        "🗑 Удалили: 0\n"
        "⏱ Прошло времени: 0 сек\n"
        "📊 Прогресс: 0%"
    )
    
    start_time = time.time()
    last_update = start_time
    
    for i, user in enumerate(users, 1):
        try:
            if data['message_type'] == "text":
                await bot.send_message(
                    user['user_id'],
                    data['text'],
                    parse_mode=data['parse_mode'],
                    reply_markup=keyboard
                )
            else:
                method = getattr(bot, f"send_{data['message_type']}")
                await method(
                    user['user_id'],
                    data['file_id'],
                    caption=data['text'],
                    reply_markup=keyboard
                )
            successful += 1
            
        except aiogram.exceptions.TelegramForbiddenError:
            blocked += 1
        except aiogram.exceptions.TelegramBadRequest as e:
            if "chat not found" in str(e).lower():
                deleted += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logging.error(f"Broadcast error for user {user['user_id']}: {e}")
            

        current_time = time.time()
        if current_time - last_update >= 3 or i == total_users:
            elapsed = int(current_time - start_time)
            progress = (i / total_users) * 100
            
            try:
                await status_message.edit_text(
                    "📨 Рассылка в процессе...\n\n"
                    f"⏳ Всего пользователей: {total_users}\n"
                    f"✅ Отправлено: {successful}\n"
                    f"❌ Ошибок: {failed}\n"
                    f"🚫 Заблокировали: {blocked}\n"
                    f"🗑 Удалили: {deleted}\n"
                    f"⏱ Прошло времени: {elapsed} сек\n"
                    f"📊 Прогресс: {progress:.1f}%"
                )
                last_update = current_time
            except:
                pass
                
        await asyncio.sleep(0.05)

    elapsed = int(time.time() - start_time)
    speed = total_users / elapsed if elapsed > 0 else 0
    
    await status_message.edit_text(
        "✅ Рассылка завершена\n\n"
        f"📊 Статистика:\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"✅ Успешно отправлено: {successful}\n"
        f"❌ Ошибок: {failed}\n"
        f"🚫 Заблокировали бота: {blocked}\n"
        f"🗑 Удалённые аккаунты: {deleted}\n"
        f"⏱ Время выполнения: {elapsed} сек\n"
        f"⚡️ Скорость: {speed:.1f} сообщений/сек\n\n"
        f"📈 Процент успеха: {(successful/total_users*100):.1f}%",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="back_to_admin")]
        ])
    )
    
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_cryptobot")
async def show_cryptobot_balance(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нет доступа", show_alert=True)
        return
    try:
        balance_data = await crypto_pay.get_balance()
        balances = balance_data.get('result', [])
        balance_text = "<b>Баланс CryptoBot</b>\n\n"
        if balances:
            for balance in balances:
                currency = balance.get('currency', '')
                available = float(balance.get('available', 0))
                balance_text += f"<b>{currency}:</b> <code>{available:.2f}</code>\n"
        else:
            balance_text += "❌ Нет доступных балансов"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить", callback_data="add_cryptobot_balance")],
            [InlineKeyboardButton(text="🧾 Активные чеки", callback_data="admin_checks")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_cryptobot_balance")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
        ])
        try:
            await callback_query.message.edit_text(
                balance_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except aiogram.exceptions.TelegramBadRequest as e:
            if "message is not modified" in str(e):
                await callback_query.answer("Баланс актуален")
            else:
                raise
    except Exception as e:
        logging.error(f"Error getting CryptoBot balance: {e}")
        error_text = (
            "❌ <b>Ошибка при получении баланса</b>\n\n"
            f"Причина: {str(e)}"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Повторить", callback_data="refresh_cryptobot_balance")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
        ])
        await callback_query.message.edit_text(
            error_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "admin_checks")
async def admin_show_checks(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нет доступа", show_alert=True)
        return
    try:
        checks_data = await crypto_pay.get_checks(status="active", asset="USDT")
        
        await bot.send_message(callback_query.from_user.id, f"Ответ get_checks: {checks_data}")
        checks = checks_data.get('result', [])
        
        if isinstance(checks, dict) and 'checks' in checks:
            checks = checks['checks']
        if not isinstance(checks, list):
            checks = []
        if not checks:
            await callback_query.message.edit_text(
                "<b>Нет активных чеков</b>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_cryptobot")]
                ]),
                parse_mode="HTML"
            )
            await callback_query.answer()
            return
        text = "<b>Активные чеки USDT</b>\n\n"
        keyboard = []
        for check in checks[:10]:
            amount = check.get('amount')
            hash_ = check.get('hash')
            status = check.get('status')
            created = check.get('created_at', '')
            text += f"<b>Сумма:</b> <code>{amount}</code> | <b>hash:</b> <code>{hash_}</code> | <b>Статус:</b> <code>{status}</code>\n"
            keyboard.append([InlineKeyboardButton(text=f"❌ Удалить {amount}$", callback_data=f"admin_delete_check_{hash_}")])
        keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_refresh_checks")])
        keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_cryptobot")])
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="HTML"
        )
    except Exception as e:
        await callback_query.message.edit_text(
            f"❌ <b>Ошибка при получении чеков:</b> {e}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_cryptobot")]
            ]),
            parse_mode="HTML"
        )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_delete_check_"))
async def admin_delete_check(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нет доступа", show_alert=True)
        return
    hash_ = callback_query.data.replace("admin_delete_check_", "")
    try:
        result = await crypto_pay.delete_check(hash_)
        if result.get('ok'):
            await callback_query.answer("Чек удалён", show_alert=True)
        else:
            await callback_query.answer(f"Ошибка: {result.get('error', 'Не удалось удалить чек')}", show_alert=True)
    except Exception as e:
        await callback_query.answer(f"Ошибка: {e}", show_alert=True)
    await admin_show_checks(callback_query)

@dp.callback_query(lambda c: c.data == "admin_refresh_checks")
async def admin_refresh_checks(callback_query: types.CallbackQuery):
    await admin_show_checks(callback_query)

@dp.callback_query(lambda c: c.data == "add_cryptobot_balance")
async def add_cryptobot_balance(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminStates.ADD_BALANCE)
    await callback_query.message.edit_text(
        "<b>💳 Пополнение баланса CryptoBot</b>\n\n"
        "Введите сумму пополнения в USDT:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_balance")]
        ])
    )
    await callback_query.answer()

@dp.message(AdminStates.ADD_BALANCE)
async def process_add_balance(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    
    try:
        amount = float(message.text)
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0")
            return
            

        invoice_data = await crypto_pay.create_invoice(
            asset="USDT",
            amount=str(amount),
            description=f"Пополнение баланса CryptoBot на {amount} USDT",
            hidden_message="Спасибо за пополнение!"
        )
        
        if not invoice_data.get('result', {}).get('pay_url'):
            raise Exception("Не удалось создать счет для оплаты")
            
        pay_url = invoice_data['result']['pay_url']
        

        await message.answer(
            "✅ <b>Счет на пополнение создан</b>\n\n"
            f"<b>Сумма:</b> <code>{amount}$</code>\n"
            f"<b>Валюта:</b> <code>USDT</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=pay_url)],
                [InlineKeyboardButton(text="🔙 Вернуться в админ-панель", callback_data="back_to_admin")]
            ])
        )
        

        await bot.send_message(
            chat_id=LOGS_ID,
            text=f"💳 <b>Создан счет на пополнение CryptoBot</b>\n\n"
                 f"<b>Администратор:</b> {message.from_user.mention_html()}\n"
                 f"<b>Сумма:</b> <code>{amount}$</code>\n"
                 f"<b>Валюта:</b> <code>USDT</code>",
            parse_mode="HTML"
        )
        
    except ValueError:
        await message.answer(
            "❌ <b>Ошибка:</b> введите корректную сумму\n"
            "<i>Пример: 100.50</i>",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Error creating invoice: {e}")
        await message.answer(
            "❌ <b>Ошибка при создании счета</b>\n\n"
            f"Причина: {str(e)}",
            parse_mode="HTML"
        )
    finally:
        await state.clear()

@dp.callback_query(lambda c: c.data == "cancel_add_balance")
async def cancel_add_balance(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text(
        "<b>Пополнение отменено</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Вернуться в админ-панель", callback_data="back_to_admin")]
        ])
    )
    await callback_query.answer()


@dp.callback_query(lambda c: c.data == "refresh_cryptobot_balance")
async def refresh_cryptobot_balance(callback_query: types.CallbackQuery):
    await show_cryptobot_balance(callback_query)



async def create_payment_check(amount: float, description: str = None) -> dict:
    try:
        if not description:
            description = f"Выигрыш {amount}$ в {CASINO_NAME}"
        
        balance_data = await crypto_pay.get_balance()
        balances = balance_data.get('result', [])
        usdt_balance = 0
        
        for balance in balances:
            currency = balance.get('currency_code', '')
            available = balance.get('available', '0')
            
            if currency and currency.upper() == 'USDT':
                usdt_balance = float(available)
                break
        
        if usdt_balance < amount:
            await bot.send_message(
                chat_id=LOGS_ID,
                text=f"⚠️ <b>Недостаточно средств для создания чека</b>\n"
                     f"<b>Требуется:</b> <code>{amount}$</code>\n"
                     f"<b>Доступно:</b> <code>{usdt_balance}$</code>",
                parse_mode="HTML"
            )
            return None
        
        result = await crypto_pay.create_check(
            asset="USDT",
            amount=str(amount),
            description=description,
            hidden_message=f"Поздравляем с выигрышем в {CASINO_NAME}!"
        )
        
        if result.get('ok') == True and 'result' in result:
            # Перемещаем это сообщение сюда, чтобы оно отправлялось только при успешном создании чека
            await bot.send_message(
                chat_id=LOGS_ID,
                text=f"💸 <b>СОЗДАН ЧЕК НА ВЫПЛАТУ</b>\n\n"
                     f"<b>Сумма:</b> <code>{amount}$</code>\n"
                     f"<b>Новый баланс казны:</b> <code>{usdt_balance - amount}$</code>",
                parse_mode="HTML"
            )

            check_data = result['result']
            return {
                'check_id': check_data.get('check_id'),
                'check_link': check_data.get('bot_check_url'),
                'amount': check_data.get('amount')
            }
        # Добавляем логирование ошибки, если чек не создан
        if result.get('ok') == False and 'error' in result:
            logging.error(f"CryptoPay check creation failed: {result['error']}")
        return None
    except Exception as e:
        logging.error(f"Error creating check: {e}")
        return None


async def process_game_result(message: types.Message, game_result: GameResult, state: FSMContext):
    user_id = message.from_user.id
    state_data = await state.get_data()
    bet_amount = state_data.get('bet_amount', 0)
    game_type = state_data.get('game_type', 'unknown')
    bet_type = state_data.get('bet_type', 'unknown')
    
    await state.clear()
    
    if game_type == 'rock_paper_scissors':
        if game_result.won:
            win_amount = float(game_result.amount)
            check_result = await create_payment_check(win_amount)
            
            # Отправляем только сообщение в логи
            current_balance = await db.get_current_balance()
            await bot.send_message(
                chat_id=LOGS_ID,
                text=f"💰 <b>ВЫПЛАТА ЧЕКОМ </b>\n\n"
                     f"<b>Игрок:</b> {message.from_user.mention_html()}\n"
                     f"<b>ID:</b> <code>{user_id}</code>\n"
                     f"<b>Сумма выигрыша:</b> <code>{win_amount}$</code>\n"
                     f"<b>Текущий баланс казны:</b> <code>{current_balance - float(win_amount)}$</code>",
                parse_mode="HTML"
            )
        return
    
    if game_result.won:
        win_amount = float(game_result.amount)
        check_result = await create_payment_check(win_amount)
        
        # Отправляем только сообщение в логи
        current_balance = await db.get_current_balance()
        await bot.send_message(
            chat_id=LOGS_ID,
            text=f"💰 <b>ВЫПЛАТА ЧЕКОМ</b>\n\n"
                 f"<b>Игрок:</b> {message.from_user.mention_html()}\n"
                 f"<b>ID:</b> <code>{user_id}</code>\n"
                 f"<b>Сумма выигрыша:</b> <code>{win_amount}$</code>\n"
                 f"<b>Текущий баланс казны:</b> <code>{current_balance - float(win_amount)}$</code>",
            parse_mode="HTML"
        )
    
    # Обрабатываем реферальное вознаграждение независимо от исхода
    user = await db.get_user(user_id)
    referrer_id = user.get('referrer_id')
    
    if referrer_id:
        if game_result.won:
            ref_penalty = float(game_result.amount) * 0.15
            await db.update_ref_balance(referrer_id, -ref_penalty)
            await bot.send_message(
                chat_id=referrer_id,
                text=f"💸 С вашего Реф.Баланса списано <code>{ref_penalty:.2f}$</code> из-за выигрыша <code>{game_result.amount:.2f}$</code>",
                parse_mode="HTML"
            )
        else:
            ref_reward = float(bet_amount) * 0.15
            await db.update_ref_balance(referrer_id, ref_reward)
            await bot.send_message(
                chat_id=referrer_id,
                text=f"💵 Ваш Реф.Баланс пополнен на <code>{ref_reward:.2f}$</code> из-за проигрыша <code>{game_result.amount:.2f}$</code>",
                parse_mode="HTML"
            )

@dp.message(GameStates.DICE_BET)
async def handle_dice_game(message: types.Message, state: FSMContext):
    dice = await message.answer_dice(emoji="🎲")
    dice_value = dice.dice.value
    
    state_data = await state.get_data()
    bet_amount = float(state_data.get('bet_amount', 0))
    bet_type = state_data.get('bet_type', '')
    
    game = CubeGame(bet_amount)
    result = await game.process(bet_type, dice_value)
    
    await process_game_result(message, result, state)

@dp.channel_post()
async def check_messages(message: types.Message):
    """Обрабатывает сообщения в канале для обработки платежей и пополнений CryptoBot"""
    if message.chat.id != LOGS_ID:
        logging.info(f"Message from wrong chat: {message.chat.id} != {LOGS_ID}")
        return

    try:
        logging.info(f"Processing message from {message.chat.id}: {message.text or message.caption}")
       
        
        # Сначала проверяем на оплату инвойса по payload
        text = message.text or message.caption or ""
        payload_match = re.search(r'payload: (bet_[a-f0-9]+)', text, re.IGNORECASE)
        
        if payload_match:
            payload = payload_match.group(1)
            logging.info(f"Found invoice payload: {payload}")
            bet_data = await db.get_invoice_bet(payload)
            
            if bet_data:
                logging.info(f"Processing invoice payment with payload: {payload}")
                
                user_info = None
                try:
                    user_info = await bot.get_chat(bet_data['user_id'])
                    user_name = user_info.full_name if user_info else f"User {bet_data['user_id']}"
                except Exception:
                    user_name = f"User {bet_data['user_id']}"

                data_for_process_bet = {
                    'id': bet_data['user_id'],
                    'name': user_name,
                    'usd_amount': bet_data['amount'],
                    'comment': bet_data['bet_type_key'],
                    'game': bet_data['game_key']
                }
                
                await process_bet(data_for_process_bet)
                await db.mark_invoice_bet_paid(payload)
                logging.info(f"Invoice bet {bet_data['invoice_id']} processed and marked as paid.")
            elif bet_data and bet_data['status'] == 'paid':
                logging.info(f"Invoice {bet_data['invoice_id']} with payload {payload} already processed.")
            else:
               
                pass 

        # Затем проверяем на обычный перевод
        if "отправил(а)" in text and "💬" in text:
            payment_data = parse_message(message)
            if payment_data:
                logging.info(f"Successfully parsed transfer message: {payment_data}")
                await process_bet(payment_data)
            else:
                logging.warning(f"Failed to parse transfer message: {text}")
            return

        # Логика для пополнения баланса бота
        if "пополнен на" in text and "USDT" in text:
            logging.info(f"Bot balance replenishment detected: {text}")
            admin_id = os.getenv("ADMIN_USER_ID")
            if admin_id:
                await bot.send_message(
                    chat_id=admin_id,
                    text="💰 <b>Баланс CryptoBot успешно пополнен.</b>",
                    parse_mode="HTML"
                )
            return

    except Exception as e:
        logging.error(f"Error processing channel message: {e}", exc_info=True)

def parse_message(message: types.Message) -> Optional[Dict]:
    """Парсит сообщение от CryptoBot о платеже"""
    try:
        comment, game, name, user_id, amount, asset = None, None, None, None, None, None
        logging.info(f"Parsing message: {message.text}")
        logging.info(f"Message entities: {message.entities}")

        if message.entities:
            if message.entities[0].user:
                user = message.entities[0].user
                name = user.full_name
                msg_text = message.text[len(name):].replace("🪙", "").split("💬")[0]
                name = re.sub(r'@[\w]+', '***', name) if '@' in name else name
                user_id = int(user.id)
                asset = msg_text.split("отправил(а)")[1].split()[1]
                amount = float(msg_text.split("($")[1].split(').')[0].replace(',', ""))
                
                logging.info(f"Parsed user: {name} ({user_id})")
                logging.info(f"Parsed amount: {amount} {asset}")

                if '💬' in message.text:
                    comment = message.text.split("💬 ")[1].lower()
                    logging.info(f"Parsed comment: {comment}")
                else:
                    logging.warning("No comment found in message")
                    comment = None
                    game = None

        if comment is not None:
            # Удаляем эту логику, так как game будет определяться в process_bet
            # game = comment.replace("ё", "е")
            # game = game.replace("ное", "")
            # game = game.replace(" ", "")
            # logging.info(f"Processed game comment: {game}")

            result = {
                'id': user_id,
                'name': name,
                'usd_amount': amount,
                'asset': asset,
                'comment': comment,
                # 'game': game # Удалена некорректная установка game
            }
            logging.info(f"Parsed payment message result: {result}")
            return result
    except Exception as e:
        logging.error(f"Error parsing payment message: {e}")
        return None

def parse_game_type_and_bet(comment: str):
    comment = comment.lower().replace(" ", "").replace("ё", "е")
    basketball_words = ["мимо", "гол"]
    if comment in basketball_words:
        return "basketball", comment
    darts_words = ["белое", "красное", "яблочко", "промах"]
    if comment in darts_words:
        return "darts", comment
    slots_words = ["казик", "слоты", "777", "джекпот"]
    if comment in slots_words:
        return "slots", comment
    bowling_words = ["боул", "боулинг", "боулпобеда", "боулпоражение", "страйк", "боулпромах"]
    if comment in bowling_words:
        return "bowling", comment
    cube_words = ["чет", "нечет", "больше", "меньше", "плинко", "пл", "сектор1", "сектор 1", "сектор2", "сектор 2", "сектор3", "сектор 3", "с1", "с2", "с3", "1", "2", "3", "4", "5", "6"]
    if comment in cube_words:
        return "cube", comment
    two_dice_words = ["ничья", "победа1", "победа2", "п1", "п2"]
    if comment in two_dice_words:
        return "two_dice", comment
    rps_words = ["камень", "ножницы", "бумага", "к", "н", "б"]
    if comment in rps_words:
        return "rock_paper_scissors", comment
    return None, None

async def process_bet(data: Dict):
    if data.get('id') == LOGS_ID:
        return
    try:
        user_id = data['id']
        if not data.get('comment'):
            error_text = (
                f"<code>{data['name']}</code> <b>Произошла ошибка!</b> \n\n"
                f"<blockquote><b>Возможные причины</b> \n"
                f"• <b>Не указан комментарий</b>\n"
                f"• <b>Некорректный комментарий</b>\n"
                f"• <b>Обратитесь в поддержку за выплатой</b></blockquote>"
            )
            await bot.send_message(
                chat_id=BETS_ID,
                text=error_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Обратиться в поддержку", url=SUPPORT_LINK)],
                    [InlineKeyboardButton(text='💬 Инструкция', url=GIDE_LINK)]
                ])
            )
            return
            
        game_type = data.get('game')
        bet_type = data.get('comment')
        
        # Для обратной совместимости со старым парсером
        if not game_type:
            game_type, bet_type = parse_game_type_and_bet(data['comment'])

        if not game_type or not bet_type:
            error_text = (
                f"<code>{data['name']}</code> <b>Произошла ошибка!</b> \n\n"
                f"<blockquote><b>Возможные причины</b> \n"
                f"• <b>Не указан комментарий</b>\n"
                f"• <b>Некорректный комментарий</b>\n"
                f"• <b>Обратитесь в поддержку за выплатой</b></blockquote>"
            )
            await bot.send_message(
                chat_id=BETS_ID,
                text=error_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Обратиться в поддержку", url=SUPPORT_LINK)]
                ])
            )
            return
        await db.add_to_queue(
            user_id=data['id'],
            amount=float(data['usd_amount']),
            game=game_type,
            bet_type=bet_type
        )
        
        # Отправляем подтверждение игроку
        await bot.send_message(
            chat_id=data['id'],
            text=f"✅ <b>Ваша ставка принята!</b>\n\n"
                 f"<b>Игра:</b> {GAMES_DATA[game_type]['name']}\n"
                 f"<b>Исход:</b> {GAMES_DATA[game_type]['types'][bet_type]}\n"
                 f"<b>Сумма:</b> <code>{data['usd_amount']}$</code>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="👀 Смотреть игру", url=BETS_LINK)]
                ]),
            parse_mode="HTML"
        )

        bet_msg = await bot.send_message(
            chat_id=BETS_ID,
            text=f"🎰 /// <b>НОВАЯ СТАВКА</b>\n\n"
                 f"<blockquote><b>Никнейм игрока:</b> {data['name']}\n\n"
                 f"<b>Сумма ставки:</b> {data['usd_amount']}$\n\n"
                 f"<b>Исход ставки:</b> {data['comment']}</blockquote>",
            parse_mode="HTML"
        )
        game_classes = {
            'cube': CubeGame,
            'two_dice': TwoDiceGame,
            'rock_paper_scissors': RockPaperScissorsGame,
            'basketball': BasketballGame,
            'darts': DartsGame,
            'slots': SlotsGame,
            'bowling': BowlingGame
        }
        game = game_classes[game_type](Decimal(str(data['usd_amount'])))
        dice_value = None
        second_dice_value = None
        if game_type == 'rock_paper_scissors':
            player_emoji = game.get_emoji(bet_type)
            await bot.send_message(
                chat_id=BETS_ID,
                text=player_emoji,
                reply_to_message_id=bet_msg.message_id
            )
            await asyncio.sleep(2)
            bot_choice_value = random.randint(1, 3)
            bot_choices = {1: "камень", 2: "ножницы", 3: "бумага"}
            bot_choice = bot_choices.get(bot_choice_value, "камень")
            bot_emoji = game.BET_EMOJIS[bot_choice]
            await bot.send_message(
                chat_id=BETS_ID,
                text=bot_emoji,
                reply_to_message_id=bet_msg.message_id
            )
            dice_value = bot_choice_value
        elif game_type in ['basketball', 'darts', 'slots', 'bowling']:
            emoji_map = {
                'basketball': '🏀',
                'darts': '🎯',
                'slots': '🎰',
                'bowling': '🎳'
            }
            dice_msg = await bot.send_dice(
                chat_id=BETS_ID,
                emoji=emoji_map[game_type],
                reply_to_message_id=bet_msg.message_id
            )
            dice_value = dice_msg.dice.value
            if game_type == 'bowling' and any(x in bet_type for x in ["боулпобеда", "боулпоражение", "боулингпобеда", "боулингпоражение", "победа", "поражение"]):
                await asyncio.sleep(2)
                second_dice_msg = await bot.send_dice(
                    chat_id=BETS_ID,
                    emoji='🎳',
                    reply_to_message_id=bet_msg.message_id
                )
                second_dice_value = second_dice_msg.dice.value
        else:
            dice_msg = await bot.send_dice(
                chat_id=BETS_ID,
                emoji=game.get_emoji(bet_type) if hasattr(game, 'get_emoji') else game.EMOJI,
                reply_to_message_id=bet_msg.message_id
            )
            dice_value = dice_msg.dice.value
            if game_type == 'two_dice':
                await asyncio.sleep(2)
                second_dice_msg = await bot.send_dice(
                    chat_id=BETS_ID,
                    emoji=game.get_emoji(bet_type) if hasattr(game, 'get_emoji') else game.EMOJI,
                    reply_to_message_id=bet_msg.message_id
                )
                second_dice_value = second_dice_msg.dice.value
        if game_type == 'two_dice' or (game_type == 'bowling' and 'second_dice_value' in locals()):
            result = await game.process(bet_type, dice_value, locals().get('second_dice_value'))
        else:
            result = await game.process(bet_type, dice_value)
        await asyncio.sleep(2)
        await db.add_transaction(
            user_id=data['id'],
            amount=-float(data['usd_amount']),
            type='game',
            game_type=game_type
        )
        referrer_id = await db.get_referrer(data['id'])
        if referrer_id:
            if result.won:
                ref_penalty = float(result.amount) * 0.15
                await db.update_ref_balance(referrer_id, -ref_penalty)
                await bot.send_message(
                    chat_id=referrer_id,
                    text=f"💸 С вашего Реф.Баланса списано <code>{ref_penalty:.2f}$</code> из-за выигрыша <code>{data['name']}</code>",
                    parse_mode="HTML"
                )
            else:
                ref_reward = float(data['usd_amount']) * 0.15
                await db.update_ref_balance(referrer_id, ref_reward)
                await bot.send_message(
                    chat_id=referrer_id,
                    text=f"💵 Ваш Реф.Баланс пополнен на <code>{ref_reward:.2f}$</code> из-за проигрыша <code>{data['name']}</code>",
                    parse_mode="HTML"
                )
        if result.won and result.draw == False:
            win_amount = float(result.amount)
            check_result = await create_payment_check(win_amount)
            if check_result and 'check_link' in check_result:
                check_token = str(uuid.uuid4())[:8]
                await db.save_win_check_token(
                    token=check_token,
                    user_id=data['id'],
                    amount=win_amount,
                    check_link=check_result['check_link'] # Передаем check_link
                )
                message_text = (
                    f"<b>🍀 Поздравляем, вы победили!</b>\n\n"
                    f"<blockquote>• <b>Удача на вашей стороне, вы выиграли {result.amount:.2f}$!</b>\n"
                    f"• <b>Забрать выигрыш можно по кнопке ниже</b></blockquote>\n\n"
                    f"<b>{await links()}</b>"
                )
                if not await db.has_seen_instruction(user_id):
                    await db.mark_instruction_seen(user_id)
                    await bot.send_photo(
                        chat_id=BETS_ID,
                        photo=types.FSInputFile("win.jpg"),
                        caption=message_text,
                        parse_mode="HTML",
                        reply_to_message_id=bet_msg.message_id,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=f"💸 Забрать {win_amount:.2f}$", url=f"https://t.me/{(await bot.get_me()).username}?start={check_token}")],
                            [InlineKeyboardButton(text="💬 Сделать ставку", url=GIDE_LINK)],
                            [InlineKeyboardButton(text='🤖 Cделать ставку', url="https://t.me/BunnyCasinoRobot?start=games")]

                        ])
                    )
                else:
                    await bot.send_photo(
                        chat_id=BETS_ID,
                        photo=types.FSInputFile("win.jpg"),
                        caption=message_text,
                        parse_mode="HTML",
                        reply_to_message_id=bet_msg.message_id,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=f"💸 Забрать {win_amount:.2f}$", url=f"https://t.me/{(await bot.get_me()).username}?start={check_token}")],
                            [InlineKeyboardButton(text='🤖 Cделать ставку', url="https://t.me/BunnyCasinoRobot?start=games")]

                        ])
                    )
            else:
                message_text = (
                    f"<b>🍀 Поздравляем, вы победили!</b>\n\n"
                    f"<blockquote>• <b>Удача на вашей стороне, выигрыш в размере {result.amount:.2f}$ будет зачислен вручную администрацией!</b></blockquote>\n\n"
                    f"<b>{await links()}</b>"
                )
                if not await db.has_seen_instruction(user_id):
                    await db.mark_instruction_seen(user_id)
                    await bot.send_photo(
                        chat_id=BETS_ID,
                        photo=types.FSInputFile("win.jpg"),
                        caption=message_text,
                        parse_mode="HTML",
                        reply_to_message_id=bet_msg.message_id,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=f"Техподдержка", url=SUPPORT_LINK)],
                            [InlineKeyboardButton(text="💬 Сделать ставку", url=GIDE_LINK)],
                            [InlineKeyboardButton(text='🤖 Cделать ставку', url="https://t.me/BunnyCasinoRobot?start=games")]

                        ])
                    )
                else:
                    await bot.send_photo(
                        chat_id=BETS_ID,
                        photo=types.FSInputFile("win.jpg"),
                        caption=message_text,
                        parse_mode="HTML",
                        reply_to_message_id=bet_msg.message_id,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=f"Техподдержка", url=SUPPORT_LINK)],
                            [InlineKeyboardButton(text='🤖 Cделать ставку', url="https://t.me/BunnyCasinoRobot?start=games")]

                        ])
                    )
                await bot.send_message(
                    chat_id=LOGS_ID,
                    text=f"⚠️ <b>ТРЕБУЕТСЯ РУЧНАЯ ВЫПЛАТА</b>\n\n"
                         f"<b>Игрок:</b> <code>{data['name']}</code>\n"
                         f"<b>ID:</b> <code>{data['id']}</code>\n"
                         f"<b>Сумма выигрыша:</b> <code>{result.amount:.2f}$</code>\n"
                         f"<b>Тип ставки:</b> <code>{data['comment']}</code>\n"
                         f"<b>Сумма ставки:</b> <code>{data['usd_amount']}$</code>\n"
                         f"<b>Тип игры:</b> <code>{game_type}</code>",
                    parse_mode="HTML"
                )

            # Записываем выигрыш как отдельную транзакцию
            await db.add_transaction(
                user_id=data['id'],
                amount=win_amount, # Положительная сумма выигрыша
                type='game',
                game_type=game_type
            )
        elif result.won == False and result.draw == False:
            message_text = (
                f"<b>🚫 К сожалению, вы проиграли...</b>\n\n"
                f"<blockquote>• <b>В этот раз удача проскакала мимо вас, но не стоит расстраиваться! 99% игроков останавливаются перед кнрупны выигрышем!</b></blockquote>\n\n"
                f"<b>{await links()}</b>"
            )
            if not await db.has_seen_instruction(user_id):
                await db.mark_instruction_seen(user_id)
                await bot.send_photo(
                    chat_id=BETS_ID,
                    photo=types.FSInputFile("lose.jpg"),
                    caption=message_text,
                    parse_mode="HTML",
                    reply_to_message_id=bet_msg.message_id,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="💬 Сделать ставку", url=GIDE_LINK)],
                        [InlineKeyboardButton(text='🤖 Cделать ставку', url="https://t.me/BunnyCasinoRobot?start=games")]

                    ])
                )
            else:
                await bot.send_photo(
                chat_id=BETS_ID,
                    photo=types.FSInputFile("lose.jpg"),
                    caption=message_text,
                    parse_mode="HTML",
                    reply_to_message_id=bet_msg.message_id,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text='🤖 Cделать ставку', url="https://t.me/BunnyCasinoRobot?start=games")]

                    ])
                )
        else:
            win_amount = float(result.amount)
            check_result = await create_payment_check(win_amount)
            if check_result and 'check_link' in check_result:
                check_token = str(uuid.uuid4())[:8]
                await db.save_win_check_token(
                    token=check_token,
                    user_id=data['id'],
                    amount=win_amount,
                    check_link=check_result['check_link']
                )

                message_text = (
                    f"<b>❎ Ничья </b>\n\n"
                    f"<blockquote>• <b>Ничья — возврат ставки {result.amount:.2f}$!</b></blockquote>\n\n"
                    f"<b>{await links()}</b>"
                )
                if not await db.has_seen_instruction(user_id):
                    await db.mark_instruction_seen(user_id)
                    await bot.send_photo(
                        chat_id=BETS_ID,
                        photo=types.FSInputFile("draw.jpg"),
                        caption=message_text,
                        parse_mode="HTML",
                        reply_to_message_id=bet_msg.message_id,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=f"Забрать {win_amount:.2f}$", url=f"https://t.me/{(await bot.get_me()).username}?start={check_token}")],
                            [InlineKeyboardButton(text="💬 Сделать ставку", url=GIDE_LINK)],
                            [InlineKeyboardButton(text='🤖 Cделать ставку', url="https://t.me/BunnyCasinoRobot?start=games")]

                        ])
                    )
                else:
                    await bot.send_photo(
                        chat_id=BETS_ID,
                        photo=types.FSInputFile("draw.jpg"),
                        caption=message_text,
                        parse_mode="HTML",
                        reply_to_message_id=bet_msg.message_id,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=f"Забрать {win_amount:.2f}$", url=f"https://t.me/{(await bot.get_me()).username}?start={check_token}")],
                            [InlineKeyboardButton(text='🤖 Cделать ставку', url="https://t.me/BunnyCasinoRobot?start=games")]

                        ])
                    )

    except Exception as e:
        logging.error(f"Error processing bet: {e}")

async def main():
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Меню"),
        types.BotCommand(command="games", description="Доступные игры"),
        types.BotCommand(command="refs", description="Реферальная система"),
        types.BotCommand(command="profile", description="Ваш профиль"),
        types.BotCommand(command="stats", description="Ваша статистика"),
        types.BotCommand(command="cancel", description="Отмена текущих действий"),
    ])

    await db.init()

    cmds = await bot.get_my_commands()
    print("🔧 Установленные команды:", cmds)
    
    asyncio.create_task(check_invoices_periodically()) # Запуск фоновой задачи
    
    await dp.start_polling(bot)


@dp.callback_query(lambda c: c.data == "withdraw_ref_balance")
async def withdraw_ref_balance(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    user = await db.get_user(user_id)
    ref_balance = user.get('ref_balance', 0)
    

    min_withdraw = 1
    
    if ref_balance < min_withdraw:
        await callback_query.answer(f"Минимальная сумма для вывода: {min_withdraw}$", show_alert=True)
        return
    

    withdraw_token = f"REF{user_id}_{int(time.time())}"
    

    await db.update_ref_balance(user_id, -ref_balance)
    

    await db.add_transaction(
        user_id=user_id,
        amount=-float(ref_balance),
        type='withdraw',
        game_type='ref_balance'
    )
    

    await bot.send_message(
        chat_id=user_id,
        text=f"<b>Запрос на вывод реф.баланса создан</b>\n\n"
             f"<blockquote>• <b>Сумма к выводу:</b> <code>{ref_balance:.2f}$</code>\n"
             f"• <b>Дата запроса:</b> <code>{time.strftime('%d.%m.%Y %H:%M')}</code>\n"
             f"• <b>Статус:</b> <code>В обработке</code></blockquote>\n\n"
             f"<b>Ваш токен:</b>\n"
             f"<code>{withdraw_token}</code>\n\n"
             f"<blockquote><b>Напишите в поддержку и укажите ваш токен для получения выплаты.</b></blockquote>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Написать в поддержку", url=SUPPORT_LINK)]
        ])
    )
    

    await bot.send_message(
        chat_id=LOGS_ID,
        text=f"<b>ЗАПРОС НА ВЫВОД РЕФ.БАЛАНСА</b>\n\n"
             f"<blockquote>• <b>Пользователь:</b> {callback_query.from_user.mention_html()}\n"
             f"• <b>ID:</b> <code>{user_id}</code>\n"
             f"• <b>Сумма:</b> <code>{ref_balance:.2f}$</code>\n"
             f"• <b>Дата запроса:</b> <code>{time.strftime('%d.%m.%Y %H:%M')}</code></blockquote>\n\n"
             f"<b>Токен для выплаты:</b>\n"
             f"<code>{withdraw_token}</code>",
        parse_mode="HTML"
    )
    
    await callback_query.answer()

@dp.message()
async def log_all_messages(message: types.Message):
    """Только для отладки - логирует все входящие сообщения"""
    logging.info(f"Received message: {message.text or message.caption}")
    logging.info(f"From: {message.from_user.id} in chat: {message.chat.id}")
    logging.info(f"Entities: {message.entities}")

async def check_invoices_periodically():
    while True:
        try:
            logging.info("Checking for paid invoices...")
            invoices_data = await crypto_pay.get_invoices(status="paid", count=100) # Проверяем последние 100 оплаченных инвойсов
            invoices = invoices_data.get('result', {}).get('items', []) # Обновлено для правильной структуры ответа

            for invoice in invoices:
                payload = invoice.get('payload')
                status = invoice.get('status')
                invoice_id = invoice.get('invoice_id') # Используем invoice_id для уникальности

                if payload and status == 'paid': # Проверяем только оплаченные инвойсы с payload
                    # Проверяем, был ли этот инвойс уже обработан
                    bet_data_from_db = await db.get_invoice_bet(payload)
                    
                    if bet_data_from_db and bet_data_from_db['status'] == 'pending': # Проверяем, что инвойс есть в нашей БД и он еще не обработан
                        logging.info(f"Found new paid invoice: {invoice_id} with payload {payload}. Processing...")
                        
                        user_info = None
                        try:
                            user_info = await bot.get_chat(bet_data_from_db['user_id'])
                            user_name = user_info.full_name if user_info else f"User {bet_data_from_db['user_id']}"
                        except Exception:
                            user_name = f"User {bet_data_from_db['user_id']}"

                        data_for_process_bet = {
                            'id': bet_data_from_db['user_id'],
                            'name': user_name,
                            'usd_amount': bet_data_from_db['amount'],
                            'comment': bet_data_from_db['bet_type_key'],
                            'game': bet_data_from_db['game_key']
                        }
                        await process_bet(data_for_process_bet)
                        await db.mark_invoice_bet_paid(payload)
                        logging.info(f"Invoice bet {invoice_id} processed and marked as paid.")
                    elif bet_data_from_db and bet_data_from_db['status'] == 'paid':
                        pass
                    else:
                       
                        pass 

        except Exception as e:
            logging.error(f"Error checking invoices periodically: {e}", exc_info=True)

        await asyncio.sleep(10) # Проверять каждые 10 секунд

if __name__ == '__main__':
    asyncio.run(main())