import asyncio
import logging
import re
import os
import traceback
from datetime import datetime, date, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton
)
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

async def admin_only(message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return False
    return True

user_data = {}

def detect_graphic(text):
    t = text.lower().strip()
    if "2-1-2-3" in t or "2123" in t:
        return "2-1-2-3"
    if "сутк" in t:
        return "24x3"
    t_clean = t.replace("×", "x").replace("х", "x").replace(" ", "")
    if "2x2" in t_clean:
        return "2x2_day"
    return None

GRAPHIC_NAMES = {
    "2x2_day": "2x2 день",
    "24x3": "сутки/3",
    "2-1-2-3": "2-1-2-3",
}

# ==================== ДОЛЖНОСТИ ====================

POSITIONS = {
    "chief_mechanic": {"name": "Главный механик", "emoji": "⚙️", "order": 1},
    "kipia_engineer": {"name": "Инженер КИПиА", "emoji": "💻", "order": 2},
    "electrician": {"name": "Электромеханик", "emoji": "⚡", "order": 3},
    "specialist": {"name": "Специалист", "emoji": "🔧", "order": 4},
}

def position_info(pos_key):
    p = POSITIONS.get(pos_key, POSITIONS["specialist"])
    return p["name"], p["emoji"], p["order"]

def detect_position(text):
    t = text.lower().strip()
    if "главн" in t and "механ" in t:
        return "chief_mechanic"
    if "кипиа" in t or "кип" in t:
        return "kipia_engineer"
    if "электро" in t:
        return "electrician"
    if "специал" in t:
        return "specialist"
    return None

WEEKDAYS_RU = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
WEEKDAYS_RU_ACC = ["понедельник","вторник","среду","четверг","пятницу","субботу","воскресенье"]
MONTHS_RU = {1:"января",2:"февраля",3:"марта",4:"апреля",5:"мая",6:"июня",7:"июля",8:"августа",9:"сентября",10:"октября",11:"ноября",12:"декабря"}

MONTHS_SHORT = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "мая": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "сент": 9, "окт": 10, "ноя": 11, "дек": 12
}

def fmt_date(d):
    return f"{d.day:02d} {MONTHS_RU[d.month]}"

def fmt_date_full(d):
    return f"{WEEKDAYS_RU[d.weekday()]}, {fmt_date(d)}"

def fmt_date_acc(d):
    return f"{WEEKDAYS_RU_ACC[d.weekday()]}, {fmt_date(d)}"

# ==================== МЕНЮ ====================

def main_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📋 Меню")]],
        resize_keyboard=True,
        persistent=True
    )
    return kb

def main_menu():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Сотрудники", callback_data="menu_employees")],
        [InlineKeyboardButton(text="⭐ PB", callback_data="menu_overrides")],
        [InlineKeyboardButton(text="📅 Расписание", callback_data="menu_schedule")],
        [InlineKeyboardButton(text="📢 Получатели", callback_data="menu_recipients")],
    ])
    return kb

def back_button():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_main")],
    ])
    return kb

@dp.message(Command("start"))
async def cmd_start(message):
    if not await admin_only(message):
        return
    await message.answer("Главное меню:", reply_markup=main_menu())
    await message.answer("Кнопка «📋 Меню» всегда внизу ⬇️", reply_markup=main_keyboard())

@dp.message(lambda m: m.text == "📋 Меню")
async def reply_menu(message):
    if not await admin_only(message):
        return
    await message.answer("Главное меню:", reply_markup=main_menu())

@dp.callback_query(lambda c: c.data == "menu_main")
async def back_to_main(callback):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())
    await callback.answer()

# ==================== ПОЛУЧАТЕЛИ / WEEK ====================

@dp.message(Command("week"))
async def cmd_week(message: types.Message):
    user_id = message.from_user.id
    recipients = db.list_recipients()
    is_recipient = any(r[0] == user_id for r in recipients)
    is_admin_user = is_admin(user_id)
    if not is_recipient and not is_admin_user:
        await message.answer("У вас нет доступа к этой команде.")
        return
    employees = db.list_employees()
    if not employees:
        await message.answer("Нет сотрудников в базе.")
        return
    text = format_week_schedule(date.today(), employees)
    await message.answer(text)

def recipient_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Расписание на неделю", callback_data="recipient_week")],
        [InlineKeyboardButton(text="🚫 Отписаться от рассылки", callback_data="recipient_unsubscribe")],
    ])
    return kb

@dp.callback_query(lambda c: c.data == "recipient_week")
async def recipient_week(callback):
    user_id = callback.from_user.id
    recipients = db.list_recipients()
    is_recipient = any(r[0] == user_id for r in recipients)
    is_admin_user = is_admin(user_id)
    if not is_recipient and not is_admin_user:
        await callback.message.edit_text("У вас нет доступа.")
        await callback.answer()
        return
    employees = db.list_employees()
    if not employees:
        await callback.message.edit_text("Нет сотрудников в базе.")
        await callback.answer()
        return
    text = format_week_schedule(date.today(), employees)
    await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "recipient_unsubscribe")
