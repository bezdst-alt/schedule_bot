import asyncio
import logging
import re
from datetime import datetime, date, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import db
from scheduler import get_day_schedule, get_night_schedule

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

db.init_db()

def is_admin(user_id):
    return user_id == config.YOUR_TELEGRAM_ID

async def admin_only(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к этой команде.")
        return False
    return True

user_data = {}

GRAPHIC_ALIASES = {
    "2-1-2-3": "2-1-2-3",
    "сутки/3": "24x3",
    "сутки через трое": "24x3",
    "сутки": "24x3",
    "2x2 день": "2x2_day",
    "2x2": "2x2_day",
    "2×2 день": "2x2_day",
    "2×2": "2x2_day",
    "два через два": "2x2_day",
}

GRAPHIC_NAMES = {
    "2x2_day": "2×2 день",
    "24x3": "сутки/3",
    "2-1-2-3": "2-1-2-3",
}

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not await admin_only(message):
        return
    text = (
        "Привет! Бот расписания сотрудников.\n\n"
        "Команды:\n"
        "/add_employee - Добавить одного сотрудника\n"
        "/add_employees_bulk - Массовое добавление\n"
        "/remove_employee - Удалить сотрудника\n"
        "/list_employees - Список сотрудников\n"
        "/add_override - Добавить РВ\n"
        "/remove_override - Удалить РВ\n"
        "/add_recipient - Добавить получателя\n"
        "/remove_recipient - Удалить получателя\n"
        "/list_recipients - Список получателей\n"
        "/schedule - Расписание\n"
        "/date_schedule - Расписание на дату"
    )
    await message.answer(text)

@dp.message(Command("add_employees_bulk"))
async def cmd_add_employees_bulk(message: types.Message):
    if not await admin_only(message):
        return
    text = (
        "Массовое добавление сотрудников\n\n"
        "Отправь список в таком формате (как в /list_employees):\n\n"
        "Иван Иванов - 2-1-2-3 (с 2026-08-01)\n"
        "Петр Петров - сутки/3 (с 2026-08-05)\n"
        "Сидор Сидоров - 2x2 день (с 2026-08-10)\n\n"
        "Доступные графики: 2-1-2-3, сутки/3, 2x2 день\n"
        "Разделитель между именем и графиком: тире с пробелами\n"
        "Дата внутри скобок: (с ГГГГ-ММ-ДД)"
    )
    await message.answer(text)
    user_data[message.from_user.id] = {'action': 'bulk_add', 'step': 'waiting_list'}

@dp.message(lambda msg: user_data.get(msg.from_user.id, {}).get('action') == 'bulk_add')
async def process_bulk_add(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()
    lines = text.strip().split("\n")
    
    added = []
    errors = []
    
    pattern = r'^(.*?)\s*[—-]\s*(.*?)\s*\(с\s*(\d{4}-\d{2}-\d{2})\)\s*$'
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        match = re.match(pattern, line)
        if not match:
            errors.append(f"Строка {i+1}: неверный формат. Нужно: Имя - график (с ГГГГ-ММ-ДД)")
            continue
        
        name = match.group(1).strip()
        graphic_text = match.group(2).strip().lower()
        date_str = match.group(3).strip()
        
        graphic_type = None
        for alias, gtype in GRAPHIC_ALIASES.items():
            if graphic_text == alias or graphic_text.startswith(alias):
                graphic_type = gtype
                break
        
        if not graphic_type:
            errors.append(f"Строка {i+1}: неизвестный график")
            continue
        
        try:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
        except:
            errors.append(f"Строка {i+1}: неверная дата")
            continue
        
        start_date = parsed_date.strftime("%Y-%m-%d")
        
        success = db.add_employee(name, graphic_type, start_date)
        if success:
            added.append(f"Добавлен: {name}")
        else:
            errors.append(f"{name} - уже существует")
    
    result_parts = []
    if added:
        result_parts.append("Добавлены:\n" + "\n".join(added))
    if errors:
        result_parts.append("Ошибки:\n" + "\n".join(errors))
    if not added and not errors:
        result_parts.append("Ничего не добавлено. Проверь формат.")
    
    await message.answer("\n\n".join(result_parts))
    del user_data[uid]

@dp.message(Command("list_employees"))
async def cmd_list_employees(message: types.Message):
    if not await admin_only(message):
        return
    employees = db.list_employees()
    if not employees:
        await message.answer("Нет сотрудников.")
        return
    lines = ["Список сотрудников:\n"]
    for emp in employees:
        name = emp[1]
        gtype = GRAPHIC_NAMES.get(emp[2], emp[2])
        start = emp[3]
        lines.append(f"{name} - {gtype} (с {start})")
    await message.answer("\n".join(lines))

@dp.message(Command("schedule"))
async def cmd_schedule(message: types.Message):
    if not await admin_only(message):
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сегодня", callback_data="sched_today")],
        [InlineKeyboardButton(text="Завтра", callback_data="sched_tomorrow")],
        [InlineKeyboardButton(text="Неделя", callback_data="sched_week")],
        [InlineKeyboardButton(text="Выбрать дату", callback_data="sched_custom")],
    ])
    await message.answer("Выберите период:", reply_markup=kb)

