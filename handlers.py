"""
Telegram bot handlers.
"""

import logging
import os
import tempfile
from typing import Dict

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message


from cleaner import clean_cookies, get_sites_by_category

logger = logging.getLogger(__name__)

router = Router()


class CookieStates(StatesGroup):
    """FSM states for cookie processing."""
    waiting_for_file = State()


class MenuStates(StatesGroup):
    """FSM states for menu navigation."""
    main_menu = State()
    id_menu = State()
    get_id_waiting = State()


@router.message(F.text == "/start")
async def start(message: Message, state: FSMContext) -> None:
    """Handle /start command."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🍪 Cookie Cleaner", callback_data="cookie_cleaner")],
            [InlineKeyboardButton(text="🆔 ID", callback_data="id_menu")]
        ]
    )
    main_msg = await message.answer("Welcome! Choose an action:", reply_markup=keyboard)
    await state.update_data(main_message_id=main_msg.message_id)
    await state.set_state(MenuStates.main_menu)


@router.callback_query(F.data == "cookie_cleaner")
async def cookie_cleaner_callback(callback_query, state: FSMContext) -> None:
    """Handle cookie cleaner button press."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")]
        ]
    )

    # Create new status message for cookie processing
    status_msg = await callback_query.message.answer("📤 Upload your cookies file (Edge format):", reply_markup=keyboard)
    await state.update_data(message_id=status_msg.message_id)

    await state.set_state(CookieStates.waiting_for_file)
    await callback_query.answer()


@router.message(F.document)
async def file_handler(message: Message, state: FSMContext) -> None:
    """Handle uploaded document."""
    document = message.document
    if not document:
        await message.answer("Please upload a file.")
        return

    # Check if more than one file is uploaded at once
    if message.media_group_id is not None:
        await message.answer("Please upload only one txt file at a time.")
        return

    # Get stored message_id
    data = await state.get_data()
    status_message_id = data.get('message_id')

    if not status_message_id:
        await message.answer("Session error. Please start over.")
        await state.clear()
        return

    temp_input = None
    temp_output = None
    stats_file = None

    try:
        # Update status: Processing file
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_message_id,
            text="⏳ Processing your cookie file..."
        )

        # Download file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as temp_file:
            temp_input = temp_file.name
            await message.bot.download(document, temp_input)

        # Update status: Cleaning cookies
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_message_id,
            text="🧹 Cleaning cookies..."
        )

        # Clean cookies and generate stats file
        temp_output = temp_input + "_cleaned.txt"
        stats: Dict = clean_cookies(temp_input, temp_output)

        # Update status: Generating statistics
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_message_id,
            text="📊 Generating statistics..."
        )

        # Create stats text file
        stats_file = temp_input + "_stats.txt"
        with open(stats_file, "w", encoding="utf-8") as f:
            # Add score and level
            from cleaner import calculate_score
            site_counter = {site: count for site, count in stats["sites"].items()}
            service_counter = {site: {svc: 1 for svc in svcs} for site, svcs in stats["services"].items()}
            auth_detected = {site: set(cookies) for site, cookies in stats["auth_detected"].items()}
            score, level, _ = calculate_score(site_counter, service_counter, auth_detected)
            categories = get_sites_by_category(site_counter)
            f.write(f"🧠 SCORE: {score} ({level})\n\n")

            # Write all sites
            for site, count in stats["sites"].items():
                site_name = site
                services = ", ".join([s for s in stats["services"].get(site, []) if s])
                if services:
                    f.write(f"{site_name}({count}) - {services}\n")
                else:
                    f.write(f"{site_name}({count})\n")

            # Add auth detected if any
            if stats["auth_detected"]:
                f.write("\n🔐 AUTH DETECTED:\n")
                for site, cookies in stats["auth_detected"].items():
                    site_name = site
                    f.write(f"{site_name}: {', '.join(cookies)}\n")

            # Add statistics
            f.write(f"\n=== STATISTICS ===\n")
            f.write(f"Total unique cookies: {stats['total_unique_cookies']}\n")
            f.write(f"Unique main domains: {stats['unique_sites']}\n")
            f.write(f"Most common domain: {stats['most_common_site']}\n")
            f.write(f"Oldest cookies age: {stats.get('oldest_cookie_age', 'Unknown')}\n")
            f.write(f"Tracking cookies detected: {stats.get('tracking_intensity', 0)}\n")
            f.write(f"🏆 Privacy Score: {stats.get('privacy_score', 0.0)}/10.0\n")

            # Add categories
            if categories:
                f.write("\n=== BY CATEGORIES ===\n")
                for category, sites in categories.items():
                    if sites:
                        f.write(f"{category.capitalize()}: {', '.join(sites)}\n")

        # Update status: Sending results
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_message_id,
            text="✅ Processing complete! Sending results..."
        )

        # Send stats file with inline keyboard
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Upload Another", callback_data="upload_another")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")]
            ]
        )
        await message.answer_document(
            FSInputFile(stats_file, filename="cleaned_cookies_stats.txt"),
            caption=f"Cleaned cookies statistics. Total: {stats['total_cleaned']}\n\nChoose an action:",
            reply_markup=keyboard
        )

        # Final status update and auto-start new session
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")]
            ]
        )
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_message_id,
            text="✅ Done! Upload another cookie file:",
            reply_markup=keyboard
        )

        # Auto-start new processing session without clearing state
        # Keep the same status message for next file

        logger.info(f"Processed cookies for user {message.from_user.id}")

    except Exception as e:
        logger.error(f"Error processing file: {e}")
        # Update status message with error and offer to continue
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Try Again", callback_data="upload_another")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")]
            ]
        )
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=status_message_id,
                text=f"❌ Error: {str(e)}\n\nUpload another file or cancel:",
                reply_markup=keyboard
            )
        except Exception:
            # Fallback if edit fails
            await message.answer(f"Error processing file: {str(e)}\n\nChoose an action:", reply_markup=keyboard)
            await state.clear()
    finally:
        # Cleanup temp files only
        for file_path in [temp_input, temp_output, stats_file]:
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)

        # DON'T clear state - keep waiting for next file