async def recipient_unsubscribe(callback):
    user_id = callback.from_user.id
    user_name = f"User {user_id}"
    try:
        user = await bot.get_chat(user_id)
        user_name = user.full_name or user_name
    except:
        pass
    db.remove_recipient(user_id)
    goodbye_text = (
        "🚫 **Вы отписались от ежедневной рассылки расписания.**\n\n"
        "Если захотите снова получать расписание — свяжитесь с администратором. 😊"
    )
    await callback.message.edit_text(goodbye_text)
    try:
        await bot.send_message(
            config.YOUR_TELEGRAM_ID,
            f"🚫 Пользователь отписался от рассылки\n👤 {user_name}\n🆔 {user_id}"
        )
    except:
        pass
    await callback.answer()

# ==================== СОТРУДНИКИ ====================

def employees_menu():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить одного", callback_data="emp_add")],
        [InlineKeyboardButton(text="👥 Добавить несколько", callback_data="emp_bulk")],
        [InlineKeyboardButton(text="📋 Список сотрудников", callback_data="emp_list")],
        [InlineKeyboardButton(text="🎖 Присвоить должность", callback_data="emp_position")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="emp_remove")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_main")],
    ])
    return kb

@dp.callback_query(lambda c: c.data == "menu_employees")
async def menu_employees(callback):
    await callback.message.edit_text("👤 Сотрудники:", reply_markup=employees_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "emp_list")
async def emp_list(callback):
    employees = db.list_employees()
    if not employees:
        await callback.message.edit_text("📭 Нет сотрудников.", reply_markup=back_button())
        await callback.answer()
        return
    lines = ["📋 Список сотрудников (можно копировать):", ""]
    sorted_emps = sorted(employees, key=lambda e: (position_info(e[4] if len(e) > 4 and e[4] else "specialist")[2], e[1]))
    for e in sorted_emps:
        name = e[1].strip()
        gtype = GRAPHIC_NAMES.get(e[2], e[2])
        start = e[3]
        pos_key = e[4] if len(e) > 4 and e[4] else "specialist"
        pos_name = position_info(pos_key)[0]
        lines.append(f"{name} — {gtype} — {pos_name} (с {start})")
    await callback.message.edit_text("\n".join(lines), reply_markup=back_button())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "emp_add")
async def emp_add(callback):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☀️ 2x2 день", callback_data="g_2x2_day")],
        [InlineKeyboardButton(text="🌙 сутки/3", callback_data="g_24x3")],
        [InlineKeyboardButton(text="🔄 2-1-2-3", callback_data="g_2-1-2-3")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_employees")],
    ])
    await callback.message.edit_text("👤 Шаг 1: Выберите график:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("g_"))
async def emp_add_graphic(callback):
    gtype = callback.data.replace("g_","")
    user_data[callback.from_user.id] = {'action':'add_emp','graphic_type':gtype,'step':'name'}
    await callback.message.edit_text("✏️ Шаг 2: Введите имя сотрудника:")
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id,{}).get('action')=='add_emp' and user_data[msg.from_user.id].get('step')=='name')
async def emp_add_name(message):
    uid = message.from_user.id
    user_data[uid]['name'] = message.text.strip()
    user_data[uid]['step'] = 'date'
    await message.answer("📅 Шаг 3: Введите дату начала (ДД.ММ.ГГГГ):")

@dp.message(lambda msg: user_data.get(msg.from_user.id,{}).get('action')=='add_emp' and user_data[msg.from_user.id].get('step')=='date')
async def emp_add_date(message):
    uid = message.from_user.id
    dt = None
    for f in ("%d.%m.%Y","%Y-%m-%d"):
        try:
            dt = datetime.strptime(message.text.strip(), f)
            break
        except:
            continue
    if not dt:
        await message.answer("❌ Неверный формат.")
        return
    user_data[uid]['start_date'] = dt.strftime("%Y-%m-%d")
    user_data[uid]['step'] = 'position'
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Главный механик", callback_data="pos_chief_mechanic")],
        [InlineKeyboardButton(text="💻 Инженер КИПиА", callback_data="pos_kipia_engineer")],
        [InlineKeyboardButton(text="⚡ Электромеханик", callback_data="pos_electrician")],
        [InlineKeyboardButton(text="🔧 Специалист", callback_data="pos_specialist")],
    ])
    await message.answer("🎖 Шаг 4: Выберите должность:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("pos_") and user_data.get(c.from_user.id,{}).get('action')=='add_emp')
async def emp_add_position(callback):
    pos = callback.data.replace("pos_","")
    uid = callback.from_user.id
    data = user_data[uid]
    ok = db.add_employee(data['name'], data['graphic_type'], data['start_date'], pos)
    if ok:
        pos_name = position_info(pos)[0]
        await callback.message.edit_text(f"✅ {data['name']} добавлен!\nДолжность: {pos_name}", reply_markup=employees_menu())
    else:
        await callback.message.edit_text(f"❌ {data['name']} уже существует.", reply_markup=employees_menu())
    del user_data[uid]
    await callback.answer()

@dp.callback_query(lambda c: c.data == "emp_bulk")
async def emp_bulk(callback):
    user_data[callback.from_user.id] = {'action':'bulk_add'}
    await callback.message.edit_text(
        "📋 Массовое добавление\n\n"
        "Формат:\n"
        "Имя — график — должность (с ГГГГ-ММ-ДД)\n\n"
        "Пример:\n"
        "Иван Иванов — 2-1-2-3 — Главный механик (с 2026-08-01)\n"
        "Пётр Петров — 2x2 день — Специалист (с 2026-08-05)\n\n"
        "Должности: Главный механик, Инженер КИПиА, Электромеханик, Специалист\n\n"
        "Также можно вставить список из «Список сотрудников» целиком."
    )
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id,{}).get('action')=='bulk_add')
async def emp_bulk_process(message):
    uid = message.from_user.id
    lines = message.text.strip().split("\n")
    added = []
    errors = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        if "список сотрудников" in line.lower() or "можно копировать" in line.lower():
            continue
        date_match = re.search(r'\(с\s+(\d{4}-\d{2}-\d{2})\)', line)
        if not date_match:
            errors.append(f"❌ Строка {i+1}: не найдена дата в формате (с ГГГГ-ММ-ДД)")
            continue
        date_str = date_match.group(1)
        before_date = line[:date_match.start()].strip()
        parts = re.split(r'\s+[—–]\s+', before_date)
        
        if len(parts) >= 3:
            name = parts[0].strip()
            gt_raw = parts[1].strip()
            pos_raw = parts[2].strip()
            pos = detect_position(pos_raw)
            if not pos:
                errors.append(f"❌ Строка {i+1}: неизвестная должность «{pos_raw}»")
                continue
        elif len(parts) == 2:
            name = parts[0].strip()
            gt_raw = parts[1].strip()
            pos = "specialist"
        else:
            errors.append(f"❌ Строка {i+1}: неверный формат")
            continue
        
        gtype = detect_graphic(gt_raw)
        if not gtype:
            errors.append(f"❌ Строка {i+1}: неизвестный график «{gt_raw}»")
            continue
        
        try:
            pd = datetime.strptime(date_str, "%Y-%m-%d")
        except:
            errors.append(f"❌ Строка {i+1}: неверная дата «{date_str}»")
            continue
        
        ok = db.add_employee(name, gtype, pd.strftime("%Y-%m-%d"), pos)
        if ok:
            added.append(f"✅ {name} ({position_info(pos)[0]})")
        else:
            errors.append(f"❌ {name} уже существует")
    
    result = []
    if added:
        result.append("✅ Добавлены:\n" + "\n".join(added))
    if errors:
        result.append("❌ Ошибки:\n" + "\n".join(errors))
    if not result:
        result.append("❌ Ничего не добавлено.")
    await message.answer("\n\n".join(result), reply_markup=employees_menu())
    del user_data[uid]