def format_schedule(for_date, employees):
    """Возвращает текст расписания на одну дату"""
    date_str = for_date.strftime("%Y-%m-%d")
    overrides_raw = db.list_overrides_for_date(date_str)
    overrides = set()
    for o in overrides_raw:
        emp = next((e for e in employees if e[1] == o[1]), None)
        if emp:
            overrides.add((emp[0], date_str, o[3]))
    
    day_workers = list(set(get_day_schedule(for_date, employees, overrides)))
    night_workers = list(set(get_night_schedule(for_date, employees, overrides)))
    
    lines = []
    lines.append("День (08:00-20:00):")
    if day_workers:
        for w in sorted(day_workers):
            emp = next((e for e in employees if e[1] == w), None)
            star = " PB" if emp and (emp[0], date_str, "day") in overrides else ""
            lines.append(f"   {w}{star}")
    else:
        lines.append("   Нет")
    lines.append("")
    lines.append("Ночь (20:00-08:00):")
    if night_workers:
        for w in sorted(night_workers):
            emp = next((e for e in employees if e[1] == w), None)
            star = " PB" if emp and (emp[0], date_str, "night") in overrides else ""
            lines.append(f"   {w}{star}")
    else:
        lines.append("   Нет")
    return "\n".join(lines)


def format_week_schedule(start_date, employees):
    """Форматирует расписание на неделю в читабельном виде"""
    lines = []
    lines.append("=" * 35)
    lines.append(f" НЕДЕЛЯ С {start_date.strftime('%d.%m.%Y')}")
    lines.append("=" * 35)
    lines.append("")
    
    for i in range(7):
        d = start_date + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        
        overrides_raw = db.list_overrides_for_date(date_str)
        overrides = set()
        for o in overrides_raw:
            emp = next((e for e in employees if e[1] == o[1]), None)
            if emp:
                overrides.add((emp[0], date_str, o[3]))
        
        day_workers = list(set(get_day_schedule(d, employees, overrides)))
        night_workers = list(set(get_night_schedule(d, employees, overrides)))
        
        day_name = d.strftime("%a")
        date_formatted = d.strftime("%d.%m")
        
        day_text = ", ".join(sorted(day_workers)) if day_workers else "-"
        night_text = ", ".join(sorted(night_workers)) if night_workers else "-"
        
        lines.append(f" {day_name} {date_formatted}")
        lines.append(f"   День: {day_text}")
        lines.append(f"   Ночь: {night_text}")
        lines.append("")
    
    lines.append("=" * 35)
    return "\n".join(lines)


@dp.callback_query(lambda c: c.data.startswith("sched_"))
async def process_schedule_query(callback: CallbackQuery):
    employees = db.list_employees()
    today = date.today()
    
    if not employees:
        await callback.message.edit_text("Нет сотрудников.")
        await callback.answer()
        return
    
    if callback.data == "sched_today":
        await show_schedule(callback.message, today, employees)
    elif callback.data == "sched_tomorrow":
        await show_schedule(callback.message, today + timedelta(days=1), employees)
    elif callback.data == "sched_week":
        text = format_week_schedule(today, employees)
        await callback.message.edit_text(text)
    elif callback.data == "sched_custom":
        user_data[callback.from_user.id] = {'action': 'schedule_custom', 'step': 'waiting'}
        await callback.message.edit_text("Введите дату (ДД.ММ.ГГГГ) или диапазон (ДД.ММ.ГГГГ-ДД.ММ.ГГГГ):")
    
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id, {}).get('action') == 'schedule_custom')
async def process_custom_schedule(message: types.Message):
    text = message.text.strip()
    uid = message.from_user.id
    employees = db.list_employees()
    
    if "-" in text and text.count("-") == 1:
        try:
            parts = text.split("-")
            start = datetime.strptime(parts[0].strip(), "%d.%m.%Y").date()
            end = datetime.strptime(parts[1].strip(), "%d.%m.%Y").date()
        except:
            await message.answer("Неверный формат. Используйте ДД.ММ.ГГГГ или ДД.ММ.ГГГГ-ДД.ММ.ГГГГ")
            return
        days = []
        d = start
        while d <= end:
            days.append(f"--- {d.strftime('%d.%m.%Y (%A)')} ---\n{format_schedule(d, employees)}")
            d += timedelta(days=1)
        for i in range(0, len(days), 3):
            await message.answer("\n\n".join(days[i:i+3]))
    else:
        try:
            d = datetime.strptime(text.strip(), "%d.%m.%Y").date()
        except:
            await message.answer("Неверный формат. Используйте ДД.ММ.ГГГГ")
            return
        await show_schedule(message, d, employees)
    
    if uid in user_data:
        del user_data[uid]

