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

async def admin_only(message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return False
    return True

user_data = {}

def detect_graphic(text):
    """Определяет тип графика по любому тексту"""
    t = text.lower().strip()
    # 2-1-2-3
    if "2-1-2-3" in t or "2123" in t:
        return "2-1-2-3"
    # сутки
    if "сутк" in t:
        return "24x3"
    # 2x2 день, 2×2 день, 2х2 день — любой вариант
    # Убираем символ × и х, заменяем на x
    t_clean = t.replace("×", "x").replace("х", "x").replace(" ", "")
    if "2x2" in t_clean:
        return "2x2_day"
    return None

GRAPHIC_NAMES = {
    "2x2_day": "2x2 день",
    "24x3": "сутки/3",
    "2-1-2-3": "2-1-2-3",
}

GRAPHIC_EMOJIS = {
    "2x2_day": "☀️",
    "24x3": "🌙",
    "2-1-2-3": "🔄",
}

WEEKDAYS_RU = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
MONTHS_RU = {1:"января",2:"февраля",3:"марта",4:"апреля",5:"мая",6:"июня",7:"июля",8:"августа",9:"сентября",10:"октября",11:"ноября",12:"декабря"}

def fmt_date(d):
    return f"{d.day:02d} {MONTHS_RU[d.month]}"

def fmt_date_full(d):
    return f"{WEEKDAYS_RU[d.weekday()]}, {fmt_date(d)}"

# ==================== ГЛАВНОЕ МЕНЮ ====================

def main_menu():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Сотрудники", callback_data="menu_employees")],
        [InlineKeyboardButton(text="⭐ PB (Работа в выходной)", callback_data="menu_overrides")],
        [InlineKeyboardButton(text="📅 Расписание", callback_data="menu_schedule")],
        [InlineKeyboardButton(text="📢 Получатели рассылки", callback_data="menu_recipients")],
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

@dp.callback_query(lambda c: c.data == "menu_main")
async def back_to_main(callback):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())
    await callback.answer()

# ==================== СОТРУДНИКИ ====================

def employees_menu():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить одного", callback_data="emp_add")],
        [InlineKeyboardButton(text="👥 Добавить несколько", callback_data="emp_bulk")],
        [InlineKeyboardButton(text="📋 Список сотрудников", callback_data="emp_list")],
        [InlineKeyboardButton(text="🗑 Удалить сотрудника", callback_data="emp_remove")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_main")],
    ])
    return kb

@dp.callback_query(lambda c: c.data == "menu_employees")
async def menu_employees(callback):
    await callback.message.edit_text("👤 Управление сотрудниками:", reply_markup=employees_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "emp_list")
async def emp_list(callback):
    employees = db.list_employees()
    if not employees:
        await callback.message.edit_text("📭 Нет сотрудников.", reply_markup=back_button())
        await callback.answer()
        return
    lines = ["📋 Список сотрудников:"]
    for e in employees:
        emoji = GRAPHIC_EMOJIS.get(e[2], "👤")
        lines.append(f"{emoji} {e[1]} - {GRAPHIC_NAMES.get(e[2],e[2])} (c {e[3]})")
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
    await callback.message.edit_text("👤 Выберите график:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("g_"))
async def emp_add_graphic(callback):
    gtype = callback.data.replace("g_","")
    user_data[callback.from_user.id] = {'action':'add_emp','graphic_type':gtype,'step':'name'}
    await callback.message.edit_text("✏️ Введите имя сотрудника:")
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id,{}).get('action')=='add_emp' and user_data[msg.from_user.id].get('step')=='name')
async def emp_add_name(message):
    uid = message.from_user.id
    user_data[uid]['name'] = message.text.strip()
    user_data[uid]['step'] = 'date'
    await message.answer("📅 Введите дату начала (ДД.ММ.ГГГГ):")

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
        await message.answer("❌ Неверный формат.", reply_markup=back_button())
        return
    data = user_data[uid]
    ok = db.add_employee(data['name'], data['graphic_type'], dt.strftime("%Y-%m-%d"))
    if ok:
        await message.answer(f"✅ Сотрудник {data['name']} добавлен!", reply_markup=employees_menu())
    else:
        await message.answer(f"❌ Сотрудник {data['name']} уже существует.", reply_markup=employees_menu())
    del user_data[uid]

