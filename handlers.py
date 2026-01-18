import logging
import os
import tempfile
import time
from typing import Dict

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, KeyboardButton, ReplyKeyboardMarkup, Message

from metrics import messages_processed, commands_processed, errors_total, processing_time, files_processed
from cleaner import clean_cookies, get_sites_by_category

logger = logging.getLogger(__name__)

router = Router()

class CookieStates(StatesGroup):
    waiting_for_file = State()

class MenuStates(StatesGroup):
    main_menu = State()
    id_menu = State()
    get_id_waiting = State()


@router.message(F.text == "/start")
async def start(message: Message, state: FSMContext) -> None:
    messages_processed.inc()
    commands_processed.labels(command="/start").inc()
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍪 Cookie Cleaner")],
            [KeyboardButton(text="🆔 ID")]
        ],
        resize_keyboard=True
    )
    main_msg = await message.answer("Welcome! Choose an action:", reply_markup=keyboard)
    await state.update_data(main_message_id=main_msg.message_id)
    await state.set_state(MenuStates.main_menu)

@router.message(F.text == "🍪 Cookie Cleaner")
async def cookie_cleaner_message(message: Message, state: FSMContext) -> None:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Cancel")]
        ],
        resize_keyboard=True
    )
    status_msg = await message.answer("📤 Upload your cookies file (Edge format):", reply_markup=keyboard)
    await state.update_data(message_id=status_msg.message_id)
    await state.set_state(CookieStates.waiting_for_file)


@router.message(F.document)
async def file_handler(message: Message, state: FSMContext) -> None:
    messages_processed.inc()
    document = message.document
    if not document:
        await message.answer("Please upload a file.")
        return

    if message.media_group_id is not None:
        await message.answer("Please upload only one txt file at a time.")
        return

    data = await state.get_data()
    status_message_id = data.get('message_id')

    if not status_message_id:
        await message.answer("Session error. Please start over.")
        await state.clear()
        return

    temp_input = None
    temp_output = None
    stats_file = None

    start_time = time.time()
    try:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=status_message_id,
                text="⏳ Processing your cookie file..."
            )
        except Exception:
            status_msg = await message.answer("⏳ Processing your cookie file...")
            await state.update_data(message_id=status_msg.message_id)
            status_message_id = status_msg.message_id

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as temp_file:
            temp_input = temp_file.name
            await message.bot.download(document, temp_input)

        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=status_message_id,
                text="🧹 Cleaning cookies..."
            )
        except Exception:
            status_msg = await message.answer("🧹 Cleaning cookies...")
            await state.update_data(message_id=status_msg.message_id)
            status_message_id = status_msg.message_id

        temp_output = temp_input + "_cleaned.txt"
        stats: Dict = clean_cookies(temp_input, temp_output)

        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=status_message_id,
                text="📊 Generating statistics..."
            )
        except Exception:
            status_msg = await message.answer("📊 Generating statistics...")
            await state.update_data(message_id=status_msg.message_id)
            status_message_id = status_msg.message_id

        stats_file = temp_input + "_stats.txt"
        with open(stats_file, "w", encoding="utf-8") as f:
            from cleaner import calculate_score
            site_counter = {site: count for site, count in stats["sites"].items()}
            service_counter = {site: {svc: 1 for svc in svcs} for site, svcs in stats["services"].items()}
            auth_detected = {site: set(cookies) for site, cookies in stats["auth_detected"].items()}
            score, level, _ = calculate_score(site_counter, service_counter, auth_detected)
            categories = get_sites_by_category(site_counter)
            f.write(f"🧠 SCORE: {score} ({level})\n\n")

            for site, count in stats["sites"].items():
                site_name = site
                services = ", ".join([s for s in stats["services"].get(site, []) if s])
                if services:
                    f.write(f"{site_name}({count}) - {services}\n")
                else:
                    f.write(f"{site_name}({count})\n")

            if stats["auth_detected"]:
                f.write("\n🔐 AUTH DETECTED:\n")
                for site, cookies in stats["auth_detected"].items():
                    site_name = site
                    f.write(f"{site_name}: {', '.join(cookies)}\n")

            f.write(f"\n=== STATISTICS ===\n")
            f.write(f"Total unique cookies: {stats['total_unique_cookies']}\n")
            f.write(f"Unique main domains: {stats['unique_sites']}\n")
            f.write(f"Most common domain: {stats['most_common_site']}\n")
            f.write(f"Oldest cookies age: {stats.get('oldest_cookie_age', 'Unknown')}\n")
            f.write(f"Tracking cookies detected: {stats.get('tracking_intensity', 0)}\n")
            f.write(f"🏆 Privacy Score: {stats.get('privacy_score', 0.0)}/10.0\n")

            if categories:
                f.write("\n=== BY CATEGORIES ===\n")
                for category, sites in categories.items():
                    if sites:
                        f.write(f"{category.capitalize()}: {', '.join(sites)}\n")

        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=status_message_id,
                text="✅ Processing complete! Sending results..."
            )
        except Exception:
            await message.answer("✅ Processing complete! Sending results...")

        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔄 Upload Another"), KeyboardButton(text="❌ Cancel")]
            ],
            resize_keyboard=True
        )
        await message.answer_document(
            FSInputFile(stats_file, filename="cleaned_cookies_stats.txt"),
            caption=f"Cleaned cookies statistics. Total: {stats['total_cleaned']}\n\nChoose an action:",
            reply_markup=keyboard
        )

        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="❌ Cancel")]
            ],
            resize_keyboard=True
        )
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=status_message_id,
                text="✅ Done! Upload another cookie file:",
                reply_markup=keyboard
            )
        except Exception:
            status_msg = await message.answer("✅ Done! Upload another cookie file:", reply_markup=keyboard)
            await state.update_data(message_id=status_msg.message_id)

        processing_time.observe(time.time() - start_time)
        files_processed.inc()
        logger.info(f"Processed cookies for user {message.from_user.id}")

    except Exception as e:
        errors_total.labels(type="file_processing").inc()
        logger.error(f"Error processing file: {e}")
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔄 Upload Another"), KeyboardButton(text="❌ Cancel")]
            ],
            resize_keyboard=True
        )
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=status_message_id,
                text=f"❌ Error: {str(e)}\n\nUpload another file or cancel:",
                reply_markup=keyboard
            )
        except Exception:
            await message.answer(f"Error processing file: {str(e)}\n\nChoose an action:", reply_markup=keyboard)
            await state.clear()
    finally:
        for file_path in [temp_input, temp_output, stats_file]:
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)