@dp.callback_query(lambda c: c.data == "emp_position")
async def emp_position_start(callback):
    employees = db.list_employees()
    if not employees:
        await callback.message.edit_text("📭 Нет сотрудников.", reply_markup=back_button())
        await callback.answer()
        return
    sorted_emps = sorted(employees, key=lambda e: (position_info(e[4] if len(e) > 4 and e[4] else "specialist")[2], e[1]))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{position_info(e[4] if len(e) > 4 and e[4] else 'specialist')[1]} {e[1]}", callback_data=f"setpos_{e[0]}")] for e in sorted_emps
    ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="menu_employees")]])
    await callback.message.edit_text("🎖 Выберите сотрудника:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("setpos_"))
async def emp_position_choose(callback):
    eid = int(callback.data.replace("setpos_",""))
    user_data[callback.from_user.id] = {'action':'set_position','eid':eid}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Главный механик", callback_data="newpos_chief_mechanic")],
        [InlineKeyboardButton(text="💻 Инженер КИПиА", callback_data="newpos_kipia_engineer")],
        [InlineKeyboardButton(text="⚡ Электромеханик", callback_data="newpos_electrician")],
        [InlineKeyboardButton(text="🔧 Специалист", callback_data="newpos_specialist")],
    ])
    await callback.message.edit_text("🎖 Выберите новую должность:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("newpos_"))
async def emp_position_apply(callback):
    pos = callback.data.replace("newpos_","")
    uid = callback.from_user.id
    data = user_data.get(uid, {})
    if 'eid' not in data:
        await callback.answer()
        return
    emp = db.get_employee(data['eid'])
    if emp:
        db.update_position(emp[1], pos)
        pos_name = position_info(pos)[0]
        await callback.message.edit_text(f"✅ Должность {emp[1]} → {pos_name}", reply_markup=employees_menu())
    else:
        await callback.message.edit_text("❌ Сотрудник не найден.", reply_markup=employees_menu())
    if uid in user_data:
        del user_data[uid]
    await callback.answer()

@dp.callback_query(lambda c: c.data == "emp_remove")
async def emp_remove(callback):
    employees = db.list_employees()
    if not employees:
        await callback.message.edit_text("📭 Нет сотрудников.", reply_markup=back_button())
        await callback.answer()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"❌ {e[1]}", callback_data=f"rememp_{e[0]}")] for e in employees
    ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="menu_employees")]])
    await callback.message.edit_text("🗑 Выберите:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("rememp_"))
async def rememp_process(callback):
    eid = int(callback.data.replace("rememp_",""))
    employees = db.list_employees()
    emp = next((e for e in employees if e[0]==eid), None)
    if emp:
        db.remove_employee(emp[1])
        await callback.message.edit_text(f"🗑 {emp[1]} удален.", reply_markup=employees_menu())
    await callback.answer()

# ==================== РВ ====================

def overrides_menu():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Добавить РВ", callback_data="ov_add")],
        [InlineKeyboardButton(text="❌ Удалить РВ", callback_data="ov_remove")],
        [InlineKeyboardButton(text="📥 Загрузить РВ из Excel", callback_data="ov_upload")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_main")],
    ])
    return kb