@dp.callback_query(lambda c: c.data == "emp_bulk")
async def emp_bulk(callback):
    user_data[callback.from_user.id] = {'action':'bulk_add'}
    await callback.message.edit_text(
        "📋 **Массовое добавление**\n\n"
        "Отправьте список в формате:\n"
        "```\n"
        "Имя - график (с ГГГГ-ММ-ДД)\n"
        "```\n\n"
        "Примеры:\n"
        "Ярослав Соколов - 2x2 день (с 2026-08-07)\n"
        "Иван Иванов - 2-1-2-3 (с 2026-08-01)\n"
        "Петр Петров - сутки/3 (с 2026-08-05)"
    )
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id,{}).get('action')=='bulk_add')
async def emp_bulk_process(message):
    uid = message.from_user.id
    lines = message.text.strip().split("\n")
    added = []
    errors = []
    pattern = r'^(.*?)\s*[—-]\s*(.*?)\s*\(с\s*(\d{4}-\d{2}-\d{2})\)\s*$'
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        m = re.match(pattern, line)
        if not m:
            errors.append(f"❌ Строка {i+1}: неверный формат")
            continue
        name = m.group(1).strip()
        gt_raw = m.group(2).strip()
        ds = m.group(3).strip()
        
        gtype = detect_graphic(gt_raw)
        if not gtype:
            errors.append(f"❌ Строка {i+1}: неизвестный график «{gt_raw}»")
            continue
        
        try:
            pd = datetime.strptime(ds, "%Y-%m-%d")
        except:
            errors.append(f"❌ Строка {i+1}: неверная дата")
            continue
        ok = db.add_employee(name, gtype, pd.strftime("%Y-%m-%d"))
        if ok:
            added.append(f"✅ {name}")
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
    await callback.message.edit_text("🗑 Выберите сотрудника для удаления:", reply_markup=kb)
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
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_main")],
    ])
    return kb

@dp.callback_query(lambda c: c.data == "menu_overrides")
async def menu_overrides(callback):
    await callback.message.edit_text("⭐ Управление РВ:", reply_markup=overrides_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "ov_add")
async def ov_add(callback):
    employees = db.list_employees()
    if not employees:
        await callback.message.edit_text("📭 Сначала добавьте сотрудников.", reply_markup=back_button())
        await callback.answer()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=e[1], callback_data=f"ovemp_{e[0]}")] for e in employees
    ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="menu_overrides")]])
    await callback.message.edit_text("⭐ Выберите сотрудника для РВ:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("ovemp_"))
async def ov_add_emp(callback):
    eid = int(callback.data.replace("ovemp_",""))
    user_data[callback.from_user.id] = {'action':'add_ov','eid':eid,'step':'date'}
    await callback.message.edit_text("📅 Введите дату РВ (ДД.ММ.ГГГГ):")
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id,{}).get('action')=='add_ov' and user_data[msg.from_user.id].get('step')=='date')
async def ov_add_date(message):
    uid = message.from_user.id
    try:
        parsed = datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except:
        await message.answer("❌ Неверный формат.", reply_markup=back_button())
        return
    user_data[uid]['date'] = parsed.strftime("%Y-%m-%d")
    user_data[uid]['step'] = 'shift'
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☀️ Дневная", callback_data="ovs_day")],
        [InlineKeyboardButton(text="🌙 Ночная", callback_data="ovs_night")],
    ])
    await message.answer("⭐ Тип смены:", reply_markup=kb)

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
    await callback.message.edit_text("🗑 Выберите сотрудника:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("rovemp_"))
async def ov_remove_emp(callback):
    eid = int(callback.data.replace("rovemp_",""))
    user_data[callback.from_user.id] = {'action':'remove_ov','eid':eid,'step':'date'}
    await callback.message.edit_text("📅 Введите дату (ДД.ММ.ГГГГ):")
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id,{}).get('action')=='remove_ov' and user_data[msg.from_user.id].get('step')=='date')
async def ov_remove_date(message):
    uid = message.from_user.id
    try:
        parsed = datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except:
        await message.answer("❌ Неверный формат.", reply_markup=back_button())
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

