"""
Aiogram FSM States for wizards.
"""

from aiogram.fsm.state import State, StatesGroup

class OrderWizard(StatesGroup):
    waiting_for_service = State()
    waiting_for_link = State()
    waiting_for_quantity = State()
    confirm_order = State()

class TicketWizard(StatesGroup):
    waiting_for_subject = State()
    waiting_for_message = State()

class AdminBroadcastWizard(StatesGroup):
    waiting_for_type = State()
    waiting_for_content = State()
    confirming = State()

class AddFundsWizard(StatesGroup):
    waiting_for_amount = State()

class AdminSettingsWizard(StatesGroup):
    waiting_for_markup = State()
    waiting_for_welcome = State()
    waiting_for_support = State()

class AdminAdjustWizard(StatesGroup):
    waiting_for_amount = State()
    waiting_for_reason = State()