@dp.callback_query(lambda c: c.data == "menu_overrides")
async def menu_overrides(callback):
    await callback.message.edit_text("⭐ РВ:", reply_markup=overrides_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "ov_add")
async def ov_add(callback):
    employees = db.list_employees()
    if not employees:
        await callback.message.edit_text("📭 Нет сотрудников.", reply_markup=back_button())
        await callback.answer()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=e[1], callback_data=f"ovemp_{e[0]}")] for e in employees
    ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="menu_overrides")]])
    await callback.message.edit_text("⭐ Выберите:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("ovemp_"))
async def ov_add_emp(callback):
    eid = int(callback.data.replace("ovemp_",""))
    user_data[callback.from_user.id] = {'action':'add_ov','eid':eid,'step':'date'}
    await callback.message.edit_text("📅 Дата РВ (ДД.ММ.ГГГГ):")
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id,{}).get('action')=='add_ov' and user_data[msg.from_user.id].get('step')=='date')
async def ov_add_date(message):
    uid = message.from_user.id
    try:
        parsed = datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except:
        await message.answer("❌ Неверный формат.")
        return
    user_data[uid]['date'] = parsed.strftime("%Y-%m-%d")
    user_data[uid]['step'] = 'shift'
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☀️ Дневная", callback_data="ovs_day")],
        [InlineKeyboardButton(text="🌙 Ночная", callback_data="ovs_night")],
    ])
    await message.answer("⭐ Тип:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("ovs_"))
async def ov_add_shift(callback):
    shift = callback.data.replace("ovs_","")
    data = user_data.get(callback.from_user.id, {})
    ok = db.add_override(data.get('eid'), data.get('date'), shift)
    if ok:
        t = "☀️ дневную" if shift=="day" else "🌙 ночную"
        await callback.message.edit_text(f"✅ PB на {t} добавлено!", reply_markup=overrides_menu())
    else:
        await callback.message.edit_text("❌ Ошибка.", reply_markup=overrides_menu())
    if callback.from_user.id in user_data:
        del user_data[callback.from_user.id]
    await callback.answer()

@dp.callback_query(lambda c: c.data == "ov_remove")
async def ov_remove(callback):
    employees = db.list_employees()
    if not employees:
        await callback.message.edit_text("📭 Нет сотрудников.", reply_markup=back_button())
        await callback.answer()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=e[1], callback_data=f"rovemp_{e[0]}")] for e in employees
    ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="menu_overrides")]])
    await callback.message.edit_text("🗑 Выберите:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("rovemp_"))
async def ov_remove_emp(callback):
    eid = int(callback.data.replace("rovemp_",""))
    user_data[callback.from_user.id] = {'action':'remove_ov','eid':eid,'step':'date'}
    await callback.message.edit_text("📅 Дата (ДД.ММ.ГГГГ):")
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id,{}).get('action')=='remove_ov' and user_data[msg.from_user.id].get('step')=='date')
async def ov_remove_date(message):
    uid = message.from_user.id
    try:
        parsed = datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except:
        await message.answer("❌ Неверный формат.")
        return
    ds = parsed.strftime("%Y-%m-%d")
    overrides = db.list_overrides_for_date(ds)
    emp = db.get_employee(user_data[uid]['eid'])
    emp_ov = [o for o in overrides if o[1]==emp[1]] if emp else []
    if not emp_ov:
        await message.answer("❌ Нет РВ на эту дату.", reply_markup=overrides_menu())
        del user_data[uid]
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'☀️ День' if o[3]=='day' else '🌙 Ночь'}", callback_data=f"delovr_{o[0]}")] for o in emp_ov
    ])
    await message.answer("🗑 Какое РВ удалить?", reply_markup=kb)
    user_data[uid]['step'] = 'choose'

@dp.callback_query(lambda c: c.data.startswith("delovr_"))
async def ov_remove_del(callback):
    oid = int(callback.data.replace("delovr_",""))
    conn = db.get_connection()
    conn.execute("DELETE FROM overrides WHERE id=?", (oid,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("✅ PB удалено.", reply_markup=overrides_menu())
    await callback.answer()
    if callback.from_user.id in user_data:
        del user_data[callback.from_user.id]

# ==================== ЗАГРУЗКА РВ ИЗ EXCEL ====================

@dp.callback_query(lambda c: c.data == "ov_upload")
async def ov_upload_start(callback):
    user_data[callback.from_user.id] = {'action':'upload_rv'}
    await callback.message.edit_text(
        "📥 Загрузите Excel-файл (.xlsx) с таблицей РВ.\n\n"
        "Формат таблицы:\n"
        "• Первая строка — заголовки с датами (например: 01.ноя, 02.ноя, ...)\n"
        "• Первая колонка — фамилия и инициал (например: Антоновский М.)\n"
        "• Вторая колонка — 'день' или 'ночь'\n"
        "• В ячейках дат — символ 'х' или 'x' означает РВ\n\n"
        "Даты в прошлом будут проигнорированы.\n"
        "Сотрудники, которых нет в базе, будут пропущены с отчётом."
    )
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id,{}).get('action')=='upload_rv' and msg.document)
async def ov_upload_process(message: types.Message):
    uid = message.from_user.id
    doc = message.document
    
    if not doc.file_name.lower().endswith('.xlsx'):
        await message.answer("❌ Нужен файл с расширением .xlsx")
        return
    
    file_path = f"/tmp/{uid}_rv.xlsx"
    try:
        await bot.download(doc, destination=file_path)
    except Exception as e:
        await message.answer(f"❌ Не удалось скачать файл: {e}")
        return
    
    result_text = parse_excel_rv(file_path)
    
    try:
        os.remove(file_path)
    except:
        pass
    
    if uid in user_data:
        del user_data[uid]
    
    await message.answer(result_text, reply_markup=overrides_menu())