@router.message(F.text == "🆔 ID")
async def id_menu_message(message: Message, state: FSMContext) -> None:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Get my ID"), KeyboardButton(text="🔍 Get ID")],
            [KeyboardButton(text="🔙 Back")]
        ],
        resize_keyboard=True
    )
    await message.answer("🆔 ID Tools:", reply_markup=keyboard)
    await state.set_state(MenuStates.id_menu)
    await state.update_data(last_menu_type='id')

@router.message(F.text == "👤 Get my ID", MenuStates.id_menu)
async def get_my_id_message(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔙 Back"), KeyboardButton(text="🏠 Main Menu")]
        ],
        resize_keyboard=True
    )
    await message.answer(f"👤 Your ID: `{user_id}`", parse_mode="Markdown", reply_markup=keyboard)

@router.message(F.text == "🔍 Get ID")
async def get_id_message(message: Message, state: FSMContext) -> None:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔙 Back"), KeyboardButton(text="🏠 Main Menu")]
        ],
        resize_keyboard=True
    )
    await message.answer("🔍 Forward a message to get the sender's ID:", reply_markup=keyboard)
    await state.set_state(MenuStates.get_id_waiting)

@router.message(F.text == "🔍 Get Another ID")
async def get_another_id_message(message: Message, state: FSMContext) -> None:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔙 Back"), KeyboardButton(text="🏠 Main Menu")]
        ],
        resize_keyboard=True
    )
    await message.answer("🔍 Forward a message to get the sender's ID:", reply_markup=keyboard)
    await state.set_state(MenuStates.get_id_waiting)

