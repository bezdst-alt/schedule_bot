from datetime import datetime, timedelta

def get_cycle_dates(graphic_type, start_date, from_date, to_date):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    
    if graphic_type == "2x2_day":
        return _calc_2x2_day(start, from_date, to_date)
    elif graphic_type == "24x3":
        return _calc_24x3(start, from_date, to_date)
    elif graphic_type == "2-1-2-3":
        return _calc_2_1_2_3(start, from_date, to_date)
    return {}

def _calc_2x2_day(start, from_date, to_date):
    result = {}
    d = from_date
    while d <= to_date:
        delta = (d - start).days
        cycle_pos = delta % 4
        if cycle_pos in (0, 1):
            result[d.strftime("%Y-%m-%d")] = "day"
        else:
            result[d.strftime("%Y-%m-%d")] = "off"
        d += timedelta(days=1)
    return result

def _calc_24x3(start, from_date, to_date):
    result = {}
    d = from_date
    while d <= to_date:
        delta = (d - start).days
        cycle_pos = delta % 4
        if cycle_pos == 0:
            result[d.strftime("%Y-%m-%d")] = "day"
            result[d.strftime("%Y-%m-%d") + "_night"] = "night"
        else:
            result[d.strftime("%Y-%m-%d")] = "off"
        d += timedelta(days=1)
    return result

def _calc_2_1_2_3(start, from_date, to_date):
    result = {}
    d = from_date
    while d <= to_date:
        delta = (d - start).days
        cycle_pos = delta % 7
        if cycle_pos in (0, 1):
            result[d.strftime("%Y-%m-%d")] = "day"
        elif cycle_pos in (2, 3):
            result[d.strftime("%Y-%m-%d")] = "night"
        else:
            result[d.strftime("%Y-%m-%d")] = "off"
        d += timedelta(days=1)
    return result

def get_day_schedule(for_date, employees, overrides):
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