def parse_excel_rv(file_path):
    """Парсит Excel с РВ и добавляет в БД"""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return "❌ Библиотека openpyxl не установлена. Добавьте её в requirements.txt и перезапустите бота."
    
    try:
        wb = load_workbook(file_path, data_only=True)
        ws = wb.active
    except Exception as e:
        return f"❌ Не удалось открыть файл: {e}"
    
    # Читаем все строки в список списков
    all_rows = []
    for row in ws.iter_rows(values_only=True):
        all_rows.append(list(row))
    
    if not all_rows:
        return "❌ Файл пустой"
    
    # Ищем строку с датами — где в ячейках есть даты типа "01.ноя" или datetime
    date_row_idx = None
    date_columns = {}  # col_idx -> date object
    
    for row_idx, row in enumerate(all_rows[:5]):  # ищем в первых 5 строках
        found_dates = {}
        for col_idx, cell in enumerate(row):
            if cell is None:
                continue
            d = parse_excel_date_cell(cell)
            if d:
                found_dates[col_idx] = d
        if len(found_dates) >= 3:  # хотя бы 3 даты — это строка с датами
            date_row_idx = row_idx
            date_columns = found_dates
            break
    
    if not date_columns:
        return "❌ Не найдена строка с датами (формат '01.ноя')"
    
    # Получаем список сотрудников из БД
    employees = db.list_employees()
    
    # Парсим строки после date_row_idx
    now = date.today()
    added_count = 0
    skipped_past = 0
    not_found_names = set()
    already_exists = 0
    total_processed = 0
    
    current_employee = None
    current_shift = None
    
    for row_idx in range(date_row_idx + 1, len(all_rows)):
        row = all_rows[row_idx]
        if not row or all(c is None for c in row):
            continue
        
        # Колонка 0 — ФИО, колонка 1 — тип смены ("день"/"ночь")
        name_cell = row[0] if len(row) > 0 else None
        shift_cell = row[1] if len(row) > 1 else None
        
        if name_cell and str(name_cell).strip():
            current_employee = str(name_cell).strip()
        
        if shift_cell:
            shift_str = str(shift_cell).strip().lower()
            if shift_str.startswith("д"):
                current_shift = "day"
            elif shift_str.startswith("н"):
                current_shift = "night"
            else:
                current_shift = None
        else:
            current_shift = None
        
        if not current_employee or not current_shift:
            continue
        
        # Ищем сотрудника в БД
        emp_match = match_employee(current_employee, employees)
        if not emp_match:
            not_found_names.add(current_employee)
            continue
        
        emp_id = emp_match[0]
        
        # Проходим по колонкам с датами
        for col_idx, rv_date in date_columns.items():
            if col_idx >= len(row):
                continue
            cell_val = row[col_idx]
            if cell_val is None:
                continue
            cell_str = str(cell_val).strip().lower()
            if cell_str in ('х', 'x', 'X', 'Х'):
                total_processed += 1
                if rv_date < now:
                    skipped_past += 1
                    continue
                rv_date_str = rv_date.strftime("%Y-%m-%d")
                ok = db.add_override(emp_id, rv_date_str, current_shift)
                if ok:
                    added_count += 1
                else:
                    already_exists += 1
    
    # Формируем отчёт
    result = []
    result.append("📥 Результат загрузки РВ:")
    result.append("")
    result.append(f"✅ Добавлено РВ: {added_count}")
    if already_exists:
        result.append(f"ℹ️ Уже были в базе: {already_exists}")
    if skipped_past:
        result.append(f"⏭ Пропущено (прошлые даты): {skipped_past}")
    if not_found_names:
        result.append("")
        result.append("⚠️ Не найдены в базе:")
        for n in sorted(not_found_names):
            result.append(f"  • {n}")
    
    if total_processed == 0:
        result.append("")
        result.append("⚠️ Не найдено ни одной отметки РВ (х) в таблице")
    
    return "\n".join(result)

def parse_excel_date_cell(cell):
    """Пытается распарсить ячейку как дату: '01.ноя', '01.11.2026', datetime"""
    from datetime import datetime as dt, date as dt_date
    if cell is None:
        return None
    
    # Если это уже дата (openpyxl может вернуть datetime)
    if isinstance(cell, dt):
        return cell.date()
    if isinstance(cell, dt_date):
        return cell
    
    s = str(cell).strip().lower()
    if not s:
        return None
    
    # Формат "01.ноя"
    m = re.match(r'^(\d{1,2})\.([а-яa-z]{3,4})', s)
    if m:
        day_num = int(m.group(1))
        month_str = m.group(2)[:3]
        if month_str in MONTHS_SHORT:
            month_num = MONTHS_SHORT[month_str]
            # Год: берём текущий, если месяц >= текущего, иначе следующий
            now = date.today()
            year = now.year if month_num >= now.month else now.year + 1
            try:
                return date(year, month_num, day_num)
            except:
                return None
    
    # Формат "01.11" (без года)
    m = re.match(r'^(\d{1,2})\.(\d{1,2})$', s)
    if m:
        day_num = int(m.group(1))
        month_num = int(m.group(2))
        now = date.today()
        year = now.year if month_num >= now.month else now.year + 1
        try:
            return date(year, month_num, day_num)
        except:
            return None
    
    # Формат "01.11.2026"
    m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except:
            return None
    
    return None

