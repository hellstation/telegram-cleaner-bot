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
from aiogram.types import FSInputFile, KeyboardButton, Message, ReplyKeyboardMarkup

from cleaner import clean_cookies

logger = logging.getLogger(__name__)

router = Router()


class CookieStates(StatesGroup):
    """FSM states for cookie processing."""
    waiting_for_file = State()


@router.message(F.text == "/start")
async def start(message: Message) -> None:
    """Handle /start command."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Cookie Cleaner")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    await message.answer("Choose action:", reply_markup=keyboard)


@router.message(F.text == "Cookie Cleaner")
async def button_handler(message: Message, state: FSMContext) -> None:
    """Handle cookie button press."""
    await message.answer("Upload cookies file (Edge format).", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Cancel")]],
        resize_keyboard=True,
        one_time_keyboard=True
    ))
    await state.set_state(CookieStates.waiting_for_file)


@router.message(CookieStates.waiting_for_file, F.document)
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

    temp_input = None
    temp_output = None
    stats_file = None
    try:
        # Download file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as temp_file:
            temp_input = temp_file.name
            await message.bot.download(document, temp_input)

        # Clean cookies and generate stats file
        temp_output = temp_input + "_cleaned.txt"
        stats: Dict = clean_cookies(temp_input, temp_output)

        # Create stats text file
        stats_file = temp_input + "_stats.txt"
        with open(stats_file, "w", encoding="utf-8") as f:
            # Add score and level
            from cleaner import calculate_score
            site_counter = {site: count for site, count in stats["sites"].items()}
            service_counter = {site: {svc: 1 for svc in svcs} for site, svcs in stats["services"].items()}
            auth_detected = {site: set(cookies) for site, cookies in stats["auth_detected"].items()}
            score, level, _ = calculate_score(site_counter, service_counter, auth_detected)
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

        # Send stats file
        await message.answer_document(
            FSInputFile(stats_file, filename="cleaned_cookies_stats.txt"),
            caption=f"Cleaned cookies statistics. Total: {stats['total_cleaned']}\n\nYou can upload another file or press 'Cancel' to exit."
        )

        logger.info(f"Processed cookies for user {message.from_user.id}")

    except Exception as e:
        logger.error(f"Error processing file: {e}")
        await message.answer(f"Error processing file: {str(e)}\n\nYou can upload the file again or press 'Cancel' to exit.")
    finally:
        # Cleanup temp files
        for file_path in [temp_input, temp_output, stats_file]:
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)


@router.message(F.text == "Cancel")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    """Handle cancel button."""
    await state.clear()
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Cookie Cleaner")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    await message.answer("Action cancelled.", reply_markup=keyboard)