@router.message(F.text == "🏠 Main Menu")
async def back_to_main_message(message: Message, state: FSMContext) -> None:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍪 Cookie Cleaner")],
            [KeyboardButton(text="🆔 ID")]
        ],
        resize_keyboard=True
    )
    await message.answer("Welcome! Choose an action:", reply_markup=keyboard)
    await state.set_state(MenuStates.main_menu)

@router.message(F.text == "🔙 Back")
async def back_button_handler(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    data = await state.get_data()
    last_menu_type = data.get('last_menu_type', 'main')

    if current_state and str(current_state).endswith('id_menu') or last_menu_type == 'id':
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🍪 Cookie Cleaner")],
                [KeyboardButton(text="🆔 ID")]
            ],
            resize_keyboard=True
        )
        await message.answer("Welcome! Choose an action:", reply_markup=keyboard)
        await state.set_state(MenuStates.main_menu)
        await state.update_data(last_menu_type='main')
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="👤 Get my ID"), KeyboardButton(text="🔍 Get ID")],
                [KeyboardButton(text="🔙 Back")]
            ],
            resize_keyboard=True
        )
        await message.answer("🆔 ID Tools:", reply_markup=keyboard)
        await state.set_state(MenuStates.id_menu)
        await state.update_data(last_menu_type='id')

@router.message(F.forward_origin, MenuStates.get_id_waiting)
async def handle_forwarded_message(message: Message, state: FSMContext) -> None:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Get Another ID")],
            [KeyboardButton(text="🏠 Main Menu")]
        ],
        resize_keyboard=True
    )

    if message.forward_origin:
        if hasattr(message.forward_origin, 'sender_user') and message.forward_origin.sender_user:
            original_user = message.forward_origin.sender_user
            user_id = original_user.id
            username = original_user.username or "No username"

            await message.reply(
                f"🔍 **Sender ID:** `{user_id}`\n**Username:** @{username}",
                parse_mode="Markdown",
                reply_markup=keyboard
            )

        elif hasattr(message.forward_origin, 'chat') and message.forward_origin.chat:
            chat = message.forward_origin.chat
            chat_id = chat.id
            chat_title = getattr(chat, 'title', 'Unknown chat')

            await message.reply(
                f"🔍 **Chat ID:** `{chat_id}`\n**Chat:** {chat_title}",
                parse_mode="Markdown",
                reply_markup=keyboard
            )

        else:
            await message.reply("❌ Unable to extract ID from this message.", reply_markup=keyboard)

    else:
        if message.forward_origin:
            if hasattr(message.forward_origin, 'sender_user') and message.forward_origin.sender_user:
                original_user = message.forward_origin.sender_user
                user_id = original_user.id
                username = original_user.username or "No username"
                await message.answer(f"Original sender ID: `{user_id}`\nUsername: @{username}", parse_mode="Markdown")
            elif hasattr(message.forward_origin, 'chat') and message.forward_origin.chat:
                chat = message.forward_origin.chat
                chat_id = chat.id
                chat_title = getattr(chat, 'title', 'Unknown chat')
                await message.answer(f"Original chat ID: `{chat_id}`\nChat: {chat_title}", parse_mode="Markdown")
            else:
                await message.answer("Unable to extract ID from this forwarded message.")

@router.message(F.text == "🔄 Upload Another")
async def upload_another_message(message: Message, state: FSMContext) -> None:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Cancel")]
        ],
        resize_keyboard=True
    )
    status_msg = await message.answer("📤 Upload your cookies file (Edge format):", reply_markup=keyboard)
    await state.update_data(message_id=status_msg.message_id)
    await state.set_state(CookieStates.waiting_for_file)

@router.message(F.text == "❌ Cancel")
async def cancel_message(message: Message, state: FSMContext) -> None:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍪 Cookie Cleaner")],
            [KeyboardButton(text="🆔 ID")]
        ],
        resize_keyboard=True
    )
    await message.answer("Action cancelled.", reply_markup=keyboard)
    await state.clear()
    await state.set_state(MenuStates.main_menu)