def match_employee(excel_name, employees):
    """Сопоставляет 'Антоновский М.' с 'Максим Антоновский' по фамилии + первой букве имени"""
    # Нормализуем
    excel_parts = excel_name.replace(".", " ").split()
    excel_parts = [p for p in excel_parts if p]
    if not excel_parts:
        return None
    
    surname_excel = excel_parts[0].lower()
    initial_excel = excel_parts[1][0].lower() if len(excel_parts) > 1 else ""
    
    for emp in employees:
        # В БД: "Максим Антоновский" (имя фамилия) или "Иван Петров"
        db_parts = emp[1].split()
        if not db_parts:
            continue
        # Фамилия — последнее слово
        surname_db = db_parts[-1].lower()
        # Имя — первое слово
        first_name_db = db_parts[0].lower()
        
        if surname_db == surname_excel:
            # Проверяем инициал
            if not initial_excel or first_name_db.startswith(initial_excel):
                return emp
    
    return None

# ==================== РАСПИСАНИЕ ====================

def schedule_menu():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☀️ Сегодня", callback_data="sched_today")],
        [InlineKeyboardButton(text="🌤 Завтра", callback_data="sched_tomorrow")],
        [InlineKeyboardButton(text="📅 Неделя", callback_data="sched_week")],
        [InlineKeyboardButton(text="📆 Выбрать дату", callback_data="sched_custom")],
        [InlineKeyboardButton(text="📨 Отправить рассылку сейчас", callback_data="sched_send_now")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_main")],
    ])
    return kb

@dp.callback_query(lambda c: c.data == "menu_schedule")
async def menu_schedule(callback):
    await callback.message.edit_text("📅 Расписание:", reply_markup=schedule_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("sched_"))
async def sched_process(callback):
    try:
        employees = db.list_employees()
        today = date.today()
        if not employees:
            await callback.message.edit_text("📭 Нет сотрудников.", reply_markup=back_button())
            await callback.answer()
            return
        if callback.data == "sched_today":
            await show_schedule(callback.message, today, employees)
        elif callback.data == "sched_tomorrow":
            await show_schedule(callback.message, today + timedelta(days=1), employees)
        elif callback.data == "sched_week":
            await callback.message.edit_text(format_week_schedule(today, employees), reply_markup=back_button())
        elif callback.data == "sched_send_now":
            await send_morning_schedule()
            await callback.message.edit_text("✅ Рассылка отправлена всем получателям!", reply_markup=back_button())
        elif callback.data == "sched_custom":
            user_data[callback.from_user.id] = {'action':'sched_custom'}
            await callback.message.edit_text("📆 Введите дату (ДД.ММ.ГГГГ) или диапазон:")
        await callback.answer()
    except Exception as e:
        err = f"❌ Ошибка: {type(e).__name__}: {e}"
        logging.error(f"sched_process: {e}\n{traceback.format_exc()}")
        try:
            await callback.message.answer(err[:4000])
        except:
            pass
        try:
            await callback.answer("Ошибка, смотри сообщение", show_alert=True)
        except:
            pass

@dp.message(lambda msg: user_data.get(msg.from_user.id,{}).get('action')=='sched_custom')
async def sched_custom_process(message):
    text = message.text.strip()
    uid = message.from_user.id
    try:
        employees = db.list_employees()
        if "-" in text and text.count("-")==1:
            try:
                parts = text.split("-")
                start = datetime.strptime(parts[0].strip(),"%d.%m.%Y").date()
                end = datetime.strptime(parts[1].strip(),"%d.%m.%Y").date()
            except:
                await message.answer("❌ Неверный формат.", reply_markup=back_button())
                if uid in user_data: del user_data[uid]
                return
            days = []
            d = start
            while d <= end:
                days.append("📆 " + fmt_date_full(d) + "\n" + format_schedule(d, employees))
                d += timedelta(days=1)
            for i in range(0, len(days), 3):
                await message.answer("\n\n".join(days[i:i+3]))
            await message.answer("✅ Готово!", reply_markup=schedule_menu())
            if uid in user_data: del user_data[uid]
            return
        try:
            d = datetime.strptime(text.strip(), "%d.%m.%Y").date()
        except:
            await message.answer("❌ Неверный формат.", reply_markup=back_button())
            if uid in user_data: del user_data[uid]
            return
        await show_schedule(message, d, employees)
        if uid in user_data: del user_data[uid]
    except Exception as e:
        err = f"❌ Ошибка: {type(e).__name__}: {e}"
        logging.error(f"sched_custom: {e}\n{traceback.format_exc()}")
        await message.answer(err[:4000])
        if uid in user_data: del user_data[uid]

async def show_schedule(msg, for_date, employees):
    text = f"📅 Расписание на {fmt_date_acc(for_date)}\n\n{format_schedule(for_date, employees)}"
    await msg.answer(text, reply_markup=back_button())