# ==================== РАСПИСАНИЕ ====================

def schedule_menu():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☀️ Сегодня", callback_data="sched_today")],
        [InlineKeyboardButton(text="🌤 Завтра", callback_data="sched_tomorrow")],
        [InlineKeyboardButton(text="📅 Неделя", callback_data="sched_week")],
        [InlineKeyboardButton(text="📆 Выбрать дату", callback_data="sched_custom")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_main")],
    ])
    return kb

@dp.callback_query(lambda c: c.data == "menu_schedule")
async def menu_schedule(callback):
    await callback.message.edit_text("📅 Расписание:", reply_markup=schedule_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("sched_"))
async def sched_process(callback):
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
    elif callback.data == "sched_custom":
        user_data[callback.from_user.id] = {'action':'sched_custom'}
        await callback.message.edit_text("📆 Введите дату (ДД.ММ.ГГГГ) или диапазон (ДД.ММ.ГГГГ-ДД.ММ.ГГГГ):")
    await callback.answer()

@dp.message(lambda msg: user_data.get(msg.from_user.id,{}).get('action')=='sched_custom')
async def sched_custom_process(message):
    text = message.text.strip()
    uid = message.from_user.id
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
            days.append(fmt_date_full(d) + "\n" + format_schedule(d, employees))
            d += timedelta(days=1)
        for i in range(0, len(days), 3):
            await message.answer("\n\n".join(days[i:i+3]))
        await message.answer("✅ Расписание готово!", reply_markup=schedule_menu())
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

async def show_schedule(msg, for_date, employees):
    text = f"📅 Расписание на {fmt_date_full(for_date)}\n\n{format_schedule(for_date, employees)}"
    await msg.answer(text, reply_markup=back_button())

def format_schedule(for_date, employees):
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
        for w in sorted(day_workers):
            emp = next((e for e in employees if e[1]==w), None)
            s = " ⭐РВ" if emp and (emp[0],date_str,"day") in overrides else ""
            lines.append(f"  👤 {w}{s}")
    else:
        lines.append("  ❌ Нет")
    lines.append("🌙 Ночь (20:00-08:00):")
    if night_workers:
        for w in sorted(night_workers):
            emp = next((e for e in employees if e[1]==w), None)
            s = " ⭐РВ" if emp and (emp[0],date_str,"night") in overrides else ""
            lines.append(f"  👤 {w}{s}")
    else:
        lines.append("  ❌ Нет")
    return "\n".join(lines)

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
        
        lines.append("━" * 30)
        lines.append(fmt_date_full(d))
        lines.append("")
        lines.append("☀️ День:")
        if day_workers:
            for w in sorted(day_workers):
                emp = next((e for e in employees if e[1]==w), None)
                s = " ⭐РВ" if emp and (emp[0],date_str,"day") in overrides else ""
                lines.append(f"  👤 {w}{s}")
        else:
            lines.append("  ❌ Нет")
        lines.append("🌙 Ночь:")
        if night_workers:
            for w in sorted(night_workers):
                emp = next((e for e in employees if e[1]==w), None)
                s = " ⭐РВ" if emp and (emp[0],date_str,"night") in overrides else ""
                lines.append(f"  👤 {w}{s}")
        else:
            lines.append("  ❌ Нет")
        lines.append("")
    
    return "\n".join(lines)