@router.callback_query(F.data == "upload_another")
async def upload_another_callback(callback_query, state: FSMContext) -> None:
    """Handle upload another button."""
    # Continue with existing session - just update status message
    data = await state.get_data()
    status_message_id = data.get('message_id')

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")]
        ]
    )

    if status_message_id:
        # Edit existing status message
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=status_message_id,
            text="📤 Upload your cookies file (Edge format):",
            reply_markup=keyboard
        )
    else:
        # Fallback: create new message if somehow lost
        status_msg = await callback_query.message.answer("📤 Upload your cookies file (Edge format):", reply_markup=keyboard)
        await state.update_data(message_id=status_msg.message_id)

    await state.set_state(CookieStates.waiting_for_file)
    await callback_query.answer()


@router.callback_query(F.data == "id_menu")
async def id_menu_callback(callback_query, state: FSMContext) -> None:
    """Handle ID menu button press."""
    data = await state.get_data()
    main_message_id = data.get('main_message_id')

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Get my ID", callback_data="get_my_id")],
            [InlineKeyboardButton(text="🔍 Get ID", callback_data="get_id")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main")]
        ]
    )

    if main_message_id:
        # Edit existing main message
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=main_message_id,
            text="🆔 ID Tools:",
            reply_markup=keyboard
        )
    else:
        # Create new main message if it doesn't exist
        main_msg = await callback_query.message.answer("🆔 ID Tools:", reply_markup=keyboard)
        await state.update_data(main_message_id=main_msg.message_id)

    await state.set_state(MenuStates.id_menu)
    await callback_query.answer()


@router.callback_query(F.data == "get_my_id", MenuStates.id_menu)
async def get_my_id_callback(callback_query, state: FSMContext) -> None:
    """Handle get my ID button press."""
    data = await state.get_data()
    main_message_id = data.get('main_message_id')

    if main_message_id:
        user_id = callback_query.from_user.id
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_id_menu")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
            ]
        )
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=main_message_id,
            text=f"👤 Your ID: `{user_id}`",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    await callback_query.answer()


@router.callback_query(F.data == "get_id")
async def get_id_callback(callback_query, state: FSMContext) -> None:
    """Handle get ID button press."""
    data = await state.get_data()
    main_message_id = data.get('main_message_id')

    if main_message_id:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_id_menu")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
            ]
        )
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=main_message_id,
            text="🔍 Forward a message to get the sender's ID:",
            reply_markup=keyboard
        )
        await state.set_state(MenuStates.get_id_waiting)

    await callback_query.answer()