def format_workers_list(names, date_str, shift, employees, overrides):
    result = []
    for w in names:
        emp = next((e for e in employees if e[1]==w), None)
        if not emp:
            continue
        pos_key = emp[4] if len(emp) > 4 and emp[4] else "specialist"
        pos_name, pos_emoji, pos_order = position_info(pos_key)
        rv = " ⭐РВ" if (emp[0], date_str, shift) in overrides else ""
        result.append((pos_order, w, f"  {pos_emoji} {w}{rv}"))
    result.sort()
    return [r[2] for r in result]

def format_schedule(for_date, employees):
    try:
        date_str = for_date.strftime("%Y-%m-%d")
        ov = db.list_overrides_for_date(date_str)
        overrides = set()
        for o in ov:
            emp = next((e for e in employees if e[1]==o[1]), None)
            if emp:
                overrides.add((emp[0], date_str, o[3]))
        day_workers = list(set(get_day_schedule(for_date, employees, overrides)))
        night_workers = list(set(get_night_schedule(for_date, employees, overrides)))
        lines = []
        lines.append("☀️ День (08:00-20:00):")
        if day_workers:
            lines.extend(format_workers_list(day_workers, date_str, "day", employees, overrides))
        else:
            lines.append("  ❌ Нет")
        lines.append("")
        lines.append("🌙 Ночь (20:00-08:00):")
        if night_workers:
            lines.extend(format_workers_list(night_workers, date_str, "night", employees, overrides))
        else:
            lines.append("  ❌ Нет")
        return "\n".join(lines)
    except Exception as e:
        logging.error(f"format_schedule: {e}\n{traceback.format_exc()}")
        return f"❌ Ошибка формирования расписания: {type(e).__name__}: {e}"

def format_week_schedule(start_date, employees):
    lines = []
    lines.append("📅 РАСПИСАНИЕ НА НЕДЕЛЮ")
    lines.append("С " + fmt_date(start_date))
    lines.append("")
    for i in range(7):
        d = start_date + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        ov = db.list_overrides_for_date(date_str)
        overrides = set()
        for o in ov:
            emp = next((e for e in employees if e[1]==o[1]), None)
            if emp:
                overrides.add((emp[0], date_str, o[3]))
        day_workers = list(set(get_day_schedule(d, employees, overrides)))
        night_workers = list(set(get_night_schedule(d, employees, overrides)))

        if i > 0:
            lines.append("———")
            lines.append("")

        lines.append("📆 " + fmt_date_full(d))
        lines.append("")
        lines.append("☀️ День:")
        if day_workers:
            lines.extend(format_workers_list(day_workers, date_str, "day", employees, overrides))
        else:
            lines.append("  ❌ Нет")
        lines.append("")
        lines.append("🌙 Ночь:")
        if night_workers:
            lines.extend(format_workers_list(night_workers, date_str, "night", employees, overrides))
        else:
            lines.append("  ❌ Нет")
        lines.append("")
    return "\n".join(lines)

# ==================== ПОЛУЧАТЕЛИ ====================

def recipients_menu():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="rec_add")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="rec_remove")],
        [InlineKeyboardButton(text="📋 Список", callback_data="rec_list")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_main")],
    ])
    return kb

@dp.callback_query(lambda c: c.data == "menu_recipients")
async def menu_recipients(callback):
    await callback.message.edit_text("📢 Получатели:", reply_markup=recipients_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "rec_add")
async def rec_add(callback):
    user_data[callback.from_user.id] = {'action':'add_recip','step':'id'}
    await callback.message.edit_text(
        "📢 Добавление получателя\n\n"
        "Отправьте одним из способов:\n"
        "• ID цифрами — например: 123456789\n"
        "• Username с @ — например: @ivanivanov\n"
        "• Или перешлите сообщение от пользователя"
    )
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id,{}).get('action')=='add_recip' and user_data[msg.from_user.id].get('step')=='id')
async def rec_add_process(message):
    uid = message.from_user.id
    uid_to_add = None
    name = ""
    if message.forward_from:
        uid_to_add = message.forward_from.id
        name = message.forward_from.full_name or f"User {uid_to_add}"
    elif message.text and message.text.strip().isdigit():
        uid_to_add = int(message.text.strip())
        name = f"User {uid_to_add}"
    elif message.text and message.text.strip().startswith("@"):
        username = message.text.strip()[1:]
        try:
            chat = await bot.get_chat(f"@{username}")
            uid_to_add = chat.id
            name = chat.full_name or username
        except:
            await message.answer(
                f"❌ Не удалось найти пользователя @{username}.\n\n"
                f"Попросите его сначала написать боту любое сообщение, а потом попробуйте снова.",
                reply_markup=recipients_menu()
            )
            del user_data[uid]
            return
    else:
        await message.answer("❌ Не удалось определить получателя.", reply_markup=recipients_menu())
        del user_data[uid]
        return
    ok = db.add_recipient(uid_to_add, name)
    if ok:
        await message.answer(f"✅ Получатель добавлен! {name} (ID: {uid_to_add})", reply_markup=recipients_menu())
        try:
            await bot.send_message(
                config.YOUR_TELEGRAM_ID,
                f"➕ Новый получатель рассылки\n👤 {name}\n🆔 {uid_to_add}"
            )
        except:
            pass
        try:
            welcome_text = (
                "👋 Привет!\n\n"
                "Я бот службы эксплуатации ФФ Порошкино. 🤖\n\n"
                "📅 Я буду отправлять тебе расписание смен твоих коллег "
                "каждое утро в 07:00 и вечером в 19:00.\n\n"
                "Спасибо что с нами! 😊"
            )
            await bot.send_message(uid_to_add, welcome_text, reply_markup=recipient_kb())
        except:
            pass
    else:
        await message.answer("❌ Ошибка.", reply_markup=recipients_menu())
    del user_data[uid]