@dp.message(Command("date_schedule"))
async def cmd_date_schedule(message: types.Message):
    if not await admin_only(message):
        return
    user_data[message.from_user.id] = {'action': 'schedule_custom', 'step': 'waiting'}
    await message.answer("Введите дату (ДД.ММ.ГГГГ) или диапазон (ДД.ММ.ГГГГ-ДД.ММ.ГГГГ):")

async def show_schedule(msg, for_date, employees):
    text = f"Расписание на {for_date.strftime('%d.%m.%Y (%A)')}\n\n{format_schedule(for_date, employees)}"
    await msg.answer(text)

@dp.message(Command("add_employee"))
async def cmd_add_employee(message: types.Message):
    if not await admin_only(message):
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Два через два (день 08-20)", callback_data="graphic_2x2_day")],
        [InlineKeyboardButton(text="Сутки через трое (день/ночь)", callback_data="graphic_24x3")],
        [InlineKeyboardButton(text="2-1-2-3 (день/день/ночь/ночь/вых)", callback_data="graphic_2-1-2-3")],
    ])
    await message.answer("Выберите график работы сотрудника:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("graphic_"))
async def process_graphic_choice(callback: CallbackQuery):
    graphic_type = callback.data.replace("graphic_", "")
    user_data[callback.from_user.id] = {
        'action': 'add_employee', 'graphic_type': graphic_type, 'step': 'waiting_name'
    }
    await callback.message.edit_text("Введите имя сотрудника:")
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id, {}).get('action') == 'add_employee' and 
            user_data[msg.from_user.id].get('step') == 'waiting_name')
async def process_employee_name(message: types.Message):
    uid = message.from_user.id
    user_data[uid]['name'] = message.text.strip()
    user_data[uid]['step'] = 'waiting_date'
    await message.answer("Введите дату начала графика (ДД.ММ.ГГГГ):")

@dp.message(lambda msg: user_data.get(msg.from_user.id, {}).get('action') == 'add_employee' and 
            user_data[msg.from_user.id].get('step') == 'waiting_date')
async def process_employee_date(message: types.Message):
    date_text = message.text.strip()
    uid = message.from_user.id
    parsed_date = None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            parsed_date = datetime.strptime(date_text, fmt)
            break
        except:
            continue
    if not parsed_date:
        await message.answer("Неверный формат. Используйте ДД.ММ.ГГГГ")
        return
    data = user_data[uid]
    success = db.add_employee(data['name'], data['graphic_type'], parsed_date.strftime("%Y-%m-%d"))
    if success:
        await message.answer(f"Сотрудник {data['name']} добавлен!")
    else:
        await message.answer(f"Сотрудник {data['name']} уже существует.")
    del user_data[uid]

@dp.message(Command("remove_employee"))
async def cmd_remove_employee(message: types.Message):
    if not await admin_only(message):
        return
    employees = db.list_employees()
    if not employees:
        await message.answer("Нет сотрудников.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=emp[1], callback_data=f"rememp_{emp[0]}")] for emp in employees
    ])
    await message.answer("Выберите сотрудника для удаления:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("rememp_"))
async def process_remove_employee(callback: CallbackQuery):
    emp_id = int(callback.data.replace("rememp_", ""))
    employees = db.list_employees()
    emp = next((e for e in employees if e[0] == emp_id), None)
    if emp:
        db.remove_employee(emp[1])
        await callback.message.edit_text(f"Сотрудник {emp[1]} удален.")
    else:
        await callback.message.edit_text("Не найден.")
    await callback.answer()

@dp.message(Command("add_override"))
async def cmd_add_override(message: types.Message):
    if not await admin_only(message):
        return
    employees = db.list_employees()
    if not employees:
        await message.answer("Сначала добавьте сотрудников.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=emp[1], callback_data=f"overemp_{emp[0]}")] for emp in employees
    ])
    await message.answer("Выберите сотрудника для РВ:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("overemp_"))
async def process_override_emp(callback: CallbackQuery):
    emp_id = int(callback.data.replace("overemp_", ""))
    user_data[callback.from_user.id] = {'action': 'add_override', 'employee_id': emp_id, 'step': 'waiting_date'}
    await callback.message.edit_text("Введите дату РВ (ДД.ММ.ГГГГ):")
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id, {}).get('action') == 'add_override' and 
            user_data[msg.from_user.id].get('step') == 'waiting_date')