# ==================== ПОЛУЧАТЕЛИ ====================

def recipients_menu():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить получателя", callback_data="rec_add")],
        [InlineKeyboardButton(text="🗑 Удалить получателя", callback_data="rec_remove")],
        [InlineKeyboardButton(text="📋 Список получателей", callback_data="rec_list")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_main")],
    ])
    return kb

@dp.callback_query(lambda c: c.data == "menu_recipients")
async def menu_recipients(callback):
    await callback.message.edit_text("📢 Получатели рассылки:", reply_markup=recipients_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "rec_add")
async def rec_add(callback):
    user_data[callback.from_user.id] = {'action':'add_recip','step':'id'}
    await callback.message.edit_text("📢 Отправьте Telegram ID или перешлите сообщение пользователя:")
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
    else:
        await message.answer("❌ Не удалось определить ID.", reply_markup=recipients_menu())
        del user_data[uid]
        return
    ok = db.add_recipient(uid_to_add, name)
    if ok:
        await message.answer(f"✅ Получатель добавлен! ID: {uid_to_add}", reply_markup=recipients_menu())
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
    await callback.message.edit_text("🗑 Выберите получателя:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("remrec_"))
async def rec_remove_process(callback):
    uid = int(callback.data.replace("remrec_",""))
    db.remove_recipient(uid)
    await callback.message.edit_text("🗑 Получатель удален.", reply_markup=recipients_menu())
    await callback.answer()

# ==================== РАССЫЛКИ ====================

async def send_morning_schedule():
    today = date.today()
    employees = db.list_employees()
    if not employees:
        return
    ds = today.strftime("%Y-%m-%d")
    ov = db.list_overrides_for_date(ds)
    overrides = set()
    for o in ov:
        emp = next((e for e in employees if e[1]==o[1]), None)
        if emp:
            overrides.add((emp[0], ds, o[3]))
    day_w = list(set(get_day_schedule(today, employees, overrides)))
    night_w = list(set(get_night_schedule(today, employees, overrides)))
    text = f"Доброе утро! Расписание на {fmt_date_full(today)}\n\n☀️ День (08-20):\n"
    if day_w:
        for w in sorted(day_w):
            text += f"  👤 {w}\n"
    else:
        text += "  ❌ Нет\n"
    text += "\n🌙 Ночь (20-08):\n"
    if night_w:
        for w in sorted(night_w):
            text += f"  👤 {w}\n"
    else:
        text += "  ❌ Нет\n"
    for r in db.list_recipients():
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
    ds = today.strftime("%Y-%m-%d")
    ov = db.list_overrides_for_date(ds)
    overrides = set()
    for o in ov:
        emp = next((e for e in employees if e[1]==o[1]), None)
        if emp:
            overrides.add((emp[0], ds, o[3]))
    night_w = list(set(get_night_schedule(today, employees, overrides)))
    tms = tomorrow.strftime("%Y-%m-%d")
    ov2 = db.list_overrides_for_date(tms)
    overrides2 = set()
    for o in ov2:
        emp = next((e for e in employees if e[1]==o[1]), None)
        if emp:
            overrides2.add((emp[0], tms, o[3]))
    day_w = list(set(get_day_schedule(tomorrow, employees, overrides2)))
    text = f"Добрый вечер!\n\n🌙 Сегодня ночью (20-08):\n"
    if night_w:
        for w in sorted(night_w):
            text += f"  👤 {w}\n"
    else:
        text += "  ❌ Нет\n"
    text += f"\n☀️ Завтра днем ({fmt_date_full(tomorrow)}):\n"
    if day_w:
        for w in sorted(day_w):
            text += f"  👤 {w}\n"
    else:
        text += "  ❌ Нет\n"
    for r in db.list_recipients():
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
