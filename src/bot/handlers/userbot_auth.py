"""
Обработчик авторизации UserBot через Telegram бота
Позволяет владельцу авторизовать UserBot без консоли
"""

import asyncio
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.bot.filters.owner import owner_filter
from src.bot.states.fsm import UserbotAuthStates
from src.utils.exceptions import UserbotError
from src.userbot.auth_manager import get_auth_manager, AuthStatus, reset_auth_manager
from src.utils.html_formatter import (
    bold, code, format_success_message, format_error_message,
    format_warning_message, format_info_message, format_list_items,
    get_parse_mode
)

# Настройка логгера модуля
logger = logger.bind(module="userbot_auth_bot")

# Создаем роутер
router = Router()


@router.message(Command("connect_userbot"), owner_filter)
async def connect_userbot_command(message: Message, state: FSMContext) -> None:
    """Команда подключения UserBot"""
    try:
        # Сбрасываем любое предыдущее состояние
        await state.clear()
        
        logger.info("Запрос подключения UserBot от {}", message.from_user.id)
        
        auth_manager = get_auth_manager()
        status = await auth_manager.get_status()
        
        if status == AuthStatus.CONNECTED:
            await message.answer(
                format_success_message(
                    "UserBot уже подключен!",
                    "🔍 UserBot активно мониторит каналы\n📊 Используйте /status для проверки состояния"
                ),
                parse_mode=get_parse_mode()
            )
            return
        
        elif status == AuthStatus.CONNECTING:
            await message.answer(
                format_warning_message(
                    "UserBot подключается...",
                    "⏳ Подождите завершения процесса подключения"
                ),
                parse_mode=get_parse_mode()
            )
            return
        
        # Начинаем процесс авторизации
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="📱 Начать авторизацию", 
                    callback_data="start_userbot_auth"
                )],
                [InlineKeyboardButton(
                    text="❌ Отмена", 
                    callback_data="cancel_userbot_auth"
                )]
            ]
        )
        
        auth_text = f"""🔑 {bold('Авторизация UserBot')}

📱 Для мониторинга каналов нужно подключить UserBot

📋 {bold('Процесс авторизации:')}
{format_list_items([
    'Нажмите "Начать авторизацию"',
    'Введите номер телефона',
    'Telegram отправит SMS код',
    'Введите код в этот чат',
    'При необходимости введите 2FA пароль'
], '1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣'.split())}

⚠️ {bold('Внимание:')} UserBot использует ваши Telegram данные только для мониторинга каналов"""
        
        await message.answer(
            auth_text,
            parse_mode=get_parse_mode(),
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error("Ошибка команды подключения UserBot: {}", str(e))
        await message.answer(
            format_error_message(
                "Ошибка инициации подключения UserBot",
                code(str(e))
            ),
            parse_mode=get_parse_mode()
        )


@router.callback_query(F.data == "start_userbot_auth", owner_filter)
async def start_userbot_auth_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Начало авторизации UserBot - запрос номера телефона"""
    try:
        await callback.answer()
        
        # Устанавливаем состояние ожидания номера телефона
        await state.set_state(UserbotAuthStates.waiting_for_phone)
        
        phone_text = f"""📞 {bold('Введите номер телефона')}

📱 Укажите номер телефона для авторизации UserBot

💡 {bold('Формат:')} 
{format_list_items([
    '+7 (XXX) XXX-XX-XX - для российских номеров',
    '+1 (XXX) XXX-XXXX - для американских номеров',
    '+380 XX XXX XXXX - для украинских номеров'
], '• • •'.split())}

📝 {bold('Примеры:')}
• {code('+79991234567')}
• {code('+16625551234')} 
• {code('+380991234567')}

🔄 Для отмены используйте /cancel"""
        
        await callback.message.edit_text(
            phone_text,
            parse_mode=get_parse_mode()
        )
        
        logger.info("Запрошен ввод номера телефона от пользователя {}", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка запроса номера телефона: {}", str(e))
        await callback.message.edit_text(
            format_error_message(
                "Ошибка начала авторизации",
                code(str(e))
            ),
            parse_mode=get_parse_mode()
        )


@router.callback_query(F.data == "cancel_userbot_auth", owner_filter)
async def cancel_userbot_auth_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Отмена авторизации UserBot"""
    await callback.answer()
    
    # Полностью сбрасываем состояние FSM
    await state.clear()
    
    # Сбрасываем состояние auth_manager если нужно
    auth_manager = get_auth_manager()
    if auth_manager.status in [AuthStatus.CONNECTING, AuthStatus.WAITING_CODE, AuthStatus.WAITING_PASSWORD]:
        await auth_manager.reset_auth()
    
    await callback.message.edit_text(
        format_warning_message(
            "Авторизация отменена",
            "Для повторной попытки используйте /connect_userbot"
        ),
        parse_mode=get_parse_mode()
    )
    
    logger.info("Авторизация UserBot отменена пользователем")


@router.message(UserbotAuthStates.waiting_for_phone, owner_filter, F.text, lambda m: not m.text.startswith('/'))
async def handle_phone_number(message: Message, state: FSMContext) -> None:
    """Обработка ввода номера телефона"""
    try:
        phone_number = message.text.strip()
        
        # Простая валидация номера телефона
        import re
        # Убираем все символы кроме цифр и +
        clean_phone = re.sub(r'[^+\d]', '', phone_number)
        
        # Проверяем формат номера (должен начинаться с + и содержать от 10 до 15 цифр)
        if not re.match(r'^\+\d{10,15}$', clean_phone):
            await message.answer(
                format_error_message(
                    "Неверный формат номера",
                    "Номер должен начинаться с + и содержать от 10 до 15 цифр\n"
                    f"Пример: {code('+79991234567')}\n"
                    "Попробуйте еще раз:"
                ),
                parse_mode=get_parse_mode()
            )
            return
        
        await message.answer(
            format_info_message(
                "Отправляю SMS код...",
                f"📞 Номер: {code(clean_phone)}\n⏳ Подождите несколько секунд"
            ),
            parse_mode=get_parse_mode()
        )
        
        # Сохраняем номер в состоянии
        await state.update_data(auth_phone=clean_phone)
        
        # Получаем auth_manager и пытаемся отправить код
        auth_manager = get_auth_manager()
        result = await auth_manager.start_auth_with_phone(clean_phone)
        
        if result.success:
            # Устанавливаем состояние ожидания кода
            await state.set_state(UserbotAuthStates.waiting_for_code)
            
            sms_text = f"""📱 {bold('SMS код отправлен!')}

📞 Номер телефона: {code(clean_phone)}

💬 {bold('Введите SMS код из Telegram:')}
Отправьте код следующим сообщением в этот чат

⏱ Время действия кода: {bold('5 минут')}

🔄 Для отмены используйте /cancel"""
            
            await message.answer(
                sms_text,
                parse_mode=get_parse_mode()
            )
            
            logger.info("SMS код запрошен для номера: {}", clean_phone)
            
        else:
            await message.answer(
                format_error_message(
                    "Ошибка отправки SMS кода",
                    f"{code(result.error)}\n\n🔄 Попробуйте ввести номер еще раз:"
                ),
                parse_mode=get_parse_mode()
            )
            
    except Exception as e:
        logger.error("Ошибка обработки номера телефона: {}", str(e))
        await message.answer(
            format_error_message(
                "Ошибка обработки номера",
                code(str(e))
            ),
            parse_mode=get_parse_mode()
        )


@router.message(UserbotAuthStates.waiting_for_code, owner_filter, F.text, lambda m: not m.text.startswith('/'))
async def handle_sms_code(message: Message, state: FSMContext) -> None:
    """Обработка SMS кода"""
    try:
        sms_code = message.text.strip()
        
        # Валидация кода
        if not sms_code.isdigit() or len(sms_code) != 5:
            await message.answer(
                format_error_message(
                    "Неверный формат кода",
                    "SMS код должен содержать 5 цифр\nПопробуйте еще раз:"
                ),
                parse_mode=get_parse_mode()
            )
            return
        
        await message.answer(
            format_info_message(
                "Проверяю код...",
                "⏳ Подождите несколько секунд"
            ),
            parse_mode=get_parse_mode()
        )
        
        auth_manager = get_auth_manager()
        result = await auth_manager.submit_code(sms_code)
        
        if result.success:
            if result.requires_password:
                # Нужен 2FA пароль
                await state.set_state(UserbotAuthStates.waiting_for_password)
                
                twofa_text = f"""🔐 {bold('Требуется 2FA пароль')}

🛡 У вашего аккаунта включена двухфакторная аутентификация

🔑 {bold('Введите пароль 2FA:')}
Отправьте пароль следующим сообщением

🔄 Для отмены используйте /cancel"""
                
                await message.answer(
                    twofa_text,
                    parse_mode=get_parse_mode()
                )
                
                logger.info("SMS код принят, требуется 2FA пароль")
                
            else:
                # Авторизация завершена
                await state.clear()
                
                success_text = f"""✅ {bold('UserBot успешно подключен!')}

🟢 Соединение установлено
📡 Мониторинг каналов активирован

🎯 Теперь можете:
{format_list_items([
    'Добавлять каналы для мониторинга (/channels)',
    'Проверять статус (/status)',
    'Модерировать найденные посты (/moderation)'
])}"""
                
                await message.answer(
                    success_text,
                    parse_mode=get_parse_mode()
                )
                
                logger.info("UserBot успешно авторизован и подключен")
        
        else:
            await message.answer(
                format_error_message(
                    "Неверный SMS код",
                    f"{code(result.error)}\n\n🔄 Попробуйте ввести код еще раз:\nИли используйте /cancel для отмены"
                ),
                parse_mode=get_parse_mode()
            )
            
    except Exception as e:
        logger.error("Ошибка обработки SMS кода: {}", str(e))
        await message.answer(
            format_error_message(
                "Ошибка обработки SMS кода",
                code(str(e))
            ),
            parse_mode=get_parse_mode()
        )


@router.message(UserbotAuthStates.waiting_for_password, owner_filter, F.text, lambda m: not m.text.startswith('/'))
async def handle_2fa_password(message: Message, state: FSMContext) -> None:
    """Обработка 2FA пароля"""
    try:
        password = message.text.strip()
        
        # Удаляем сообщение с паролем для безопасности
        try:
            await message.delete()
        except Exception:
            pass
        
        await message.answer(
            format_info_message(
                "Проверяю пароль...",
                "⏳ Подождите несколько секунд"
            ),
            parse_mode=get_parse_mode()
        )
        
        auth_manager = get_auth_manager()
        result = await auth_manager.submit_password(password)
        
        if result.success:
            await state.clear()
            
            success_text = f"""✅ {bold('UserBot успешно подключен!')}

🟢 Соединение установлено
📡 Мониторинг каналов активирован

🎯 Теперь можете:
{format_list_items([
    'Добавлять каналы для мониторинга (/channels)',
    'Проверять статус (/status)',
    'Модерировать найденные посты (/moderation)'
])}"""
            
            await message.answer(
                success_text,
                parse_mode=get_parse_mode()
            )
            
            logger.info("UserBot успешно авторизован с 2FA")
        
        else:
            await message.answer(
                format_error_message(
                    "Неверный пароль 2FA",
                    f"{code(result.error)}\n\n🔄 Попробуйте ввести пароль еще раз:\nИли используйте /cancel для отмены"
                ),
                parse_mode=get_parse_mode()
            )
            
    except Exception as e:
        logger.error("Ошибка обработки 2FA пароля: {}", str(e))
        await message.answer(
            format_error_message(
                "Ошибка обработки пароля",
                code(str(e))
            ),
            parse_mode=get_parse_mode()
        )


@router.callback_query(F.data == "disconnect_userbot", owner_filter)
async def disconnect_userbot_callback(callback: CallbackQuery) -> None:
    """Callback для отключения UserBot"""
    try:
        await callback.answer("🔌 Отключение UserBot...")
        
        auth_manager = get_auth_manager()
        result = await auth_manager.disconnect()
        
        if result.success:
            await callback.message.edit_text(
                format_warning_message(
                    "UserBot отключен",
                    "📡 Мониторинг каналов остановлен\n🔄 Для повторного подключения используйте /connect_userbot"
                ),
                parse_mode=get_parse_mode()
            )
            
            logger.info("UserBot отключен по callback пользователя")
        
        else:
            await callback.message.edit_text(
                format_error_message(
                    "Ошибка отключения",
                    code(result.error)
                ),
                parse_mode=get_parse_mode()
            )
            
    except Exception as e:
        logger.error("Ошибка callback отключения UserBot: {}", str(e))
        await callback.answer("❌ Произошла ошибка при отключении", show_alert=True)


@router.message(Command("disconnect_userbot"), owner_filter)
async def disconnect_userbot_command(message: Message) -> None:
    """Команда отключения UserBot"""
    try:
        auth_manager = get_auth_manager()
        result = await auth_manager.disconnect()
        
        if result.success:
            await message.answer(
                format_warning_message(
                    "UserBot отключен",
                    "📡 Мониторинг каналов остановлен\n🔄 Для повторного подключения используйте /connect_userbot"
                ),
                parse_mode=get_parse_mode()
            )
            
            logger.info("UserBot отключен по команде пользователя")
        
        else:
            await message.answer(
                format_error_message(
                    "Ошибка отключения",
                    code(result.error)
                ),
                parse_mode=get_parse_mode()
            )
            
    except Exception as e:
        logger.error("Ошибка команды отключения UserBot: {}", str(e))
        await message.answer(
            format_error_message(
                "Ошибка отключения UserBot",
                code(str(e))
            ),
            parse_mode=get_parse_mode()
        )


@router.message(Command("reset_userbot"), owner_filter)
async def reset_userbot_command(message: Message) -> None:
    """Команда полного сброса UserBot - удаляет сессию и сбрасывает все состояния"""
    try:
        logger.info("Запрос полного сброса UserBot от {}", message.from_user.id)
        
        # Показываем предупреждение с подтверждением
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔄 Да, сбросить полностью", 
                    callback_data="confirm_reset_userbot"
                )],
                [InlineKeyboardButton(
                    text="❌ Отмена", 
                    callback_data="cancel_reset_userbot"
                )]
            ]
        )
        
        reset_text = f"""⚠️ {bold('Полный сброс UserBot')}

🔄 Это действие {bold('полностью удалит')}:
{format_list_items([
    'Текущую сессию авторизации',
    'Все сохраненные данные входа',
    'Подключение к Telegram аккаунту'
], '• • • •'.split())}

📱 {bold('После сброса потребуется:')}
{format_list_items([
    'Заново авторизоваться через /connect_userbot',
    'Ввести номер телефона и SMS код',
    'При необходимости ввести 2FA пароль'
], '1️⃣ 2️⃣ 3️⃣'.split())}

⚠️ {bold('Внимание:')} Это необратимое действие!"""
        
        await message.answer(
            reset_text,
            parse_mode=get_parse_mode(),
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error("Ошибка команды сброса UserBot: {}", str(e))
        await message.answer(
            format_error_message(
                "Ошибка инициации сброса UserBot",
                code(str(e))
            ),
            parse_mode=get_parse_mode()
        )


@router.callback_query(F.data == "confirm_reset_userbot", owner_filter)
async def confirm_reset_userbot_callback(callback: CallbackQuery) -> None:
    """Подтверждение полного сброса UserBot"""
    try:
        await callback.answer("🔄 Выполняю полный сброс UserBot...")
        
        # Выполняем полный сброс
        result = await reset_auth_manager()
        
        if result.success:
            await callback.message.edit_text(
                format_success_message(
                    "UserBot полностью сброшен!",
                    "✅ Сессия удалена, все состояния очищены\n🔄 Для нового подключения используйте /connect_userbot"
                ),
                parse_mode=get_parse_mode()
            )
            
            logger.info("UserBot полностью сброшен пользователем {}", callback.from_user.id)
        
        else:
            await callback.message.edit_text(
                format_error_message(
                    "Ошибка сброса UserBot",
                    code(result.error)
                ),
                parse_mode=get_parse_mode()
            )
            
    except Exception as e:
        logger.error("Ошибка подтверждения сброса UserBot: {}", str(e))
        await callback.answer("❌ Произошла ошибка при сбросе", show_alert=True)


@router.callback_query(F.data == "cancel_reset_userbot", owner_filter)
async def cancel_reset_userbot_callback(callback: CallbackQuery) -> None:
    """Отмена сброса UserBot"""
    await callback.answer()
    
    await callback.message.edit_text(
        format_warning_message(
            "Сброс отменен",
            "UserBot остается в текущем состоянии"
        ),
        parse_mode=get_parse_mode()
    )
    
    logger.info("Сброс UserBot отменен пользователем")


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    """Отмена текущего состояния"""
    current_state = await state.get_state()
    
    if current_state:
        # Если это состояние авторизации UserBot, сбрасываем auth_manager
        if current_state in [
            UserbotAuthStates.waiting_for_phone.state,
            UserbotAuthStates.waiting_for_code.state,
            UserbotAuthStates.waiting_for_password.state
        ]:
            auth_manager = get_auth_manager()
            await auth_manager.reset_auth()
            logger.info("Сброшено состояние auth_manager при отмене авторизации")
        
        # Полностью очищаем FSM состояние
        await state.clear()
        
        await message.answer(
            format_warning_message(
                "Операция отменена",
                "Все действия прерваны\nДля новой авторизации используйте /connect_userbot"
            ),
            parse_mode=get_parse_mode()
        )
        
        logger.info("Пользователь отменил операцию в состоянии: {}", current_state)
    else:
        await message.answer(
            format_info_message(
                "Нет активных операций",
                "Нечего отменять"
            ),
            parse_mode=get_parse_mode()
        )


def get_userbot_auth_router() -> Router:
    """Получить роутер авторизации UserBot"""
    return router