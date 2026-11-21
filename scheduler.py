from datetime import datetime, timedelta

def get_cycle_dates(graphic_type, start_date, from_date, to_date):
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    result = {}
    d = from_date
    while d <= to_date:
        delta_days = (d - start).days
        if graphic_type == "2x2_day":
            pos = delta_days % 4
            if pos in (0, 1):
                result[d.strftime("%Y-%m-%d")] = "day"
            else:
                result[d.strftime("%Y-%m-%d")] = "off"
        elif graphic_type == "24x3":
            pos = delta_days % 4
            if pos == 0:
                result[d.strftime("%Y-%m-%d")] = "day"
                result[d.strftime("%Y-%m-%d") + "_night"] = "night"
            else:
                result[d.strftime("%Y-%m-%d")] = "off"
        elif graphic_type == "2-1-2-3":
            pos = delta_days % 8
            if pos in (0, 1):
                result[d.strftime("%Y-%m-%d")] = "day"
            elif pos == 2:
                result[d.strftime("%Y-%m-%d")] = "off"
            elif pos in (3, 4):
                result[d.strftime("%Y-%m-%d")] = "night"
            else:
                result[d.strftime("%Y-%m-%d")] = "off"
        d += timedelta(days=1)
    return result

def get_day_schedule(for_date, employees, overrides):
    date_str = for_date.strftime("%Y-%m-%d")
    result = []
    for emp in employees:
        emp_id, name, gtype, start_date = emp[0], emp[1], emp[2], emp[3]
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
        emp_id, name, gtype, start_date = emp[0], emp[1], emp[2], emp[3]
        if (emp_id, date_str, "night") in overrides:
            result.append(name)
            continue
        schedule = get_cycle_dates(gtype, start_date, for_date, for_date)
        if schedule.get(date_str) == "night" or schedule.get(date_str + "_night") == "night":
            result.append(name)
    return result
