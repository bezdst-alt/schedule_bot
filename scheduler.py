from datetime import datetime, timedelta

def get_cycle_dates(graphic_type, start_date, from_date, to_date):
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    
    result = {}
    d = from_date
    while d <= to_date:
        delta_days = (d - start).days
        
        if graphic_type == "2x2_day":
            # Два через два: день/день/off/off (цикл 4 дня)
            pos = delta_days % 4
            if pos in (0, 1):
                result[d.strftime("%Y-%m-%d")] = "day"
            else:
                result[d.strftime("%Y-%m-%d")] = "off"
                
        elif graphic_type == "24x3":
            # Сутки через трое: в первый день смена 08-08 (день+ночь)
            pos = delta_days % 4
            if pos == 0:
                result[d.strftime("%Y-%m-%d")] = "day"
                result[d.strftime("%Y-%m-%d") + "_night"] = "night"
            else:
                result[d.strftime("%Y-%m-%d")] = "off"
                
        elif graphic_type == "2-1-2-3":
            # 2 дня день, 1 выходной, 2 дня ночь, 3 выходных
            # Цикл: день/день/off/ночь/ночь/off/off/off = 8 дней
            pos = delta_days % 8
            if pos in (0, 1):        # Дни 1-2: дневные смены
                result[d.strftime("%Y-%m-%d")] = "day"
            elif pos == 2:           # День 3: выходной
                result[d.strftime("%Y-%m-%d")] = "off"
            elif pos in (3, 4):      # Дни 4-5: ночные смены
                result[d.strftime("%Y-%m-%d")] = "night"
            else:                    # Дни 6-8: выходные
                result[d.strftime("%Y-%m-%d")] = "off"
        
        d += timedelta(days=1)
    
    return result

def get_day_schedule(for_date, employees, overrides):
    """Кто работает в дневную смену (08-20)"""
    date_str = for_date.strftime("%Y-%m-%d")
    result = []
    for emp in employees:
        emp_id, name, gtype, start_date = emp
        if (emp_id, date_str, "day") in overrides:
            result.append(name)
            continue
        schedule = get_cycle_dates(gtype, start_date, for_date, for_date)
        if schedule.get(date_str) == "day":
            result.append(name)
    return result

def get_night_schedule(for_date, employees, overrides):
    """Кто работает в ночную смену (20-08)"""
    date_str = for_date.strftime("%Y-%m-%d")
    result = []
    for emp in employees:
        emp_id, name, gtype, start_date = emp
        if (emp_id, date_str, "night") in overrides:
            result.append(name)
            continue
        schedule = get_cycle_dates(gtype, start_date, for_date, for_date)
        if schedule.get(date_str) == "night" or schedule.get(date_str + "_night") == "night":
            result.append(name)
    return result
