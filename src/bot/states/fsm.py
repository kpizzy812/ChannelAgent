"""
Состояния FSM для Telegram бота
Управление многоэтапными операциями
"""

from aiogram.fsm.state import State, StatesGroup


class UserbotAuthStates(StatesGroup):
    """Состояния для авторизации UserBot"""
    waiting_for_phone = State()     # Ожидание ввода номера телефона
    waiting_for_code = State()      # Ожидание SMS кода
    waiting_for_password = State()  # Ожидание 2FA пароля


class ChannelManagementStates(StatesGroup):
    """Состояния для управления каналами"""
    adding_channel = State()        # Добавление нового канала
    editing_channel = State()       # Редактирование канала


class PostModerationStates(StatesGroup):
    """Состояния для модерации постов"""
    editing_post = State()          # Редактирование текста поста
    scheduling_post = State()       # Планирование публикации


class ExamplePostStates(StatesGroup):
    """Состояния для работы с примерами постов"""
    adding_example = State()        # Добавление примера поста
    editing_example = State()       # Редактирование примера


class SettingsStates(StatesGroup):
    """Состояния для настроек системы"""
    editing_setting = State()       # Редактирование настройки


class DailyPostStates(StatesGroup):
    """Состояния для ежедневных постов"""
    creating_custom_template = State()  # Создание пользовательского шаблона
    entering_template_name = State()    # Ввод названия шаблона
    entering_template_text = State()    # Ввод текста шаблона
    entering_copy_name = State()        # Ввод названия для копии
    editing_template_name = State()     # Редактирование названия шаблона
    editing_template_text = State()     # Редактирование текста шаблона
    configuring_post = State()          # Настройка поста
    editing_post_content = State()      # Редактирование контента поста
    setting_publish_time = State()      # Установка времени публикации
    setting_template_time = State()     # Установка времени для шаблона