@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback_query, state: FSMContext) -> None:
    """Handle back to main menu."""
    data = await state.get_data()
    main_message_id = data.get('main_message_id')

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🍪 Cookie Cleaner", callback_data="cookie_cleaner")],
            [InlineKeyboardButton(text="🆔 ID", callback_data="id_menu")]
        ]
    )

    if main_message_id:
        # Edit existing main message
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=main_message_id,
            text="Welcome! Choose an action:",
            reply_markup=keyboard
        )
    else:
        # Create new main message if it doesn't exist
        main_msg = await callback_query.message.answer("Welcome! Choose an action:", reply_markup=keyboard)
        await state.update_data(main_message_id=main_msg.message_id)

    await state.set_state(MenuStates.main_menu)
    await callback_query.answer()


@router.callback_query(F.data == "back_to_id_menu")
async def back_to_id_menu_callback(callback_query, state: FSMContext) -> None:
    """Handle back to ID menu."""
    data = await state.get_data()
    main_message_id = data.get('main_message_id')

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Get my ID", callback_data="get_my_id")],
            [InlineKeyboardButton(text="🔍 Get ID", callback_data="get_id")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main")]
        ]
    )

    if main_message_id:
        # Edit existing main message
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=main_message_id,
            text="🆔 ID Tools:",
            reply_markup=keyboard
        )
    else:
        # Create new main message if it doesn't exist
        main_msg = await callback_query.message.answer("🆔 ID Tools:", reply_markup=keyboard)
        await state.update_data(main_message_id=main_msg.message_id)

    await state.set_state(MenuStates.id_menu)
    await callback_query.answer()


@router.message(F.forward_origin, MenuStates.get_id_waiting)
async def handle_forwarded_message(message: Message, state: FSMContext) -> None:
    """Handle forwarded messages to extract sender ID."""
    if message.forward_origin:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Get Another ID", callback_data="get_id_reply")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_id_menu_reply")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main_reply")]
            ]
        )

        if hasattr(message.forward_origin, 'sender_user') and message.forward_origin.sender_user:
            original_user = message.forward_origin.sender_user
            user_id = original_user.id
            username = original_user.username or "No username"

            # Reply with result and buttons - save reply message ID
            reply_msg = await message.reply(
                f"🔍 **Sender ID:** `{user_id}`\n**Username:** @{username}",
                parse_mode="Markdown",
                reply_markup=keyboard
            )

            # Save reply message ID for this session
            await state.update_data(reply_message_id=reply_msg.message_id)

        elif hasattr(message.forward_origin, 'chat') and message.forward_origin.chat:
            chat = message.forward_origin.chat
            chat_id = chat.id
            chat_title = getattr(chat, 'title', 'Unknown chat')

            # Reply with result and buttons - save reply message ID
            reply_msg = await message.reply(
                f"🔍 **Chat ID:** `{chat_id}`\n**Chat:** {chat_title}",
                parse_mode="Markdown",
                reply_markup=keyboard
            )

            # Save reply message ID for this session
            await state.update_data(reply_message_id=reply_msg.message_id)

        else:
            reply_msg = await message.reply("❌ Unable to extract ID from this message.")
            await state.update_data(reply_message_id=reply_msg.message_id)

    else:
        # Fallback for when not in get_id_waiting state
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


@router.callback_query(F.data == "get_id_reply")
async def get_id_reply_callback(callback_query, state: FSMContext) -> None:
    """Handle get another ID from reply buttons."""
    data = await state.get_data()
    reply_message_id = data.get('reply_message_id')

    if reply_message_id:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Get Another ID", callback_data="get_id_reply")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_id_menu_reply")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main_reply")]
            ]
        )
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=reply_message_id,
            text="🔍 Forward a message to get the sender's ID:",
            reply_markup=keyboard
        )
        await state.set_state(MenuStates.get_id_waiting)

    await callback_query.answer()


@router.callback_query(F.data == "back_to_id_menu_reply")
async def back_to_id_menu_reply_callback(callback_query, state: FSMContext) -> None:
    """Handle back to ID menu from reply buttons."""
    data = await state.get_data()
    reply_message_id = data.get('reply_message_id')

    if reply_message_id:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👤 Get my ID", callback_data="get_my_id_reply")],
                [InlineKeyboardButton(text="🔍 Get ID", callback_data="get_id_reply")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main_reply")]
            ]
        )
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=reply_message_id,
            text="🆔 ID Tools:",
            reply_markup=keyboard
        )
        await state.set_state(MenuStates.id_menu)

    await callback_query.answer()


@router.callback_query(F.data == "back_to_main_reply")
async def back_to_main_reply_callback(callback_query, state: FSMContext) -> None:
    """Handle back to main menu from reply buttons."""
    data = await state.get_data()
    reply_message_id = data.get('reply_message_id')

    if reply_message_id:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🍪 Cookie Cleaner", callback_data="cookie_cleaner_reply")],
                [InlineKeyboardButton(text="🆔 ID", callback_data="id_menu_reply")]
            ]
        )
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=reply_message_id,
            text="Welcome! Choose an action:",
            reply_markup=keyboard
        )
        await state.set_state(MenuStates.main_menu)

    await callback_query.answer()