@dp.callback_query(lambda c: c.data == "rec_list")
async def rec_list(callback):
    recipients = db.list_recipients()
    if not recipients:
        await callback.message.edit_text("📭 Нет получателей.", reply_markup=back_button())
        await callback.answer()
        return
    lines = ["📢 Получатели:"] + [f"👤 {r[1]} (ID:{r[0]})" for r in recipients]
    await callback.message.edit_text("\n".join(lines), reply_markup=back_button())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "rec_remove")
async def rec_remove(callback):
    recipients = db.list_recipients()
    if not recipients:
        await callback.message.edit_text("📭 Нет получателей.", reply_markup=back_button())
        await callback.answer()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"❌ {r[1] or str(r[0])}", callback_data=f"remrec_{r[0]}")] for r in recipients
    ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="menu_recipients")]])
    await callback.message.edit_text("🗑 Выберите:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("remrec_"))
async def rec_remove_process(callback):
    uid = int(callback.data.replace("remrec_",""))
    recipients = db.list_recipients()
    recip = next((r for r in recipients if r[0] == uid), None)
    name = recip[1] if recip else "Пользователь"
    db.remove_recipient(uid)
    try:
        goodbye_text = (
            "🚫 Вы отключены от получения ежедневной рассылки расписания.\n\n"
            "Если захотите снова получать расписание — свяжитесь с администратором. 😊"
        )
        await bot.send_message(uid, goodbye_text)
    except:
        pass
    try:
        await bot.send_message(
            config.YOUR_TELEGRAM_ID,
            f"➖ Получатель удален из рассылки\n👤 {name}\n🆔 {uid}"
        )
    except:
        pass
    await callback.message.edit_text(f"🗑 {name} удален из получателей.", reply_markup=recipients_menu())
    await callback.answer()

# ==================== РАССЫЛКИ ====================

async def send_morning_schedule():
    today = date.today()
    employees = db.list_employees()
    if not employees:
        return

    def get_overrides(for_date):
        ds = for_date.strftime("%Y-%m-%d")
        ov = db.list_overrides_for_date(ds)
        s = set()
        for o in ov:
            emp = next((e for e in employees if e[1]==o[1]), None)
            if emp:
                s.add((emp[0], ds, o[3]))
        return s, ds

    ds_today = today.strftime("%Y-%m-%d")
    ov_today, _ = get_overrides(today)
    day_w = list(set(get_day_schedule(today, employees, ov_today)))
    night_w = list(set(get_night_schedule(today, employees, ov_today)))

    text = f"🌅 Доброе утро!\n📅 {fmt_date_full(today)}\n\n"
    text += "☀️ Дневная смена (08:00-20:00):\n"
    if day_w:
        text += "\n".join(format_workers_list(day_w, ds_today, "day", employees, ov_today)) + "\n"
    else:
        text += "  ❌ Нет\n"
    text += "\n🌙 Ночная смена (20:00-08:00):\n"
    if night_w:
        text += "\n".join(format_workers_list(night_w, ds_today, "night", employees, ov_today)) + "\n"
    else:
        text += "  ❌ Нет\n"

    for r in db.list_recipients():
        try:
            await bot.send_message(r[0], text, reply_markup=recipient_kb())
        except:
            pass

async def send_evening_schedule():
    today = date.today()
    tomorrow = today + timedelta(days=1)
    employees = db.list_employees()
    if not employees:
        return

    def get_overrides(for_date):
        ds = for_date.strftime("%Y-%m-%d")
        ov = db.list_overrides_for_date(ds)
        s = set()
        for o in ov:
            emp = next((e for e in employees if e[1]==o[1]), None)
            if emp:
                s.add((emp[0], ds, o[3]))
        return s, ds

    ov_today, ds_today = get_overrides(today)
    ov_tomorrow, ds_tomorrow = get_overrides(tomorrow)

    night_w = list(set(get_night_schedule(today, employees, ov_today)))
    day_w = list(set(get_day_schedule(tomorrow, employees, ov_tomorrow)))

    text = f"🌆 Добрый вечер!\n📅 {fmt_date_full(today)}\n\n"
    text += "🌙 Ночная смена сегодня (20:00-08:00):\n"
    if night_w:
        text += "\n".join(format_workers_list(night_w, ds_today, "night", employees, ov_today)) + "\n"
    else:
        text += "  ❌ Нет\n"
    text += f"\n☀️ Дневная смена завтра ({fmt_date_full(tomorrow)}, 08:00-20:00):\n"
    if day_w:
        text += "\n".join(format_workers_list(day_w, ds_tomorrow, "day", employees, ov_tomorrow)) + "\n"
    else:
        text += "  ❌ Нет\n"

    for r in db.list_recipients():
        try:
            await bot.send_message(r[0], text, reply_markup=recipient_kb())
        except:
            pass

async def on_startup():
    scheduler.add_job(send_morning_schedule, "cron", hour=7, minute=0, timezone="Etc/GMT-3")
    scheduler.add_job(send_evening_schedule, "cron", hour=19, minute=0, timezone="Etc/GMT-3")
    scheduler.start()

async def main():
    dp.startup.register(on_startup)
    print("Bot starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