async def process_override_date(message: types.Message):
    uid = message.from_user.id
    try:
        parsed = datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except:
        await message.answer("Неверный формат.")
        return
    user_data[uid]['date'] = parsed.strftime("%Y-%m-%d")
    user_data[uid]['step'] = 'waiting_shift'
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Дневная (08-20)", callback_data="overshift_day")],
        [InlineKeyboardButton(text="Ночная (20-08)", callback_data="overshift_night")],
    ])
    await message.answer("Тип смены для РВ:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("overshift_"))
async def process_override_shift(callback: CallbackQuery):
    shift_type = callback.data.replace("overshift_", "")
    data = user_data.get(callback.from_user.id, {})
    success = db.add_override(data.get('employee_id'), data.get('date'), shift_type)
    if success:
        await callback.message.edit_text("РВ добавлено!")
    else:
        await callback.message.edit_text("Ошибка.")
    if callback.from_user.id in user_data:
        del user_data[callback.from_user.id]
    await callback.answer()

@dp.message(Command("remove_override"))
async def cmd_remove_override(message: types.Message):
    if not await admin_only(message):
        return
    employees = db.list_employees()
    if not employees:
        await message.answer("Нет сотрудников.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=emp[1], callback_data=f"removr_{emp[0]}")] for emp in employees
    ])
    await message.answer("Выберите сотрудника:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("removr_"))
async def proc_rem_ovr_emp(callback: CallbackQuery):
    emp_id = int(callback.data.replace("removr_", ""))
    user_data[callback.from_user.id] = {'action': 'remove_override', 'employee_id': emp_id, 'step': 'waiting_date'}
    await callback.message.edit_text("Введите дату для удаления РВ (ДД.ММ.ГГГГ):")
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id, {}).get('action') == 'remove_override' and 
            user_data[msg.from_user.id].get('step') == 'waiting_date')
async def proc_rem_ovr_date(message: types.Message):
    uid = message.from_user.id
    try:
        parsed = datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except:
        await message.answer("Неверный формат.")
        return
    date_str = parsed.strftime("%Y-%m-%d")
    overrides = db.list_overrides_for_date(date_str)
    emp = db.get_employee(user_data[uid]['employee_id'])
    emp_overrides = [o for o in overrides if o[1] == emp[1]] if emp else []
    if not emp_overrides:
        await message.answer("Нет РВ на эту дату.")
        del user_data[uid]
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'День' if o[3]=='day' else 'Ночь'}", callback_data=f"delovr_{o[0]}")] for o in emp_overrides
    ])
    await message.answer("Какое РВ удалить?", reply_markup=kb)
    user_data[uid]['step'] = 'waiting_choice'