@router.callback_query(F.data == "get_my_id_reply")
async def get_my_id_reply_callback(callback_query, state: FSMContext) -> None:
    """Handle get my ID from reply buttons."""
    data = await state.get_data()
    reply_message_id = data.get('reply_message_id')

    if reply_message_id:
        user_id = callback_query.from_user.id
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_id_menu_reply")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main_reply")]
            ]
        )
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=reply_message_id,
            text=f"👤 Your ID: `{user_id}`",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    await callback_query.answer()


@router.callback_query(F.data == "id_menu_reply")
async def id_menu_reply_callback(callback_query, state: FSMContext) -> None:
    """Handle ID menu from reply buttons."""
    data = await state.get_data()
    reply_message_id = data.get('reply_message_id')

    if reply_message_id:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👤 Get my ID", callback_data="get_my_id_reply")],
                [InlineKeyboardButton(text="🔍 Get ID", callback_data="get_id_reply")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main_reply")]
            ]
        )
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=reply_message_id,
            text="🆔 ID Tools:",
            reply_markup=keyboard
        )
        await state.set_state(MenuStates.id_menu)

    await callback_query.answer()


@router.callback_query(F.data == "cookie_cleaner_reply")
async def cookie_cleaner_reply_callback(callback_query, state: FSMContext) -> None:
    """Handle cookie cleaner from reply buttons."""
    data = await state.get_data()
    reply_message_id = data.get('reply_message_id')

    if reply_message_id:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_reply")]
            ]
        )
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=reply_message_id,
            text="📤 Upload your cookies file (Edge format):",
            reply_markup=keyboard
        )
        await state.set_state(CookieStates.waiting_for_file)

    await callback_query.answer()


@router.callback_query(F.data == "cancel_reply")
async def cancel_reply_callback(callback_query, state: FSMContext) -> None:
    """Handle cancel from reply buttons."""
    data = await state.get_data()
    reply_message_id = data.get('reply_message_id')

    if reply_message_id:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🍪 Cookie Cleaner", callback_data="cookie_cleaner_reply")],
                [InlineKeyboardButton(text="🆔 ID", callback_data="id_menu_reply")]
            ]
        )
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=reply_message_id,
            text="Welcome! Choose an action:",
            reply_markup=keyboard
        )
        await state.set_state(MenuStates.main_menu)

    await callback_query.answer()


@router.callback_query(F.data == "clear_id_history")
async def clear_id_history_callback(callback_query, state: FSMContext) -> None:
    """Handle clear ID history."""
    data = await state.get_data()
    main_message_id = data.get('main_message_id')

    if main_message_id:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_id_menu")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
            ]
        )
        await callback_query.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=main_message_id,
            text="🗑️ History cleared!\n\n🔍 Forward a message to get the sender's ID:",
            reply_markup=keyboard
        )
        # Clear processed_ids
        await state.update_data(processed_ids=[])

    await callback_query.answer()


@router.callback_query(F.data == "cancel")
async def cancel_callback(callback_query, state: FSMContext) -> None:
    """Handle cancel button."""
    data = await state.get_data()
    main_message_id = data.get('main_message_id')

    # If we have a main message, edit it back to main menu
    if main_message_id:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🍪 Cookie Cleaner", callback_data="cookie_cleaner")],
                [InlineKeyboardButton(text="🆔 ID", callback_data="id_menu")]
            ]
        )
        try:
            await callback_query.bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=main_message_id,
                text="Welcome! Choose an action:",
                reply_markup=keyboard
            )
            # Clear state but preserve main_message_id for future use
            current_state = await state.get_state()
            await state.clear()
            await state.update_data(main_message_id=main_message_id)
            await state.set_state(MenuStates.main_menu)
        except Exception:
            # Fallback if edit fails
            await callback_query.message.answer("Action cancelled.", reply_markup=keyboard)
            await state.clear()
    else:
        # Fallback for when no main message exists
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🍪 Cookie Cleaner", callback_data="cookie_cleaner")],
                [InlineKeyboardButton(text="🆔 ID", callback_data="id_menu")]
            ]
        )
        await callback_query.message.answer("Action cancelled.", reply_markup=keyboard)
        await state.clear()

    await callback_query.answer()