@dp.callback_query(lambda c: c.data.startswith("delovr_"))
async def proc_del_ovr(callback: CallbackQuery):
    override_id = int(callback.data.replace("delovr_", ""))
    conn = db.get_connection()
    conn.execute("DELETE FROM overrides WHERE id=?", (override_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("РВ удалено.")
    await callback.answer()
    if callback.from_user.id in user_data:
        del user_data[callback.from_user.id]

@dp.message(Command("add_recipient"))
async def cmd_add_recipient(message: types.Message):
    if not await admin_only(message):
        return
    user_data[message.from_user.id] = {'action': 'add_recipient', 'step': 'waiting_id'}
    await message.answer("Отправьте Telegram ID или перешлите сообщение пользователя.")

@dp.message(lambda msg: user_data.get(msg.from_user.id, {}).get('action') == 'add_recipient' and 
            user_data[msg.from_user.id].get('step') == 'waiting_id')
async def process_recipient_id(message: types.Message):
    uid = message.from_user.id
    user_id_to_add = None
    name = ""
    if message.forward_from:
        user_id_to_add = message.forward_from.id
        name = message.forward_from.full_name or f"User {user_id_to_add}"
    elif message.text and message.text.strip().isdigit():
        user_id_to_add = int(message.text.strip())
        name = f"User {user_id_to_add}"
    else:
        await message.answer("Не удалось определить ID.")
        return
    success = db.add_recipient(user_id_to_add, name)
    if success:
        await message.answer(f"Получатель добавлен! ID: {user_id_to_add}")
    else:
        await message.answer("Ошибка.")
    del user_data[uid]

@dp.message(Command("remove_recipient"))
async def cmd_remove_recipient(message: types.Message):
    if not await admin_only(message):
        return
    recipients = db.list_recipients()
    if not recipients:
        await message.answer("Нет получателей.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{r[1] or r[0]}", callback_data=f"remrec_{r[0]}")] for r in recipients
    ])
    await message.answer("Выберите получателя:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("remrec_"))
async def process_remove_recipient(callback: CallbackQuery):
    uid = int(callback.data.replace("remrec_", ""))
    db.remove_recipient(uid)
    await callback.message.edit_text("Получатель удален.")
    await callback.answer()

@dp.message(Command("list_recipients"))
async def cmd_list_recipients(message: types.Message):
    if not await admin_only(message):
        return
    recipients = db.list_recipients()
    if not recipients:
        await message.answer("Нет получателей.")
        return
    lines = ["Получатели:\n"]
    for r in recipients:
        lines.append(f"{r[1]} (ID: {r[0]})")
    await message.answer("\n".join(lines))

async def send_morning_schedule():
    today = date.today()
    employees = db.list_employees()
    if not employees:
        return
    date_str = today.strftime("%Y-%m-%d")
    overrides_raw = db.list_overrides_for_date(date_str)
    overrides = set()
    for o in overrides_raw:
        emp = next((e for e in employees if e[1] == o[1]), None)
        if emp:
            overrides.add((emp[0], date_str, o[3]))
    day_workers = list(set(get_day_schedule(today, employees, overrides)))
    night_workers = list(set(get_night_schedule(today, employees, overrides)))
    
    text = f"Доброе утро! Расписание на {today.strftime('%d.%m.%Y')}\n\nДень (08:00-20:00):\n"
    if day_workers:
        for w in sorted(day_workers):
            text += f"   {w}\n"
    else:
        text += "   Нет\n"
    text += "\nНочь (20:00-08:00):\n"
    if night_workers:
        for w in sorted(night_workers):
            text += f"   {w}\n"
    else:
        text += "   Нет\n"
    
    recipients = db.list_recipients()
    for r in recipients:
        try:
            await bot.send_message(r[0], text)
        except:
            pass

async def send_evening_schedule():
    today = date.today()
    tomorrow = today + timedelta(days=1)
    employees = db.list_employees()
    if not employees:
        return
    date_str = today.strftime("%Y-%m-%d")
    overrides_raw = db.list_overrides_for_date(date_str)
    overrides = set()
    for o in overrides_raw:
        emp = next((e for e in employees if e[1] == o[1]), None)
        if emp:
            overrides.add((emp[0], date_str, o[3]))
    night_workers = list(set(get_night_schedule(today, employees, overrides)))
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")
    overrides_t = db.list_overrides_for_date(tomorrow_str)
    overrides_tomorrow = set()
    for o in overrides_t:
        emp = next((e for e in employees if e[1] == o[1]), None)
        if emp:
            overrides_tomorrow.add((emp[0], tomorrow_str, o[3]))
    tomorrow_day = list(set(get_day_schedule(tomorrow, employees, overrides_tomorrow)))
    
    text = f"Добрый вечер!\n\nСегодня ночью (20:00-08:00):\n"
    if night_workers:
        for w in sorted(night_workers):
            text += f"   {w}\n"
    else:
        text += "   Нет\n"
    text += f"\nЗавтра днем ({tomorrow.strftime('%d.%m.%Y')}, 08:00-20:00):\n"
    if tomorrow_day:
        for w in sorted(tomorrow_day):
            text += f"   {w}\n"
    else:
        text += "   Нет\n"
    
    recipients = db.list_recipients()
    for r in recipients:
        try:
            await bot.send_message(r[0], text)
        except:
            pass

async def on_startup():
    scheduler.add_job(send_morning_schedule, "cron", hour=7, minute=0)
    scheduler.add_job(send_evening_schedule, "cron", hour=19, minute=0)
    scheduler.start()

async def main():
    dp.startup.register(on_startup)
    print("Bot starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
